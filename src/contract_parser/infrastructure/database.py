"""Camada de conexão SQLite (infraestrutura). Ver ADR-002 (D2-bis revista).

Plumbing puro: sem regra de negócio, sem dependência de application/presentation.
Lê a configuração exclusivamente de ``config.settings``.

Princípios SRE aplicados:
- ``check_health`` NUNCA lança exceção: retorna um estado estruturado. Quem chama
  decide o que fazer (degradação graciosa).
- ``reset_connection`` permite graceful shutdown / fechamento explícito do
  singleton de processo (também usado para isolar testes).
- ``RepositoryError`` é a exceção de infraestrutura agnóstica de motor: envolve
  falhas de ``sqlite3`` antes de propagar às camadas superiores. Nenhuma exceção
  de driver deve vazar para ``application``/``presentation`` (ADR-002 §2).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from contract_parser.config import settings

# Singleton de processo (reuso da conexão entre chamadas).
_connection: sqlite3.Connection | None = None


class RepositoryError(Exception):
    """Erro de infraestrutura de persistência, agnóstico do motor de banco.

    Introduzida pela migração MongoDB → SQLite (ADR-002): a camada de
    apresentação deve capturar apenas este tipo, nunca exceções específicas de
    driver (``sqlite3.Error`` hoje; ``PyMongoError`` ontem).
    """


@dataclass(frozen=True)
class HealthResult:
    """Resultado estruturado de uma checagem de saúde do banco.

    ``ok`` indica sucesso da checagem; ``detalhe`` traz mensagem legível para
    log/CLI.
    """

    ok: bool
    detalhe: str


def _abrir_conexao(database_path: str) -> sqlite3.Connection:
    """Abre uma conexão sqlite3 pronta para uso (schema à parte, ver ``init_schema``).

    Cria o diretório pai do arquivo se ausente (exceto para ``:memory:``, que não
    tem arquivo). ``check_same_thread=False`` porque a GUI (CustomTkinter) e a
    aplicação single-user podem acessar a conexão fora da thread que a criou.
    """
    if database_path != ":memory:":
        Path(database_path).resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL separa leitores de escritores: evita que a GUI (thread principal)
    # trave esperando uma escrita do processamento (thread separada) terminar,
    # e vice-versa. busy_timeout faz uma conexao aguardar um instante em vez
    # de falhar na hora com "database is locked" em contencao momentanea.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_connection(database_path: str | None = None) -> sqlite3.Connection:
    """Factory/singleton da conexão sqlite3.

    Sem ``database_path`` explícito: usa ``settings.database_path`` e reusa a
    mesma instância (singleton de processo). Com ``database_path`` explícito:
    cria uma conexão ad-hoc (útil para testes/composição alternativa) sem afetar
    o singleton.
    """
    global _connection
    if database_path is not None:
        return _abrir_conexao(database_path)
    if _connection is None:
        _connection = _abrir_conexao(settings.database_path)
    return _connection


def reset_connection() -> None:
    """Fecha e descarta o singleton. Idempotente (seguro chamar múltiplas vezes).

    Usado em graceful shutdown e para isolar testes.
    """
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def init_schema(conn: sqlite3.Connection) -> None:
    """Cria as tabelas ``empresas``, ``tabela_irrf`` e ``contratos`` se ainda
    não existirem.

    ``CREATE TABLE IF NOT EXISTS`` — idempotente, sem migração versionada
    (YAGNI, ver ADR-002). Chamada tanto pela composição de produção quanto
    pelos repositórios/testes, sem custo relevante em reexecução.
    """
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                cnpj TEXT PRIMARY KEY,
                razao_social TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]',
                nomes_fantasia TEXT NOT NULL DEFAULT '[]',
                ativo INTEGER NOT NULL DEFAULT 1,
                origem_import TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tabela_irrf (
                vigencia TEXT PRIMARY KEY,
                faixas TEXT NOT NULL,
                fonte_url TEXT NOT NULL,
                base_legal TEXT NOT NULL,
                validado INTEGER NOT NULL DEFAULT 0,
                validado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS contratos (
                id TEXT PRIMARY KEY,
                arquivo_nome TEXT NOT NULL,
                arquivo_hash TEXT NOT NULL UNIQUE,
                processado_em TEXT NOT NULL,
                revisao INTEGER NOT NULL DEFAULT 0,
                arquivo_ausente INTEGER NOT NULL DEFAULT 0,
                contrato_json TEXT NOT NULL,
                linha_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_contratos_processado_em
                ON contratos (processado_em DESC);
            """
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise RepositoryError(f"Falha ao inicializar o schema do banco: {exc}") from exc


def check_health(conn: sqlite3.Connection | None = None) -> HealthResult:
    """Testa a conexão com ``SELECT 1`` e retorna estado estruturado.

    NUNCA lança exceção. Passar ``conn`` permite injetar uma conexão específica
    (testes ou ad-hoc); sem argumento, resolve o singleton via
    :func:`get_connection`.
    """
    try:
        conexao = conn if conn is not None else get_connection()
        conexao.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        return HealthResult(
            ok=False,
            detalhe=(
                f"Banco SQLite inacessivel em {settings.database_path}: {exc}. "
                "Verifique se o caminho do arquivo existe e e gravavel."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - degradacao graciosa: nunca propagar
        return HealthResult(
            ok=False,
            detalhe=f"Falha inesperada ao checar o banco SQLite: {exc!r}",
        )
    return HealthResult(ok=True, detalhe="Banco SQLite respondeu (SELECT 1 ok).")
