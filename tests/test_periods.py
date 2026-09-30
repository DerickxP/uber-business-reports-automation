from __future__ import annotations

from datetime import date

import pytest

from uber_reports.automation.uber_portal import report_period


def test_previous_month():
    assert report_period("previous_month", today=date(2026, 3, 10)) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )


def test_previous_month_crosses_the_year():
    assert report_period("previous_month", today=date(2026, 1, 5)) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_last_n_days():
    assert report_period("last_n_days", last_n_days=30, today=date(2026, 3, 10)) == (
        date(2026, 2, 8),
        date(2026, 3, 10),
    )


def test_unknown_period():
    with pytest.raises(ValueError):
        report_period("weekly")
