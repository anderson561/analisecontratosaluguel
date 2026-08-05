"""Testes do serviço de validação de portfólio (RF05 → CA-04)."""
from __future__ import annotations

from contract_parser.application.portfolio_validation_service import (
    PortfolioValidationService,
)
from contract_parser.domain.contrato import Contrato, Parte
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.match_portfolio import MetodoMatch, StatusMatch
from tests.support.fakes import FakeEmpresaRepository
from tests.support.fixture_builders import cnpj_valido_sequencial

CNPJ_A = cnpj_valido_sequencial(1)
CNPJ_B = cnpj_valido_sequencial(2)
CNPJ_C = cnpj_valido_sequencial(3)


def _repo(*empresas: Empresa) -> FakeEmpresaRepository:
    repo = FakeEmpresaRepository()
    for e in empresas:
        repo.add(e)
    return repo


def _contrato(*, nome: str | None = None, documento: str | None = None) -> Contrato:
    return Contrato(locatario=Parte(nome=nome, documento=documento))


def _status_de(resumo, cnpj):
    return next(e for e in resumo.empresas_status if e.empresa.cnpj == cnpj)


# --------------------------------------------------------------------------- #
# CA-04 — o coração da fase
# --------------------------------------------------------------------------- #
def test_ca04_empresa_sem_contrato_vira_pendencia_com_mensagem_exata():
    empresa_c = Empresa(cnpj=CNPJ_C, razao_social="Gamma Holding SA")
    repo = _repo(
        Empresa(cnpj=CNPJ_A, razao_social="Alpha LTDA"),
        Empresa(cnpj=CNPJ_B, razao_social="Beta ME"),
        empresa_c,
    )
    service = PortfolioValidationService(repo)

    # Só há contratos das empresas A e B (match por CNPJ).
    contratos = [
        _contrato(documento=CNPJ_A),
        _contrato(documento=CNPJ_B),
    ]
    resumo = service.validar(contratos)

    assert _status_de(resumo, CNPJ_A).status is StatusMatch.ENCONTRADO
    assert _status_de(resumo, CNPJ_B).status is StatusMatch.ENCONTRADO
    assert _status_de(resumo, CNPJ_C).status is StatusMatch.NAO_ENCONTRADO

    # C vira pendência com a mensagem EXATA do PRD (razão social + CNPJ de C).
    assert resumo.pendencias == [
        f"Contrato da Empresa Gamma Holding SA / {CNPJ_C} não encontrado"
    ]
    assert resumo.total_encontrados == 2
    assert resumo.total_pendencias == 1


def test_metodo_cnpj_registrado_e_score_100():
    repo = _repo(Empresa(cnpj=CNPJ_A, razao_social="Alpha LTDA"))
    resumo = PortfolioValidationService(repo).validar([_contrato(documento=CNPJ_A)])
    status = _status_de(resumo, CNPJ_A)
    assert status.metodo is MetodoMatch.CNPJ
    assert status.score == 100.0
    assert status.contratos_correspondentes == 1


def test_multiplos_contratos_da_mesma_empresa_sao_contados():
    repo = _repo(Empresa(cnpj=CNPJ_A, razao_social="Alpha LTDA"))
    resumo = PortfolioValidationService(repo).validar(
        [_contrato(documento=CNPJ_A), _contrato(documento=CNPJ_A)]
    )
    assert _status_de(resumo, CNPJ_A).contratos_correspondentes == 2


def test_contrato_sem_empresa_correspondente_e_listado():
    repo = _repo(Empresa(cnpj=CNPJ_A, razao_social="Alpha LTDA"))
    # Locatário com CNPJ não cadastrado e nome que não casa.
    resumo = PortfolioValidationService(repo).validar(
        [_contrato(nome="Empresa Desconhecida XYZ", documento=CNPJ_B)]
    )
    assert len(resumo.contratos_sem_empresa) == 1
    assert resumo.contratos_sem_empresa[0].locatario_documento == CNPJ_B
    # Empresa A não teve contrato → também é pendência.
    assert resumo.total_pendencias == 1


def test_match_via_fuzzy_por_alias_no_service():
    repo = _repo(
        Empresa(cnpj=CNPJ_A, razao_social="Alpha Comercio LTDA", aliases=["Alpha Com"])
    )
    # Sem CNPJ utilizável; nome bate no alias por fuzzy real (rapidfuzz).
    resumo = PortfolioValidationService(repo).validar(
        [_contrato(nome="Alpha Comercio Ltda")]
    )
    status = _status_de(resumo, CNPJ_A)
    assert status.status is StatusMatch.ENCONTRADO
    assert status.metodo is MetodoMatch.FUZZY
    assert status.score >= 85


def test_threshold_customizado_derruba_match_fraco():
    repo = _repo(Empresa(cnpj=CNPJ_A, razao_social="Alpha LTDA"))
    # Similaridade constante 80; threshold 90 → não casa.
    service = PortfolioValidationService(
        repo, threshold=90, similaridade=lambda a, b: 80.0
    )
    resumo = service.validar([_contrato(nome="qualquer coisa")])
    assert _status_de(resumo, CNPJ_A).status is StatusMatch.NAO_ENCONTRADO


def test_portfolio_vazio_sem_pendencias():
    resumo = PortfolioValidationService(_repo()).validar([_contrato(documento=CNPJ_A)])
    assert resumo.total_empresas == 0
    assert resumo.pendencias == []
    # Contrato sem empresa cadastrada correspondente é listado.
    assert len(resumo.contratos_sem_empresa) == 1


def test_ordem_das_pendencias_segue_o_portfolio():
    repo = _repo(
        Empresa(cnpj=CNPJ_A, razao_social="Alpha LTDA"),
        Empresa(cnpj=CNPJ_B, razao_social="Beta ME"),
        Empresa(cnpj=CNPJ_C, razao_social="Gamma SA"),
    )
    resumo = PortfolioValidationService(repo).validar([])
    assert resumo.pendencias == [
        f"Contrato da Empresa Alpha LTDA / {CNPJ_A} não encontrado",
        f"Contrato da Empresa Beta ME / {CNPJ_B} não encontrado",
        f"Contrato da Empresa Gamma SA / {CNPJ_C} não encontrado",
    ]
