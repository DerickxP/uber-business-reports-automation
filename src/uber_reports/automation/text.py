"""Normalização de texto lido de páginas web.

O portal alterna idioma (pt-BR/en) e acentuação nos rótulos, e às vezes entrega texto
com codificação quebrada. Comparar tudo sem acentos e em caixa alta é o que mantém os
seletores estáveis.
"""

from __future__ import annotations

import unicodedata


def normalize_text(text: str | None) -> str:
    """Sem acentos, caixa alta, espaços únicos."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.upper().split())


def slugify(text: str | None) -> str:
    """Nome seguro para arquivo: ``EMPRESA EXEMPLO LTDA`` -> ``EMPRESA_EXEMPLO_LTDA``."""
    base = normalize_text(text).replace(" ", "_")
    return "".join(char for char in base if char.isalnum() or char == "_")


def normalize_date_range(text: str | None) -> str:
    """Iguala travessões, meias-riscas e mojibake ao hífen simples usado na digitação."""
    return (
        (text or "")
        .replace("–", "-")
        .replace("—", "-")
        .replace("â€“", "-")
        .replace("â€”", "-")
        .replace("  ", " ")
        .strip()
    )
