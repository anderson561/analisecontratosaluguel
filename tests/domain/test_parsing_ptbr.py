"""Testes dos parsers primitivos pt-BR (moeda, datas, extenso, documentos).

Camada ``domain`` — funções puras e determinísticas (RF03). Cobrem os formatos
exigidos pelo §3/§4: moeda ``R$ 1.234,56``, datas ``dd/mm/aaaa`` e ``mm/aaaa``,
meses por extenso e a dedução PF/PJ por documento (11 × 14 dígitos).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contract_parser.domain.parsing_ptbr import (
    brl_para_decimal,
    detectar_documento,
    encontrar_valores_brl,
    numero_por_extenso,
    parse_data,
)


# --------------------------------------------------------------------------- #
# Moeda pt-BR
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("6.000,00", Decimal("6000.00")),
        ("600,00", Decimal("600.00")),
        ("6000", Decimal(6000)),
        ("1.234.567,89", Decimal("1234567.89")),
    ],
)
def test_brl_para_decimal(bruto, esperado):
    assert brl_para_decimal(bruto) == esperado


def test_brl_para_decimal_invalido_retorna_none():
    assert brl_para_decimal("") is None
    assert brl_para_decimal("abc") is None


def test_encontrar_valores_brl_em_ordem():
    texto = "aluguel de R$ 3.500,00 e multa de R$ 10.500,00 e taxa R$ 50"
    assert encontrar_valores_brl(texto) == [
        Decimal("3500.00"),
        Decimal("10500.00"),
        Decimal(50),
    ]


def test_encontrar_valores_brl_vazio():
    assert encontrar_valores_brl("sem dinheiro aqui") == []


# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("início em 01/03/2024", date(2024, 3, 1)),  # dd/mm/aaaa
        ("vigência 03/2024", date(2024, 3, 1)),  # mm/aaaa -> dia 1
        ("1º de março de 2024", date(2024, 3, 1)),  # extenso com ordinal
        ("15 de dezembro de 2025", date(2025, 12, 15)),  # extenso
        ("10 de janeiro de 2030", date(2030, 1, 10)),
        ("assinado em 5 de agosto de 2026", date(2026, 8, 5)),
    ],
)
def test_parse_data_formatos(texto, esperado):
    assert parse_data(texto) == esperado


def test_parse_data_prefere_numerica_sobre_mes_ano():
    # Havendo dd/mm/aaaa, a data completa vence a mm/aaaa.
    assert parse_data("de 01/03/2024 a 05/2024") == date(2024, 3, 1)


def test_parse_data_mes_por_extenso_todos_os_meses():
    meses = [
        ("janeiro", 1), ("fevereiro", 2), ("março", 3), ("abril", 4),
        ("maio", 5), ("junho", 6), ("julho", 7), ("agosto", 8),
        ("setembro", 9), ("outubro", 10), ("novembro", 11), ("dezembro", 12),
    ]
    for nome, num in meses:
        assert parse_data(f"1 de {nome} de 2027") == date(2027, num, 1)


def test_parse_data_invalida_retorna_none():
    assert parse_data("31/02/2024") is None  # 31 de fevereiro não existe
    assert parse_data("sem data") is None
    assert parse_data("") is None


# --------------------------------------------------------------------------- #
# Inteiros por extenso
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("doze", 12),
        ("trinta", 30),
        ("vinte e quatro", 24),
        ("trinta e um", 31),
        ("cinco", 5),
    ],
)
def test_numero_por_extenso(texto, esperado):
    assert numero_por_extenso(texto) == esperado


def test_numero_por_extenso_fora_de_escopo():
    assert numero_por_extenso("cento e vinte") is None
    assert numero_por_extenso("") is None


# --------------------------------------------------------------------------- #
# Documentos: dedução PF (11) × PJ (14)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        # CPF (11 dígitos) -> PF, mascarado e cru
        ("CPF 123.456.789-09", ("PF", "12345678909")),
        ("CPF 12345678909", ("PF", "12345678909")),
        # CNPJ (14 dígitos) -> PJ, mascarado e cru
        ("CNPJ 11.222.333/0001-81", ("PJ", "11222333000181")),
        ("CNPJ 12345678000190", ("PJ", "12345678000190")),
    ],
)
def test_detectar_documento_pf_pj(texto, esperado):
    assert detectar_documento(texto) == esperado


def test_detectar_documento_prioriza_cnpj_sobre_cpf():
    # Um CNPJ mascarado contém prefixo parecido com CPF; deve deduzir PJ.
    assert detectar_documento("inscrita no CNPJ 45.566.778/0001-09") == (
        "PJ",
        "45566778000109",
    )


def test_detectar_documento_ausente():
    assert detectar_documento("nenhum documento aqui") is None
    assert detectar_documento("") is None
