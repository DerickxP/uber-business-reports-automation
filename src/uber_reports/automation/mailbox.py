"""Localização e download do relatório no webmail (Outlook Web ou Gmail).

O Uber for Business não entrega o arquivo na hora: ele envia um e-mail com um link de
download quando a exportação fica pronta. Este módulo pesquisa a caixa de entrada,
abre a mensagem certa (uma por organização) e intercepta o download.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from urllib.parse import quote

from uber_reports.automation.text import normalize_text, slugify
from uber_reports.config import Company, MailSettings

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover

    class PlaywrightTimeoutError(Exception):  # type: ignore[no-redef]
        """Substituto usado quando o Playwright não está instalado."""


log = logging.getLogger(__name__)

MESSAGE_LIST_SELECTOR = "div[role='option'], tr, [role='row'], article, li"
DOWNLOAD_SELECTORS = (
    "a:has-text('Baixar arquivo')",
    "a:has-text('Baixar')",
    "a:has-text('Download')",
    "a[href*='email.mgt.uber.com/c/']",
)
MAX_MESSAGES_TO_CHECK = 10


class Mailbox:
    def __init__(self, page, settings: MailSettings) -> None:
        self.page = page
        self.settings = settings

    def open(self) -> None:
        self.page.goto(self.settings.url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(4000)

    def search_query(self) -> str:
        subject = self.settings.subject
        if self.settings.provider == "gmail":
            return f'subject:"{subject}" newer_than:1d'
        return f'"{subject}" received:today'

    def search(self, query: str) -> None:
        if self.settings.provider == "gmail":
            url = f"https://mail.google.com/mail/u/0/#search/{quote(query)}"
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(4000)
            return

        # Outlook Web: o atalho Alt+Q leva o foco à busca sem depender de seletores
        # que mudam a cada versão da interface.
        self.open()
        self.page.keyboard.press("Alt+q")
        self.page.wait_for_timeout(1000)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.page.keyboard.type(query, delay=30)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(4000)

    def open_matching_message(self, keywords: Iterable[str]) -> bool:
        """Abre, entre os resultados, a mensagem cujo corpo cita todas as palavras-chave."""
        wanted = [normalize_text(word) for word in keywords]
        self.page.wait_for_timeout(3000)
        candidates = self.page.locator(MESSAGE_LIST_SELECTOR)
        total = min(candidates.count(), MAX_MESSAGES_TO_CHECK)
        for index in range(total):
            item = candidates.nth(index)
            try:
                item.click(timeout=5000)
                self.page.wait_for_timeout(4000)
                text = normalize_text(self.page.locator("body").inner_text(timeout=2000))
            except PlaywrightTimeoutError:
                continue
            if all(word in text for word in wanted):
                return True
            log.debug("Mensagem %d não corresponde; tentando a próxima.", index + 1)
        return False

    def _find_download_link(self):
        # O Outlook costuma isolar o corpo do e-mail em um iframe; por isso a busca
        # percorre todos os frames, não só a página principal.
        for frame in self.page.frames:
            for selector in DOWNLOAD_SELECTORS:
                try:
                    candidate = frame.locator(selector).first
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue
        return None

    def download_report(self, company: Company, downloads_dir: Path) -> Path:
        self.page.wait_for_timeout(4000)
        link = self._find_download_link()
        if link is None:
            raise RuntimeError(f"Link de download não encontrado no e-mail de '{company.name}'.")

        link.scroll_into_view_if_needed(timeout=2000)
        # O link abre em nova aba (target=_blank). Sem o atributo, o download acontece na
        # mesma página e o Playwright consegue interceptá-lo com expect_download.
        link.evaluate("element => element.removeAttribute('target')")
        with self.page.expect_download(timeout=30000) as download_info:
            link.click(timeout=5000, force=True)
        download = download_info.value

        suffix = Path(download.suggested_filename).suffix or ".xlsx"
        target = (
            downloads_dir / f"uber_report_{slugify(company.name)}_{date.today():%Y-%m-%d}{suffix}"
        )
        download.save_as(str(target))
        log.info("Download concluído: %s", target)
        return target


def wait_and_download(
    context, companies: Iterable[Company], settings: MailSettings, downloads_dir: Path
) -> list[Path]:
    """Aguarda o e-mail de cada organização e baixa o arquivo, dentro do tempo limite."""
    page = context.new_page()
    mailbox = Mailbox(page, settings)
    mailbox.open()

    pending = list(companies)
    downloaded: list[Path] = []
    started = time.time()
    query = mailbox.search_query()
    try:
        while pending and (time.time() - started) < settings.wait_max_seconds:
            company = pending[0]
            log.info("Procurando o e-mail de %s", company.name)
            mailbox.search(query)
            if mailbox.open_matching_message(company.email_keywords):
                downloaded.append(mailbox.download_report(company, downloads_dir))
                pending.pop(0)
                mailbox.open()
                continue
            log.info(
                "E-mail de %s ainda não chegou. Nova tentativa em %ds.",
                company.name,
                settings.retry_interval_seconds,
            )
            page.wait_for_timeout(settings.retry_interval_seconds * 1000)
            mailbox.open()
    finally:
        page.close()

    if pending:
        names = ", ".join(company.name for company in pending)
        raise RuntimeError(f"E-mails não localizados dentro do tempo limite: {names}")
    return downloaded
