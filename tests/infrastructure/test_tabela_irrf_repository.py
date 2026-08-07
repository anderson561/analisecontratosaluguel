"""Testes do ``TabelaIRRFRepository`` contra ``sqlite3.connect(":memory:")`` real.

Desde a migração MongoDB -> SQLite (ADR-002), estes testes não exigem nenhum
serviço externo. Preserva o cenário do CA-03 (tabela 2026 oficial persistida e
recuperada, base R$ 5.000,00 PF->PJ com desconto simplificado ADR-004 +
redutor Lei nº 15.270/2025 -> imposto final R$ 0,00) agora contra SQLite real.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from contract_parser.domain.contrato import TipoParte
from contract_parser.domain.irrf import Faixa, TabelaIRRF, calcular_irrf, tabela_irrf_2026
from contract_parser.infrastructure.database import init_schema
from contract_parser.infrastructure.tabela_irrf_repository import TabelaIRRFRepository


def _conexao() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


@pytest.fixture
def repo():
    conn = _conexao()
    try:
        yield TabelaIRRFRepository(conn=conn)
    finally:
        conn.close()


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


def test_upsert_atualiza_campos_em_conflito(repo):
    repo.upsert(_tabela("2026"))
    atualizada = tabela_irrf_2026()
    repo.upsert(atualizada)
    obtida = repo.get_por_vigencia("2026")
    assert obtida.faixas[-1].deducao == Decimal("908.73")
    assert obtida.validado is True


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


def test_documento_serializa_decimal_como_texto(repo):
    """Decimal deve virar str na linha persistida (round-trip determinístico)."""
    repo.upsert(tabela_irrf_2026())
    cur = repo._conn.execute(
        "SELECT faixas FROM tabela_irrf WHERE vigencia = ?", ("2026",)
    )
    import json

    faixas = json.loads(cur.fetchone()["faixas"])
    assert faixas[-1]["deducao"] == "908.73"  # string, não float


# --------------------------------------------------------------------------- #
# CA-03 — tabela IRRF 2026 oficial persistida/recuperada em SQLite real
# --------------------------------------------------------------------------- #
def test_ca03_tabela_2026_persistida_e_recuperada_em_sqlite_real():
    """Persiste a tabela oficial 2026 em SQLite real (em memória), recupera via
    ``get_vigente`` e confirma o cálculo do CA-03: base R$ 5.000,00, locador PF
    -> locatário PJ, desconto simplificado de R$607,20 (ADR-004) leva à base
    tributável R$4.392,80 -> tabela padrão R$312,89 reduzida a R$ 0,00 pelo
    redutor da Lei nº 15.270/2025 (ADR-003), sobre o rendimento bruto de
    R$5.000,00 — aplica a fórmula sobre a tabela efetivamente lida do banco,
    não sobre a factory em memória)."""
    conn = _conexao()
    try:
        repo = TabelaIRRFRepository(conn=conn)
        repo.upsert(tabela_irrf_2026())

        tabela_persistida = repo.get_vigente()
        assert tabela_persistida is not None
        assert tabela_persistida.vigencia == "2026"

        resultado = calcular_irrf(
            base_mensal=Decimal("5000.00"),
            tipo_locador=TipoParte.PF,
            tabela=tabela_persistida,
        )

        assert resultado.retido is False
        assert resultado.imposto_antes_reducao == Decimal("312.89")
        assert resultado.imposto == Decimal("0.00")
    finally:
        conn.close()
