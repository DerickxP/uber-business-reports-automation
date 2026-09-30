"""Esquema do banco SQLite.

Três tabelas:

* ``rides``: uma linha por corrida, identificada por hash de conteúdo (idempotência).
* ``employees``: cadastro mínimo de pessoas, derivado da planilha de mapeamento.
* ``assignment_history``: lotação (centro de custo + loja) com vigência. É o que permite
  atribuir cada corrida à lotação válida na data da corrida, e não à lotação atual.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DDL = (
    """
    CREATE TABLE IF NOT EXISTS rides (
        ride_id          TEXT PRIMARY KEY,
        employee_id      TEXT NOT NULL,
        first_name       TEXT,
        last_name        TEXT,
        ride_date        TEXT NOT NULL,
        request_hour     INTEGER,
        amount           REAL NOT NULL,
        service          TEXT,
        city             TEXT,
        pickup_address   TEXT,
        dropoff_address  TEXT,
        company          TEXT,
        source_file      TEXT,
        loaded_at        TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS employees (
        employee_id  TEXT PRIMARY KEY,
        first_name   TEXT,
        last_name    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assignment_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id  TEXT NOT NULL REFERENCES employees(employee_id),
        cost_center  TEXT NOT NULL,
        store        TEXT NOT NULL,
        valid_from   TEXT NOT NULL,
        valid_to     TEXT,
        UNIQUE (employee_id, cost_center, store, valid_from)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(ride_date)",
    "CREATE INDEX IF NOT EXISTS idx_rides_employee ON rides(employee_id)",
    "CREATE INDEX IF NOT EXISTS idx_assignment_employee ON assignment_history(employee_id)",
    "CREATE INDEX IF NOT EXISTS idx_assignment_validity"
    " ON assignment_history(valid_from, valid_to)",
)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def database(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Conexão que fecha ao sair do bloco (o context manager nativo do sqlite3 não fecha)."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with database(db_path) as conn:
        for statement in DDL:
            conn.execute(statement)
        conn.commit()
