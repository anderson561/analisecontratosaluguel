"""Testes do ``EmpresaRepository`` com coleção pymongo mockada (FakeCollection).

Não exigem MongoDB vivo. Um teste de integração real fica marcado com
``@pytest.mark.integration`` (skip automático se o Mongo não responder).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pymongo import UpdateOne

from contract_parser.domain.empresa import Empresa
from contract_parser.infrastructure.empresa_repository import (
    COLLECTION_NAME,
    EmpresaJaExisteError,
    EmpresaRepository,
)
from tests.support.fakes import FakeCollection


@pytest.fixture
def repo() -> EmpresaRepository:
    return EmpresaRepository(collection=FakeCollection())


def _empresa(cnpj: str = "11222333000181", razao: str = "Alpha LTDA") -> Empresa:
    return Empresa(cnpj=cnpj, razao_social=razao)


def test_add_e_get_by_cnpj(repo):
    repo.add(_empresa())
    obtido = repo.get_by_cnpj("11.222.333/0001-81")
    assert obtido is not None
    assert obtido.cnpj == "11222333000181"
    assert obtido.razao_social == "Alpha LTDA"


def test_get_by_cnpj_ausente_retorna_none(repo):
    assert repo.get_by_cnpj("11222333000181") is None


def test_add_duplicado_levanta_erro_de_dominio(repo):
    repo.add(_empresa())
    with pytest.raises(EmpresaJaExisteError):
        repo.add(_empresa())


def test_list_all(repo):
    repo.add(_empresa("11222333000181", "Alpha"))
    repo.add(_empresa("45566778000109", "Beta"))
    cnpjs = {e.cnpj for e in repo.list_all()}
    assert cnpjs == {"11222333000181", "45566778000109"}


def test_update(repo):
    repo.add(_empresa(razao="Alpha"))
    atualizado = _empresa(razao="Alpha Nova")
    repo.update(atualizado)
    assert repo.get_by_cnpj("11222333000181").razao_social == "Alpha Nova"


def test_remove(repo):
    repo.add(_empresa())
    assert repo.remove("11.222.333/0001-81") is True
    assert repo.remove("11222333000181") is False


def test_upsert_many_idempotente(repo):
    lote = [_empresa("11222333000181", "Alpha"), _empresa("45566778000109", "Beta")]
    assert repo.upsert_many(lote) == 2
    repo.upsert_many(lote)  # reexecução não duplica
    assert len(repo.list_all()) == 2


def test_upsert_many_lista_vazia(repo):
    assert repo.upsert_many([]) == 0


def test_upsert_many_constroi_updateone_com_upsert():
    """Verifica a interação com pymongo: bulk_write recebe UpdateOne(upsert=True)."""
    collection = MagicMock()
    repo = EmpresaRepository(collection=collection)

    repo.upsert_many([_empresa("11222333000181", "Alpha")])

    collection.bulk_write.assert_called_once()
    ops, kwargs = collection.bulk_write.call_args
    operacoes = ops[0]
    assert len(operacoes) == 1
    assert isinstance(operacoes[0], UpdateOne)
    assert operacoes[0]._filter == {"_id": "11222333000181"}
    assert operacoes[0]._upsert is True
    assert kwargs.get("ordered") is False


def test_add_usa_document_com_id():
    collection = MagicMock()
    repo = EmpresaRepository(collection=collection)
    repo.add(_empresa())
    doc = collection.insert_one.call_args[0][0]
    assert doc["_id"] == "11222333000181"


@pytest.mark.integration
def test_repositorio_real_roundtrip(require_mongo):
    """Integração: CRUD real contra o MongoDB (skip se indisponível)."""
    from contract_parser.config import settings
    from contract_parser.infrastructure.database import get_client

    client = get_client()
    collection = client[settings.mongo_db][f"{COLLECTION_NAME}_it_test"]
    collection.delete_many({})
    try:
        repo = EmpresaRepository(collection=collection)
        repo.add(_empresa())
        assert repo.get_by_cnpj("11222333000181") is not None
        repo.upsert_many([_empresa("45566778000109", "Beta")])
        assert len(repo.list_all()) == 2
    finally:
        collection.drop()
