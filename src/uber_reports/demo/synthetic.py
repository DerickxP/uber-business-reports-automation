"""Gerador de dados sintéticos.

Produz relatórios no mesmo layout exportado pelo Uber for Business e uma planilha de
mapeamento de lotação, para que o pipeline inteiro (ingest -> load-mapping -> dashboard)
possa ser executado e testado sem acesso a nenhum portal e sem nenhum dado real.
Nomes, lojas e endereços são fictícios. O gerador também sabe a "verdade" (em qual
loja cada pessoa estava em cada data), o que permite testar o join temporal.
"""

from __future__ import annotations

import csv
import random
from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from uber_reports.automation.text import slugify

DEFAULT_COMPANIES = ("EMPRESA EXEMPLO ATACADO LTDA", "EMPRESA EXEMPLO VAREJO LTDA")

FIRST_NAMES = (
    "Ana",
    "Bruno",
    "Carla",
    "Daniel",
    "Eduarda",
    "Felipe",
    "Gabriela",
    "Henrique",
    "Isabela",
    "João",
    "Karina",
    "Lucas",
    "Mariana",
    "Nicolas",
    "Olívia",
    "Paulo",
    "Rafaela",
    "Samuel",
    "Tatiana",
    "Vinícius",
    "Yasmin",
    "Caio",
    "Letícia",
    "Marcos",
    "Natália",
    "Otávio",
    "Priscila",
    "Rodrigo",
    "Sofia",
    "Thiago",
)
LAST_NAMES = (
    "Almeida",
    "Andrade",
    "Cardoso",
    "Dias",
    "Esteves",
    "Ferreira",
    "Gomes",
    "Lopes",
    "Machado",
    "Jesus",
    "Lima",
    "Martins",
    "Nascimento",
    "Oliveira",
    "Pereira",
    "Queiroz",
    "Ribeiro",
    "Santos",
    "Teixeira",
    "Vieira",
    "Xavier",
    "Azevedo",
    "Batista",
    "Castro",
    "Duarte",
    "Fonseca",
    "Guimarães",
    "Moraes",
    "Nunes",
    "Rocha",
)
STORES = {
    "Loja Centro": "Comercial",
    "Loja Norte": "Comercial",
    "Loja Sul": "Comercial",
    "Loja Shopping": "Comercial",
    "Centro de Distribuição": "Logística",
    "Escritório Central": "Administrativo",
}
CITIES = ("São Paulo", "Campinas", "Santos")
SERVICES = (("UberX", 70, 1.0), ("Comfort", 20, 1.35), ("Black", 10, 1.9))
STREETS = (
    "Rua das Flores",
    "Avenida Brasil",
    "Rua XV de Novembro",
    "Avenida Paulista",
    "Rua da Consolação",
    "Avenida Industrial",
    "Rua do Comércio",
    "Alameda dos Ipês",
)
NEIGHBORHOODS = ("Centro", "Jardins", "Vila Nova", "Bela Vista", "Distrito Industrial")
# Picos de manhã e fim de tarde, madrugada quase vazia.
HOUR_WEIGHTS = (1, 1, 1, 1, 2, 4, 10, 16, 14, 8, 6, 7, 9, 7, 6, 7, 10, 16, 14, 9, 6, 4, 3, 2)
REPORT_HEADER = (
    "Nome",
    "Sobrenome",
    "ID do funcionário",
    "Serviço",
    "Cidade",
    "Endereço de partida",
    "Endereço de destino",
    "Data da solicitação (local)",
    "Hora da solicitação (local)",
    "Várias paradas",
    "Valor total: BRL",
    "Nome do convidado",
    "Sobrenome do convidado",
)
MOVER_SHARE = 0.2
HISTORY_START_OFFSET_DAYS = 365


