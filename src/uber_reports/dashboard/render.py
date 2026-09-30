"""Geração do dashboard: um único arquivo HTML, sem servidor e sem bibliotecas externas.

Os dados entram embutidos como JSON e toda a interação (filtros cruzados, gráficos SVG,
heatmap, tabelas) roda no navegador. O arquivo pode ser enviado por e-mail ou aberto de
um compartilhamento de rede sem nenhuma infraestrutura.
"""

from __future__ import annotations

import base64
import html
import json
import math
import mimetypes
from pathlib import Path
from typing import Any

import pandas as pd

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
DATA_FIELDS = [
    "cost_center",
    "user",
    "store",
    "month",
    "month_num",
    "period",
    "request_hour",
    "amount",
    "ride_date",
    "pickup_address",
    "dropoff_address",
]

DEFAULT_LOGO_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="6" cy="19" r="2.5"/><circle cx="18" cy="5" r="2.5"/>'
    '<path d="M8.2 17.5 15.8 6.5"/><path d="M6 16.5V11a3 3 0 0 1 3-3h1"/></svg>'
)


def _native(value: Any) -> Any:
    """Converte valores numpy/pandas em tipos nativos e NaN em None (JSON válido)."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def records_from_frame(rides: pd.DataFrame) -> list[dict[str, Any]]:
    frame = rides.copy()
    for column in DATA_FIELDS:
        if column not in frame.columns:
            frame[column] = None
    frame["ride_date"] = pd.to_datetime(frame["ride_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["request_hour"] = frame["request_hour"].map(lambda v: None if pd.isna(v) else int(v))
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").round(2)
    return [
        {key: _native(value) for key, value in row.items()}
        for row in frame[DATA_FIELDS].to_dict(orient="records")
    ]


def _logo_html(logo: Path | None) -> str:
    if logo and Path(logo).exists():
        mime = mimetypes.guess_type(str(logo))[0] or "image/png"
        encoded = base64.b64encode(Path(logo).read_bytes()).decode("ascii")
        return f'<img src="data:{mime};base64,{encoded}" alt="logo">'
    return DEFAULT_LOGO_SVG


def render_html(
    records: list[dict[str, Any]],
    *,
    title: str,
    subtitle: str,
    brand: str,
    logo: Path | None = None,
) -> str:
    template = (ASSETS_DIR / "template.html").read_text(encoding="utf-8")
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    # "</" escapado impede que um endereço contendo "</script>" encerre o bloco de dados.
    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")

    page = (
        template.replace("__TITLE__", html.escape(title))
        .replace("__SUBTITLE__", html.escape(subtitle))
        .replace("__BRAND__", html.escape(brand))
        .replace("__LOGO__", _logo_html(logo))
        .replace("__STYLES__", styles)
        .replace("__SCRIPT__", script)
    )
    return page.replace("__DATA_JSON__", data_json)


def build_dashboard(
    rides: pd.DataFrame,
    output: Path,
    *,
    title: str = "Uber Corporativo",
    subtitle: str = "Dashboard de corridas",
    brand: str = "Demo",
    logo: Path | None = None,
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    page = render_html(
        records_from_frame(rides), title=title, subtitle=subtitle, brand=brand, logo=logo
    )
    output.write_text(page, encoding="utf-8")
    return output
