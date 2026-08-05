"""Fixtures e hooks globais de teste.

Desde a migracao MongoDB -> SQLite (ADR-002), os testes de repositorio rodam
contra ``sqlite3.connect(":memory:")`` embarcado — sem skip condicional, sem
dependencia de servico externo.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_db_singleton():
    """Garante isolamento: descarta o singleton de conexao sqlite entre testes."""
    from contract_parser.infrastructure import database

    database.reset_connection()
    yield
    database.reset_connection()
