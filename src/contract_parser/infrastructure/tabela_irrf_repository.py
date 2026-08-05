"""Repositório MongoDB da coleção ``tabela_irrf`` (camada infrastructure).

Persiste as tabelas progressivas do IRRF **versionadas por ``vigencia``** (D5 do
ADR-001: corretude fiscal, tabela data-driven, nunca hardcoded na aplicação). A
coleção é **injetável** no construtor (mesmo padrão de ``empresa_repository`` e
``database``): produção resolve via ``get_client``; testes injetam uma
``FakeCollection``/``MagicMock``.

Chave natural: a ``vigencia`` (ex.: ``"2026"``) é usada como ``_id`` do
documento, tornando o ``upsert`` idempotente sem índice extra.
"""
from __future__ import annotations

from pymongo.collection import Collection

from contract_parser.config import settings
from contract_parser.domain.irrf import TabelaIRRF
from contract_parser.infrastructure.database import get_client

COLLECTION_NAME = "tabela_irrf"


def _to_document(tabela: TabelaIRRF) -> dict:
    """Serializa a tabela para documento Mongo (``vigencia`` vira ``_id``).

    Usa ``mode="json"`` para converter ``Decimal``→str e ``date``→ISO, evitando
    surpresas de codec do BSON (Decimal128) e mantendo o round-trip determinístico.
    """
    doc = tabela.model_dump(mode="json")
    doc["_id"] = tabela.vigencia
    return doc


def _from_document(doc: dict) -> TabelaIRRF:
    """Reidrata a tabela a partir do documento Mongo (ignora ``_id`` redundante)."""
    dados = {k: v for k, v in doc.items() if k != "_id"}
    return TabelaIRRF(**dados)


def get_tabela_irrf_collection(db_name: str | None = None) -> Collection:
    """Resolve a coleção ``tabela_irrf`` no banco configurado (singleton de client)."""
    client = get_client()
    nome = db_name if db_name is not None else settings.mongo_db
    return client[nome][COLLECTION_NAME]


class TabelaIRRFRepository:
    """Repositório da coleção ``tabela_irrf`` (versionada por ``vigencia``).

    Parameters
    ----------
    collection:
        Coleção pymongo (ou compatível) injetada. Se ``None``, resolve a coleção
        real de produção via :func:`get_tabela_irrf_collection`.
    """

    def __init__(self, collection: Collection | None = None) -> None:
        self._collection = (
            collection if collection is not None else get_tabela_irrf_collection()
        )

    def upsert(self, tabela: TabelaIRRF) -> TabelaIRRF:
        """Insere/atualiza a tabela por ``vigencia`` (idempotente)."""
        doc = _to_document(tabela)
        self._collection.replace_one({"_id": tabela.vigencia}, doc, upsert=True)
        return tabela

    def get_por_vigencia(self, vigencia: str) -> TabelaIRRF | None:
        """Busca a tabela de uma vigência específica. ``None`` se ausente."""
        doc = self._collection.find_one({"_id": vigencia})
        return _from_document(doc) if doc else None

    def get_vigente(self) -> TabelaIRRF | None:
        """Retorna a tabela de maior ``vigencia`` persistida (a mais recente).

        A ``vigencia`` é um ano em texto ("2026"), então a ordenação lexicográfica
        coincide com a cronológica no formato usado. ``None`` se a coleção estiver
        vazia — a aplicação deve então semear a tabela oficial (factory) ou avisar.
        """
        docs = list(self._collection.find({}))
        if not docs:
            return None
        mais_recente = max(docs, key=lambda d: d["_id"])
        return _from_document(mais_recente)

    def list_all(self) -> list[TabelaIRRF]:
        """Lista todas as tabelas persistidas (ordem determinística por vigência)."""
        docs = sorted(self._collection.find({}), key=lambda d: d["_id"])
        return [_from_document(d) for d in docs]
