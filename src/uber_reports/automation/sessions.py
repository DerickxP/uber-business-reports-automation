"""Captura de sessão de login para reutilização pelo robô.

Em vez de automatizar login e senha (frágil, sujeito a 2FA e a bloqueios), o usuário
faz login uma única vez em um navegador controlado e o estado (cookies e storage) é
salvo em um JSON local. Esse arquivo é ignorado pelo git e deve ser tratado como
credencial.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def save_session(url: str, output: Path, *, label: str) -> Path:
    """Abre ``url`` em um navegador visível, espera o login manual e grava a sessão."""
    from playwright.sync_api import sync_playwright

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"  Salvando sessão: {label}")
    print("=" * 60)
    print("O navegador vai abrir. Faça o login normalmente.")
    print("Quando a página inicial (ou a caixa de entrada) aparecer, volte aqui e pressione ENTER.")
    print()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        input("Pressione ENTER quando estiver logado... ")
        context.storage_state(path=str(output))
        context.close()
        browser.close()

    log.info("Sessão salva em %s", output)
    return output
