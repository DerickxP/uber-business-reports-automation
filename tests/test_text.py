from __future__ import annotations

from uber_reports.automation.text import normalize_date_range, normalize_text, slugify


def test_normalize_text_removes_accents_and_collapses_spaces():
    assert normalize_text("  Relatórios   e informações ") == "RELATORIOS E INFORMACOES"
    assert normalize_text(None) == ""


def test_slugify_is_filename_safe():
    assert slugify("Empresa Exemplo Ltda.") == "EMPRESA_EXEMPLO_LTDA"


def test_normalize_date_range_handles_dashes_and_mojibake():
    assert normalize_date_range("2026/01/01 – 2026/01/31") == "2026/01/01 - 2026/01/31"
    assert normalize_date_range("2026/01/01 â€“ 2026/01/31") == "2026/01/01 - 2026/01/31"
