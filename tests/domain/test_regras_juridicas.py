"""Testes das regras jurídicas de conformidade (Lei 8.245/91 — camada domain).

Cada flag decorre de uma condição objetiva e determinística sobre os campos
extraídos ou de um padrão de redação inequívoco (RF03/§3, §6). Cobre Art. 37
(cumulação de garantias), Art. 18 (índice vedado / periodicidade < 12 meses) e
as cláusulas abusivas (renúncia a benfeitorias; cumulação de multas bis in idem).
"""
from __future__ import annotations

from contract_parser.domain.contrato import ModalidadeGarantia, Reajuste
from contract_parser.domain.regras_juridicas import avaliar_flags


def _reajuste(indice=None, periodicidade=None) -> Reajuste:
    return Reajuste(indice=indice, periodicidade_meses=periodicidade)


# --------------------------------------------------------------------------- #
# Caso limpo: nenhuma flag
# --------------------------------------------------------------------------- #
def test_contrato_conforme_nao_gera_flags():
    flags = avaliar_flags(
        garantias=[ModalidadeGarantia.CAUCAO],
        reajuste=_reajuste("IPCA", 12),
        texto="Contrato regular, sem cláusulas vedadas.",
    )
    assert not flags.houve_alerta
    assert flags.model_dump(exclude={"alertas"}) == {
        "violacao_art37_multiplas_garantias": False,
        "indice_vedado_art18": False,
        "periodicidade_inferior_12m_art18": False,
        "renuncia_benfeitorias_necessarias": False,
        "cumulacao_multas_bis_in_idem": False,
    }


# --------------------------------------------------------------------------- #
# Art. 37 — cumulação de garantias
# --------------------------------------------------------------------------- #
def test_art37_multiplas_garantias():
    flags = avaliar_flags(
        garantias=[ModalidadeGarantia.CAUCAO, ModalidadeGarantia.FIANCA],
        reajuste=_reajuste("IPCA", 12),
        texto="caução e fiança",
    )
    assert flags.violacao_art37_multiplas_garantias
    assert any("Art. 37" in a for a in flags.alertas)


def test_art37_garantia_unica_nao_viola():
    flags = avaliar_flags(
        garantias=[ModalidadeGarantia.SEGURO_FIANCA],
        reajuste=_reajuste("IPCA", 12),
        texto="seguro-fiança",
    )
    assert not flags.violacao_art37_multiplas_garantias


def test_art37_garantia_duplicada_nao_conta_como_multipla():
    # A mesma modalidade repetida não é cumulação (usa-se o conjunto).
    flags = avaliar_flags(
        garantias=[ModalidadeGarantia.CAUCAO, ModalidadeGarantia.CAUCAO],
        reajuste=_reajuste("IPCA", 12),
        texto="caução",
    )
    assert not flags.violacao_art37_multiplas_garantias


# --------------------------------------------------------------------------- #
# Art. 18 — índice vedado e periodicidade < 12 meses
# --------------------------------------------------------------------------- #
def test_art18_indice_salario_minimo_vedado():
    flags = avaliar_flags(
        garantias=[], reajuste=_reajuste("salário mínimo", 12), texto=""
    )
    assert flags.indice_vedado_art18
    assert any("Art. 18" in a and "vedado" in a for a in flags.alertas)


def test_art18_indice_moeda_estrangeira_vedado():
    flags = avaliar_flags(
        garantias=[], reajuste=_reajuste("moeda estrangeira", 12), texto=""
    )
    assert flags.indice_vedado_art18


def test_art18_periodicidade_inferior_12m():
    flags = avaliar_flags(garantias=[], reajuste=_reajuste("IPCA", 6), texto="")
    assert flags.periodicidade_inferior_12m_art18
    assert not flags.indice_vedado_art18  # IPCA é lícito


def test_art18_periodicidade_12m_ok():
    flags = avaliar_flags(garantias=[], reajuste=_reajuste("IPCA", 12), texto="")
    assert not flags.periodicidade_inferior_12m_art18


def test_art18_indice_valido_nao_vedado():
    flags = avaliar_flags(garantias=[], reajuste=_reajuste("IGP-M", 12), texto="")
    assert not flags.indice_vedado_art18


# --------------------------------------------------------------------------- #
# Cláusulas abusivas — renúncia a benfeitorias e cumulação de multas
# --------------------------------------------------------------------------- #
def test_renuncia_benfeitorias_necessarias():
    flags = avaliar_flags(
        garantias=[],
        reajuste=_reajuste("IPCA", 12),
        texto="A locatária renuncia a indenização por benfeitorias necessárias.",
    )
    assert flags.renuncia_benfeitorias_necessarias
    assert any("benfeitoria" in a.lower() for a in flags.alertas)


def test_renuncia_variante_abre_mao():
    flags = avaliar_flags(
        garantias=[],
        reajuste=_reajuste("IPCA", 12),
        texto="O locatário abre mão de qualquer benfeitoria realizada.",
    )
    assert flags.renuncia_benfeitorias_necessarias


def test_cumulacao_multas_bis_in_idem():
    flags = avaliar_flags(
        garantias=[],
        reajuste=_reajuste("IPCA", 12),
        texto="Serão aplicadas cumulativamente a multa moratória e a multa penal.",
    )
    assert flags.cumulacao_multas_bis_in_idem
    assert any("bis in idem" in a.lower() for a in flags.alertas)


def test_multa_unica_nao_gera_bis_in_idem():
    flags = avaliar_flags(
        garantias=[],
        reajuste=_reajuste("IPCA", 12),
        texto="Multa rescisória de três aluguéis em caso de rescisão antecipada.",
    )
    assert not flags.cumulacao_multas_bis_in_idem


def test_multiplas_violacoes_acumulam_alertas():
    flags = avaliar_flags(
        garantias=[ModalidadeGarantia.CAUCAO, ModalidadeGarantia.FIANCA],
        reajuste=_reajuste("salário mínimo", 6),
        texto="renúncia a benfeitorias necessárias e multas cumulativas de mora",
    )
    # Art.37 + índice vedado + periodicidade + renúncia + cumulação = 5 alertas.
    assert len(flags.alertas) == 5
