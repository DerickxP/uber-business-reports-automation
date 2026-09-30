"""Carregamento e validação da configuração (``config.json``).

A configuração é um JSON simples e sem segredos: credenciais nunca entram aqui.
O acesso aos portais usa sessões de navegador salvas localmente e ignoradas pelo git
(ver ``uber_reports.automation.sessions``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_ENV_VAR = "UBER_REPORTS_CONFIG"
DEFAULT_CONFIG_FILES = ("config.json", "config.example.json")
VALID_PERIODS = ("previous_month", "last_n_days")
VALID_PROVIDERS = ("outlook", "gmail")


class ConfigError(ValueError):
    """Configuração ausente ou inválida."""


@dataclass(frozen=True)
class Company:
    """Empresa (organização) cadastrada no Uber for Business."""

    name: str
    email_keywords: tuple[str, ...]


@dataclass(frozen=True)
class ReportSettings:
    period: str = "previous_month"
    last_n_days: int = 30


@dataclass(frozen=True)
class MailSettings:
    provider: str = "outlook"
    url: str = "https://outlook.office.com/mail/"
    subject: str = "Seu arquivo foi exportado e esta pronto"
    wait_max_seconds: int = 300
    retry_interval_seconds: int = 15


@dataclass(frozen=True)
class BrowserSettings:
    headless: bool = False
    locale: str = "pt-BR"


@dataclass(frozen=True)
class PathSettings:
    downloads: Path
    sessions: Path
    database: Path
    mapping_workbook: Path
    dashboard: Path

    @property
    def uber_session(self) -> Path:
        return self.sessions / "uber.session.json"

    @property
    def mail_session(self) -> Path:
        return self.sessions / "mail.session.json"


@dataclass(frozen=True)
class DashboardSettings:
    title: str = "Uber Corporativo"
    subtitle: str = "Dashboard de corridas"
    brand: str = "Demo"
    logo: Path | None = None


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    companies: tuple[Company, ...]
    report: ReportSettings
    mail: MailSettings
    browser: BrowserSettings
    paths: PathSettings
    dashboard: DashboardSettings


def _resolve(base_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def settings_from_dict(data: dict[str, Any], base_dir: Path) -> Settings:
    """Monta ``Settings`` a partir do dicionário do JSON, validando o essencial."""
    companies_raw = data.get("companies") or []
    if not isinstance(companies_raw, list) or not companies_raw:
        raise ConfigError("Informe ao menos uma empresa em 'companies'.")

    companies: list[Company] = []
    for item in companies_raw:
        name = str(item.get("name", "")).strip()
        if not name:
            raise ConfigError("Cada empresa em 'companies' precisa de 'name'.")
        keywords = tuple(
            str(word).strip() for word in item.get("email_keywords", []) if str(word).strip()
        )
        companies.append(Company(name=name, email_keywords=keywords or (name.split()[0],)))

    report_raw = data.get("report", {})
    report = ReportSettings(
        period=str(report_raw.get("period", ReportSettings.period)),
        last_n_days=int(report_raw.get("last_n_days", ReportSettings.last_n_days)),
    )
    if report.period not in VALID_PERIODS:
        raise ConfigError(f"'report.period' deve ser um de {VALID_PERIODS}.")

    mail_raw = data.get("mail", {})
    mail = MailSettings(
        provider=str(mail_raw.get("provider", MailSettings.provider)).lower(),
        url=str(mail_raw.get("url", MailSettings.url)),
        subject=str(mail_raw.get("subject", MailSettings.subject)),
        wait_max_seconds=int(mail_raw.get("wait_max_seconds", MailSettings.wait_max_seconds)),
        retry_interval_seconds=int(
            mail_raw.get("retry_interval_seconds", MailSettings.retry_interval_seconds)
        ),
    )
    if mail.provider not in VALID_PROVIDERS:
        raise ConfigError(f"'mail.provider' deve ser um de {VALID_PROVIDERS}.")

    browser_raw = data.get("browser", {})
    browser = BrowserSettings(
        headless=bool(browser_raw.get("headless", BrowserSettings.headless)),
        locale=str(browser_raw.get("locale", BrowserSettings.locale)),
    )

    paths_raw = data.get("paths", {})
    paths = PathSettings(
        downloads=_resolve(base_dir, paths_raw.get("downloads", "data/downloads")),
        sessions=_resolve(base_dir, paths_raw.get("sessions", "data/sessions")),
        database=_resolve(base_dir, paths_raw.get("database", "data/rides.db")),
        mapping_workbook=_resolve(base_dir, paths_raw.get("mapping_workbook", "data/mapping.xlsx")),
        dashboard=_resolve(base_dir, paths_raw.get("dashboard", "output/dashboard.html")),
    )

    dash_raw = data.get("dashboard", {})
    logo = dash_raw.get("logo")
    dashboard = DashboardSettings(
        title=str(dash_raw.get("title", DashboardSettings.title)),
        subtitle=str(dash_raw.get("subtitle", DashboardSettings.subtitle)),
        brand=str(dash_raw.get("brand", DashboardSettings.brand)),
        logo=_resolve(base_dir, logo) if logo else None,
    )

    return Settings(
        base_dir=base_dir,
        companies=tuple(companies),
        report=report,
        mail=mail,
        browser=browser,
        paths=paths,
        dashboard=dashboard,
    )


def find_config_file(explicit: str | Path | None = None) -> Path:
    """Localiza o arquivo de configuração: argumento, variável de ambiente ou diretório atual."""
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise ConfigError(f"Arquivo de configuração não encontrado: {path}")
        return path

    env_value = os.environ.get(CONFIG_ENV_VAR)
    if env_value:
        return find_config_file(env_value)

    for name in DEFAULT_CONFIG_FILES:
        candidate = Path.cwd() / name
        if candidate.exists():
            return candidate

    raise ConfigError(
        "Nenhum config.json encontrado. Copie config.example.json para config.json e ajuste."
    )


def load_settings(path: str | Path | None = None) -> Settings:
    config_file = find_config_file(path)
    with open(config_file, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"JSON inválido em {config_file}: {exc}") from exc
    return settings_from_dict(data, config_file.resolve().parent)
