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
    Parte,
    Prorrogacao,
    ResponsavelDespesa,
    TipoDespesa,
    TipoParte,
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


# --------------------------------------------------------------------------- #
# Fase 1 do plano de Múltiplos Locadores
# (.claude\agents\specs\plano-multiplos-locadores.md): campo aditivo
# ``Contrato.locadores_adicionais`` — só identificação/exibição, sem tocar em
# ``Contrato.locador`` nem no cálculo de IRRF.
# --------------------------------------------------------------------------- #
def test_contrato_defaults_locadores_adicionais():
    contrato = Contrato()
    assert contrato.locadores_adicionais == []


def test_contrato_round_trip_locadores_adicionais():
    contrato = Contrato(
        locadores_adicionais=[
            Parte(tipo=TipoParte.PF, nome="Fulano de Tal", documento="00000000000")
        ],
    )

    reidratado = Contrato.model_validate_json(contrato.model_dump_json())

    assert reidratado.locadores_adicionais == [
        Parte(tipo=TipoParte.PF, nome="Fulano de Tal", documento="00000000000")
    ]


def test_contrato_locador_e_locadores_adicionais_sao_independentes():
    contrato = Contrato(
        locador=Parte(nome="A"),
        locadores_adicionais=[Parte(nome="B"), Parte(nome="C")],
    )

    assert contrato.locador == Parte(nome="A")
    assert contrato.locadores_adicionais == [Parte(nome="B"), Parte(nome="C")]