@dataclass(frozen=True)
class Employee:
    first_name: str
    last_name: str
    company: str
    store: str
    weight: float
    moved_on: date | None = None
    new_store: str | None = None

    def store_at(self, day: date) -> str:
        """Loja em que a pessoa estava lotada em ``day`` (a verdade do gerador)."""
        if self.moved_on and self.new_store and day >= self.moved_on:
            return self.new_store
        return self.store

    @property
    def current_store(self) -> str:
        return self.new_store or self.store


@dataclass(frozen=True)
class DemoDataset:
    reports_dir: Path
    reports: tuple[Path, ...]
    mapping_workbook: Path
    staff: tuple[Employee, ...]
    rides: int
    range_start: date
    range_end: date

    @property
    def employees(self) -> int:
        return len(self.staff)


def _month_starts(months: int, anchor: date) -> list[date]:
    """Os ``months`` meses completos anteriores ao mês de ``anchor``, em ordem."""
    first = anchor.replace(day=1)
    starts: list[date] = []
    for _ in range(months):
        first = (first - timedelta(days=1)).replace(day=1)
        starts.append(first)
    return sorted(starts)


def _month_end(day: date) -> date:
    return day.replace(day=monthrange(day.year, day.month)[1])


def _next_month(day: date) -> date:
    return _month_end(day) + timedelta(days=1)


def _build_staff(
    rng: random.Random,
    count: int,
    companies: Sequence[str],
    range_start: date,
    range_end: date,
) -> list[Employee]:
    combos = [(first, last) for first in FIRST_NAMES for last in LAST_NAMES]
    chosen = rng.sample(combos, min(count, len(combos)))
    stores = list(STORES)
    span = (range_end - range_start).days
    staff: list[Employee] = []
    for index, (first, last) in enumerate(chosen):
        store = rng.choice(stores)
        moved_on = new_store = None
        if span > 60 and rng.random() < MOVER_SHARE:
            moved_on = range_start + timedelta(days=rng.randint(30, span - 30))
            new_store = rng.choice([other for other in stores if other != store])
        staff.append(
            Employee(
                first_name=first,
                last_name=last,
                company=companies[index % len(companies)],
                store=store,
                weight=rng.lognormvariate(0, 0.8),
                moved_on=moved_on,
                new_store=new_store,
            )
        )
    return staff


def _address(rng: random.Random) -> str:
    return f"{rng.choice(STREETS)}, {rng.randint(10, 2500)} - {rng.choice(NEIGHBORHOODS)}"


def _month_rides(
    rng: random.Random, staff: Sequence[Employee], month_start: date, count: int
) -> list[list[str]]:
    if not staff or count <= 0:
        return []
    weights = [employee.weight for employee in staff]
    days_in_month = monthrange(month_start.year, month_start.month)[1]
    service_names = [name for name, _, _ in SERVICES]
    service_weights = [weight for _, weight, _ in SERVICES]
    multipliers = {name: multiplier for name, _, multiplier in SERVICES}

    rows: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for _ in range(count):
        employee = rng.choices(staff, weights=weights)[0]
        day = month_start.replace(day=rng.randint(1, days_in_month))
        hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
        minute = rng.randint(0, 59)
        service = rng.choices(service_names, weights=service_weights)[0]
        amount = min(max(rng.lognormvariate(2.95, 0.45) * multipliers[service], 6.0), 180.0)
        city = rng.choice(CITIES)
        has_address = rng.random() > 0.05
        key = (employee.first_name, employee.last_name, day.isoformat(), f"{hour:02d}:{minute:02d}")
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            [
                employee.first_name,
                employee.last_name,
                "",
                service,
                city,
                _address(rng) if has_address else "",
                _address(rng) if has_address else "",
                day.isoformat(),
                f"{hour:02d}:{minute:02d}",
                "Não",
                f"{amount:.2f}".replace(".", ","),
                "",
                "",
            ]
        )
    rows.sort(key=lambda row: (row[7], row[8]))
    return rows


def _write_report(path: Path, company: str, rows: list[list[str]], generated: date) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Empresa:", company])
        writer.writerow(["Administrador:", ""])
        writer.writerow(["Data do relatório:", f"{generated.isoformat()} 06:00:00 +0000 UTC"])
        writer.writerow([])
        writer.writerow(["Transações"])
        writer.writerow(REPORT_HEADER)
        writer.writerows(rows)


