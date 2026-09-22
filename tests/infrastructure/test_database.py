"""Testes unitarios da camada de conexao SQLite.

Rodam sempre contra ``sqlite3.connect(":memory:")`` — SQLite e embarcado na
stdlib, entao nao ha skip condicional nem dependencia de servico externo
(ADR-002: efeito colateral positivo da migracao MongoDB -> SQLite).
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from contract_parser.infrastructure import database
from contract_parser.infrastructure.database import (
    HealthResult,
    RepositoryError,
    check_health,
    get_connection,
    init_schema,
    reset_connection,
)


def test_check_health_ok_com_conexao_injetada():
    conn = sqlite3.connect(":memory:")
    try:
        result = check_health(conn=conn)

        assert isinstance(result, HealthResult)
        assert result.ok is True
        assert "select 1" in result.detalhe.lower()
    finally:
        conn.close()


def test_check_health_falha_com_conexao_fechada():
    conn = sqlite3.connect(":memory:")
    conn.close()

    result = check_health(conn=conn)

    assert result.ok is False
    assert "inacessivel" in result.detalhe.lower()
    # nao deve vazar excecao
    assert isinstance(result, HealthResult)


def test_check_health_falha_generica_nao_propaga():
    conn = MagicMock()
    conn.execute.side_effect = RuntimeError("boom inesperado")

    result = check_health(conn=conn)

    assert result.ok is False
    assert "inesperada" in result.detalhe.lower()


def test_check_health_usa_get_connection_quando_sem_argumento():
    fake_conn = sqlite3.connect(":memory:")
    try:
        with patch.object(database, "get_connection", return_value=fake_conn) as mock_get:
            result = check_health()

        assert result.ok is True
        mock_get.assert_called_once()
    finally:
        fake_conn.close()


def test_init_schema_cria_tabelas_empresas_e_tabela_irrf():
    conn = sqlite3.connect(":memory:")
    try:
        init_schema(conn)

        cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tabelas = {row[0] for row in cur.fetchall()}
        assert "empresas" in tabelas
        assert "tabela_irrf" in tabelas
    finally:
        conn.close()


def test_init_schema_e_idempotente():
    conn = sqlite3.connect(":memory:")
    try:
        init_schema(conn)
        init_schema(conn)  # segunda chamada nao deve levantar nem duplicar

        cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tabelas = [row[0] for row in cur.fetchall()]
        assert tabelas.count("empresas") == 1
        assert tabelas.count("tabela_irrf") == 1
    finally:
        conn.close()


def test_init_schema_cria_indice_processado_em():
    conn = sqlite3.connect(":memory:")
    try:
        init_schema(conn)

        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_contratos_processado_em'"
        )
        assert cur.fetchone() is not None
    finally:
        conn.close()


def test_init_schema_envolve_erro_sqlite_em_repository_error():
    conn = sqlite3.connect(":memory:")
    conn.close()

    try:
        init_schema(conn)
    except RepositoryError as exc:
        assert "schema" in str(exc).lower()
    else:  # pragma: no cover - falha do teste, nao do codigo
        raise AssertionError("init_schema deveria levantar RepositoryError em conexao fechada")


def test_get_connection_e_singleton(tmp_path):
    caminho = str(tmp_path / "singleton.db")
    reset_connection()
    with patch.object(database, "settings", SimpleNamespace(database_path=caminho)):
        try:
            c1 = get_connection()
            c2 = get_connection()
            assert c1 is c2
        finally:
            reset_connection()


def test_get_connection_com_path_explicito_nao_vira_singleton(tmp_path):
    caminho = str(tmp_path / "ad_hoc.db")
    reset_connection()
    with patch.object(database, "settings", SimpleNamespace(database_path=caminho)):
        try:
            ad_hoc = get_connection(database_path=":memory:")
            singleton = get_connection()
            assert ad_hoc is not singleton
        finally:
            ad_hoc.close()
            reset_connection()


def test_get_connection_aplica_pragma_foreign_keys():
    conn = get_connection(database_path=":memory:")
    try:
        cur = conn.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_get_connection_usa_row_factory():
    conn = get_connection(database_path=":memory:")
    try:
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_get_connection_aplica_pragma_journal_mode_wal(tmp_path):
    # ":memory:" nao suporta WAL (sempre reporta "memory"), entao precisa de
    # um arquivo real para validar o pragma persistido pela conexao.
    caminho = str(tmp_path / "wal.db")
    conn = get_connection(database_path=caminho)
    try:
        cur = conn.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_get_connection_aplica_pragma_busy_timeout():
    conn = get_connection(database_path=":memory:")
    try:
        cur = conn.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 5000
    finally:
        conn.close()


def test_get_connection_cria_diretorio_pai(tmp_path):
    caminho = tmp_path / "subdir" / "novo.db"
    assert not caminho.parent.exists()

    conn = get_connection(database_path=str(caminho))
    try:
        assert caminho.parent.exists()
    finally:
        conn.close()


def test_reset_connection_fecha_e_descarta(tmp_path):
    caminho = str(tmp_path / "reset.db")
    reset_connection()
    with patch.object(database, "settings", SimpleNamespace(database_path=caminho)):
        conn = get_connection()
        reset_connection()

    assert database._connection is None
    # a conexao antiga foi fechada: qualquer uso deve falhar
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        pass
    else:  # pragma: no cover - falha do teste, nao do codigo
        raise AssertionError("conexao deveria estar fechada apos reset_connection")


def test_reset_connection_idempotente():
    reset_connection()
    # segunda chamada nao deve levantar
    reset_connection()
