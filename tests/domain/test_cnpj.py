"""Testes unitários de normalização e validação de CNPJ (domain puro)."""
from __future__ import annotations

import pytest

from contract_parser.domain.cnpj import (
    CNPJInvalidoError,
    calcular_dv_cnpj,
    normalizar_cnpj,
    parece_cnpj,
    validar_dv_cnpj,
)


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("11.222.333/0001-81", "11222333000181"),
        ("  11222333000181  ", "11222333000181"),
        ("11 222 333 0001 81", "11222333000181"),
        ("11.222.333/0001-81\n", "11222333000181"),
    ],
)
def test_normalizar_cnpj_remove_mascara(entrada, esperado):
    assert normalizar_cnpj(entrada) == esperado


def test_normalizar_cnpj_int_recompoe_zeros_a_esquerda():
    # int perde zeros à esquerda; devem ser recompostos para 14 dígitos.
    assert normalizar_cnpj(11222333000181) == "11222333000181"
    assert normalizar_cnpj(12345678000195) == "12345678000195"
    # CNPJ que começa com zero, lido como número (célula xlsx numérica).
    assert normalizar_cnpj(222333000181) == "00222333000181"


def test_normalizar_cnpj_string_numerica_curta_e_invalida():
    # Uma STRING já preservou seus caracteres → 12 dígitos é inválido (não é zfill).
    with pytest.raises(CNPJInvalidoError):
        normalizar_cnpj("222333000181")


@pytest.mark.parametrize("ruim", ["", "   ", "abc", "123", "1" * 15, None])
def test_normalizar_cnpj_invalido_levanta(ruim):
    with pytest.raises(CNPJInvalidoError):
        normalizar_cnpj(ruim)


def test_parece_cnpj():
    assert parece_cnpj("11.222.333/0001-81") is True
    assert parece_cnpj("00222333000181") is True
    assert parece_cnpj("nao-cnpj") is False
    assert parece_cnpj(None) is False


def test_calcular_dv_cnpj():
    assert calcular_dv_cnpj("112223330001") == "81"


def test_calcular_dv_cnpj_base_invalida():
    with pytest.raises(CNPJInvalidoError):
        calcular_dv_cnpj("123")


@pytest.mark.parametrize(
    "cnpj, valido",
    [
        ("11222333000181", True),
        ("11.222.333/0001-81", True),
        ("11222333000180", False),  # DV errado
        ("11111111111111", False),  # todos iguais
        ("00000000000000", False),
        ("123", False),
    ],
)
def test_validar_dv_cnpj(cnpj, valido):
    assert validar_dv_cnpj(cnpj) is valido
