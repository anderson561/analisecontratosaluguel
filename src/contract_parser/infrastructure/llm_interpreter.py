"""Stub de produção do interpretador de cláusulas via LLM (infrastructure).

Implementa o Protocol ``domain.interpretador.InterpretadorClausula``, mas **NÃO
integra nenhum provedor de LLM** — a decisão está adiada por LGPD (ADR-001: dados
sensíveis, minimização). Este stub existe para:

1. documentar o ponto de extensão (onde o adaptador real será plugado); e
2. falhar de forma explícita e segura se algum código de produção tentar usá-lo
   sem que um provedor tenha sido escolhido/configurado.

O import de qualquer SDK de LLM é **preguiçoso** (dentro do método), seguindo o
padrão dos demais backends (``text_extractors``): construir o objeto nunca exige
dependências pesadas, e a suíte de testes usa um FAKE em vez deste stub.
"""
from __future__ import annotations

from contract_parser.domain.interpretador import (
    PedidoInterpretacao,
    ResultadoInterpretacao,
)


class InterpretadorLLMNaoConfigurado(NotImplementedError):
    """Sinaliza uso do interpretador de LLM antes de um provedor ser definido."""


class StubInterpretadorLLM:
    """Interpretador de produção placeholder: recusa-se a operar sem provedor.

    Satisfaz o Protocol ``InterpretadorClausula`` para permitir a injeção de
    dependência, mas ``interpretar`` sempre levanta — o orquestrador híbrido,
    quando recebe este stub (ou ``None``), simplesmente marca o campo ambíguo
    para revisão manual em vez de quebrar.
    """

    def __init__(self, *, provedor: str = "", api_key: str = "") -> None:
        self._provedor = provedor
        self._api_key = api_key

    def interpretar(self, pedido: PedidoInterpretacao) -> ResultadoInterpretacao:
        # Import preguiçoso do (futuro) SDK ficaria aqui, guardado por provedor.
        raise InterpretadorLLMNaoConfigurado(
            "Interpretação por LLM indisponível: provedor não definido "
            "(decisão adiada por LGPD). Campo ambíguo permanece para revisão manual."
        )
