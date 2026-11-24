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
    Prorrogacao,
    Reajuste,
    ResponsavelDespesa,
    TipoDespesa,
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
    """Aluguel PF→PJ de R$ 5.000,00 → desconto simplificado de R$607,20
    (Lei nº 14.663/2023, art. 6º, ADR-004) → base tributável R$4.392,80 →
    tabela 312,89 (0,225 − 675,49) reduzida a R$ 0,00 pelo redutor da Lei nº
    15.270/2025, sobre o rendimento BRUTO de R$5.000,00 (ADR-003)."""
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    linha = relatorio.contratos.linhas[0]

    assert linha.irrf is not None
    assert linha.irrf.retido is False
    assert linha.irrf.aliquota == Decimal("0.225")
    assert linha.irrf.deducao == Decimal("675.49")
    assert linha.irrf.imposto_antes_reducao == Decimal("312.89")
    assert linha.irrf.rendimento_bruto == Decimal("5000.00")
    assert linha.irrf.desconto_simplificado_aplicado == Decimal("607.20")
    assert linha.irrf_retido == Decimal("0.00")
    # Redução exposta para auditabilidade (ADR-003): igual ao imposto da
    # tabela nesta base (312,89), por isso o imposto final zera (ADR-004).
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
    # 0,00 (PF, desconto simplificado ADR-004 + redutor Lei nº 15.270/2025
    # zeram o imposto) + 0,00 (PJ) = 0,00.
    assert relatorio.contratos.total_irrf_retido == Decimal("0.00")


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
# Bug L-01 — o tipo do LOCATÁRIO também decide a retenção
# --------------------------------------------------------------------------- #
CPF_FICTICIO = "11111111111"


def _contrato_locador_pf(locatario: Parte, valor: str = "6000.00") -> Contrato:
    return Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="FULANO DE TAL", documento=CPF_FICTICIO),
        locatario=locatario,
        valor_aluguel=Decimal(valor),
    )


class _RepoQueContaListAll(FakeEmpresaRepository):
    """Fake que conta as leituras do portfólio (uma carga por ``montar``)."""

    def __init__(self) -> None:
        super().__init__()
        self.leituras = 0

    def list_all(self):
        self.leituras += 1
        return super().list_all()


def test_locador_pf_locatario_pj_mantem_calculo_de_referencia():
    contrato = _contrato_locador_pf(
        Parte(tipo=TipoParte.PJ, nome="Alpha Comercio LTDA", documento=CNPJ_A)
    )
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf_retido == Decimal("394.54")  # ADR-004, base 6.000
    assert linha.dados_incompletos is False


def test_locatario_pf_nao_retem_irrf_e_nao_vai_para_revisao():
    contrato = _contrato_locador_pf(
        Parte(tipo=TipoParte.PF, nome="CICLANO DE TAL", documento="22222222222")
    )
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf is not None
    assert linha.irrf.retido is False
    assert linha.irrf_retido == Decimal("0.00")
    assert linha.irrf.faixa_descricao == "não aplicável (locatário PF)"
    assert "carnê-leão" in linha.irrf.observacao
    assert linha.dados_incompletos is False


def test_locador_pj_prevalece_sobre_locatario_pf():
    contrato = Contrato(
        locador=Parte(tipo=TipoParte.PJ, nome="Imobiliaria XPTO LTDA", documento=CNPJ_X),
        locatario=Parte(tipo=TipoParte.PF, nome="CICLANO DE TAL"),
        valor_aluguel=Decimal("6000.00"),
    )
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf_retido == Decimal("0.00")
    assert linha.irrf.faixa_descricao == "não aplicável (locador PJ)"


def test_locador_pj_prevalece_sobre_locatario_sem_tipo_fora_do_portfolio():
    contrato = Contrato(
        locador=Parte(tipo=TipoParte.PJ, nome="Imobiliaria XPTO LTDA", documento=CNPJ_X),
        locatario=Parte(tipo=None, nome="Desconhecida XYZ SA"),
        valor_aluguel=Decimal("6000.00"),
    )
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf is not None
    assert linha.irrf_retido == Decimal("0.00")
    assert linha.dados_incompletos is False


def test_locatario_sem_tipo_casado_por_cnpj_no_portfolio_e_tratado_como_pj():
    contrato = _contrato_locador_pf(Parte(tipo=None, nome="Nome Ilegivel", documento=CNPJ_A))
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf_retido == Decimal("394.54")
    assert linha.dados_incompletos is False


