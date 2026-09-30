"""Leitura dos relatórios exportados pelo Uber for Business.

O arquivo exportado (CSV ou XLSX) traz um bloco de metadados antes da tabela::

    Empresa:;NOME DA EMPRESA
    Administrador:;
    Data do relatório:;2026-08-03 18:01:06 +0000 UTC
    <linha em branco>
    Transações
    Nome;Sobrenome;ID do funcionário;Serviço;Cidade;...

Em vez de assumir um número fixo de linhas a pular, o cabeçalho é localizado pelo
conteúdo (a linha que contém "Nome" e "Sobrenome"). Isso resiste a mudanças no bloco
de metadados e funciona tanto com ``;`` quanto com ``,`` como separador.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from uber_reports.etl.parsing import (
    clean_text,
    find_column,
    normalize_key,
    parse_brl,
    parse_date,
    parse_hour,
    person_id,
    ride_fingerprint,
)

log = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = (".csv", ".xlsx", ".xls")
HEADER_MARKERS = ("nome", "sobrenome")
MAX_HEADER_SCAN = 30
DELIMITERS = (";", ",", "\t")

REPORT_COLUMNS: dict[str, tuple[str, ...]] = {
    "first_name": ("Nome", "First name"),
    "last_name": ("Sobrenome", "Last name"),
    "service": ("Serviço", "Servico", "Service"),
    "city": ("Cidade", "City"),
    "pickup_address": ("Endereço de partida", "Endereco de partida", "Pickup address"),
    "dropoff_address": ("Endereço de destino", "Endereco de destino", "Drop-off address"),
    "request_date": (
        "Data da solicitação (local)",
        "Data da solicitacao (local)",
        "Request date (local)",
    ),
    "request_time": (
        "Hora da solicitação (local)",
        "Hora da solicitacao (local)",
        "Request time (local)",
    ),
    "amount": ("Valor total: BRL", "Total amount: BRL", "Valor total"),
}
OPTIONAL_COLUMNS = frozenset({"service", "city", "pickup_address", "dropoff_address"})
INVALID_NAMES = frozenset({"", "-", "--", "nan", "none"})

RIDE_COLUMNS = [
    "ride_id",
    "employee_id",
    "first_name",
    "last_name",
    "ride_date",
    "request_hour",
    "amount",
    "service",
    "city",
    "pickup_address",
    "dropoff_address",
    "company",
]


@dataclass(frozen=True)
class ReportFile:
    """Um relatório lido do disco, ainda com as colunas originais do portal."""

    path: Path
    company: str | None
    generated_at: str | None
    header_row: int
    raw: pd.DataFrame


def _is_header(cells: Iterable[str]) -> bool:
    keys = {normalize_key(cell) for cell in cells}
    return all(marker in keys for marker in HEADER_MARKERS)


def _metadata(rows: Iterable[list[str]]) -> dict[str, str]:
    meta: dict[str, str] = {}
    for cells in rows:
        if len(cells) >= 2 and cells[0].strip().endswith(":"):
            meta[normalize_key(cells[0].rstrip(":"))] = cells[1].strip()
    return meta


def _read_csv_report(path: Path) -> ReportFile:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()

    header_row: int | None = None
    delimiter = ";"
    for index, line in enumerate(lines[:MAX_HEADER_SCAN]):
        for candidate in DELIMITERS:
            cells = next(csv.reader([line], delimiter=candidate), [])
            if len(cells) > 1 and _is_header(cells):
                header_row, delimiter = index, candidate
                break
        if header_row is not None:
            break
    if header_row is None:
        raise ValueError(
            f"Cabeçalho não encontrado nas {MAX_HEADER_SCAN} primeiras linhas de {path.name}"
        )

    meta_rows = [next(csv.reader([line], delimiter=delimiter), []) for line in lines[:header_row]]
    frame = pd.read_csv(
        io.StringIO("\n".join(lines[header_row:])),
        sep=delimiter,
        dtype=str,
        keep_default_na=False,
        engine="python",
    )
    frame.columns = [str(column).strip() for column in frame.columns]
    meta = _metadata(meta_rows)
    return ReportFile(
        path=path,
        company=meta.get("empresa") or None,
        generated_at=meta.get("data do relatorio") or None,
        header_row=header_row,
        raw=frame,
    )


def _read_excel_report(path: Path) -> ReportFile:
    probe = pd.read_excel(path, header=None, nrows=MAX_HEADER_SCAN, dtype=str).fillna("")
    header_row: int | None = None
    meta_rows: list[list[str]] = []
    for index in range(len(probe)):
        cells = [str(cell) for cell in probe.iloc[index].tolist()]
        if _is_header(cells):
            header_row = index
            break
        meta_rows.append(cells)
    if header_row is None:
        raise ValueError(
            f"Cabeçalho não encontrado nas {MAX_HEADER_SCAN} primeiras linhas de {path.name}"
        )

    frame = pd.read_excel(path, header=header_row, dtype=str).fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    meta = _metadata(meta_rows)
    return ReportFile(
        path=path,
        company=meta.get("empresa") or None,
        generated_at=meta.get("data do relatorio") or None,
        header_row=header_row,
        raw=frame,
    )


def read_report(path: Path) -> ReportFile:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_report(path)
    if suffix in (".xlsx", ".xls"):
        return _read_excel_report(path)
    raise ValueError(f"Formato não suportado: {path.name} (esperado {SUPPORTED_SUFFIXES})")


def normalize_rides(report: ReportFile) -> pd.DataFrame:
    """Converte as colunas do portal no esquema canônico de ``rides``."""
    raw = report.raw
    if raw.empty:
        return pd.DataFrame(columns=RIDE_COLUMNS)

    columns: dict[str, str | None] = {}
    for canonical, candidates in REPORT_COLUMNS.items():
        try:
            columns[canonical] = find_column(raw, candidates)
        except KeyError:
            if canonical not in OPTIONAL_COLUMNS:
                raise
            columns[canonical] = None

    def series(name: str) -> pd.Series:
        source = columns[name]
        if source is None:
            return pd.Series([""] * len(raw), index=raw.index, dtype=object)
        return raw[source]

    first = series("first_name").map(clean_text)
    last = series("last_name").map(clean_text)
    dates = [parse_date(value) for value in series("request_date")]
    raw_time = series("request_time").map(clean_text)

    out = pd.DataFrame(
        {
            "employee_id": pd.Series(
                [person_id(fn, ln) for fn, ln in zip(first, last, strict=True)], index=raw.index
            ),
            "first_name": first,
            "last_name": last,
            "ride_date": pd.Series(
                [d.strftime("%Y-%m-%d") if d is not None else None for d in dates],
                index=raw.index,
                dtype=object,
            ),
            "request_hour": raw_time.map(parse_hour),
            "amount": series("amount").map(parse_brl),
            "service": series("service").map(clean_text),
            "city": series("city").map(clean_text),
            "pickup_address": series("pickup_address").map(clean_text),
            "dropoff_address": series("dropoff_address").map(clean_text),
            "company": report.company or "",
            "raw_time": raw_time,
        }
    )

    valid = (
        ~out["first_name"].str.lower().isin(INVALID_NAMES)
        & out["ride_date"].notna()
        & out["amount"].notna()
    )
    dropped = int((~valid).sum())
    if dropped:
        log.debug("%s: %d linha(s) ignorada(s) sem nome, data ou valor", report.path.name, dropped)
    out = out[valid].copy()

    out["ride_id"] = [
        ride_fingerprint(
            [
                row.employee_id,
                row.first_name,
                row.last_name,
                row.ride_date,
                row.raw_time,
                float(row.amount),
                row.service,
                row.city,
            ]
        )
        for row in out.itertuples(index=False)
    ]
    return out[RIDE_COLUMNS].reset_index(drop=True)


def find_report_files(directory: Path) -> list[Path]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in SUPPORTED_SUFFIXES and not path.name.startswith("~$")
    )


def load_reports(paths: Iterable[Path]) -> pd.DataFrame:
    """Lê vários relatórios e devolve um único DataFrame sem corridas repetidas."""
    frames: list[pd.DataFrame] = []
    for path in paths:
        report = read_report(path)
        rides = normalize_rides(report)
        rides["source_file"] = path.name
        log.info(
            "%s: %d corrida(s) [%s]",
            path.name,
            len(rides),
            report.company or "empresa não identificada",
        )
        frames.append(rides)

    if not frames:
        return pd.DataFrame(columns=RIDE_COLUMNS + ["source_file"])
    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset="ride_id", keep="last").reset_index(drop=True)
