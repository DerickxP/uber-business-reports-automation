"""Orquestração da extração: portal Uber (solicitar) + webmail (baixar)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from uber_reports.automation.mailbox import wait_and_download
from uber_reports.automation.uber_portal import UberBusinessPortal, report_period
from uber_reports.config import Settings

log = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    requested: list[str] = field(default_factory=list)
    downloaded: list[Path] = field(default_factory=list)


def _safe_screenshot(page, path: Path) -> None:
    try:
        if page is not None and not page.is_closed():
            page.screenshot(path=str(path))
            log.info("Screenshot do erro salva em %s", path)
    except Exception:
        log.debug("Não foi possível salvar a screenshot do erro.")


def run_extraction(settings: Settings) -> ExtractionResult:
    from playwright.sync_api import sync_playwright

    uber_session = settings.paths.uber_session
    mail_session = settings.paths.mail_session
    if not uber_session.exists():
        raise FileNotFoundError(
            f"Sessão da Uber não encontrada em {uber_session}. Rode: uber-reports save-session uber"
        )
    if not mail_session.exists():
        raise FileNotFoundError(
            f"Sessão do webmail não encontrada em {mail_session}. "
            "Rode: uber-reports save-session mail"
        )

    downloads = settings.paths.downloads
    downloads.mkdir(parents=True, exist_ok=True)
    start, end = report_period(settings.report.period, last_n_days=settings.report.last_n_days)
    result = ExtractionResult()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.browser.headless)
        uber_context = mail_context = page = None
        try:
            uber_context = browser.new_context(
                storage_state=str(uber_session),
                accept_downloads=True,
                locale=settings.browser.locale,
            )
            page = uber_context.new_page()
            portal = UberBusinessPortal(page)
            for company in settings.companies:
                log.info("---- %s ----", company.name)
                portal.go_home()
                portal.select_company(company.name)
                portal.open_reports()
                portal.request_report(company.name, start, end)
                result.requested.append(company.name)
                page.wait_for_timeout(3000)
            uber_context.close()
            uber_context = page = None

            mail_context = browser.new_context(
                storage_state=str(mail_session),
                accept_downloads=True,
                locale=settings.browser.locale,
            )
            result.downloaded = wait_and_download(
                mail_context, settings.companies, settings.mail, downloads
            )
        except Exception:
            _safe_screenshot(page, downloads / "error_screenshot.png")
            raise
        finally:
            for context in (uber_context, mail_context):
                if context is not None:
                    context.close()
            browser.close()

    log.info(
        "Extração concluída: %d reporte(s) solicitado(s), %d arquivo(s) baixado(s).",
        len(result.requested),
        len(result.downloaded),
    )
    return result
