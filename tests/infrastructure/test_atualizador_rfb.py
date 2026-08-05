"""Testes do revalidador da tabela IRRF contra a RFB (interface + stub).

O domínio expõe o Protocol ``AtualizadorTabelaRFB``; a produção é um stub que
falha explicitamente (rede desabilitada nesta fase) e os testes usam um FAKE.
Verifica-se que ambos SATISFAZEM o Protocol (Dependency Inversion / SOLID).
"""
from __future__ import annotations

import pytest

from contract_parser.domain.irrf import AtualizadorTabelaRFB, tabela_irrf_2026
from contract_parser.infrastructure.atualizador_rfb import (
    FONTE_RFB,
    RevalidacaoRFBIndisponivelError,
    StubAtualizadorTabelaRFB,
)
from tests.support.fakes import FakeAtualizadorTabelaRFB


def test_stub_satisfaz_o_protocol():
    assert isinstance(StubAtualizadorTabelaRFB(), AtualizadorTabelaRFB)


def test_fake_satisfaz_o_protocol():
    assert isinstance(FakeAtualizadorTabelaRFB(), AtualizadorTabelaRFB)


def test_stub_falha_explicitamente_sem_rede():
    stub = StubAtualizadorTabelaRFB()
    with pytest.raises(RevalidacaoRFBIndisponivelError, match="não habilitada"):
        stub.buscar_tabela_vigente()


def test_stub_documenta_a_fonte_oficial():
    assert "receitafederal" in FONTE_RFB


def test_fake_devolve_tabela_e_conta_chamadas():
    fake = FakeAtualizadorTabelaRFB()
    tabela = fake.buscar_tabela_vigente()
    assert tabela.vigencia == "2026"
    assert fake.chamadas == 1


def test_fake_pode_simular_falha():
    fake = FakeAtualizadorTabelaRFB(erro=RuntimeError("timeout RFB"))
    with pytest.raises(RuntimeError, match="timeout"):
        fake.buscar_tabela_vigente()


def test_fake_aceita_tabela_customizada():
    fake = FakeAtualizadorTabelaRFB(tabela=tabela_irrf_2026())
    assert fake.buscar_tabela_vigente().base_legal == "Lei nº 15.191/2025"
