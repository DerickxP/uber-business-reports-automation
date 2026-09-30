"""Automação do portal Uber for Business.

Estratégia adotada:

* A sessão de login é reaproveitada via ``storage_state`` do Playwright. Nenhuma senha
  passa pelo código e não há login automatizado, o que evita bloqueios por 2FA.
* Todo texto lido da página é comparado sem acentos e em caixa alta, porque o portal
  alterna entre pt-BR e inglês e varia a acentuação dos rótulos.
* Cada ação tem seletores alternativos com fallback. O robô só desiste depois de
  esgotar as opções, e registra o motivo.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import date, timedelta

from uber_reports.automation.text import normalize_date_range, normalize_text

try:  # o Playwright só é necessário para a extração; ETL e testes não dependem dele
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover

    class PlaywrightTimeoutError(Exception):  # type: ignore[no-redef]
        """Substituto usado quando o Playwright não está instalado."""


log = logging.getLogger(__name__)

HOME_URL = "https://business.uber.com/"
REPORTS_URL = "https://business.uber.com/p/reports"
DATE_FORMAT = "%Y/%m/%d"

ORG_PICKER_MARKERS = ("ESCOLHA UMA DAS ORGANIZACOES", "PAINEIS")
COOKIE_LABELS = ("Aceitar", "Accept", "Rejeitar", "Reject")
REPORTS_MENU_LABELS = ("Relatorios e informacoes", "Reports and insights")
REPORTS_ITEM_LABELS = ("Relatorios", "Reports")
CREATE_REPORT_LABELS = ("Criar reporte", "Create report")
HOME_LINK_LABELS = ("Inicio", "Início", "Home")
DATE_RANGE_SELECTORS = (
    "xpath=//label[contains(., 'Intervalo de datas')]/following::input[1]",
    "xpath=//*[contains(normalize-space(.), 'Intervalo de datas')]/following::input[1]",
    "xpath=//*[contains(normalize-space(.), 'Date range')]/following::input[1]",
    "xpath=//*[contains(normalize-space(.), 'Filtrar dados')]//input[1]",
    "xpath=(//main//input)[1]",
)
CLICKABLE_SELECTOR = "a, button, [role='button'], [role='menuitem'], span, div"


def report_period(
    kind: str, *, last_n_days: int = 30, today: date | None = None
) -> tuple[date, date]:
    """Intervalo do relatório. ``previous_month`` é o padrão do fechamento mensal."""
    today = today or date.today()
    if kind == "previous_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if kind == "last_n_days":
        return today - timedelta(days=last_n_days), today
    raise ValueError(f"Período desconhecido: {kind!r}")


class UberBusinessPortal:
    """Operações de alto nível sobre uma ``page`` já autenticada."""

    def __init__(self, page) -> None:
        self.page = page

    # ---------------------------------------------------------------- leitura

    def page_text(self, timeout_ms: int = 10000) -> str:
        return normalize_text(self.page.locator("body").inner_text(timeout=timeout_ms))

    def _mentions(self, labels: Iterable[str], text: str | None = None) -> bool:
        haystack = text if text is not None else self.page_text()
        return any(normalize_text(label) in haystack for label in labels)

    # -------------------------------------------------------------- navegação

    def go_home(self) -> None:
        self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(2000)
        self.dismiss_cookie_banner()

    def dismiss_cookie_banner(self) -> None:
        for label in COOKIE_LABELS:
            candidates = (
                self.page.get_by_role("button", name=label),
                self.page.locator(f"button:has-text('{label}')"),
            )
            for candidate in candidates:
                try:
                    button = candidate.first
                    button.wait_for(state="visible", timeout=1000)
                    button.click(timeout=3000, force=True)
                except Exception:
                    continue
                self.page.wait_for_timeout(800)
                log.debug("Banner de cookies fechado (%s).", label)
                return

    def wait_until_stable(self, timeout_ms: int = 15000) -> None:
        """Espera sair da tela de escolha de organização (ela some quando a seleção pega)."""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            self.dismiss_cookie_banner()
            try:
                text = self.page_text(timeout_ms=2000)
            except PlaywrightTimeoutError:
                self.page.wait_for_timeout(500)
                continue
            if not self._mentions(ORG_PICKER_MARKERS, text):
                return
            self.page.wait_for_timeout(500)

    def click_by_text(self, labels: Iterable[str], timeout_ms: int = 10000, scope=None) -> bool:
        """Clica no primeiro elemento cujo texto normalizado seja igual a um dos rótulos."""
        targets = {normalize_text(label) for label in labels}
        root = scope or self.page.locator(CLICKABLE_SELECTOR)
        for index in range(root.count()):
            element = root.nth(index)
            try:
                text = normalize_text(element.inner_text(timeout=1000))
            except PlaywrightTimeoutError:
                continue
            if text not in targets:
                continue
            try:
                element.click(timeout=timeout_ms, no_wait_after=True)
                return True
            except PlaywrightTimeoutError:
                try:
                    element.scroll_into_view_if_needed(timeout=3000)
                    self.page.wait_for_timeout(200)
                    element.click(timeout=3000, force=True, no_wait_after=True)
                    return True
                except PlaywrightTimeoutError:
                    continue
        return False

    # ------------------------------------------------------------------ fluxo

    def select_company(self, name: str) -> None:
        log.info("Selecionando organização: %s", name)
        self.dismiss_cookie_banner()
        wanted = normalize_text(name)

        if self._mentions(ORG_PICKER_MARKERS):
            cards = self.page.locator("a, button, div[role='button']")
            for index in range(cards.count()):
                card = cards.nth(index)
                try:
                    card_text = card.inner_text(timeout=1000)
                except PlaywrightTimeoutError:
                    continue
                if wanted in normalize_text(card_text):
                    self.dismiss_cookie_banner()
                    card.click(timeout=10000, no_wait_after=True)
                    self.wait_until_stable()
                    self.dismiss_cookie_banner()
                    return
            raise RuntimeError(f"Organização '{name}' não encontrada na tela inicial.")

        try:
            self.page.get_by_role("button", name="Selecionar conta").click(timeout=8000)
        except PlaywrightTimeoutError:
            self.page.locator("[data-testid='account-selector']").click(timeout=8000)

        options = self.page.locator("text=/./")
        for index in range(options.count()):
            option = options.nth(index)
            try:
                option_text = option.inner_text(timeout=1000)
            except PlaywrightTimeoutError:
                continue
            if wanted in normalize_text(option_text):
                option.click(timeout=10000, no_wait_after=True)
                self.wait_until_stable()
                self.dismiss_cookie_banner()
                return
        raise RuntimeError(f"Organização '{name}' não encontrada no seletor de contas.")

    def ensure_home_before_reports(self) -> None:
        """Se a tela de criação de reporte ficou aberta, volta ao início antes de navegar."""
        self.dismiss_cookie_banner()
        if not self._mentions(CREATE_REPORT_LABELS):
            return
        log.debug("Tela de criação de reporte ainda aberta; voltando ao início.")
        for label in HOME_LINK_LABELS:
            try:
                self.page.get_by_role("link", name=label).click(timeout=8000)
                break
            except PlaywrightTimeoutError:
                continue
        else:
            self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(2000)

    def open_reports(self) -> None:
        log.info("Abrindo a área de relatórios.")
        self.ensure_home_before_reports()
        self.dismiss_cookie_banner()

        if self.click_by_text(REPORTS_MENU_LABELS, timeout_ms=15000):
            self.page.wait_for_timeout(1500)
            self.dismiss_cookie_banner()
            if self.click_by_text(REPORTS_ITEM_LABELS, timeout_ms=15000):
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(2000)
                self.dismiss_cookie_banner()
                return
            raise RuntimeError("Menu de relatórios aberto, mas a opção 'Relatórios' não apareceu.")

        log.debug("Menu lateral não apareceu; abrindo a URL de relatórios diretamente.")
        self.page.goto(REPORTS_URL, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(2000)
        self.dismiss_cookie_banner()

    def fill_date_range(self, start: date, end: date) -> None:
        """Digita o intervalo como um usuário faria e confere o valor final do campo."""
        start_text, end_text = start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)

        field = None
        for selector in DATE_RANGE_SELECTORS:
            locator = self.page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeoutError:
                continue
            placeholder = normalize_text(locator.get_attribute("placeholder") or "")
            current = normalize_text(locator.input_value() or "")
            if "PESQUISE" in placeholder or "PESQUISE" in current or "SEARCH" in placeholder:
                continue  # é o campo de busca, não o de datas
            field = locator
            break
        if field is None:
            raise RuntimeError("Campo 'Intervalo de datas' não encontrado.")

        expected = normalize_date_range(f"{start_text} - {end_text}")
        last_value = ""
        for attempt in range(1, 4):
            field.click(timeout=10000)
            field.press("Control+A")
            self.page.wait_for_timeout(150)
            field.press("Backspace")
            self.page.wait_for_timeout(300)
            field.type(start_text, delay=140)
            self.page.wait_for_timeout(700)
            field.type(end_text, delay=140)
            self.page.wait_for_timeout(700)
            last_value = field.input_value()
            if normalize_date_range(last_value) == expected:
                return
            log.warning("Tentativa %d de preencher o período falhou: %r", attempt, last_value)
            self.page.wait_for_timeout(1000)
        raise RuntimeError(
            f"Período preenchido incorretamente. Esperado {expected!r}, obtido {last_value!r}."
        )

    def _click_create_report_final(self) -> None:
        for label in CREATE_REPORT_LABELS:
            candidates = (
                self.page.get_by_role("button", name=label),
                self.page.locator(f"button:has-text('{label}')"),
            )
            for candidate in candidates:
                try:
                    button = candidate.last
                    button.scroll_into_view_if_needed(timeout=5000)
                    self.page.wait_for_timeout(500)
                    button.click(timeout=10000, force=True)
                    return
                except PlaywrightTimeoutError:
                    continue
        raise RuntimeError("Botão final 'Criar reporte' não encontrado.")

    def request_report(self, company_name: str, start: date, end: date) -> None:
        log.info("Solicitando reporte de %s a %s para %s", start, end, company_name)
        self.dismiss_cookie_banner()
        if not self.click_by_text(CREATE_REPORT_LABELS, timeout_ms=15000):
            raise RuntimeError("Botão 'Criar reporte' não encontrado.")
        self.page.wait_for_timeout(1500)
        self.dismiss_cookie_banner()
        self.fill_date_range(start, end)
        self._click_create_report_final()
        self.page.wait_for_timeout(3000)
        log.info("Reporte solicitado para %s. O arquivo chega por e-mail.", company_name)
