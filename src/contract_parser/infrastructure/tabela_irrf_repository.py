"""Repositório SQLite da tabela ``tabela_irrf`` (camada infrastructure).

Persiste as tabelas progressivas do IRRF **versionadas por ``vigencia``** (D5 do
ADR-001: corretude fiscal, tabela data-driven, nunca hardcoded na aplicação). A
conexão é **injetável** no construtor (mesmo padrão de ``empresa_repository`` e
``database``, ver ADR-002): produção resolve via ``get_connection``; testes
injetam ``sqlite3.connect(":memory:")``.

Chave natural: a ``vigencia`` (ex.: ``"2026"``) é ``PRIMARY KEY`` da tabela,
tornando o ``upsert`` idempotente via ``INSERT ... ON CONFLICT(vigencia) DO
UPDATE`` sem índice extra.
"""
from __future__ import annotations

import json
import sqlite3

from contract_parser.domain.irrf import TabelaIRRF
from contract_parser.infrastructure.database import (
    RepositoryError,
    get_connection,
    init_schema,
)

TABLE_NAME = "tabela_irrf"


def _to_row(tabela: TabelaIRRF) -> dict:
    """Serializa a tabela para os parâmetros de uma linha da tabela.

    Usa ``mode="json"`` para converter ``Decimal``→str e ``date``→ISO, evitando
    surpresas de tipo no SQLite e mantendo o round-trip determinístico — mesma
    estratégia de serialização já usada no round-trip Mongo.
    """
    dados = tabela.model_dump(mode="json")
    return {
        "vigencia": tabela.vigencia,
        "faixas": json.dumps(dados["faixas"], ensure_ascii=False),
        "fonte_url": tabela.fonte_url,
        "base_legal": tabela.base_legal,
        "validado": int(tabela.validado),
        "validado_em": dados["validado_em"],
    }


def _from_row(row: sqlite3.Row) -> TabelaIRRF:
    """Reidrata a :class:`TabelaIRRF` a partir de uma linha da tabela."""
    dados = {
        "vigencia": row["vigencia"],
        "faixas": json.loads(row["faixas"]),
        "fonte_url": row["fonte_url"],
        "base_legal": row["base_legal"],
        "validado": bool(row["validado"]),
        "validado_em": row["validado_em"],
    }
    return TabelaIRRF(**dados)


class TabelaIRRFRepository:
    """Repositório da tabela ``tabela_irrf`` (versionada por ``vigencia``).

    Parameters
    ----------
    conn:
        Conexão ``sqlite3`` (ou compatível) injetada. Se ``None``, resolve a
        conexão real de produção via :func:`get_connection` (singleton de
        processo). Em ambos os casos, ``init_schema`` é aplicado — idempotente.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn if conn is not None else get_connection()
        # Garante leitura por nome de coluna independentemente de quem abriu a
        # conexão (produção via get_connection já define; testes que injetam
        # sqlite3.connect(":memory:") cru, não).
        self._conn.row_factory = sqlite3.Row
        init_schema(self._conn)

    def upsert(self, tabela: TabelaIRRF) -> TabelaIRRF:
        """Insere/atualiza a tabela por ``vigencia`` (idempotente)."""
        row = _to_row(tabela)
        try:
            self._conn.execute(
                """
                INSERT INTO tabela_irrf
                    (vigencia, faixas, fonte_url, base_legal, validado, validado_em)
                VALUES
                    (:vigencia, :faixas, :fonte_url, :base_legal, :validado, :validado_em)
                ON CONFLICT(vigencia) DO UPDATE SET
                    faixas = excluded.faixas,
                    fonte_url = excluded.fonte_url,
                    base_legal = excluded.base_legal,
                    validado = excluded.validado,
                    validado_em = excluded.validado_em
                """,
                row,
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao gravar tabela IRRF {tabela.vigencia}: {exc}"
            ) from exc
        return tabela

    def get_por_vigencia(self, vigencia: str) -> TabelaIRRF | None:
        """Busca a tabela de uma vigência específica. ``None`` se ausente."""
        try:
            cur = self._conn.execute(
                "SELECT * FROM tabela_irrf WHERE vigencia = ?", (vigencia,)
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao buscar tabela IRRF {vigencia}: {exc}"
            ) from exc
        return _from_row(row) if row is not None else None

    def get_vigente(self) -> TabelaIRRF | None:
        """Retorna a tabela de maior ``vigencia`` persistida (a mais recente).

        A ``vigencia`` é um ano em texto ("2026"), então a ordenação lexicográfica
        (``ORDER BY vigencia DESC``) coincide com a cronológica no formato usado.
        ``None`` se a tabela estiver vazia.
        """
        try:
            cur = self._conn.execute(
                "SELECT * FROM tabela_irrf ORDER BY vigencia DESC LIMIT 1"
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao buscar tabela IRRF vigente: {exc}"
            ) from exc
        return _from_row(row) if row is not None else None

    def list_all(self) -> list[TabelaIRRF]:
        """Lista todas as tabelas persistidas (ordem determinística por vigência)."""
        try:
            cur = self._conn.execute("SELECT * FROM tabela_irrf ORDER BY vigencia ASC")
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise RepositoryError(f"Falha ao listar tabelas IRRF: {exc}") from exc
        return [_from_row(r) for r in rows]