def _write_mapping_workbook(path: Path, staff: Sequence[Employee], range_start: date) -> None:
    history_start = range_start - timedelta(days=HISTORY_START_OFFSET_DAYS)
    employees_rows = [
        {
            "Nome": employee.first_name,
            "Sobrenome": employee.last_name,
            "Centro de Custo": STORES[employee.current_store],
            "Setor/Loja": employee.current_store,
        }
        for employee in staff
    ]
    history_rows: list[dict[str, object]] = []
    for employee in staff:
        base = {"Nome": employee.first_name, "Sobrenome": employee.last_name}
        if employee.moved_on and employee.new_store:
            history_rows.append(
                {
                    **base,
                    "Centro de Custo": STORES[employee.store],
                    "Setor/Loja": employee.store,
                    "Data Inicio": history_start,
                    "Data Fim": employee.moved_on - timedelta(days=1),
                }
            )
            history_rows.append(
                {
                    **base,
                    "Centro de Custo": STORES[employee.new_store],
                    "Setor/Loja": employee.new_store,
                    "Data Inicio": employee.moved_on,
                    "Data Fim": None,
                }
            )
        else:
            history_rows.append(
                {
                    **base,
                    "Centro de Custo": STORES[employee.store],
                    "Setor/Loja": employee.store,
                    "Data Inicio": history_start,
                    "Data Fim": None,
                }
            )

    history_columns = [
        "Nome",
        "Sobrenome",
        "Centro de Custo",
        "Setor/Loja",
        "Data Inicio",
        "Data Fim",
    ]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(employees_rows).to_excel(writer, sheet_name="Funcionarios", index=False)
        pd.DataFrame(history_rows, columns=history_columns).to_excel(
            writer, sheet_name="HistoricoUsuarios", index=False
        )


def generate_demo_dataset(
    reports_dir: Path,
    mapping_workbook: Path,
    *,
    seed: int = 42,
    months: int = 6,
    employees: int = 40,
    rides_per_month: int = 300,
    companies: Sequence[str] = DEFAULT_COMPANIES,
    anchor: date | None = None,
) -> DemoDataset:
    """Gera relatórios mensais por empresa e a planilha de lotação correspondente.

    ``rides_per_month`` é o total aproximado do mês somando todas as empresas (o volume
    varia entre meses). ``anchor`` fixa o "hoje" do gerador (útil em testes); os meses
    gerados são os anteriores a ele.
    """
    rng = random.Random(seed)
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    mapping_workbook = Path(mapping_workbook)
    mapping_workbook.parent.mkdir(parents=True, exist_ok=True)

    month_starts = _month_starts(max(months, 1), anchor or date.today())
    range_start, range_end = month_starts[0], _month_end(month_starts[-1])
    staff = _build_staff(rng, employees, companies, range_start, range_end)
    per_company = max(rides_per_month // len(companies), 1)

    reports: list[Path] = []
    total = 0
    for company in companies:
        company_staff = [employee for employee in staff if employee.company == company]
        for month_start in month_starts:
            # Volume varia entre meses para o comparativo mensal do dashboard ter sentido.
            count = max(int(per_company * rng.uniform(0.8, 1.25)), 1)
            rows = _month_rides(rng, company_staff, month_start, count)
            generated = _next_month(month_start)
            path = reports_dir / f"uber_report_{slugify(company)}_{generated.isoformat()}.csv"
            _write_report(path, company, rows, generated)
            reports.append(path)
            total += len(rows)

    _write_mapping_workbook(mapping_workbook, staff, range_start)
    return DemoDataset(
        reports_dir=reports_dir,
        reports=tuple(reports),
        mapping_workbook=mapping_workbook,
        staff=tuple(staff),
        rides=total,
        range_start=range_start,
        range_end=range_end,
    )
