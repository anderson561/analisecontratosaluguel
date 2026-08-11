"""Log de auditoria leve e permanente (infrastructure), sem regra de negócio.

Suporte ao plano de diagnóstico do painel vazio intermitente
(``.agent/specs/plano-log-auditoria-carregamento-historico.md``): registra
eventos de baixo volume — hoje, cada chamada a
``RelatorioController.carregar_historico()`` — para capturar evidência real
(contagem carregada, erros) na próxima ocorrência do bug, já que a falha não
foi reproduzível sob controle.

Fora de escopo (YAGNI, ver plano): rotação/limite de tamanho do arquivo e
exibição do log na UI — é uma ferramenta de diagnóstico para o PM, não uma
feature de usuário final.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from contract_parser.config import settings


def registrar_evento(mensagem: str, *, log_path: str | None = None) -> None:
    """Acrescenta uma linha "``<timestamp ISO UTC>`` ``<mensagem>``" ao log.

    Usa ``settings.log_path`` quando ``log_path`` não é informado. Cria o
    diretório pai se ausente.

    NUNCA lança: falha de log (disco cheio, permissão negada, caminho
    inválido/não gravável etc.) é engolida silenciosamente — mesmo princípio
    de degradação graciosa já usado em ``infrastructure/database.py::check_health``
    (uma falha ao AUDITAR não pode derrubar a UI).
    """
    destino = Path(log_path if log_path is not None else settings.log_path)
    timestamp = datetime.now(UTC).isoformat()
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as arquivo:
            arquivo.write(f"{timestamp} {mensagem}\n")
    except Exception:  # noqa: BLE001, S110 - degradacao graciosa: nunca propagar
        pass
