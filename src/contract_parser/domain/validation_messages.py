"""Tradução de ``pydantic.ValidationError`` em mensagem legível — camada domain.

Módulo neutro (sem IO) para que tanto ``application`` (ex.: importador de
planilhas) quanto ``presentation`` (ex.: controllers da GUI) traduzam o dump
técnico bruto (``value_error``, ``input_value=``, URL ``errors.pydantic.dev``)
para uma frase amigável em pt-BR, sem duplicar a lógica nem violar a direção
de dependência das camadas (nenhuma das duas pode depender da outra).
"""
from __future__ import annotations

from pydantic import ValidationError

# Rótulos amigáveis para os campos técnicos dos modelos de domínio.
_CAMPOS_AMIGAVEIS = {
    "cnpj": "CNPJ",
    "razao_social": "Razão Social",
}

_PREFIXO_VALUE_ERROR = "Value error, "


def formatar_erro_validacao(exc: ValidationError) -> str:
    """Traduz um ``pydantic.ValidationError`` para uma frase legível em pt-BR.

    Ex.: ``"CNPJ: CNPJ sem dígitos: ''.; Razão Social: String should have at
    least 1 character"`` — sem ``type=``, ``input_value=`` ou URLs de doc.
    """
    partes = []
    for erro in exc.errors():
        campo = ".".join(str(p) for p in erro["loc"]) or "campo"
        rotulo = _CAMPOS_AMIGAVEIS.get(campo, campo)
        msg = erro["msg"].removeprefix(_PREFIXO_VALUE_ERROR)
        partes.append(f"{rotulo}: {msg}")
    return "; ".join(partes)
