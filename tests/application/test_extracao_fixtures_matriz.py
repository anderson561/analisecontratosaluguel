"""Matriz de acertos por campo sobre as fixtures sintéticas (proxy de precisão).

Ground truth (gabarito) codificado à mão para cada fixture; o motor híbrido
(regras, SEM LLM) é executado e cada campo do §3 é comparado ao gabarito. Como a
parametrização é por ``(fixture, campo)``, cada célula da matriz é uma asserção
independente — a suíte falha apontando exatamente qual campo/fixture regrediu.

Determinístico: sem LLM, sem aleatoriedade — a mesma fixture produz sempre o
mesmo resultado (regra de ouro da skill python-ds-architect).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contract_parser.application.contract_extraction_service import ExtratorContrato
from contract_parser.domain.contrato import (
    Contrato,
    ModalidadeGarantia,
    TipoLocacao,
    TipoParte,
)
from tests.support import contract_fixtures as cf

G = ModalidadeGarantia  # apelido curto para o gabarito abaixo

_FLAGS_LIMPAS = {
    "violacao_art37_multiplas_garantias": False,
    "indice_vedado_art18": False,
    "periodicidade_inferior_12m_art18": False,
    "renuncia_benfeitorias_necessarias": False,
    "cumulacao_multas_bis_in_idem": False,
}


def _flags(**overrides) -> dict:
    return {**_FLAGS_LIMPAS, **overrides}


# Gabarito por fixture. Chaves == campos lógicos do §3.
GROUND_TRUTH: dict[str, dict] = {
    cf.RESIDENCIAL_PF_PJ: {
        "locador": (TipoParte.PF, "João Pereira da Silva", "12345678909"),
        "locatario": (TipoParte.PJ, "Comércio de Alimentos Boa Mesa LTDA", "11222333000181"),
        "tipo_locacao": TipoLocacao.RESIDENCIAL,
        "valor_aluguel": Decimal("3500.00"),
        "garantias": (G.CAUCAO,),
        "multa_rescisoria_total": Decimal("10500.00"),
        "data_inicio_vigencia": date(2024, 3, 1),
        "data_fim_vigencia": date(2026, 2, 28),
        "prazo_meses": 24,
        "dia_vencimento_mensal": 5,
        "reajuste_indice": "IGP-M",
        "reajuste_periodicidade_meses": 12,
        "reajuste_proximo": "2025-03-01",
        "reajuste_automatico": True,
        "flags": _flags(),
    },
    cf.COMERCIAL_PJ_PJ_ABUSIVO: {
        "locador": (TipoParte.PJ, "Imobiliária Horizonte Empreendimentos S.A", "45566778000109"),
        "locatario": (TipoParte.PJ, "Tech Solutions Comércio e Serviços LTDA", "98765432000110"),
        "tipo_locacao": TipoLocacao.COMERCIAL,
        "valor_aluguel": Decimal("12000.00"),
        "garantias": (G.CAUCAO, G.FIANCA),
        "multa_rescisoria_total": Decimal("24000.00"),
        "data_inicio_vigencia": date(2025, 1, 1),
        "data_fim_vigencia": date(2029, 12, 31),
        "prazo_meses": 60,
        "dia_vencimento_mensal": 10,
        "reajuste_indice": "IPCA",
        "reajuste_periodicidade_meses": 12,
        "reajuste_proximo": None,
        "reajuste_automatico": False,
        "flags": _flags(
            violacao_art37_multiplas_garantias=True,
            renuncia_benfeitorias_necessarias=True,
            cumulacao_multas_bis_in_idem=True,
        ),
    },
    cf.RESIDENCIAL_PJ_PF_REAJUSTE_VEDADO: {
        "locador": (TipoParte.PJ, "Administradora de Bens São Jorge Ltda", "45997418000153"),
        "locatario": (TipoParte.PF, "Maria Aparecida de Souza", "98765432100"),
        "tipo_locacao": TipoLocacao.RESIDENCIAL,
        "valor_aluguel": Decimal("1800.00"),
        "garantias": (G.SEGURO_FIANCA,),
        "multa_rescisoria_total": None,
        "data_inicio_vigencia": date(2026, 7, 15),
        "data_fim_vigencia": date(2028, 7, 14),
        "prazo_meses": 24,
        "dia_vencimento_mensal": 20,
        "reajuste_indice": "salário mínimo",
        "reajuste_periodicidade_meses": 6,
        "reajuste_proximo": None,
        "reajuste_automatico": False,
        "flags": _flags(indice_vedado_art18=True, periodicidade_inferior_12m_art18=True),
    },
    cf.TIPO_AMBIGUO_PF_PF: {
        "locador": (TipoParte.PF, "Carlos Henrique Martins", "11144477735"),
        "locatario": (TipoParte.PF, "Ana Paula Ribeiro", "22255588842"),
        "tipo_locacao": None,  # ambíguo; sem LLM permanece indeterminado
        "valor_aluguel": Decimal("2000.00"),
        "garantias": (G.CAUCAO,),
        "multa_rescisoria_total": None,
        "data_inicio_vigencia": None,
        "data_fim_vigencia": None,
        "prazo_meses": 30,
        "dia_vencimento_mensal": 8,
        "reajuste_indice": "IPCA",
        "reajuste_periodicidade_meses": None,
        "reajuste_proximo": None,
        "reajuste_automatico": False,
        "flags": _flags(),
    },
}

CAMPOS = list(next(iter(GROUND_TRUTH.values())).keys())


def achatar(c: Contrato) -> dict:
    """Projeta um :class:`Contrato` no mesmo formato do gabarito."""
    return {
        "locador": (c.locador.tipo, c.locador.nome, c.locador.documento),
        "locatario": (c.locatario.tipo, c.locatario.nome, c.locatario.documento),
        "tipo_locacao": c.tipo_locacao,
        "valor_aluguel": c.valor_aluguel,
        "garantias": tuple(c.garantias),
        "multa_rescisoria_total": c.multa_rescisoria_total,
        "data_inicio_vigencia": c.data_inicio_vigencia,
        "data_fim_vigencia": c.data_fim_vigencia,
        "prazo_meses": c.prazo_meses,
        "dia_vencimento_mensal": c.dia_vencimento_mensal,
        "reajuste_indice": c.reajuste.indice,
        "reajuste_periodicidade_meses": c.reajuste.periodicidade_meses,
        "reajuste_proximo": c.reajuste.proximo_reajuste,
        "reajuste_automatico": c.reajuste.automatico,
        "flags": c.flags.model_dump(exclude={"alertas"}),
    }


# Extração única por fixture, reutilizada em todas as células (determinístico).
_EXTRAIDO: dict[str, dict] = {
    nome: achatar(ExtratorContrato().extrair(cf.carregar_contrato(nome)))
    for nome in cf.TODAS
}


@pytest.mark.parametrize("fixture", list(GROUND_TRUTH))
@pytest.mark.parametrize("campo", CAMPOS)
def test_matriz_de_acertos_por_campo(campo: str, fixture: str):
    esperado = GROUND_TRUTH[fixture][campo]
    obtido = _EXTRAIDO[fixture][campo]
    assert obtido == esperado, f"{fixture} :: {campo}: obtido {obtido!r} != esperado {esperado!r}"
