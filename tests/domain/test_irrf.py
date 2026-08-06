"""Testes do motor de cálculo de IRRF (RF04 → CA-03) — camada domain, puros.

Cobrem: cálculo em CADA faixa da tabela 2026 (isento, três intermediárias e a
última aberta), o **CA-03** (base R$ 5.000,00 · Locador PF → Locatário PJ ⇒
R$ 153,38 — tabela padrão R$ 466,27 reduzida pelo redutor da Lei nº 15.270/2025,
ver ADR-003) com verificação da memória de cálculo, a regra Locador PJ ⇒
R$ 0,00, a factory oficial, o redutor da Lei nº 15.270/2025 e as invariantes do
modelo ``TabelaIRRF``.

O valor do CA-03 é **conferido de forma independente** a partir das próprias
faixas da tabela e da fórmula do redutor (não é um número mágico solto): a
fórmula da regra de negócio é recomputada no teste e comparada ao resultado do
serviço de produção.
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
    calcular_irrf,
    calcular_reducao_lei_15270,
    tabela_irrf_2026,
)

CENTAVO = Decimal("0.01")


@pytest.fixture
def tabela() -> TabelaIRRF:
    return tabela_irrf_2026()


def _esperado(base: str, aliquota: str, deducao: str) -> Decimal:
    """Recomputa o IRRF da tabela padrão (ANTES do redutor) — independente da produção."""
    bruto = Decimal(base) * Decimal(aliquota) - Decimal(deducao)
    return max(Decimal("0.00"), bruto).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _reducao_esperada(rendimento: str) -> Decimal:
    """Recomputa o redutor da Lei nº 15.270/2025 (Art. 3º-A) — ver ADR-003 §2/§4."""
    valor = Decimal(rendimento)
    if valor <= Decimal("5000.00"):
        return Decimal("312.89")
    if valor <= Decimal("7350.00"):
        bruto = Decimal("978.62") - (Decimal("0.133145") * valor)
        return max(Decimal("0.00"), bruto).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return Decimal("0.00")


def _imposto_final_esperado(base: str, aliquota: str, deducao: str) -> Decimal:
    """Recomputa o imposto final (tabela padrão − redutor, nunca negativo)."""
    antes = _esperado(base, aliquota, deducao)
    reducao = _reducao_esperada(base)
    return max(Decimal("0.00"), antes - reducao).quantize(CENTAVO, rounding=ROUND_HALF_UP)


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
    # Usa `imposto_antes_reducao` (tabela padrão pura) — o redutor da Lei
    # 15.270/2025 é testado separadamente (não muda a seleção de faixa).
    assert (
        resultado.imposto_antes_reducao
        == Decimal(esperado)
        == _esperado(base, aliquota, deducao)
    )
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
    # 5000 × 0,275 − 908,73 = 466,27 (tabela padrão) − 312,89 (redutor Lei nº
    # 15.270/2025, ADR-003) = 153,38 (imposto final retido).
    assert resultado.imposto_antes_reducao == Decimal("466.27")
    assert resultado.reducao_aplicada == Decimal("312.89")
    assert resultado.imposto == Decimal("153.38")
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
    dump = resultado.model_dump(mode="json")
    assert Decimal(dump["imposto"]) == Decimal("153.38")
    assert Decimal(dump["imposto_antes_reducao"]) == Decimal("466.27")
    assert Decimal(dump["reducao_aplicada"]) == Decimal("312.89")


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
    # (imposto ANTES do redutor). Rendimento ≤ 5000 → redutor de R$312,89 zera
    # o imposto final (Lei nº 15.270/2025, ADR-003).
    resultado = calcular_irrf(
        base_mensal=Decimal("2826.65"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert resultado.imposto_antes_reducao == Decimal("29.84")
    assert resultado.imposto == Decimal("0.00")


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
# Redutor da Lei nº 15.270/2025 (Art. 3º-A) — ADR-003, ativo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("rendimento", "esperado"),
    [
        ("0.00", "312.89"),  # abaixo do teto
        ("5000.00", "312.89"),  # limite inferior — fixo
        ("5000.01", "312.89"),  # continuidade: sem salto na fronteira
        ("6000.00", "179.75"),  # meio da faixa de transição
        ("7350.00", "0.00"),  # limite superior — zera exatamente aqui
        ("7350.01", "0.00"),  # acima do teto — sem redução
        ("10000.00", "0.00"),  # bem acima — sem redução
    ],
)
def test_calcular_reducao_lei_15270_por_faixa(rendimento, esperado):
    assert calcular_reducao_lei_15270(Decimal(rendimento)) == Decimal(esperado) == (
        _reducao_esperada(rendimento)
    )


# --------------------------------------------------------------------------- #
# CA-03 (ADR-003) — 5 valores de referência conferidos à mão
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("base", "imposto_final_esperado"),
    [
        ("5000.00", "153.38"),
        ("5000.01", "153.38"),  # contínuo, sem salto em relação a 5000,00
        ("6000.00", "561.52"),
        ("7350.00", "1112.52"),
        ("7800.00", "1236.27"),  # > 7350: sem redução, tabela padrão pura
    ],
)
def test_ca03_reducao_lei_15270_valores_de_referencia(tabela, base, imposto_final_esperado):
    resultado = calcular_irrf(
        base_mensal=Decimal(base), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert resultado.imposto == Decimal(imposto_final_esperado)
    # Conferência dupla, independente da produção (tabela + redutor recompostos
    # no próprio teste — ver ADR-003 §3 para a tabela de referência completa).
    faixa = tabela.faixa_para(Decimal(base))
    assert resultado.imposto == _imposto_final_esperado(
        base, str(faixa.aliquota), str(faixa.deducao)
    )


def test_reducao_nunca_deixa_imposto_negativo(tabela):
    # Rendimento baixo (isento) já tem imposto-tabela R$0,00; o redutor não
    # pode gerar imposto negativo (§1º do Art. 3º-A).
    resultado = calcular_irrf(
        base_mensal=Decimal("2000.00"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert resultado.imposto == Decimal("0.00")
    assert resultado.imposto_antes_reducao == Decimal("0.00")
    assert resultado.reducao_aplicada == Decimal("0.00")


def test_reducao_nao_aplicada_a_locador_pj(tabela):
    # Locador PJ não sofre retenção (regra já existente) — o redutor não entra
    # nem precisa ser considerado nesse ramo.
    resultado = calcular_irrf(
        base_mensal=Decimal("5000.00"), tipo_locador=TipoParte.PJ, tabela=tabela
    )
    assert resultado.imposto == Decimal("0.00")
    assert resultado.imposto_antes_reducao == Decimal("0.00")
    assert resultado.reducao_aplicada == Decimal("0.00")


def test_observacao_menciona_reducao_quando_aplicada(tabela):
    resultado = calcular_irrf(
        base_mensal=Decimal("5000.00"), tipo_locador=TipoParte.PF, tabela=tabela
    )
    assert "153.38" in resultado.observacao or "153,38" in resultado.observacao
    assert "15.270" in resultado.observacao
