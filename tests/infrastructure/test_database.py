"""Testes unitarios da camada de conexao MongoDB.

Nao exigem um MongoDB vivo: o pymongo/MongoClient e mockado.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from contract_parser.infrastructure import database
from contract_parser.infrastructure.database import HealthResult, check_health


def test_check_health_ok_com_client_injetado():
    client = MagicMock()
    client.admin.command.return_value = {"ok": 1.0}

    result = check_health(client=client)

    assert isinstance(result, HealthResult)
    assert result.ok is True
    assert "pong" in result.detalhe.lower()
    client.admin.command.assert_called_once_with("ping")


def test_check_health_falha_quando_pymongo_error():
    client = MagicMock()
    client.admin.command.side_effect = ServerSelectionTimeoutError("no servers")

    result = check_health(client=client)

    assert result.ok is False
    assert "inacessivel" in result.detalhe.lower()
    # nao deve vazar excecao
    assert isinstance(result, HealthResult)


def test_check_health_falha_generica_nao_propaga():
    client = MagicMock()
    client.admin.command.side_effect = RuntimeError("boom inesperado")

    result = check_health(client=client)

    assert result.ok is False
    assert "inesperada" in result.detalhe.lower()


def test_check_health_usa_get_client_quando_sem_argumento():
    fake_client = MagicMock()
    fake_client.admin.command.return_value = {"ok": 1.0}

    with patch.object(database, "get_client", return_value=fake_client) as mock_get:
        result = check_health()

    assert result.ok is True
    mock_get.assert_called_once()


def test_get_client_e_singleton():
    with patch.object(database, "MongoClient") as mock_mongo:
        mock_mongo.side_effect = lambda *a, **k: MagicMock()
        c1 = database.get_client()
        c2 = database.get_client()

    assert c1 is c2
    # MongoClient instanciado uma unica vez (singleton)
    assert mock_mongo.call_count == 1


def test_get_client_com_uri_explicita_nao_vira_singleton():
    with patch.object(database, "MongoClient") as mock_mongo:
        mock_mongo.side_effect = lambda *a, **k: MagicMock()
        ad_hoc = database.get_client(uri="mongodb://outro:27017")
        singleton = database.get_client()

    assert ad_hoc is not singleton
    assert mock_mongo.call_count == 2


def test_get_client_aplica_timeout_curto():
    with patch.object(database, "MongoClient") as mock_mongo:
        database.get_client()

    _, kwargs = mock_mongo.call_args
    assert kwargs["serverSelectionTimeoutMS"] == database.DEFAULT_SERVER_SELECTION_TIMEOUT_MS


def test_reset_client_fecha_e_descarta():
    with patch.object(database, "MongoClient") as mock_mongo:
        instancia = MagicMock()
        mock_mongo.return_value = instancia
        database.get_client()
        database.reset_client()

    instancia.close.assert_called_once()
    assert database._client is None


def test_reset_client_idempotente():
    database.reset_client()
    # segunda chamada nao deve levantar
    database.reset_client()


@pytest.mark.integration
def test_ping_mongo_real(require_mongo):
    """Integracao: exige MongoDB vivo (skip automatico via fixture require_mongo)."""
    result = check_health()
    assert result.ok is True
