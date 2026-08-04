"""Normalização e validação de CNPJ (camada domain — sem IO).

Regra de negócio central da Fase 2 (ver ADR-001 D4 e requisitos §4):
o **CNPJ normalizado** (apenas dígitos, 14 posições) é a chave de match do
portfólio. Este módulo é puro: não faz IO, não importa nada de infraestrutura.

Decisões de validação:
- ``normalizar_cnpj``: remove todos os não-dígitos e exige exatamente 14 dígitos.
  É a regra aplicada pelo modelo ``Empresa`` e pelo importador em lote.
- ``validar_dv_cnpj`` / ``calcular_dv_cnpj``: implementam o cálculo dos dois
  dígitos verificadores (algoritmo oficial da Receita Federal). Estão disponíveis
  e testados, mas **NÃO são impostos por padrão** na normalização/modelo — para
  tolerar bases legadas e dados de OCR que podem conter CNPJs com DV inconsistente
  (ver requisitos §6). Quem precisar de checagem estrita chama ``validar_dv_cnpj``.
"""
from __future__ import annotations

import re

CNPJ_LEN = 14

_NAO_DIGITO = re.compile(r"\D")

# Pesos oficiais do cálculo dos dígitos verificadores (RFB).
_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


class CNPJInvalidoError(ValueError):
    """CNPJ que não pode ser normalizado para 14 dígitos."""


def apenas_digitos(valor: str) -> str:
    """Remove tudo que não for dígito. Não valida comprimento."""
    return _NAO_DIGITO.sub("", valor or "")


def normalizar_cnpj(valor: str | int) -> str:
    """Normaliza um CNPJ para a forma canônica de 14 dígitos.

    Aceita máscaras (``00.000.000/0000-00``), espaços, ``int`` (perde zeros à
    esquerda — por isso são recompostos com ``zfill``) e strings sujas.

    Levanta ``CNPJInvalidoError`` se, após remover não-dígitos, não restarem
    exatamente 14 dígitos (ou 14 após completar zeros à esquerda de um número
    com no máximo 14 dígitos).
    """
    if valor is None:
        raise CNPJInvalidoError("CNPJ ausente (None).")

    bruto = str(valor).strip()
    digitos = apenas_digitos(bruto)

    if not digitos:
        raise CNPJInvalidoError(f"CNPJ sem dígitos: {bruto!r}.")

    # Origem numérica (ex.: célula xlsx lida como int) perde zeros à esquerda.
    # Só recompomos zeros para entrada INTEIRA: uma string já preservou seus
    # caracteres, logo uma string curta é genuinamente inválida (ex.: "123").
    if isinstance(valor, int) and not isinstance(valor, bool) and len(digitos) < CNPJ_LEN:
        digitos = digitos.zfill(CNPJ_LEN)

    if len(digitos) != CNPJ_LEN:
        raise CNPJInvalidoError(
            f"CNPJ deve ter {CNPJ_LEN} dígitos; obtido {len(digitos)} em {bruto!r}."
        )
    return digitos


def parece_cnpj(valor: str | int | None) -> bool:
    """Heurística de fallback do importador: o valor VIRA 14 dígitos sem erro?"""
    if valor is None:
        return False
    try:
        normalizar_cnpj(valor)
        return True
    except CNPJInvalidoError:
        return False


def _dv(base: str, pesos: tuple[int, ...]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def calcular_dv_cnpj(base12: str) -> str:
    """Calcula os 2 dígitos verificadores a partir dos 12 primeiros dígitos.

    Útil para gerar CNPJs sintéticos válidos em fixtures de teste e para
    validação estrita opcional.
    """
    digitos = apenas_digitos(base12)
    if len(digitos) != 12:
        raise CNPJInvalidoError(
            f"Base do CNPJ deve ter 12 dígitos; obtido {len(digitos)}."
        )
    dv1 = _dv(digitos, _PESOS_DV1)
    dv2 = _dv(digitos + dv1, _PESOS_DV2)
    return dv1 + dv2


def validar_dv_cnpj(valor: str | int) -> bool:
    """Valida os dígitos verificadores de um CNPJ (checagem estrita, opcional).

    Rejeita também CNPJs com todos os dígitos iguais (ex.: ``00000000000000``),
    que passam na aritmética do DV mas são inválidos.
    """
    try:
        cnpj = normalizar_cnpj(valor)
    except CNPJInvalidoError:
        return False
    if cnpj == cnpj[0] * CNPJ_LEN:
        return False
    return cnpj[12:] == calcular_dv_cnpj(cnpj[:12])
