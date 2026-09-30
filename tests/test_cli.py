from __future__ import annotations

import pytest

from uber_reports.cli import main


def test_demo_command_runs_the_whole_pipeline(tmp_path):
    output = tmp_path / "demo"
    code = main(
        [
            "demo",
            "--output-dir",
            str(output),
            "--months",
            "1",
            "--employees",
            "5",
            "--rides-per-month",
            "20",
            "--seed",
            "1",
        ]
    )
    assert code == 0
    assert (output / "dashboard.html").exists()
    assert (output / "rides.db").exists()
    assert (output / "mapping.xlsx").exists()
    assert len(list((output / "downloads").glob("*.csv"))) == 2


def test_missing_config_is_reported_as_usage_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UBER_REPORTS_CONFIG", raising=False)
    with pytest.raises(SystemExit) as raised:
        main(["init-db"])
    assert raised.value.code == 2
