from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from uber_reports.demo.synthetic import DemoDataset, generate_demo_dataset


@pytest.fixture
def small_dataset(tmp_path: Path) -> DemoDataset:
    """Três meses fechados antes de ago/2026, com poucas pessoas e algumas transferências."""
    return generate_demo_dataset(
        tmp_path / "downloads",
        tmp_path / "mapping.xlsx",
        seed=7,
        months=3,
        employees=8,
        rides_per_month=60,
        anchor=date(2026, 8, 15),
    )
