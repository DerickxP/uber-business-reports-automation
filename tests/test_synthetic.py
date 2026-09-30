from __future__ import annotations

from uber_reports.dashboard.queries import UNMAPPED, load_enriched_rides
from uber_reports.dashboard.render import build_dashboard
from uber_reports.etl.load import ingest_reports, load_mapping
from uber_reports.etl.parsing import person_id


def test_generated_reports_follow_the_portal_layout(small_dataset):
    assert len(small_dataset.reports) == 6  # 2 empresas x 3 meses
    first = small_dataset.reports[0].read_text(encoding="utf-8-sig").splitlines()
    assert first[0].startswith("Empresa:;")
    assert first[4] == "Transações"
    assert first[5].startswith("Nome;Sobrenome;")
    assert small_dataset.rides > 0
    assert any(employee.moved_on for employee in small_dataset.staff)


def test_pipeline_reproduces_the_generators_truth(small_dataset, tmp_path):
    db = tmp_path / "rides.db"
    ingest_reports(small_dataset.reports_dir, db)
    load_mapping(small_dataset.mapping_workbook, db)

    rides = load_enriched_rides(db)
    assert len(rides) == small_dataset.rides
    assert not (rides["store"] == UNMAPPED).any()

    truth = {person_id(e.first_name, e.last_name): e for e in small_dataset.staff}
    mismatches = [
        (row.employee_id, row.ride_date.date(), row.store)
        for row in rides.itertuples(index=False)
        if truth[row.employee_id].store_at(row.ride_date.date()) != row.store
    ]
    assert mismatches == []

    dashboard = build_dashboard(rides, tmp_path / "dashboard.html")
    assert dashboard.stat().st_size > 20_000
