from __future__ import annotations

import pytest

from uber_reports.dashboard.queries import UNMAPPED, classify_period, load_enriched_rides
from uber_reports.etl.schema import database, init_db


def _seed(db, assignments, rides):
    init_db(db)
    with database(db) as conn:
        people = {employee_id for employee_id, *_ in assignments} | {r[1] for r in rides}
        conn.executemany(
            "INSERT INTO employees (employee_id, first_name, last_name) VALUES (?, ?, ?)",
            [(person, person.split()[0].title(), person.split()[-1].title()) for person in people],
        )
        conn.executemany(
            "INSERT INTO assignment_history (employee_id, cost_center, store, valid_from, valid_to)"
            " VALUES (?, ?, ?, ?, ?)",
            assignments,
        )
        conn.executemany(
            "INSERT INTO rides (ride_id, employee_id, first_name, last_name, ride_date,"
            " request_hour, amount) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rides,
        )
        conn.commit()


def test_ride_gets_the_assignment_valid_on_its_date(tmp_path):
    db = tmp_path / "rides.db"
    _seed(
        db,
        assignments=[
            ("ANA SOUZA", "Comercial", "Loja Norte", "2026-01-01", "2026-06-30"),
            ("ANA SOUZA", "Comercial", "Loja Sul", "2026-07-01", None),
        ],
        rides=[
            ("r1", "ANA SOUZA", "Ana", "Souza", "2026-06-15", 8, 20.0),
            ("r2", "ANA SOUZA", "Ana", "Souza", "2026-07-01", 18, 30.0),
            ("r3", "BIA LIMA", "Bia", "Lima", "2026-07-02", None, 10.0),
        ],
    )
    frame = load_enriched_rides(db).set_index("ride_id")

    assert frame.loc["r1", "store"] == "Loja Norte"
    assert frame.loc["r2", "store"] == "Loja Sul"
    assert frame.loc["r3", "store"] == UNMAPPED
    assert frame.loc["r3", "cost_center"] == UNMAPPED
    assert frame.loc["r1", "period"] == "Manhã"
    assert frame.loc["r2", "period"] == "Noite"
    assert frame.loc["r3", "period"] == "Sem hora"
    assert frame.loc["r1", "month"] == "jun"
    assert frame.loc["r1", "user"] == "Ana Souza"
    assert frame.loc["r3", "pickup_address"] == "Não informado"


def test_overlapping_assignments_do_not_duplicate_rides(tmp_path):
    db = tmp_path / "rides.db"
    _seed(
        db,
        assignments=[
            ("ANA SOUZA", "Comercial", "Loja Norte", "2026-01-01", None),
            ("ANA SOUZA", "Logística", "CD", "2026-01-01", None),
        ],
        rides=[("r1", "ANA SOUZA", "Ana", "Souza", "2026-03-10", 9, 12.0)],
    )
    frame = load_enriched_rides(db)
    assert len(frame) == 1


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "Madrugada"),
        (5, "Madrugada"),
        (6, "Manhã"),
        (11, "Manhã"),
        (12, "Tarde"),
        (17, "Tarde"),
        (18, "Noite"),
        (23, "Noite"),
        (None, "Sem hora"),
        (float("nan"), "Sem hora"),
    ],
)
def test_classify_period(hour, expected):
    assert classify_period(hour) == expected
