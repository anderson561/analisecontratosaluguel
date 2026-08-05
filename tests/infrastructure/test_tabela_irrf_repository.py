"""Testes do ``TabelaIRRFRepository`` com coleção pymongo mockada (FakeCollection).

Não exigem MongoDB vivo. Um teste de integração real fica marcado com
``@pytest.mark.integration`` (skip automático se o Mongo não responder).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from contract_parser.domain.irrf import Faixa, TabelaIRRF, tabela_irrf_2026
from contract_parser.infrastructure.tabela_irrf_repository import (
    COLLECTION_NAME,
    TabelaIRRFRepository,
)
from tests.support.fakes import FakeCollection


@pytest.fixture
def repo() -> TabelaIRRFRepository:
    return TabelaIRRFRepository(collection=FakeCollection())


def _tabela(vigencia: str) -> TabelaIRRF:
    return TabelaIRRF(
        vigencia=vigencia,
        fonte_url="http://x",
        base_legal="teste",
        faixas=[
            Faixa(minimo=Decimal(0), maximo=None, aliquota=Decimal(0), deducao=Decimal(0)),
        ],
    )


def test_upsert_e_get_por_vigencia(repo):
    repo.upsert(tabela_irrf_2026())
    obtida = repo.get_por_vigencia("2026")
    assert obtida is not None
    assert obtida.vigencia == "2026"
    assert obtida.validado is True
    assert obtida.validado_em == date(2026, 1, 1)
    # Round-trip preserva Decimal exatamente (via serialização JSON).
    assert obtida.faixas[-1].aliquota == Decimal("0.275")
    assert obtida.faixas[-1].deducao == Decimal("908.73")


def test_get_por_vigencia_ausente_retorna_none(repo):
    assert repo.get_por_vigencia("1999") is None


def test_upsert_idempotente(repo):
    repo.upsert(tabela_irrf_2026())
    repo.upsert(tabela_irrf_2026())  # reexecução não duplica
    assert len(repo.list_all()) == 1


def test_get_vigente_retorna_mais_recente(repo):
    repo.upsert(_tabela("2024"))
    repo.upsert(_tabela("2026"))
    repo.upsert(_tabela("2025"))
    vigente = repo.get_vigente()
    assert vigente is not None
    assert vigente.vigencia == "2026"


def test_get_vigente_colecao_vazia_retorna_none(repo):
    assert repo.get_vigente() is None


def test_list_all_ordenada(repo):
    repo.upsert(_tabela("2026"))
    repo.upsert(_tabela("2024"))
    assert [t.vigencia for t in repo.list_all()] == ["2024", "2026"]


def test_upsert_usa_replace_one_com_id_e_upsert():
    """Verifica a interação com pymongo: replace_one por _id, upsert=True."""
    collection = MagicMock()
    repo = TabelaIRRFRepository(collection=collection)

    repo.upsert(tabela_irrf_2026())

    collection.replace_one.assert_called_once()
    args, kwargs = collection.replace_one.call_args
    assert args[0] == {"_id": "2026"}
    doc = args[1]
    assert doc["_id"] == "2026"
    assert kwargs.get("upsert") is True


def test_documento_serializa_decimal_como_texto():
    """Decimal deve virar str no documento (evita Decimal128/float no BSON)."""
    collection = MagicMock()
    repo = TabelaIRRFRepository(collection=collection)
    repo.upsert(tabela_irrf_2026())
    doc = collection.replace_one.call_args[0][1]
    assert doc["faixas"][-1]["deducao"] == "908.73"  # string, não float


@pytest.mark.integration
def test_repositorio_real_roundtrip(require_mongo):
    """Integração: upsert/get real contra o MongoDB (skip se indisponível)."""
    from contract_parser.config import settings
    from contract_parser.infrastructure.database import get_client

    client = get_client()
    collection = client[settings.mongo_db][f"{COLLECTION_NAME}_it_test"]
    collection.delete_many({})
    try:
        repo = TabelaIRRFRepository(collection=collection)
        repo.upsert(tabela_irrf_2026())
        obtida = repo.get_vigente()
        assert obtida is not None
        assert obtida.vigencia == "2026"
        assert obtida.faixas[-1].deducao == Decimal("908.73")
    finally:
        collection.drop()
