"""Testes da montagem dos relatórios (RF06) — camada application.

Cobre o Relatório 01 (linhas + IRRF por linha, incluindo locador PJ ⇒ 0) e o
Relatório 02 (totais + pendências com a mensagem exata do PRD), a partir de
fixtures de domínio. Dados 100% fictícios (sem PII real).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from contract_parser.application.relatorio_service import RelatorioService
from contract_parser.domain.contrato import (
    Contrato,
    Parte,
    Reajuste,
    TipoParte,
)
from contract_parser.domain.empresa import Empresa
from tests.support.fakes import FakeEmpresaRepository
from tests.support.fixture_builders import cnpj_valido_sequencial

CNPJ_A = cnpj_valido_sequencial(1)  # Alpha (locatário PF→PJ, com contrato)
CNPJ_B = cnpj_valido_sequencial(2)  # Beta  (locatário de contrato com locador PJ)
CNPJ_C = cnpj_valido_sequencial(3)  # Gamma (cadastrada, SEM contrato → pendência)
CNPJ_X = cnpj_valido_sequencial(9)  # não cadastrada (contrato órfão)


def _repo() -> FakeEmpresaRepository:
    repo = FakeEmpresaRepository()
    repo.add(Empresa(cnpj=CNPJ_A, razao_social="Alpha Comercio LTDA"))
    repo.add(Empresa(cnpj=CNPJ_B, razao_social="Beta Servicos ME"))
    repo.add(Empresa(cnpj=CNPJ_C, razao_social="Gamma Holding SA"))
    return repo


def _contrato_pf_pj() -> Contrato:
    """Locador PF × Locatário PJ (Alpha), aluguel R$ 5.000,00 (CA-03)."""
    return Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="João da Silva", documento="11111111111"),
        locatario=Parte(tipo=TipoParte.PJ, nome="Alpha Comercio LTDA", documento=CNPJ_A),
        valor_aluguel=Decimal("5000.00"),
        data_fim_vigencia=date(2028, 10, 10),
        reajuste=Reajuste(indice="IPCA", proximo_reajuste="10/2026", automatico=True),
    )


def _contrato_locador_pj() -> Contrato:
    """Locador PJ ⇒ IRRF R$ 0,00 (Beta como locatário)."""
    return Contrato(
        locador=Parte(tipo=TipoParte.PJ, nome="Imobiliaria XPTO LTDA", documento=CNPJ_X),
        locatario=Parte(tipo=TipoParte.PJ, nome="Beta Servicos ME", documento=CNPJ_B),
        valor_aluguel=Decimal("8000.00"),
        data_fim_vigencia=date(2027, 5, 1),
        reajuste=Reajuste(indice="IGP-M", proximo_reajuste="05/2026", automatico=False),
    )


def _contrato_empresa_nao_cadastrada() -> Contrato:
    """Contrato de empresa que não está no portfólio (locatário órfão)."""
    return Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="Maria Souza", documento="22222222222"),
        locatario=Parte(tipo=TipoParte.PJ, nome="Desconhecida XYZ SA", documento=CNPJ_X),
        valor_aluguel=Decimal("3000.00"),
    )


# --------------------------------------------------------------------------- #
# Relatório 01 — contratos + IRRF por linha
# --------------------------------------------------------------------------- #
def test_relatorio01_uma_linha_por_contrato_na_ordem_de_entrada():
    contratos = [_contrato_pf_pj(), _contrato_locador_pj()]
    relatorio = RelatorioService(_repo()).montar(contratos)

    linhas = relatorio.contratos.linhas
    assert len(linhas) == 2
    assert linhas[0].locatario_nome == "Alpha Comercio LTDA"
    assert linhas[0].locatario_cnpj == CNPJ_A
    assert linhas[0].locador_nome == "João da Silva"
    assert linhas[0].indice == "IPCA"
    assert linhas[0].proximo_reajuste == "10/2026"
    assert linhas[0].reajuste_automatico is True
    assert linhas[0].vencimento == date(2028, 10, 10)
    assert relatorio.contratos.tabela_vigencia == "2026"


def test_ca03_irrf_pf_pj_base_5000():
    """Aluguel PF→PJ de R$ 5.000,00 → tabela 466,27 (0,275 − 908,73) reduzida
    a R$ 153,38 pelo redutor da Lei nº 15.270/2025 (ADR-003)."""
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    linha = relatorio.contratos.linhas[0]

    assert linha.irrf is not None
    assert linha.irrf.retido is True
    assert linha.irrf.aliquota == Decimal("0.275")
    assert linha.irrf.deducao == Decimal("908.73")
    assert linha.irrf.imposto_antes_reducao == Decimal("466.27")
    assert linha.irrf_retido == Decimal("153.38")
    # Redução exposta para auditabilidade (ADR-003): 466,27 − 153,38 = 312,89.
    assert linha.reducao_irrf == Decimal("312.89")
    assert linha.dados_incompletos is False


def test_locador_pj_gera_irrf_zero():
    relatorio = RelatorioService(_repo()).montar([_contrato_locador_pj()])
    linha = relatorio.contratos.linhas[0]

    assert linha.irrf is not None
    assert linha.irrf.retido is False
    assert linha.irrf_retido == Decimal("0.00")
    assert linha.reducao_irrf == Decimal("0.00")


def test_total_irrf_retido_soma_as_linhas():
    contratos = [_contrato_pf_pj(), _contrato_locador_pj()]
    relatorio = RelatorioService(_repo()).montar(contratos)
    # 153,38 (PF, já com o redutor da Lei nº 15.270/2025) + 0,00 (PJ) = 153,38.
    assert relatorio.contratos.total_irrf_retido == Decimal("153.38")


def test_total_reducao_irrf_soma_as_linhas():
    contratos = [_contrato_pf_pj(), _contrato_locador_pj()]
    relatorio = RelatorioService(_repo()).montar(contratos)
    # 312,89 (PF) + 0,00 (PJ) = 312,89.
    assert relatorio.contratos.total_reducao_irrf == Decimal("312.89")


def test_contrato_sem_valor_de_aluguel_nao_calcula_irrf():
    contrato = Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="Fulano"),
        locatario=Parte(tipo=TipoParte.PJ, nome="Alpha", documento=CNPJ_A),
        valor_aluguel=None,
    )
    relatorio = RelatorioService(_repo()).montar([contrato])
    linha = relatorio.contratos.linhas[0]

    assert linha.irrf is None
    assert linha.irrf_retido == Decimal("0.00")
    assert linha.reducao_irrf == Decimal("0.00")
    assert linha.dados_incompletos is True


def test_contrato_sem_tipo_de_locador_vai_para_revisao():
    contrato = Contrato(
        locador=Parte(tipo=None, nome="Locador Indefinido"),
        locatario=Parte(tipo=TipoParte.PJ, nome="Alpha", documento=CNPJ_A),
        valor_aluguel=Decimal("5000.00"),
    )
    relatorio = RelatorioService(_repo()).montar([contrato])
    assert relatorio.contratos.linhas[0].dados_incompletos is True


# --------------------------------------------------------------------------- #
# Relatório 02 — conformidade + pendências (mensagem exata do PRD)
# --------------------------------------------------------------------------- #
def test_relatorio02_totais_e_pendencia_com_mensagem_exata():
    contratos = [
        _contrato_pf_pj(),  # casa com Alpha (A)
        _contrato_locador_pj(),  # casa com Beta (B)
        _contrato_empresa_nao_cadastrada(),  # locatário órfão (CNPJ_X)
    ]
    relatorio = RelatorioService(_repo()).montar(contratos)
    conf = relatorio.conformidade

    assert conf.total_empresas_cadastradas == 3
    assert conf.total_contratos_localizados == 3
    assert conf.total_encontrados == 2  # A e B
    # Gamma (C) cadastrada porém sem contrato → pendência com a mensagem EXATA.
    assert conf.total_pendencias == 1
    assert conf.pendencias == [
        f"Contrato da Empresa Gamma Holding SA / {CNPJ_C} não encontrado"
    ]


def test_montagem_completa_agrega_os_dois_relatorios():
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    assert relatorio.contratos.total_contratos == 1
    assert relatorio.conformidade.total_empresas_cadastradas == 3
