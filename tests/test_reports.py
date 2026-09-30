from __future__ import annotations

from tests.helpers import RIDE_ROW, write_report
from uber_reports.etl.reports import find_report_files, load_reports, normalize_rides, read_report


def test_read_report_detects_header_company_and_delimiter(tmp_path):
    path = write_report(tmp_path / "report.csv", "EMPRESA X", [RIDE_ROW])
    report = read_report(path)
    assert report.company == "EMPRESA X"
    assert report.header_row == 5
    assert len(report.raw) == 1
    assert "Valor total: BRL" in report.raw.columns


def test_read_report_accepts_comma_delimiter(tmp_path):
    path = write_report(tmp_path / "report.csv", "EMPRESA X", [RIDE_ROW], delimiter=",")
    report = read_report(path)
    assert len(report.raw) == 1
    assert report.raw.iloc[0]["Nome"] == "Ana"


def test_normalize_rides_drops_invalid_rows_and_builds_canonical_columns(tmp_path):
    rows = [
        RIDE_ROW,
        ["--", "", "", "UberX", "SP", "", "", "2026-07-16", "09:00", "Não", "10,00", "", ""],
        ["Bia", "Lima", "", "UberX", "SP", "", "", "2026-07-16", "09:00", "Não", "", "", ""],
        ["Caio", "Melo", "", "UberX", "SP", "", "", "", "09:00", "Não", "5,00", "", ""],
    ]
    rides = normalize_rides(read_report(write_report(tmp_path / "r.csv", "EMPRESA X", rows)))

    assert len(rides) == 1
    ride = rides.iloc[0]
    assert ride.employee_id == "ANA SOUZA"
    assert ride.ride_date == "2026-07-15"
    assert int(ride.request_hour) == 8
    assert ride.amount == 23.45
    assert ride.pickup_address == "Rua A, 1"
    assert ride.company == "EMPRESA X"
    assert len(ride.ride_id) == 40


def test_load_reports_deduplicates_the_same_ride_across_files(tmp_path):
    first = write_report(tmp_path / "a.csv", "EMPRESA X", [RIDE_ROW])
    second = write_report(tmp_path / "b.csv", "EMPRESA X", [RIDE_ROW])
    rides = load_reports([first, second])
    assert len(rides) == 1
    assert rides.iloc[0].source_file == "b.csv"


def test_find_report_files_ignores_temp_and_unrelated_files(tmp_path):
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "b.xlsx").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "~$open.xlsx").write_bytes(b"")
    assert [path.name for path in find_report_files(tmp_path)] == ["a.csv", "b.xlsx"]
    assert find_report_files(tmp_path / "missing") == []
