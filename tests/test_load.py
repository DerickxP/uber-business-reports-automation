from __future__ import annotations

import pandas as pd
import pytest

from tests.helpers import write_workbook
from uber_reports.etl.load import ingest_reports, load_mapping
from uber_reports.etl.schema import database


def test_ingest_is_idempotent(small_dataset, tmp_path):
    db = tmp_path / "rides.db"
    first = ingest_reports(small_dataset.reports_dir, db)
    second = ingest_reports(small_dataset.reports_dir, db)

    assert first.files == len(small_dataset.reports)
    assert first.rides == first.inserted == small_dataset.rides
    assert second.rides == first.rides
    assert second.inserted == 0
    with database(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM rides").fetchone()[0] == first.rides


def test_ingest_with_empty_directory_creates_schema(tmp_path):
    summary = ingest_reports(tmp_path / "empty", tmp_path / "rides.db")
    assert (summary.files, summary.rides, summary.inserted) == (0, 0, 0)
    with database(tmp_path / "rides.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM rides").fetchone()[0] == 0


def _employees_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Nome": "Ana",
                "Sobrenome": "Souza",
                "Centro de Custo": "Comercial",
                "Setor/Loja": "Loja Sul",
            }
        ]
    )


def test_load_mapping_with_history_sheet_replaces_previous_load(tmp_path):
    history = pd.DataFrame(
        [
            {
                "Nome": "Ana",
                "Sobrenome": "Souza",
                "Centro de Custo": "Comercial",
                "Setor/Loja": "Loja Norte",
                "Data Inicio": "01/01/2026",
                "Data Fim": "30/06/2026",
            },
            {
                "Nome": "Ana",
                "Sobrenome": "Souza",
                "Centro de Custo": "Comercial",
                "Setor/Loja": "Loja Sul",
                "Data Inicio": "01/07/2026",
                "Data Fim": None,
            },
        ]
    )
    workbook = write_workbook(
        tmp_path / "map.xlsx", {"Funcionarios": _employees_sheet(), "HistoricoUsuarios": history}
    )
    db = tmp_path / "rides.db"

    assert load_mapping(workbook, db) == (1, 2)
    assert load_mapping(workbook, db) == (1, 2)  # recarga não acumula

    with database(db) as conn:
        rows = conn.execute(
            "SELECT store, valid_from, valid_to FROM assignment_history ORDER BY valid_from"
        ).fetchall()
    assert rows == [("Loja Norte", "2026-01-01", "2026-06-30"), ("Loja Sul", "2026-07-01", None)]


def test_load_mapping_bootstraps_history_from_employees_sheet(tmp_path):
    workbook = write_workbook(tmp_path / "map.xlsx", {"Usuarios": _employees_sheet()})
    db = tmp_path / "rides.db"
    assert load_mapping(workbook, db) == (1, 1)
    with database(db) as conn:
        row = conn.execute("SELECT store, valid_from, valid_to FROM assignment_history").fetchone()
    assert row == ("Loja Sul", "1900-01-01", None)


def test_load_mapping_requires_an_employees_sheet(tmp_path):
    workbook = write_workbook(tmp_path / "map.xlsx", {"Outra": _employees_sheet()})
    with pytest.raises(ValueError, match="Aba de funcionários"):
        load_mapping(workbook, tmp_path / "rides.db")
