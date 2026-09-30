from __future__ import annotations

from datetime import datetime, time

import pandas as pd
import pytest

from uber_reports.etl.parsing import (
    find_column,
    parse_brl,
    parse_date,
    parse_hour,
    person_id,
    ride_fingerprint,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R$ 1.234,56", 1234.56),
        ("23,45", 23.45),
        ("12.5", 12.5),
        (12, 12.0),
        ("-8,10", -8.10),
        ("", None),
        (None, None),
        (float("nan"), None),
        ("abc", None),
    ],
)
def test_parse_brl(raw, expected):
    assert parse_brl(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("14:35", 14),
        ("2:35 PM", 14),
        ("2:35 AM", 2),
        ("14", 14),
        ("09:05:30", 9),
        (time(9, 15), 9),
        (datetime(2026, 1, 1, 23, 5), 23),
        (0.5, 12),
        (13, 13),
        (25, None),
        ("", None),
        (None, None),
        ("xx", None),
    ],
)
def test_parse_hour(raw, expected):
    assert parse_hour(raw) == expected


def test_parse_date_accepts_iso_and_brazilian_formats():
    assert parse_date("2026-07-15").strftime("%Y-%m-%d") == "2026-07-15"
    assert parse_date("2026-07-15 10:20:00").strftime("%Y-%m-%d") == "2026-07-15"
    assert parse_date("15/07/2026").strftime("%Y-%m-%d") == "2026-07-15"
    assert parse_date(datetime(2026, 7, 15, 8)).strftime("%Y-%m-%d") == "2026-07-15"
    assert parse_date("") is None
    assert parse_date("n/a") is None


def test_find_column_ignores_accents_case_and_spaces():
    frame = pd.DataFrame(columns=["Serviço", " Cidade "])
    assert find_column(frame, ["Servico"]) == "Serviço"
    assert find_column(frame, ["cidade"]) == " Cidade "
    with pytest.raises(KeyError):
        find_column(frame, ["Nome"])


def test_person_id_is_stable_across_spelling_variations():
    assert person_id("José", "da Silva") == "JOSE DA SILVA"
    assert person_id("jose ", "DA  SILVA") == "JOSE DA SILVA"
    assert person_id(None, "") == ""


def test_ride_fingerprint_is_deterministic_and_sensitive():
    base = ["ANA SOUZA", "Ana", "Souza", "2026-07-15", "08:12", 23.45, "UberX", "São Paulo"]
    assert ride_fingerprint(base) == ride_fingerprint(list(base))
    assert ride_fingerprint(base) == ride_fingerprint(base[:5] + [23.450001] + base[6:])
    assert ride_fingerprint(base) != ride_fingerprint(base[:5] + [23.46] + base[6:])