def test_locatario_sem_tipo_casado_por_nome_no_portfolio_e_tratado_como_pj():
    contrato = _contrato_locador_pf(Parte(tipo=None, nome="Alpha Comercio LTDA"))
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf_retido == Decimal("394.54")


def test_locatario_sem_tipo_fora_do_portfolio_vai_para_revisao():
    contrato = _contrato_locador_pf(
        Parte(tipo=None, nome="Desconhecida XYZ SA", documento=CNPJ_X)
    )
    linha = RelatorioService(_repo()).montar([contrato]).contratos.linhas[0]

    assert linha.irrf is None
    assert linha.irrf_retido == Decimal("0.00")
    assert linha.dados_incompletos is True


def test_montar_le_o_portfolio_uma_unica_vez():
    repo = _RepoQueContaListAll()
    repo.add(Empresa(cnpj=CNPJ_A, razao_social="Alpha Comercio LTDA"))
    contratos = [
        _contrato_locador_pf(Parte(tipo=None, nome="Alpha Comercio LTDA")),
        _contrato_locador_pf(Parte(tipo=None, nome="Outra SA", documento=CNPJ_X)),
        _contrato_pf_pj(),
    ]
    RelatorioService(repo).montar(contratos)

    assert repo.leituras == 1


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


def test_relatorio01_linha_leva_despesas_e_prorrogacao_do_contrato():
    """Passthrough: despesas/prorrogacao do Contrato vão crus para a linha."""
    contrato = _contrato_pf_pj().model_copy(
        update={
            "despesas": {
                TipoDespesa.IPTU: ResponsavelDespesa.LOCADOR,
                TipoDespesa.CONDOMINIO_ORDINARIO: None,
            },
            "prorrogacao": Prorrogacao(automatica=True, prazo_meses=12),
        }
    )
    relatorio = RelatorioService(_repo()).montar([contrato])
    linha = relatorio.contratos.linhas[0]

    assert linha.despesas == {
        TipoDespesa.IPTU: ResponsavelDespesa.LOCADOR,
        TipoDespesa.CONDOMINIO_ORDINARIO: None,
    }
    assert linha.prorrogacao_automatica is True
    assert linha.prorrogacao_prazo_meses == 12


def test_relatorio01_linha_prorrogacao_default_quando_contrato_nao_informa():
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    linha = relatorio.contratos.linhas[0]

    assert linha.despesas == {}
    assert linha.prorrogacao_automatica is False
    assert linha.prorrogacao_prazo_meses is None


def test_relatorio01_linha_leva_locadores_adicionais_do_contrato():
    """Passthrough: locadores_adicionais do Contrato vão crus para a linha."""
    locadores_adicionais = [
        Parte(tipo=TipoParte.PF, nome="Maria Souza", documento="22222222222"),
        Parte(tipo=TipoParte.PF, nome="Pedro Alves", documento="33333333333"),
    ]
    contrato = _contrato_pf_pj().model_copy(
        update={"locadores_adicionais": locadores_adicionais}
    )
    relatorio = RelatorioService(_repo()).montar([contrato])
    linha = relatorio.contratos.linhas[0]

    assert linha.locadores_adicionais == tuple(locadores_adicionais)


def test_relatorio01_linha_locadores_adicionais_default_vazio():
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    linha = relatorio.contratos.linhas[0]

    assert linha.locadores_adicionais == ()


def test_relatorio01_linha_leva_indice_fonte_e_carencia_do_contrato():
    """Passthrough: indice_fonte (Reajuste) e carencia_meses (Contrato) crus."""
    contrato = _contrato_pf_pj().model_copy(
        update={
            "reajuste": Reajuste(
                indice="IGP-M", indice_fonte="FGV", proximo_reajuste="10/2026", automatico=True
            ),
            "carencia_meses": 2,
        }
    )
    relatorio = RelatorioService(_repo()).montar([contrato])
    linha = relatorio.contratos.linhas[0]

    assert linha.indice_fonte == "FGV"
    assert linha.carencia_meses == 2


def test_relatorio01_linha_indice_fonte_e_carencia_default_none():
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    linha = relatorio.contratos.linhas[0]

    assert linha.indice_fonte is None
    assert linha.carencia_meses is None


def test_montagem_completa_agrega_os_dois_relatorios():
    relatorio = RelatorioService(_repo()).montar([_contrato_pf_pj()])
    assert relatorio.contratos.total_contratos == 1
    assert relatorio.conformidade.total_empresas_cadastradas == 3
