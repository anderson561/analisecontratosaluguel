"""Repositório SQLite da tabela ``empresas`` (camada infrastructure).

Implementa ``EmpresaRepositoryProtocol`` sobre ``sqlite3`` (ADR-002). A conexão
é **injetável** no construtor (mesmo padrão de injeção do ``database.py``):
produção resolve a conexão via ``get_connection``; testes injetam
``sqlite3.connect(":memory:")``.

Chave natural: o CNPJ normalizado é ``PRIMARY KEY`` da tabela, o que torna
``upsert_many`` idempotente via ``INSERT ... ON CONFLICT(cnpj) DO UPDATE`` sem
índice extra.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from contract_parser.domain.cnpj import normalizar_cnpj
from contract_parser.domain.empresa import Empresa
from contract_parser.infrastructure.database import (
    RepositoryError,
    get_connection,
    init_schema,
)

TABLE_NAME = "empresas"


class EmpresaJaExisteError(Exception):
    """Tentativa de ``add`` de um CNPJ já presente na tabela."""


def _to_row(empresa: Empresa) -> dict:
    """Serializa a empresa para os parâmetros de uma linha da tabela.

    ``aliases``/``nomes_fantasia`` (listas) viram TEXT com JSON serializado —
    mesma estratégia de composição usada para ``tabela_irrf`` (ver ADR-002 §2).
    """
    return {
        "cnpj": empresa.cnpj,
        "razao_social": empresa.razao_social,
        "aliases": json.dumps(empresa.aliases, ensure_ascii=False),
        "nomes_fantasia": json.dumps(empresa.nomes_fantasia, ensure_ascii=False),
        "ativo": int(empresa.ativo),
        "origem_import": empresa.origem_import,
        "created_at": empresa.created_at.isoformat(),
    }


def _from_row(row: sqlite3.Row) -> Empresa:
    """Reidrata uma :class:`Empresa` a partir de uma linha da tabela."""
    return Empresa(
        cnpj=row["cnpj"],
        razao_social=row["razao_social"],
        aliases=json.loads(row["aliases"]) if row["aliases"] else [],
        nomes_fantasia=json.loads(row["nomes_fantasia"]) if row["nomes_fantasia"] else [],
        ativo=bool(row["ativo"]),
        origem_import=row["origem_import"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class EmpresaRepository:
    """Repositório da tabela ``empresas``.

    Parameters
    ----------
    conn:
        Conexão ``sqlite3`` (ou compatível) injetada. Se ``None``, resolve a
        conexão real de produção via :func:`get_connection` (singleton de
        processo). Em ambos os casos, ``init_schema`` é aplicado — idempotente,
        garante que a tabela exista independentemente de quem forneceu a conexão.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn if conn is not None else get_connection()
        # Garante leitura por nome de coluna independentemente de quem abriu a
        # conexão (produção via get_connection já define; testes que injetam
        # sqlite3.connect(":memory:") cru, não).
        self._conn.row_factory = sqlite3.Row
        init_schema(self._conn)

    def add(self, empresa: Empresa) -> Empresa:
        row = _to_row(empresa)
        try:
            self._conn.execute(
                """
                INSERT INTO empresas
                    (cnpj, razao_social, aliases, nomes_fantasia, ativo,
                     origem_import, created_at)
                VALUES
                    (:cnpj, :razao_social, :aliases, :nomes_fantasia, :ativo,
                     :origem_import, :created_at)
                """,
                row,
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise EmpresaJaExisteError(
                f"Empresa com CNPJ {empresa.cnpj} já cadastrada."
            ) from exc
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao inserir empresa {empresa.cnpj}: {exc}"
            ) from exc
        return empresa

    def get_by_cnpj(self, cnpj: str) -> Empresa | None:
        try:
            cur = self._conn.execute(
                "SELECT * FROM empresas WHERE cnpj = ?", (normalizar_cnpj(cnpj),)
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise RepositoryError(f"Falha ao buscar empresa {cnpj}: {exc}") from exc
        return _from_row(row) if row is not None else None

    def list_all(self) -> list[Empresa]:
        try:
            cur = self._conn.execute("SELECT * FROM empresas")
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise RepositoryError(f"Falha ao listar empresas: {exc}") from exc
        return [_from_row(r) for r in rows]

    def update(self, empresa: Empresa) -> Empresa:
        # Não recria created_at em updates; substitui os demais campos
        # (mesma semântica do replace_one(upsert=False) de antes: nenhum efeito
        # se o CNPJ não existir).
        row = _to_row(empresa)
        try:
            self._conn.execute(
                """
                UPDATE empresas
                SET razao_social = :razao_social,
                    aliases = :aliases,
                    nomes_fantasia = :nomes_fantasia,
                    ativo = :ativo,
                    origem_import = :origem_import
                WHERE cnpj = :cnpj
                """,
                row,
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao atualizar empresa {empresa.cnpj}: {exc}"
            ) from exc
        return empresa

    def remove(self, cnpj: str) -> bool:
        try:
            cur = self._conn.execute(
                "DELETE FROM empresas WHERE cnpj = ?", (normalizar_cnpj(cnpj),)
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(f"Falha ao remover empresa {cnpj}: {exc}") from exc
        return cur.rowcount > 0

    def upsert_many(self, empresas: list[Empresa]) -> int:
        """Insere/atualiza em lote de forma idempotente por CNPJ.

        Usa ``INSERT ... ON CONFLICT(cnpj) DO UPDATE`` dentro de uma única
        transação: reexecutar com os mesmos dados não duplica linhas
        (equivalente ao ``bulk_write``/``UpdateOne(upsert=True)`` de antes).
        """
        if not empresas:
            return 0
        rows = [_to_row(e) for e in empresas]
        try:
            self._conn.executemany(
                """
                INSERT INTO empresas
                    (cnpj, razao_social, aliases, nomes_fantasia, ativo,
                     origem_import, created_at)
                VALUES
                    (:cnpj, :razao_social, :aliases, :nomes_fantasia, :ativo,
                     :origem_import, :created_at)
                ON CONFLICT(cnpj) DO UPDATE SET
                    razao_social = excluded.razao_social,
                    aliases = excluded.aliases,
                    nomes_fantasia = excluded.nomes_fantasia,
                    ativo = excluded.ativo,
                    origem_import = excluded.origem_import
                """,
                rows,
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao processar upsert em lote de empresas: {exc}"
            ) from exc
        return len(rows)
