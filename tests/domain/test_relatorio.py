"""Testes do modelo de domínio dos relatórios (RF06) — camada domain, puros.

Cobre :class:`LinhaContrato` e :class:`RelatorioContratos` isoladamente, com um
``ResultadoIRRF`` fake (sem depender do motor de cálculo) — em particular a
property ``reducao_irrf`` (ADR-003: dá visibilidade ao valor que o redutor da
Lei nº 15.270/2025 abateu do imposto da tabela padrão).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from contract_parser.domain.irrf import ResultadoIRRF
from contract_parser.domain.relatorio import LinhaContrato, RelatorioContratos


def _resultado_irrf(*, imposto: Decimal, reducao_aplicada: Decimal) -> ResultadoIRRF:
    return ResultadoIRRF(
        retido=imposto > 0,
        imposto=imposto,
        base_calculo=Decimal("5000.00"),
        aliquota=Decimal("0.275"),
        deducao=Decimal("908.73"),
        faixa_descricao="acima de 4664.69 — 27.5%",
        tabela_vigencia="2026",
        base_legal="Lei nº 15.191/2025",
        fonte_url="https://exemplo.invalido/tabela",
        imposto_antes_reducao=imposto + reducao_aplicada,
        reducao_aplicada=reducao_aplicada,
    )


def _linha(irrf: ResultadoIRRF | None) -> LinhaContrato:
    return LinhaContrato(
        locatario_nome="Alpha Comercio LTDA",
        locatario_cnpj="00000000000159",
        locador_nome="João da Silva",
        valor_aluguel=Decimal("5000.00"),
        irrf=irrf,
        indice="IPCA",
        proximo_reajuste="10/2026",
        reajuste_automatico=True,
        vencimento=date(2028, 10, 10),
    )


def test_reducao_irrf_expoe_o_valor_reduzido_pela_lei_15270():
    # Valores de referência pós ADR-004 (base R$6.000,00): tabela 574,29
    # reduzida em 179,75 pelo redutor da Lei nº 15.270/2025 -> imposto 394,54.
    linha = _linha(_resultado_irrf(imposto=Decimal("394.54"), reducao_aplicada=Decimal("179.75")))
    assert linha.reducao_irrf == Decimal("179.75")


def test_reducao_irrf_zero_quando_irrf_nao_calculado():
    linha = _linha(None)
    assert linha.reducao_irrf == Decimal("0.00")


def test_reducao_irrf_zero_quando_sem_reducao_aplicada():
    """Locador PJ (ou base acima de R$ 7.350,00) não tem redução: fica R$ 0,00."""
    linha = _linha(_resultado_irrf(imposto=Decimal("1200.00"), reducao_aplicada=Decimal("0.00")))
    assert linha.reducao_irrf == Decimal("0.00")


def test_total_reducao_irrf_soma_as_linhas():
    linhas = [
        _linha(_resultado_irrf(imposto=Decimal("394.54"), reducao_aplicada=Decimal("179.75"))),
        _linha(_resultado_irrf(imposto=Decimal("1200.00"), reducao_aplicada=Decimal("0.00"))),
        _linha(None),
    ]
    relatorio = RelatorioContratos(linhas=linhas, tabela_vigencia="2026")
    assert relatorio.total_reducao_irrf == Decimal("179.75")
