"""Smoke test do módulo de view CustomTkinter.

Só roda se ``customtkinter`` estiver instalado (``importorskip``). NÃO instancia
janela (headless não tem display): apenas garante que o módulo importa e expõe a
classe ``MainWindow`` — a lógica real é testada nos controllers headless.
"""
from __future__ import annotations

import pytest


def test_view_importavel_e_expoe_main_window():
    pytest.importorskip("customtkinter")
    from contract_parser.presentation.views import main_window

    assert hasattr(main_window, "MainWindow")


def test_entrypoint_app_importavel_sem_abrir_janela():
    # ``app`` NÃO deve importar customtkinter no topo (import lazy em main()).
    from contract_parser.presentation import app

    assert callable(app.main)
    assert callable(app.build_controller)
