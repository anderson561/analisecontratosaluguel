"""Testes dos extratores determinísticos por campo (RF03, camada domain).

Cobrem cada extrator de ``regras_extracao`` isoladamente, incluindo três testes
de REGRESSÃO para defeitos corrigidos nesta fase:

- ``test_valor_aluguel_com_r_no_conector``  → classe negada ``[^R]`` sob
  ``IGNORECASE`` excluía o 'r' minúsculo, quebrando a captura do valor.
- ``test_prazo_nao_confunde_com_periodicidade`` → o genérico "<n> meses"
  capturava a periodicidade do reajuste como se fosse o prazo total.
- ``detectar_documento`` cru de 14 dígitos (testado em ``test_parsing_ptbr``).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contract_parser.domain import regras_extracao as R
from contract_parser.domain.contrato import ModalidadeGarantia, TipoLocacao, TipoParte
from contract_parser.domain.regras_extracao import CONF_ALTA, CONF_BAIXA, CONF_MEDIA


# --------------------------------------------------------------------------- #
# Partes (Locador / Locatário) — nome, documento, dedução PF/PJ
# --------------------------------------------------------------------------- #
def test_extrair_locador_pf_com_cpf():
    texto = "LOCADOR: João da Silva, brasileiro, portador do CPF nº 123.456.789-09.\n\n"
    res = R.extrair_locador(texto)
    assert res.resolvido
    assert res.valor.tipo == TipoParte.PF
    assert res.valor.nome == "João da Silva"
    assert res.valor.documento == "12345678909"
    assert res.confianca == CONF_ALTA


def test_extrair_locatario_pj_com_cnpj():
    texto = "LOCATÁRIO: Alpha Comercio LTDA, inscrita no CNPJ 11.222.333/0001-81.\n\n"
    res = R.extrair_locatario(texto)
    assert res.valor.tipo == TipoParte.PJ
    assert res.valor.nome == "Alpha Comercio LTDA"
    assert res.valor.documento == "11222333000181"


def test_extrair_parte_pj_por_termo_societario_sem_documento():
    # Sem documento, mas o nome carrega termo societário -> deduz PJ (conf média).
    texto = "LOCADORA: Beta Empreendimentos LTDA\n\n"
    res = R.extrair_locador(texto)
    assert res.valor.tipo == TipoParte.PJ
    assert res.valor.documento is None
    assert res.confianca == CONF_MEDIA


def test_extrair_parte_sem_rotulo_nao_encontrado():
    res = R.extrair_locador("documento sem partes rotuladas")
    assert not res.resolvido
    assert res.valor is None


def test_rotulo_parentetico_com_bloco_em_linha_separada():
    # REGRESSÃO (contrato_02): "LOCADOR (A/S/ES):" com o parentético de flexão e o
    # bloco numa linha após linha em branco. O parentético NÃO pode impedir o
    # casamento do separador ':'.
    texto = (
        "LOCADOR (A/S/ES):\n\n"
        "FULANO DE TAL, brasileiro, CPF:111.444.777-35, casado.\n\n"
        "LOCATÁRIOS (A/S):\n\n"
        "EMPRESA EXEMPLO LTDA , CNPJ : 11.444.777/0001-61 , email x@y.com\n\n"
        "CLAUSULA 1"
    )
    loc = R.extrair_locador(texto)
    assert loc.valor.tipo == TipoParte.PF
    assert loc.valor.nome == "FULANO DE TAL"
    assert loc.valor.documento == "11144477735"

    lct = R.extrair_locatario(texto)
    assert lct.valor.tipo == TipoParte.PJ
    assert lct.valor.nome == "EMPRESA EXEMPLO LTDA"
    assert lct.valor.documento == "11444777000161"


def test_rotulo_variacoes_genero_plural():
    assert R.extrair_locador("LOCADORES: Alfa S.A., CNPJ 22.333.444/0001-81\n\n").valor.tipo == (
        TipoParte.PJ
    )
    assert R.extrair_locatario("LOCATÁRIA (O/S): Maria Exemplo, CPF 222.555.888-42\n\n").valor.nome == (
        "Maria Exemplo"
    )


def test_bloco_assinatura_underscore_nao_e_nome():
    # Bloco só de traços/underscores (assinatura) não vira parte resolvida.
    res = R.extrair_locador("LOCADORA: ________________________\n\n")
    assert not res.resolvido
    assert res.valor is None


def test_parte_narrativa_como_locador_deduz_pj_por_cnpj():
    # REGRESSÃO (contrato_03): partes em prosa, sem separador após o rótulo.
    texto = (
        "de um lado, como LOCADORA e aqui doravante assim denominada, "
        "ALFA LOGISTICA LTDA, inscrita no CNPJ sob nº 22.333.444/0001-81, "
        "e do outro, como LOCATÁRIO a sociedade empresária BETA CONSTRUTORA LTDA, "
        "inscrita no CNPJ sob o nº 33.555.666/0001-65, mediante cláusulas."
    )
    loc = R.extrair_locador(texto)
    assert loc.resolvido
    assert loc.valor.tipo == TipoParte.PJ
    assert loc.valor.documento == "22333444000181"
    assert loc.confianca == CONF_MEDIA  # prosa: confiança-teto média

    lct = R.extrair_locatario(texto)
    assert lct.valor.tipo == TipoParte.PJ
    assert lct.valor.nome == "BETA CONSTRUTORA LTDA"
    assert lct.valor.documento == "33555666000165"


# --------------------------------------------------------------------------- #
# Tipo de locação
# --------------------------------------------------------------------------- #
def test_tipo_locacao_residencial():
    assert R.extrair_tipo_locacao("destina-se a fins residenciais").valor == (
        TipoLocacao.RESIDENCIAL
    )


def test_tipo_locacao_comercial():
    assert R.extrair_tipo_locacao("para atividade empresarial").valor == (
        TipoLocacao.COMERCIAL
    )


def test_tipo_locacao_ambiguo_quando_ambos_ou_nenhum():
    # Ambos os termos presentes -> ambíguo (deixa para o interpretador).
    assert not R.extrair_tipo_locacao("uso residencial e também comercial").resolvido
    # Nenhum termo -> ambíguo.
    assert not R.extrair_tipo_locacao("o imóvel objeto deste contrato").resolvido


def test_tipo_locacao_pelo_titulo_vence_corpo():
    # REGRESSÃO (contrato_02): título "RESIDENCIAL" prevalece sobre "comercial"
    # citado no corpo (ex.: descrição "sala comercial").
    texto = (
        "CONTRATO DE LOCAÇÃO RESIDENCIAL COM DEPÓSITO-CAUÇÃO\n"
        "O objeto é a sala comercial 1202 do edifício."
    )
    res = R.extrair_tipo_locacao(texto)
    assert res.valor == TipoLocacao.RESIDENCIAL
    assert res.detalhe == "tipo pelo título"


def test_tipo_locacao_titulo_comercial():
    assert R.extrair_tipo_locacao(
        "INSTRUMENTO PARTICULAR DE LOCAÇÃO COMERCIAL\ncláusulas."
    ).valor == TipoLocacao.COMERCIAL


def test_tipo_locacao_corpo_comerciais_plural():
    # Sem tipo no título: corpo com "fins exclusivamente comerciais" (plural).
    assert R.extrair_tipo_locacao(
        "dando-o em locação ao LOCATÁRIO para fins exclusivamente comerciais"
    ).valor == TipoLocacao.COMERCIAL


# --------------------------------------------------------------------------- #
# Valor do aluguel  (inclui REGRESSÃO do 'r' minúsculo)
# --------------------------------------------------------------------------- #
def test_extrair_valor_aluguel_simples():
    res = R.extrair_valor_aluguel("O aluguel mensal é de R$ 3.500,00.")
    assert res.valor == Decimal("3500.00")
    assert res.confianca == CONF_ALTA


def test_valor_aluguel_com_r_no_conector():
    # REGRESSÃO: "importa"/"corresponde" têm 'r' minúsculo; a classe [^R\n] sob
    # IGNORECASE excluía 'r' e a captura falhava. Deve extrair normalmente.
    assert R.extrair_valor_aluguel("O aluguel mensal importa em R$ 1.800,00.").valor == (
        Decimal("1800.00")
    )
    assert R.extrair_valor_aluguel("aluguel correspondente a R$ 900,00").valor == (
        Decimal("900.00")
    )


def test_extrair_valor_aluguel_ausente():
    assert not R.extrair_valor_aluguel("contrato sem valor monetário").resolvido


# --------------------------------------------------------------------------- #
# Multa rescisória: valor direto OU "N aluguéis" (× base)
# --------------------------------------------------------------------------- #
def test_multa_valor_direto():
    res = R.extrair_multa_rescisoria("multa rescisória de R$ 5.000,00")
    assert res.valor == Decimal("5000.00")
    assert res.confianca == CONF_ALTA


def test_multa_em_alugueis_com_base_monetiza():
    res = R.extrair_multa_rescisoria(
        "multa equivalente a 3 (três) aluguéis", valor_aluguel=Decimal(1000)
    )
    assert res.valor == Decimal(3000)
    assert res.confianca == CONF_MEDIA


def test_multa_em_alugueis_sem_base_nao_monetiza():
    res = R.extrair_multa_rescisoria("multa de 3 aluguéis", valor_aluguel=None)
    assert not res.resolvido


def test_multa_ausente():
    assert not R.extrair_multa_rescisoria("contrato sem cláusula penal").resolvido


# --------------------------------------------------------------------------- #
# Garantias (Art. 37)
# --------------------------------------------------------------------------- #
def test_garantia_caucao_unica():
    assert R.extrair_garantias("garantido por caução em dinheiro").valor == [
        ModalidadeGarantia.CAUCAO
    ]


def test_garantia_seguro_fianca_nao_conta_como_fianca_pura():
    # "seguro-fiança" NÃO deve gerar também a modalidade "fiança".
    assert R.extrair_garantias("garantia: seguro-fiança locatícia").valor == [
        ModalidadeGarantia.SEGURO_FIANCA
    ]


def test_garantia_multiplas():
    res = R.extrair_garantias("caução em dinheiro e fiança de fiador idôneo")
    assert set(res.valor) == {ModalidadeGarantia.CAUCAO, ModalidadeGarantia.FIANCA}


def test_garantia_cessao_fiduciaria():
    assert R.extrair_garantias("mediante cessão fiduciária de quotas").valor == [
        ModalidadeGarantia.CESSAO_FIDUCIARIA
    ]


def test_garantia_ausente():
    assert not R.extrair_garantias("contrato sem garantia expressa").resolvido


# --------------------------------------------------------------------------- #
# Vigência: início, fim, prazo, dia de vencimento
# --------------------------------------------------------------------------- #
def test_periodo_de_a_ambos_alta_confianca():
    texto = "com vigência de 01/03/2024 a 28/02/2026"
    assert R.extrair_data_inicio(texto).valor == date(2024, 3, 1)
    assert R.extrair_data_fim(texto).valor == date(2026, 2, 28)


def test_inicio_e_fim_por_ancora_isolada():
    assert R.extrair_data_inicio("início em 15/07/2026").valor == date(2026, 7, 15)
    assert R.extrair_data_fim("término em 14/07/2028").valor == date(2028, 7, 14)


def test_prazo_meses_numerico_ancorado():
    res = R.extrair_prazo_meses("pelo prazo de 24 (vinte e quatro) meses")
    assert res.valor == 24
    assert res.confianca == CONF_ALTA


def test_prazo_meses_por_extenso():
    res = R.extrair_prazo_meses("prazo de vinte e quatro meses")
    assert res.valor == 24
    assert res.confianca == CONF_MEDIA


def test_prazo_nao_confunde_com_periodicidade():
    # REGRESSÃO: prazo por extenso + reajuste "a cada 6 meses" na mesma peça.
    # O prazo é 24 (extenso, ancorado), NÃO 6 (periodicidade do reajuste).
    texto = (
        "DA VIGÊNCIA: prazo de vinte e quatro meses.\n"
        "DO REAJUSTE: correção a cada 6 meses pelo IPCA."
    )
    assert R.extrair_prazo_meses(texto).valor == 24


def test_prazo_generico_sem_ancora_e_baixa_confianca():
    # Sem a palavra "prazo": "<n> meses" isolado é sinal fraco -> revisão.
    res = R.extrair_prazo_meses("locação pactuada por 12 meses")
    assert res.valor == 12
    assert res.confianca == CONF_BAIXA
    assert not res.resolvido  # cai abaixo do limiar -> revisão manual


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("pagamento até o dia 5 de cada mês", 5),
        ("com vencimento todo dia 10", 10),
        ("todo o dia 20", 20),
    ],
)
def test_dia_vencimento(texto, esperado):
    assert R.extrair_dia_vencimento(texto).valor == esperado


def test_dia_vencimento_fora_de_faixa():
    assert not R.extrair_dia_vencimento("dia 40 de cada mês").resolvido


# --------------------------------------------------------------------------- #
# Reajuste: índice, periodicidade, automático, próximo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("reajuste pelo IPCA", "IPCA"),
        ("correção pelo IGP-M", "IGP-M"),
        ("índice INPC", "INPC"),
    ],
)
def test_indice_reajuste_valido(texto, esperado):
    assert R.extrair_indice_reajuste(texto).valor == esperado


def test_indice_reajuste_vedado_salario_minimo():
    res = R.extrair_indice_reajuste("reajuste pelo salário mínimo nacional")
    assert res.valor == "salário mínimo"


def test_indice_reajuste_vedado_moeda_estrangeira():
    res = R.extrair_indice_reajuste("reajustado pela variação cambial do dólar")
    assert res.valor == "moeda estrangeira"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("reajuste a cada 12 meses", 12),
        ("reajustado anualmente", 12),
        ("correção semestral", 6),
        ("a cada 6 meses", 6),
    ],
)
def test_periodicidade_meses(texto, esperado):
    assert R.extrair_periodicidade_meses(texto).valor == esperado


def test_reajuste_automatico_sim():
    res = R.extrair_reajuste_automatico("reajuste automático, independentemente de aviso")
    assert res.valor is True
    assert res.confianca == CONF_ALTA


def test_reajuste_automatico_nao_mencionado_marca_revisao():
    res = R.extrair_reajuste_automatico("o aluguel será corrigido pelo IPCA")
    assert res.valor is False
    assert res.confianca == CONF_BAIXA  # não mencionado != explicitamente não


def test_proximo_reajuste():
    res = R.extrair_proximo_reajuste("próximo reajuste em 03/2025")
    assert res.valor == "2025-03-01"
