"""Parsers primitivos de formatos brasileiros (camada domain — puros, sem IO).

Blocos de construção determinísticos do motor de regras (RF03): moeda pt-BR,
datas (numéricas, ``mm/aaaa`` e por extenso), inteiros por extenso e detecção de
documentos (CPF × CNPJ). Nenhuma função aqui faz IO ou depende de infraestrutura.

Determinismo (regra de ouro da skill): não há aleatoriedade; a mesma entrada
produz sempre a mesma saída.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from contract_parser.domain.cnpj import apenas_digitos

# --------------------------------------------------------------------------- #
# Moeda pt-BR: "R$ 6.000,00" / "R$ 1.234.567,89" / "R$ 600,00" / "R$ 6000"
# --------------------------------------------------------------------------- #
_RE_VALOR_BRL = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)",
    re.IGNORECASE,
)


def brl_para_decimal(bruto: str) -> Decimal | None:
    """Converte um literal monetário pt-BR ("6.000,00") em :class:`Decimal`.

    Remove separador de milhar (``.``) e troca a vírgula decimal por ponto.
    Retorna ``None`` se o texto não for conversível.
    """
    limpo = (bruto or "").strip().replace(".", "").replace(",", ".")
    if not limpo:
        return None
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return None


def encontrar_valores_brl(texto: str) -> list[Decimal]:
    """Extrai todos os valores monetários pt-BR do texto, em ordem de ocorrência."""
    valores: list[Decimal] = []
    for m in _RE_VALOR_BRL.finditer(texto or ""):
        valor = brl_para_decimal(m.group(1))
        if valor is not None:
            valores.append(valor)
    return valores


# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #
MESES_PT: dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

# Sub-padrão reutilizável (como string) para as três formas de data suportadas.
DATA_REGEX = (
    r"(?:\d{1,2}[ºo°]?\s+de\s+[A-Za-zçãéêíóôúÇÃÉÊÍÓÔÚ]+\s+de\s+\d{4}"  # 1º de março de 2024
    r"|\d{1,2}/\d{1,2}/\d{4}"  # 01/03/2024
    r"|\d{1,2}/\d{4})"  # 03/2024
)

_RE_DATA_NUMERICA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_DATA_MES_ANO = re.compile(r"\b(\d{1,2})/(\d{4})\b")
_RE_DATA_EXTENSO = re.compile(
    r"\b(\d{1,2})[ºo°]?\s+de\s+([A-Za-zçãéêíóôúÇÃÉÊÍÓÔÚ]+)\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)


def _normalizar_mes(nome: str) -> int | None:
    return MESES_PT.get(nome.strip().lower())


def parse_data(texto: str) -> date | None:
    """Interpreta a PRIMEIRA data reconhecível em ``texto``.

    Ordem de tentativa: ``dd/mm/aaaa`` → ``dd de <mês> de aaaa`` → ``mm/aaaa``.
    Em ``mm/aaaa`` assume-se o **dia 1** (a granularidade da vigência é mensal;
    ver requisitos §4). Retorna ``None`` se nada casar ou a data for inválida.
    """
    if not texto:
        return None

    m = _RE_DATA_NUMERICA.search(texto)
    if m:
        dia, mes, ano = (int(g) for g in m.groups())
        return _data_segura(ano, mes, dia)

    m = _RE_DATA_EXTENSO.search(texto)
    if m:
        dia = int(m.group(1))
        mes = _normalizar_mes(m.group(2))
        ano = int(m.group(3))
        if mes is not None:
            return _data_segura(ano, mes, dia)

    m = _RE_DATA_MES_ANO.search(texto)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
        return _data_segura(ano, mes, 1)

    return None


def _data_segura(ano: int, mes: int, dia: int) -> date | None:
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Inteiros (dígitos ou por extenso 0–31, suficiente p/ prazos/dias/meses)
# --------------------------------------------------------------------------- #
_UNIDADES = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14,
    "catorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30,
}
_DEZENAS_COMPOSTAS = {"vinte": 20, "trinta": 30}


def numero_por_extenso(texto: str) -> int | None:
    """Converte um número pequeno por extenso em ``int`` (0–39). ``None`` se não.

    Cobre "trinta", "vinte e quatro", "doze" — faixa útil para prazos em meses e
    dias de vencimento. Fora do escopo: centenas/milhares (não ocorrem nesses
    campos).
    """
    if not texto:
        return None
    limpo = texto.strip().lower()
    if limpo in _UNIDADES:
        return _UNIDADES[limpo]
    # Forma composta "vinte e quatro" / "trinta e um".
    m = re.match(r"(vinte|trinta)\s+e\s+([a-zçãêé]+)", limpo)
    if m:
        base = _DEZENAS_COMPOSTAS[m.group(1)]
        unidade = _UNIDADES.get(m.group(2))
        if unidade is not None and unidade < 10:
            return base + unidade
    return None


# --------------------------------------------------------------------------- #
# Documentos: CPF (11) × CNPJ (14)
# --------------------------------------------------------------------------- #
# CNPJ exige a barra da máscara OU 14 dígitos crus; testado ANTES do CPF porque
# um CNPJ mascarado contém uma sequência que se parece com CPF no prefixo.
# A 2ª alternativa (``\b\d{14}\b``) cobre o CNPJ SEM máscara (14 dígitos crus),
# comum em OCR/planilhas — sem ela um CNPJ não mascarado não era reconhecido
# como PJ (a 1ª alternativa exige a barra) e a dedução 11×14 dígitos falhava.
_RE_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}\b|\b\d{14}\b")
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def detectar_documento(texto: str) -> tuple[str, str] | None:
    """Encontra o primeiro documento e deduz o tipo pela estrutura.

    Retorna ``(tipo, digitos)`` com ``tipo`` em ``{"PJ", "PF"}`` e ``digitos``
    normalizado (só números), ou ``None`` se nenhum documento for reconhecido.
    A dedução é estrutural: CNPJ (14 díg./barra) → PJ; CPF (11 díg.) → PF.
    """
    if not texto:
        return None

    m = _RE_CNPJ.search(texto)
    if m:
        return "PJ", apenas_digitos(m.group(0))

    m = _RE_CPF.search(texto)
    if m:
        return "PF", apenas_digitos(m.group(0))

    return None
