"""Funções puras de parsing e normalização usadas pelo ETL.

Os relatórios chegam com variações de acentuação nos cabeçalhos, valores no formato
brasileiro ("1.234,56") e horas em formatos diversos ("14:35", "2:35 PM", fração de dia
do Excel). Tudo isso é resolvido aqui, em funções pequenas e testáveis.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Iterable
from datetime import datetime, time
from typing import Any

import pandas as pd


def _is_na(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def clean_text(value: Any) -> str:
    """Texto limpo para armazenamento: sem NA, sem espaços nas pontas."""
    if _is_na(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def normalize_key(value: Any) -> str:
    """Chave de comparação: sem acentos, minúscula, espaços únicos."""
    if _is_na(value):
        return ""
    text = strip_accents(str(value)).strip().lower()
    return " ".join(text.split())


def full_name(first: Any, last: Any) -> str:
    parts = [clean_text(part) for part in (first, last)]
    return " ".join(part for part in parts if part)


def person_id(first: Any, last: Any) -> str:
    """Identificador estável de pessoa derivado do nome.

    O portal não exporta um ID de funcionário confiável (a coluna vem vazia na maioria
    das organizações), e a planilha de lotação é mantida por pessoas usando nome e
    sobrenome. Normalizar o nome é o que permite cruzar as duas fontes.
    """
    return normalize_key(full_name(first, last)).upper()


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str:
    """Encontra a coluna real do DataFrame ignorando acentos, caixa e espaços."""
    candidates = list(candidates)
    lookup = {normalize_key(column): column for column in df.columns}
    for candidate in candidates:
        key = normalize_key(candidate)
        if key in lookup:
            return lookup[key]
    raise KeyError(
        f"Coluna não encontrada. Procuradas={candidates} | Disponíveis={list(df.columns)}"
    )


def parse_brl(value: Any) -> float | None:
    """Converte "R$ 1.234,56", "23,45", 12.5 ou "12.5" em float. Inválido vira None."""
    if _is_na(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace("R$", "").replace(" ", "").replace(" ", "")
    if not text:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()-+")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def parse_hour(value: Any) -> int | None:
    """Extrai a hora (0-23) de time, datetime, fração de dia do Excel ou texto."""
    if _is_na(value) or isinstance(value, bool):
        return None
    if isinstance(value, (datetime, time)) or hasattr(value, "hour"):
        hour = int(value.hour)
        return hour if 0 <= hour <= 23 else None
    if isinstance(value, (int, float)):
        number = float(value)
        if 0 <= number < 1:  # fração de dia, como o Excel armazena horas
            return int(number * 24)
        if 0 <= number <= 23 and number.is_integer():
            return int(number)
        return None

    text = str(value).strip().upper().replace(" ", "").replace(".", "")
    if not text:
        return None
    for fmt in ("%I:%M%p", "%I:%M:%S%p", "%I%p", "%H:%M", "%H:%M:%S", "%H"):
        try:
            return datetime.strptime(text, fmt).hour
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    return None if pd.isna(parsed) else int(parsed.hour)


def parse_date(value: Any) -> pd.Timestamp | None:
    """Data sem hora. Aceita datetime, ISO ("2026-07-15") e brasileiro ("15/07/2026")."""
    if _is_na(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).normalize()
    text = str(value).strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce", format="ISO8601")
    if pd.isna(parsed):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.normalize()


def ride_fingerprint(fields: Iterable[Any]) -> str:
    """SHA-1 dos campos que identificam uma corrida.

    É a chave primária de ``rides`` e o que torna a carga idempotente: o mesmo
    relatório pode ser importado quantas vezes for preciso sem duplicar corridas.
    Endereços ficam de fora de propósito, porque o portal os reformata entre
    exportações e isso faria a mesma corrida entrar duas vezes.
    """
    parts: list[str] = []
    for field in fields:
        if _is_na(field):
            parts.append("")
        elif isinstance(field, float):
            parts.append(f"{field:.2f}")
        else:
            parts.append(str(field).strip())
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
