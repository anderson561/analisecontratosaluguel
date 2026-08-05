"""Testes do motor de cálculo de IRRF (RF04 → CA-03) — camada domain, puros.

Cobrem: cálculo em CADA faixa da tabela 2026 (isento, três intermediárias e a
última aberta), o **CA-03** (base R$ 5.000,00 · Locador PF → Locatário PJ ⇒
R$ 466,27) com verificação da memória de cálculo, a regra Locador PJ ⇒ R$ 0,00, a
factory oficial e as invariantes do modelo ``TabelaIRRF``.

O valor do CA-03 é **conferido de forma independente** a partir das próprias
faixas da tabela (não é um número mágico solto): a fórmula da regra de negócio é
recomputada no teste e comparada ao resultado do serviço de produção.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from contract_parser.domain.contrato import TipoParte
from contract_parser.domain.irrf import (
    Faixa,
    ResultadoIRRF,
    TabelaIRRF,
    aplicar_redutor_15270,
    calcular_irrf,
    tabela_irrf_2026,
)

CENTAVO = Decimal("0.01")


@pytest.fixture
def tabela() -> TabelaIRRF:
    return tabela_irrf_2026()


def _esperado(base: str, aliquota: str, deducao: str) -> Decimal:
    """Recomputa o IRRF pela fórmula da regra (independente da produção)."""
    bruto = Decimal(base) * Decimal(aliquota) - Decimal(deducao)
    return max(Decimal("0.00"), bruto).quantize(CENTAVO, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Cálculo em cada faixa (PF → PJ)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("base", "aliquota", "deducao", "esperado"),
    [
        ("2000.00", "0", "0.00", "0.00"),  # isento (miolo)
        ("2428.80", "0", "0.00", "0.00"),  # isento (limite superior)
        ("2500.00", "0.075", "182.16", "5.34"),  # 7,5%
        ("2826.65", "0.075", "182.16", "29.84"),  # 7,5% (limite)
        ("3000.00", "0.15", "394.16", "55.84"),  # 15%
        ("3751.05", "0.15", "394.16", "168.50"),  # 15% (limite)
        ("4000.00", "0.225", "675.49", "224.51"),  # 22,5%
        ("4664.68", "0.225", "675.49", "374.06"),  # 22,5% (limite)
        ("5000.00", "0.275", "908.73", "466.27"),  # 27,5% (faixa aberta) = CA-03
        ("10000.00", "0.275", "908.73", "1841.27"),  # 27,5% (valor alto)
    ],
)
def test_calculo_por_faixa(tabela, base, aliquota, deducao, esperado):
    resultado = calcular_irrf(
        base_mensal=Decimal(base), tipo_locador=TipoParte.PF, tabela=tabela
    )
    # Conferência dupla: valor literal esperado == recomputo independente.
    assert resultado.imposto == Decimal(esperado) == _esperado(base, aliquota, deducao)
    assert resultado.aliquota == Decimal(aliquota)
    assert resultado.deducao == Decimal(deducao)


def test_faixa_isenta_nao_retem():
    resultado = calcular_irrf(
        base_mensal=Decimal("2000.00"), tipo_locador=TipoParte.PF, tabela=tabela_irrf_2026()
    )
    assert resultado.imposto == Decimal("0.00")
    assert resultado.retido is False
    assert "isenta" in resultado.observacao.lower()


# --------------------------------------------------------------------------- #
# CA-03 — o critério de aceite central da Fase 5
# --------------------------------------------------------------------------- #
def test_ca03_base_5000_pf_para_pj(tabela):
    resultado = calcular_irrf(
        base_mensal=Decimal("5000.00"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    # 5000 × 0,275 − 908,73 = 466,27
    assert resultado.imposto == Decimal("466.27")
    assert resultado.retido is True


def test_ca03_registra_memoria_de_calculo(tabela):
    """A memória de cálculo deve registrar faixa/alíquota/dedução/versão."""
    resultado = calcular_irrf(
        base_mensal=Decimal("5000.00"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert isinstance(resultado, ResultadoIRRF)
    assert resultado.base_calculo == Decimal("5000.00")
    assert resultado.aliquota == Decimal("0.275")
    assert resultado.deducao == Decimal("908.73")
    assert resultado.tabela_vigencia == "2026"
    assert resultado.base_legal == "Lei nº 15.191/2025"
    assert "receitafederal" in resultado.fonte_url
    assert "27.5%" in resultado.faixa_descricao
    # Serializável para persistência (contratos.irrf) sem perder precisão.
    assert Decimal(resultado.model_dump(mode="json")["imposto"]) == Decimal("466.27")


# --------------------------------------------------------------------------- #
# Regra de negócio: Locador PJ ⇒ IRRF = R$ 0,00
# --------------------------------------------------------------------------- #
def test_locador_pj_nao_retem(tabela):
    resultado = calcular_irrf(
        base_mensal=Decimal("5000.00"), tipo_locador=TipoParte.PJ, tabela=tabela
    )
    assert resultado.imposto == Decimal("0.00")
    assert resultado.retido is False
    assert resultado.aliquota == Decimal(0)
    assert resultado.base_calculo == Decimal("5000.00")  # base preservada na memória
    assert "PJ" in resultado.observacao


# --------------------------------------------------------------------------- #
# Arredondamento e fronteiras
# --------------------------------------------------------------------------- #
def test_arredondamento_half_up(tabela):
    # 2826.65 × 0.075 = 211.99875 → −182.16 = 29.83875 → ROUND_HALF_UP → 29.84
    resultado = calcular_irrf(
        base_mensal=Decimal("2826.65"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert resultado.imposto == Decimal("29.84")


def test_base_negativa_e_rejeitada(tabela):
    with pytest.raises(ValueError, match="negativa"):
        calcular_irrf(
            base_mensal=Decimal("-1.00"), tipo_locador=TipoParte.PF, tabela=tabela
        )


def test_fronteira_entre_faixas_seleciona_por_teto(tabela):
    # 2428.80 é isento; 2428.81 já entra na faixa de 7,5%.
    assert tabela.faixa_para(Decimal("2428.80")).aliquota == Decimal(0)
    assert tabela.faixa_para(Decimal("2428.81")).aliquota == Decimal("0.075")


# --------------------------------------------------------------------------- #
# Factory oficial 2026 e invariantes do modelo
# --------------------------------------------------------------------------- #
def test_factory_2026_validada_e_proveniente():
    tabela = tabela_irrf_2026()
    assert tabela.vigencia == "2026"
    assert tabela.validado is True
    assert tabela.validado_em == date(2026, 1, 1)
    assert tabela.base_legal == "Lei nº 15.191/2025"
    assert tabela.fonte_url.startswith("https://www.gov.br/receitafederal")
    assert len(tabela.faixas) == 5
    assert tabela.faixas[-1].maximo is None  # última faixa aberta
    assert tabela.faixas[0].aliquota == Decimal(0)  # primeira isenta


def test_tabela_exige_ultima_faixa_aberta():
    with pytest.raises(ValueError, match="última faixa"):
        TabelaIRRF(
            vigencia="teste",
            fonte_url="http://x",
            base_legal="teste",
            faixas=[
                Faixa(minimo=Decimal(0), maximo=Decimal(100), aliquota=Decimal(0), deducao=Decimal(0)),
            ],
        )


def test_tabela_so_ultima_faixa_pode_ser_aberta():
    with pytest.raises(ValueError, match="Apenas a última"):
        TabelaIRRF(
            vigencia="teste",
            fonte_url="http://x",
            base_legal="teste",
            faixas=[
                Faixa(minimo=Decimal(0), maximo=None, aliquota=Decimal(0), deducao=Decimal(0)),
                Faixa(minimo=Decimal(100), maximo=None, aliquota=Decimal("0.1"), deducao=Decimal(0)),
            ],
        )


def test_tabela_ordena_faixas_por_minimo():
    # Faixas fora de ordem são normalizadas pelo validador.
    tabela = TabelaIRRF(
        vigencia="teste",
        fonte_url="http://x",
        base_legal="teste",
        faixas=[
            Faixa(minimo=Decimal(100), maximo=None, aliquota=Decimal("0.1"), deducao=Decimal(0)),
            Faixa(minimo=Decimal(0), maximo=Decimal("99.99"), aliquota=Decimal(0), deducao=Decimal(0)),
        ],
    )
    assert [f.minimo for f in tabela.faixas] == [Decimal(0), Decimal(100)]


# --------------------------------------------------------------------------- #
# Ponto de extensão: redutor Lei 15.270/2025 permanece no-op (desligado)
# --------------------------------------------------------------------------- #
def test_redutor_15270_e_noop_por_enquanto():
    # Enquanto não validado na fonte legal, o redutor não altera o imposto.
    assert aplicar_redutor_15270(Decimal("466.27"), Decimal("5000.00")) == Decimal("466.27")


def test_redutor_nao_afeta_ca03(tabela):
    # Garante que o CA-03 não é alterado pelo (ainda desligado) redutor.
    resultado = calcular_irrf(
        base_mensal=Decimal("5000.00"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert resultado.imposto == Decimal("466.27")
