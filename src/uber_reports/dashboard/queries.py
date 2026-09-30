"""Consultas analíticas sobre o banco.

O ponto central é o join temporal: cada corrida recebe o centro de custo e a loja que
valiam na data da corrida. Sem isso, uma pessoa transferida de loja em julho teria todo
o histórico de junho reatribuído à loja nova, distorcendo o custo por loja.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from uber_reports.etl.parsing import full_name
from uber_reports.etl.schema import database

UNMAPPED = "Não mapeado"
NOT_INFORMED = "Não informado"
MONTHS_PT = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}
PERIODS = ("Madrugada", "Manhã", "Tarde", "Noite", "Sem hora")

# Para cada corrida, escolhe a vigência de lotação válida na data da corrida. Se houver
# mais de uma (vigências sobrepostas), vence a que começou por último; o LIMIT 1 garante
# que nenhuma corrida seja duplicada pelo join.
ENRICHED_RIDES_SQL = """
SELECT
    r.ride_id,
    r.employee_id,
    r.first_name,
    r.last_name,
    r.ride_date,
    r.request_hour,
    r.amount,
    r.service,
    r.city,
    r.company,
    COALESCE(NULLIF(r.pickup_address, ''), :not_informed)  AS pickup_address,
    COALESCE(NULLIF(r.dropoff_address, ''), :not_informed) AS dropoff_address,
    COALESCE(a.cost_center, :unmapped) AS cost_center,
    COALESCE(a.store, :unmapped)       AS store
FROM rides r
LEFT JOIN assignment_history a
  ON a.id = (
      SELECT a2.id
      FROM assignment_history a2
      WHERE a2.employee_id = r.employee_id
        AND date(r.ride_date) >= date(a2.valid_from)
        AND (a2.valid_to IS NULL OR date(r.ride_date) <= date(a2.valid_to))
      ORDER BY a2.valid_from DESC, a2.id DESC
      LIMIT 1
  )
ORDER BY r.ride_date, r.request_hour
"""


def classify_period(hour) -> str:
    """Faixa do dia usada nos filtros e no gráfico de rosca."""
    if hour is None or pd.isna(hour):
        return "Sem hora"
    value = int(hour)
    if 0 <= value <= 5:
        return "Madrugada"
    if 6 <= value <= 11:
        return "Manhã"
    if 12 <= value <= 17:
        return "Tarde"
    return "Noite"


def load_enriched_rides(db_path: Path) -> pd.DataFrame:
    """Corridas com lotação vigente, nome apresentável, mês e período do dia."""
    with database(db_path) as conn:
        frame = pd.read_sql_query(
            ENRICHED_RIDES_SQL,
            conn,
            params={"not_informed": NOT_INFORMED, "unmapped": UNMAPPED},
        )

    frame["user"] = [
        full_name(fn, ln).title() for fn, ln in zip(frame.first_name, frame.last_name, strict=True)
    ]
    frame["ride_date"] = pd.to_datetime(frame["ride_date"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    hours = pd.to_numeric(frame["request_hour"], errors="coerce")
    frame["request_hour"] = hours.where(hours.between(0, 23))

    frame = frame.dropna(subset=["ride_date", "amount"]).copy()
    frame["month_num"] = frame["ride_date"].dt.month
    frame["month"] = frame["month_num"].map(MONTHS_PT)
    frame["period"] = frame["request_hour"].map(classify_period)
    return frame.reset_index(drop=True)
