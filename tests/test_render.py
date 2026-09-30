from __future__ import annotations

import pandas as pd

from uber_reports.dashboard.render import build_dashboard


def test_build_dashboard_embeds_data_branding_and_escapes_scripts(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "cost_center": "Comercial",
                "user": "Ana Souza",
                "store": "Loja Sul",
                "month": "jul",
                "month_num": 7,
                "period": "Manhã",
                "request_hour": 8.0,
                "amount": 23.456,
                "ride_date": pd.Timestamp("2026-07-15"),
                "pickup_address": "</script><b>x</b>",
                "dropoff_address": None,
            }
        ]
    )
    output = build_dashboard(
        frame, tmp_path / "dash.html", title="Título X", subtitle="Sub", brand="Marca Y"
    )
    html = output.read_text(encoding="utf-8")

    assert "Título X" in html and "Marca Y" in html
    for token in ("__DATA_JSON__", "__STYLES__", "__SCRIPT__", "__TITLE__", "__LOGO__"):
        assert token not in html
    assert '"user": "Ana Souza"' in html
    assert '"request_hour": 8,' in html
    assert '"amount": 23.46,' in html
    assert '"dropoff_address": null' in html
    assert "<\\/script><b>x<\\/b>" in html
    assert "window.DASHBOARD_DATA = [" in html


def test_build_dashboard_with_custom_logo(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")
    output = build_dashboard(pd.DataFrame(), tmp_path / "dash.html", logo=logo)
    html = output.read_text(encoding="utf-8")
    assert 'src="data:image/png;base64,' in html
    assert "window.DASHBOARD_DATA = []" in html
