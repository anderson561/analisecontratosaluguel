"""Camada de conexão MongoDB (infraestrutura). Ver ADR-001 (D2-bis).

Plumbing puro: sem regra de negócio, sem dependência de application/presentation.
Lê a configuração exclusivamente de ``config.settings``.

Princípios SRE aplicados:
- Timeout de seleção de servidor curto: falha rápido quando o Mongo está fora do ar
  em vez de pendurar a UI/CLI por 30s (default do pymongo).
- ``check_health`` NUNCA lança exceção: retorna um estado estruturado. Quem chama
  decide o que fazer (degradação graciosa).
- ``reset_client`` permite graceful shutdown / fechamento explícito do pool.
"""
from __future__ import annotations

from dataclasses import dataclass

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from contract_parser.config import settings

# Timeout curto (ms) de seleção de servidor. Falha rápido se o Mongo não estiver de pé.
DEFAULT_SERVER_SELECTION_TIMEOUT_MS = 2000

# Singleton de processo (reuso do pool de conexões entre chamadas).
_client: MongoClient | None = None


@dataclass(frozen=True)
class HealthResult:
    """Resultado estruturado de uma checagem de saúde do banco.

    ``ok`` indica sucesso do ping; ``detalhe`` traz mensagem legível para log/CLI.
    """

    ok: bool
    detalhe: str


def get_client(
    uri: str | None = None,
    *,
    timeout_ms: int = DEFAULT_SERVER_SELECTION_TIMEOUT_MS,
) -> MongoClient:
    """Factory/singleton do ``MongoClient``.

    Sem ``uri`` explícita: usa ``settings.mongo_uri`` e reusa a mesma instância
    (singleton de processo). Com ``uri`` explícita: cria uma conexão ad-hoc
    (útil para testes de integração) sem afetar o singleton.
    """
    global _client
    if uri is not None:
        return MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    if _client is None:
        _client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=timeout_ms)
    return _client


def reset_client() -> None:
    """Fecha e descarta o singleton. Idempotente (seguro chamar múltiplas vezes).

    Usado em graceful shutdown e para isolar testes.
    """
    global _client
    if _client is not None:
        _client.close()
        _client = None


def check_health(client: MongoClient | None = None) -> HealthResult:
    """Faz ``ping`` no MongoDB e retorna estado estruturado, sem lançar exceção.

    Passar ``client`` permite injetar um mock nos testes ou uma conexão ad-hoc.
    """
    try:
        conn = client if client is not None else get_client()
        conn.admin.command("ping")
    except PyMongoError as exc:
        return HealthResult(
            ok=False,
            detalhe=(
                f"MongoDB inacessivel em {settings.mongo_uri}: {exc}. "
                "Verifique se o servico MongoDB Community esta em execucao."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - degradacao graciosa: nunca propagar
        return HealthResult(
            ok=False,
            detalhe=f"Falha inesperada ao checar o MongoDB: {exc!r}",
        )
    return HealthResult(ok=True, detalhe="MongoDB respondeu ao ping (pong).")
