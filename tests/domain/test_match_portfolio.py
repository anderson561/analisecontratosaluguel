"""Testes do motor de match contrato × portfólio (RF05 / D4)."""
from __future__ import annotations

from contract_parser.domain.contrato import Contrato, Parte
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.match_portfolio import (
    MetodoMatch,
    StatusMatch,
    casar_contrato,
    mensagem_pendencia,
    similaridade_padrao,
)
from tests.support.fixture_builders import cnpj_valido_sequencial

CNPJ_A = cnpj_valido_sequencial(1)
CNPJ_B = cnpj_valido_sequencial(2)
CNPJ_C = cnpj_valido_sequencial(3)


def _contrato(*, nome: str | None = None, documento: str | None = None) -> Contrato:
    return Contrato(locatario=Parte(nome=nome, documento=documento))


def _empresa(cnpj: str, razao: str, **kw) -> Empresa:
    return Empresa(cnpj=cnpj, razao_social=razao, **kw)


# --------------------------------------------------------------------------- #
# Match primário por CNPJ
# --------------------------------------------------------------------------- #
def test_match_por_cnpj_exato():
    empresas = [_empresa(CNPJ_A, "Alpha LTDA")]
    resultado = casar_contrato(_contrato(documento=CNPJ_A), empresas, threshold=85)

    assert resultado.status is StatusMatch.ENCONTRADO
    assert resultado.metodo is MetodoMatch.CNPJ
    assert resultado.score == 100.0
    assert resultado.encontrado is True
    assert resultado.empresa is not None and resultado.empresa.cnpj == CNPJ_A


def test_match_cnpj_com_mascara_normaliza():
    empresas = [_empresa("11222333000181", "Alpha LTDA")]
    # Documento do locatário vem mascarado (como no texto do contrato).
    resultado = casar_contrato(
        _contrato(documento="11.222.333/0001-81"), empresas, threshold=85
    )
    assert resultado.metodo is MetodoMatch.CNPJ
    assert resultado.status is StatusMatch.ENCONTRADO


def test_cnpj_presente_mas_nao_cadastrado_sem_nome_nao_encontrado():
    # §6: CNPJ presente mas não cadastrado + nome não casa → Não Encontrado.
    empresas = [_empresa(CNPJ_A, "Alpha LTDA")]
    resultado = casar_contrato(_contrato(documento=CNPJ_B), empresas, threshold=85)

    assert resultado.status is StatusMatch.NAO_ENCONTRADO
    assert resultado.metodo is MetodoMatch.NENHUM
    assert resultado.encontrado is False
    assert resultado.empresa is None


def test_cnpj_nao_cadastrado_mas_nome_casa_via_fuzzy():
    # CNPJ não bate, mas o nome do locatário cai no fallback fuzzy e casa.
    empresas = [_empresa(CNPJ_A, "Alpha Comercio LTDA")]
    resultado = casar_contrato(
        _contrato(nome="Alpha Comercio LTDA", documento=CNPJ_B),
        empresas,
        threshold=85,
    )
    assert resultado.status is StatusMatch.ENCONTRADO
    assert resultado.metodo is MetodoMatch.FUZZY


# --------------------------------------------------------------------------- #
# Fallback fuzzy (limiar controlado por similaridade injetada)
# --------------------------------------------------------------------------- #
def test_fuzzy_acima_do_limiar_com_alias():
    empresas = [_empresa(CNPJ_A, "Alpha Comercio LTDA", aliases=["Alfa Com"])]
    # Similaridade injetada: casa o alias com 90 (>= 85).
    sim = lambda a, b: 90.0 if b == "Alfa Com" else 10.0
    resultado = casar_contrato(
        _contrato(nome="Alfa Com"), empresas, threshold=85, similaridade=sim
    )
    assert resultado.status is StatusMatch.ENCONTRADO
    assert resultado.metodo is MetodoMatch.FUZZY
    assert resultado.score == 90.0


def test_fuzzy_abaixo_do_limiar_nao_encontrado():
    empresas = [_empresa(CNPJ_A, "Alpha Comercio LTDA")]
    sim = lambda a, b: 80.0
    resultado = casar_contrato(
        _contrato(nome="Coisa Aleatoria"), empresas, threshold=85, similaridade=sim
    )
    assert resultado.status is StatusMatch.NAO_ENCONTRADO
    assert resultado.metodo is MetodoMatch.NENHUM
    # O melhor score sub-limiar é reportado (faixa de revisão manual).
    assert resultado.score == 80.0


def test_fuzzy_no_limiar_exato_encontra():
    empresas = [_empresa(CNPJ_A, "Alpha")]
    sim = lambda a, b: 85.0
    resultado = casar_contrato(
        _contrato(nome="Alpha"), empresas, threshold=85, similaridade=sim
    )
    assert resultado.status is StatusMatch.ENCONTRADO


def test_locatario_sem_cnpj_usa_fuzzy():
    empresas = [_empresa(CNPJ_A, "Alpha Comercio LTDA")]
    resultado = casar_contrato(
        _contrato(nome="Alpha Comercio LTDA", documento=None), empresas, threshold=85
    )
    assert resultado.status is StatusMatch.ENCONTRADO
    assert resultado.metodo is MetodoMatch.FUZZY


def test_locatario_pf_com_cpf_cai_no_fuzzy():
    # CPF (11 dígitos) não é CNPJ utilizável → precisa cair no fuzzy por nome.
    empresas = [_empresa(CNPJ_A, "Alpha Comercio LTDA")]
    resultado = casar_contrato(
        _contrato(nome="Alpha Comercio LTDA", documento="12345678901"),
        empresas,
        threshold=85,
    )
    assert resultado.status is StatusMatch.ENCONTRADO
    assert resultado.metodo is MetodoMatch.FUZZY


def test_sem_cnpj_e_sem_nome_nao_encontrado():
    empresas = [_empresa(CNPJ_A, "Alpha")]
    resultado = casar_contrato(_contrato(), empresas, threshold=85)
    assert resultado.status is StatusMatch.NAO_ENCONTRADO
    assert resultado.score == 0.0


def test_empate_de_score_resolve_pela_ordem_do_portfolio():
    empresas = [_empresa(CNPJ_A, "Empresa X"), _empresa(CNPJ_B, "Empresa X")]
    sim = lambda a, b: 95.0
    resultado = casar_contrato(
        _contrato(nome="Empresa X"), empresas, threshold=85, similaridade=sim
    )
    # Primeira ocorrência vence (determinístico).
    assert resultado.empresa is not None and resultado.empresa.cnpj == CNPJ_A


# --------------------------------------------------------------------------- #
# Similaridade real (rapidfuzz) — sanidade
# --------------------------------------------------------------------------- #
def test_similaridade_padrao_robusta_a_ordem_e_caixa():
    # token_sort_ratio: ordem de tokens e caixa não derrubam o score.
    assert similaridade_padrao("Alpha Comercio LTDA", "COMERCIO ALPHA ltda") >= 85
    assert similaridade_padrao("Alpha Comercio LTDA", "Zeta Servicos SA") < 85


# --------------------------------------------------------------------------- #
# Mensagem de pendência (CA-04)
# --------------------------------------------------------------------------- #
def test_mensagem_pendencia_formato_exato():
    empresa = _empresa(CNPJ_C, "Gamma Holding SA")
    assert (
        mensagem_pendencia(empresa)
        == f"Contrato da Empresa Gamma Holding SA / {CNPJ_C} não encontrado"
    )
