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
    Reajuste,
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


# --------------------------------------------------------------------------- #
# Plano B, Fase 1: campos aditivos ``Reajuste.indice_fonte`` e
# ``Contrato.carencia_meses`` — mesmo padrão de ``locadores_adicionais``.
# --------------------------------------------------------------------------- #
def test_reajuste_indice_fonte_default_none():
    reajuste = Reajuste()
    assert reajuste.indice_fonte is None


def test_reajuste_indice_fonte_round_trip_json():
    reajuste = Reajuste(indice="IGP-M", indice_fonte="FGV")

    reidratado = Reajuste.model_validate_json(reajuste.model_dump_json())

    assert reidratado.indice_fonte == "FGV"
    assert reidratado.indice == "IGP-M"


def test_contrato_carencia_meses_default_none():
    contrato = Contrato()
    assert contrato.carencia_meses is None


def test_contrato_carencia_meses_round_trip_json():
    contrato = Contrato(carencia_meses=2)

    reidratado = Contrato.model_validate_json(contrato.model_dump_json())

    assert reidratado.carencia_meses == 2


def test_contrato_carencia_meses_independente_de_prazo_meses():
    contrato = Contrato(prazo_meses=24, carencia_meses=2)

    assert contrato.prazo_meses == 24
    assert contrato.carencia_meses == 2
