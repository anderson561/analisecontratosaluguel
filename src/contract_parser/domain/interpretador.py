"""Contrato (Protocol) do interpretador de cláusulas ambíguas — domain, sem IO.

Peça central do **D1 híbrido** (ADR-001): as regras determinísticas resolvem os
campos objetivos; o que sobra ambíguo é delegado a um :class:`InterpretadorClausula`.

⚠️ Decisão de provedor de LLM está **adiada por LGPD** — o domínio define apenas
*o quê* (a interface); *como* (qual LLM, se algum) fica atrás desta abstração. A
implementação de produção é um stub que falha explicitamente
(``infrastructure.llm_interpreter``); os testes injetam um FAKE. O orquestrador
só recorre ao interpretador quando a regra não resolve com confiança suficiente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PedidoInterpretacao:
    """Entrada para o interpretador: qual campo, o trecho e o contexto já extraído.

    ``texto`` é o recorte de cláusula relevante (não o contrato inteiro — minimiza
    o que seria enviado a um LLM, aderente à minimização da LGPD). ``contexto``
    traz campos já resolvidos pelas regras, úteis para desambiguação.
    """

    campo: str
    texto: str
    contexto: dict[str, Any]


@dataclass(frozen=True)
class ResultadoInterpretacao:
    """Saída do interpretador: valor inferido, confiança e justificativa."""

    valor: Any | None
    confianca: float
    justificativa: str = ""


@runtime_checkable
class InterpretadorClausula(Protocol):
    """Backend plugável de interpretação semântica de cláusulas ambíguas."""

    def interpretar(self, pedido: PedidoInterpretacao) -> ResultadoInterpretacao:
        """Infere o valor de um campo ambíguo a partir do trecho e do contexto."""
        ...
