"""Testes do ``EmpresaRepository`` contra ``sqlite3.connect(":memory:")`` real.

Desde a migração MongoDB -> SQLite (ADR-002), estes testes não exigem nenhum
serviço externo: SQLite é embarcado na stdlib, sempre disponível.
"""
from __future__ import annotations

import sqlite3

import pytest

from contract_parser.domain.empresa import Empresa
from contract_parser.infrastructure.database import init_schema
from contract_parser.infrastructure.empresa_repository import (
    TABLE_NAME,
    EmpresaJaExisteError,
    EmpresaRepository,
)
from tests.support.fixture_builders import cnpj_valido_sequencial


def _conexao() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


@pytest.fixture
def repo():
    conn = _conexao()
    try:
        yield EmpresaRepository(conn=conn)
    finally:
        conn.close()


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


def test_update_nao_recria_created_at(repo):
    original = repo.add(_empresa(razao="Alpha"))
    repo.update(_empresa(razao="Alpha Nova"))
    obtido = repo.get_by_cnpj("11222333000181")
    assert obtido.created_at == original.created_at


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


def test_upsert_many_atualiza_campos_em_conflito(repo):
    repo.upsert_many([_empresa("11222333000181", "Alpha")])
    repo.upsert_many([_empresa("11222333000181", "Alpha Renomeada")])
    obtido = repo.get_by_cnpj("11222333000181")
    assert obtido.razao_social == "Alpha Renomeada"
    assert len(repo.list_all()) == 1


def test_aliases_e_nomes_fantasia_roundtrip_via_json(repo):
    empresa = Empresa(
        cnpj="11222333000181",
        razao_social="Alpha LTDA",
        aliases=["Alpha", "Alpha Comercio"],
        nomes_fantasia=["AlphaCorp"],
    )
    repo.add(empresa)
    obtido = repo.get_by_cnpj("11222333000181")
    assert obtido.aliases == ["Alpha", "Alpha Comercio"]
    assert obtido.nomes_fantasia == ["AlphaCorp"]


def test_add_persiste_linha_na_tabela_empresas(repo):
    repo.add(_empresa())
    cur = repo._conn.execute(f"SELECT cnpj FROM {TABLE_NAME} WHERE cnpj = ?", ("11222333000181",))
    assert cur.fetchone() is not None


# --------------------------------------------------------------------------- #
# CA-01 (equivalente de infraestrutura) — 50 empresas persistidas em SQLite real
# --------------------------------------------------------------------------- #
def test_ca01_50_empresas_persistidas_e_listadas_em_sqlite_real():
    """Prova, contra SQLite real (em memória), que o repositório sustenta 50
    empresas — mesmo cenário de volumetria do CA-01 (antes só validado com o
    importador contra um fake in-memory; agora contra a implementação real de
    infraestrutura pós-migração MongoDB -> SQLite, ADR-002)."""
    conn = _conexao()
    repo = EmpresaRepository(conn=conn)
    lote = [
        Empresa(
            cnpj=cnpj_valido_sequencial(i + 1),
            razao_social=f"Empresa Exemplo {i + 1:02d} LTDA",
        )
        for i in range(50)
    ]

    try:
        processados = repo.upsert_many(lote)

        assert processados == 50
        todas = repo.list_all()
        assert len(todas) == 50
        assert {e.cnpj for e in todas} == {e.cnpj for e in lote}

        # Reimportação idempotente: não duplica (mesma garantia exigida pelo CA-01).
        repo.upsert_many(lote)
        assert len(repo.list_all()) == 50
    finally:
        conn.close()
