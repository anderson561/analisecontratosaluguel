"""Testes do modelo de domínio ``Contrato`` — camada domain, puros (pydantic v2).

Cobre os novos tipos da Fase 1 do plano de Despesas/Prorrogação
(``.claude\\agents\\specs\\plano-despesas-prorrogacao.md``): ``TipoDespesa``,
``ResponsavelDespesa``, ``Prorrogacao`` e os campos ``Contrato.despesas`` /
``Contrato.prorrogacao``. Ainda sem extração de texto nem persistência — só o
formato do dado (defaults, round-trip JSON e ``extra="forbid"``).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from contract_parser.domain.contrato import (
    Contrato,
    Prorrogacao,
    ResponsavelDespesa,
    TipoDespesa,
)


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #
def test_prorrogacao_defaults():
    prorrogacao = Prorrogacao()
    assert prorrogacao.automatica is False
    assert prorrogacao.prazo_meses is None


def test_contrato_defaults_despesas_e_prorrogacao():
    contrato = Contrato()
    assert contrato.despesas == {}
    assert contrato.prorrogacao == Prorrogacao()


# --------------------------------------------------------------------------- #
# Round-trip JSON
# --------------------------------------------------------------------------- #
def test_contrato_round_trip_despesas_e_prorrogacao():
    contrato = Contrato(
        despesas={
            TipoDespesa.IPTU: ResponsavelDespesa.LOCATARIO,
            TipoDespesa.CONDOMINIO_EXTRAORDINARIO: None,
        },
        prorrogacao=Prorrogacao(automatica=True, prazo_meses=12),
    )

    reidratado = Contrato.model_validate_json(contrato.model_dump_json())

    assert reidratado.despesas == {
        TipoDespesa.IPTU: ResponsavelDespesa.LOCATARIO,
        TipoDespesa.CONDOMINIO_EXTRAORDINARIO: None,
    }
    assert reidratado.prorrogacao == Prorrogacao(automatica=True, prazo_meses=12)


# --------------------------------------------------------------------------- #
# extra="forbid"
# --------------------------------------------------------------------------- #
def test_prorrogacao_rejeita_campo_desconhecido():
    with pytest.raises(ValidationError):
        Prorrogacao(campo_invalido=1)
