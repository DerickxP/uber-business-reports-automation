from __future__ import annotations

import json

import pytest

from uber_reports.config import ConfigError, load_settings, settings_from_dict


def test_settings_from_dict_resolves_relative_paths_and_defaults(tmp_path):
    settings = settings_from_dict({"companies": [{"name": "EMPRESA X LTDA"}]}, tmp_path)
    assert settings.companies[0].email_keywords == ("EMPRESA",)
    assert settings.paths.database == (tmp_path / "data" / "rides.db").resolve()
    assert settings.paths.uber_session.name == "uber.session.json"
    assert settings.report.period == "previous_month"
    assert settings.mail.provider == "outlook"
    assert settings.dashboard.logo is None


def test_missing_companies_is_an_error(tmp_path):
    with pytest.raises(ConfigError):
        settings_from_dict({}, tmp_path)


def test_invalid_period_and_provider_are_errors(tmp_path):
    with pytest.raises(ConfigError):
        settings_from_dict({"companies": [{"name": "X"}], "report": {"period": "weekly"}}, tmp_path)
    with pytest.raises(ConfigError):
        settings_from_dict({"companies": [{"name": "X"}], "mail": {"provider": "yahoo"}}, tmp_path)


def test_load_settings_reads_config_json_from_cwd(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"companies": [{"name": "EMPRESA Y", "email_keywords": ["Y"]}]}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UBER_REPORTS_CONFIG", raising=False)
    settings = load_settings()
    assert settings.companies[0].name == "EMPRESA Y"
    assert settings.base_dir == tmp_path.resolve()
