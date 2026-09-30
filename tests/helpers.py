"""Utilitários compartilhados pelos testes."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

REPORT_HEADER = [
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
]

RIDE_ROW = [
    "Ana",
    "Souza",
    "",
    "UberX",
    "São Paulo",
    "Rua A, 1",
    "Rua B, 2",
    "2026-07-15",
    "08:12",
    "Não",
    "23,45",
    "",
    "",
]


def write_report(path: Path, company: str, rows: list[list[str]], delimiter: str = ";") -> Path:
    """Escreve um CSV no layout exportado pelo portal (metadados + tabela)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(["Empresa:", company])
        writer.writerow(["Administrador:", ""])
        writer.writerow(["Data do relatório:", "2026-08-03 18:01:06 +0000 UTC"])
        writer.writerow([])
        writer.writerow(["Transações"])
        writer.writerow(REPORT_HEADER)
        writer.writerows(rows)
    return path


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path
