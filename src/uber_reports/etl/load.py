"""Carga no SQLite.

* Corridas: upsert por ``ride_id``. Rodar de novo com os mesmos arquivos não duplica nada.
* Lotação: a planilha é a fonte da verdade. A cada carga, ``employees`` e
  ``assignment_history`` são recriadas a partir dela.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from uber_reports.etl.parsing import clean_text, find_column, normalize_key, parse_date, person_id
from uber_reports.etl.reports import INVALID_NAMES, find_report_files, load_reports
from uber_reports.etl.schema import database, init_db

log = logging.getLogger(__name__)

RIDE_UPSERT = """
INSERT INTO rides (ride_id, employee_id, first_name, last_name, ride_date, request_hour, amount,
                   service, city, pickup_address, dropoff_address, company, source_file)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ride_id) DO UPDATE SET
    employee_id     = excluded.employee_id,
    first_name      = excluded.first_name,
    last_name       = excluded.last_name,
    ride_date       = excluded.ride_date,
    request_hour    = excluded.request_hour,
    amount          = excluded.amount,
    service         = excluded.service,
    city            = excluded.city,
    pickup_address  = excluded.pickup_address,
    dropoff_address = excluded.dropoff_address,
    company         = excluded.company,
    source_file     = excluded.source_file
"""

EMPLOYEE_SHEETS = (
    "Employees",
    "Funcionarios",
    "Funcionários",
    "Usuarios",
    "Usuários",
    "Usuarios&Lojas",
)
HISTORY_SHEETS = ("AssignmentHistory", "Historico", "Histórico", "HistoricoUsuarios")

MAPPING_COLUMNS: dict[str, tuple[str, ...]] = {
    "first_name": ("Nome", "First name"),
    "last_name": ("Sobrenome", "Last name"),
    "cost_center": ("Centro de Custo", "Cost center"),
    "store": ("Setor/Loja", "Loja", "Setor", "Store"),
    "valid_from": (
        "Data Inicio",
        "Data Início",
        "Início",
        "Inicio",
        "Vigência Início",
        "Vigencia Inicio",
        "Valid from",
    ),
    "valid_to": ("Data Fim", "Fim", "Final", "Vigência Fim", "Vigencia Fim", "Valid to"),
}
ASSIGNMENT_COLUMNS = [
    "employee_id",
    "first_name",
    "last_name",
    "cost_center",
    "store",
    "valid_from",
    "valid_to",
]
BOOTSTRAP_VALID_FROM = "1900-01-01"


@dataclass(frozen=True)
class IngestSummary:
    files: int
    rides: int
    inserted: int


def _int_or_none(value) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def _text_or_none(value) -> str | None:
    text = clean_text(value)
    return text or None


def upsert_rides(conn, rides: pd.DataFrame) -> int:
    """Grava as corridas e devolve quantas eram novas."""
    if rides.empty:
        return 0
    before = conn.execute("SELECT COUNT(*) FROM rides").fetchone()[0]
    rows = [
        (
            row.ride_id,
            row.employee_id,
            row.first_name,
            row.last_name,
            row.ride_date,
            _int_or_none(row.request_hour),
            float(row.amount),
            _text_or_none(row.service),
            _text_or_none(row.city),
            _text_or_none(row.pickup_address),
            _text_or_none(row.dropoff_address),
            _text_or_none(row.company),
            _text_or_none(getattr(row, "source_file", None)),
        )
        for row in rides.itertuples(index=False)
    ]
    conn.executemany(RIDE_UPSERT, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM rides").fetchone()[0]
    return after - before


def ingest_reports(reports_dir: Path, db_path: Path) -> IngestSummary:
    """Lê todos os relatórios de um diretório e grava as corridas no banco."""
    init_db(db_path)
    files = find_report_files(Path(reports_dir))
    if not files:
        log.warning("Nenhum relatório (.csv/.xlsx) encontrado em %s", reports_dir)
        return IngestSummary(files=0, rides=0, inserted=0)

    rides = load_reports(files)
    with database(db_path) as conn:
        inserted = upsert_rides(conn, rides)
    return IngestSummary(files=len(files), rides=len(rides), inserted=inserted)


# ------------------------------------------------------------------ planilha de lotação


def _optional_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    try:
        return find_column(df, candidates)
    except KeyError:
        return None


def _iso_date(value) -> str | None:
    parsed = parse_date(value)
    return None if parsed is None else parsed.strftime("%Y-%m-%d")


def normalize_assignments(df: pd.DataFrame, *, require_dates: bool) -> pd.DataFrame:
    """Converte uma aba da planilha (funcionários ou histórico) no esquema canônico."""
    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]

    first = df[find_column(df, MAPPING_COLUMNS["first_name"])].map(clean_text)
    last = df[find_column(df, MAPPING_COLUMNS["last_name"])].map(clean_text)
    cost_center = df[find_column(df, MAPPING_COLUMNS["cost_center"])].map(clean_text)
    store = df[find_column(df, MAPPING_COLUMNS["store"])].map(clean_text)

    from_column = _optional_column(df, MAPPING_COLUMNS["valid_from"])
    to_column = _optional_column(df, MAPPING_COLUMNS["valid_to"])
    valid_from = df[from_column].map(_iso_date) if from_column else pd.Series(None, index=df.index)
    valid_to = df[to_column].map(_iso_date) if to_column else pd.Series(None, index=df.index)

    out = pd.DataFrame(
        {
            "employee_id": [person_id(fn, ln) for fn, ln in zip(first, last, strict=True)],
            "first_name": first,
            "last_name": last,
            "cost_center": cost_center,
            "store": store,
            "valid_from": valid_from.astype(object).where(valid_from.notna(), None),
            "valid_to": valid_to.astype(object).where(valid_to.notna(), None),
        }
    )
    valid = (
        ~out["first_name"].str.lower().isin(INVALID_NAMES)
        & (out["employee_id"] != "")
        & (out["cost_center"] != "")
        & (out["store"] != "")
    )
    if require_dates:
        valid &= out["valid_from"].notna()
    return out[valid][ASSIGNMENT_COLUMNS].reset_index(drop=True)


def _pick_sheet(sheet_names: Iterable[str], candidates: Iterable[str]) -> str | None:
    lookup = {normalize_key(name): name for name in sheet_names}
    for candidate in candidates:
        if normalize_key(candidate) in lookup:
            return lookup[normalize_key(candidate)]
    return None


def read_mapping_workbook(path: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Lê a aba de funcionários (obrigatória) e a de histórico (opcional)."""
    workbook = pd.ExcelFile(path)
    employees_sheet = _pick_sheet(workbook.sheet_names, EMPLOYEE_SHEETS)
    if employees_sheet is None:
        raise ValueError(
            f"Aba de funcionários não encontrada em {Path(path).name}. "
            f"Esperada uma de: {EMPLOYEE_SHEETS}"
        )
    history_sheet = _pick_sheet(workbook.sheet_names, HISTORY_SHEETS)

    employees = normalize_assignments(
        pd.read_excel(path, sheet_name=employees_sheet), require_dates=False
    )
    history = None
    if history_sheet is not None:
        history = normalize_assignments(
            pd.read_excel(path, sheet_name=history_sheet), require_dates=True
        )
    return employees, history


