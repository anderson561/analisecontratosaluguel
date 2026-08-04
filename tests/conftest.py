"""Fixtures e hooks globais de teste.

Skip automatico dos testes marcados com ``@pytest.mark.integration`` quando o
MongoDB real nao estiver acessivel (ambiente sem servico de pe).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_mongo_singleton():
    """Garante isolamento: descarta o singleton de MongoClient entre testes."""
    from contract_parser.infrastructure import database

    database.reset_client()
    yield
    database.reset_client()


@pytest.fixture
def require_mongo():
    """Skip do teste de integracao se o MongoDB real nao responder ao ping."""
    from contract_parser.infrastructure.database import check_health

    health = check_health()
    if not health.ok:
        pytest.skip(f"MongoDB indisponivel para teste de integracao: {health.detalhe}")
    return health
