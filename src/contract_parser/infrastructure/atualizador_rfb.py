"""Stub de produção do revalidador da tabela IRRF contra a RFB (infrastructure).

Implementa o Protocol ``domain.irrf.AtualizadorTabelaRFB``, mas **NÃO integra
rede** nesta fase. A produção real buscaria/parsearia a página oficial da RFB
(a fonte da tabela progressiva) sob demanda — o import de qualquer cliente HTTP é
**preguiçoso** (dentro do método), seguindo o padrão dos demais backends
(``text_extractors``, ``llm_interpreter``): construir o objeto nunca exige
dependências de rede, e a suíte de testes usa um FAKE em vez deste stub.

Este stub existe para:

1. documentar o ponto de extensão e a fonte oficial (``FONTE_RFB``); e
2. falhar de forma explícita e segura se algum código de produção tentar
   revalidar online antes de a integração de rede ser habilitada — a aplicação
   deve, nesse caso, cair na última tabela persistida (``TabelaIRRFRepository``)
   e avisar a data de validade (§6 dos requisitos).
"""
from __future__ import annotations

from contract_parser.domain.irrf import TabelaIRRF

FONTE_RFB = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/"
    "meu-imposto-de-renda/tabelas/2026"
)


class RevalidacaoRFBIndisponivelError(NotImplementedError):
    """Sinaliza tentativa de revalidar online antes de a rede ser habilitada."""


class StubAtualizadorTabelaRFB:
    """Revalidador de produção placeholder: recusa-se a operar sem integração.

    Satisfaz o Protocol ``AtualizadorTabelaRFB`` para permitir injeção de
    dependência. ``buscar_tabela_vigente`` sempre levanta — quem chama (a camada
    de aplicação/GUI) trata o erro caindo na última tabela persistida.
    """

    def __init__(self, *, fonte_url: str = FONTE_RFB, timeout_s: float = 10.0) -> None:
        self._fonte_url = fonte_url
        self._timeout_s = timeout_s

    def buscar_tabela_vigente(self) -> TabelaIRRF:
        # O import preguiçoso do cliente HTTP + parser da página RFB ficaria aqui,
        # guardado por configuração. Mantido desabilitado nesta fase (sem rede).
        raise RevalidacaoRFBIndisponivelError(
            "Revalidação online da tabela IRRF indisponível: integração com a "
            f"RFB ({self._fonte_url}) não habilitada nesta fase. Use a última "
            "tabela persistida (TabelaIRRFRepository.get_vigente) e avise a "
            "data de validade."
        )