def replace_assignments(
    conn, employees: pd.DataFrame, history: pd.DataFrame | None
) -> tuple[int, int]:
    """Recria pessoas e vigências a partir da planilha (fonte da verdade)."""
    source = history if history is not None and not history.empty else employees

    people = pd.concat(
        [
            employees[["employee_id", "first_name", "last_name"]],
            source[["employee_id", "first_name", "last_name"]],
        ],
        ignore_index=True,
    ).drop_duplicates(subset="employee_id")

    conn.execute("DELETE FROM assignment_history")
    conn.execute("DELETE FROM employees")
    conn.executemany(
        "INSERT INTO employees (employee_id, first_name, last_name) VALUES (?, ?, ?)",
        [
            (row.employee_id, row.first_name, row.last_name)
            for row in people.itertuples(index=False)
        ],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO assignment_history
            (employee_id, cost_center, store, valid_from, valid_to)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                row.employee_id,
                row.cost_center,
                row.store,
                _text_or_none(row.valid_from) or BOOTSTRAP_VALID_FROM,
                _text_or_none(row.valid_to),
            )
            for row in source.itertuples(index=False)
        ],
    )
    conn.commit()

    people_count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    assignments_count = conn.execute("SELECT COUNT(*) FROM assignment_history").fetchone()[0]
    return people_count, assignments_count


def load_mapping(workbook: Path, db_path: Path) -> tuple[int, int]:
    init_db(db_path)
    employees, history = read_mapping_workbook(workbook)
    with database(db_path) as conn:
        return replace_assignments(conn, employees, history)
