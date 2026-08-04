"""Repositório MongoDB da coleção ``empresas`` (camada infrastructure).

Implementa ``EmpresaRepositoryProtocol`` sobre pymongo. A coleção é **injetável**
no construtor (mesmo padrão de injeção do ``database.py``): produção resolve a
coleção via ``get_client``; testes injetam um ``mongomock``/``MagicMock``.

Chave natural: o CNPJ normalizado é usado como ``_id`` do documento, o que torna
``upsert_many`` idempotente sem índice extra (o ``_id`` já é único e indexado).
"""
from __future__ import annotations

from typing import Any

from pymongo import UpdateOne
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from contract_parser.config import settings
from contract_parser.domain.cnpj import normalizar_cnpj
from contract_parser.domain.empresa import Empresa
from contract_parser.infrastructure.database import get_client

COLLECTION_NAME = "empresas"


class EmpresaJaExisteError(Exception):
    """Tentativa de ``add`` de um CNPJ já presente na coleção."""


def get_empresas_collection(db_name: str | None = None) -> Collection:
    """Resolve a coleção ``empresas`` no banco configurado (singleton de client)."""
    client = get_client()
    nome = db_name if db_name is not None else settings.mongo_db
    return client[nome][COLLECTION_NAME]


class EmpresaRepository:
    """Repositório da coleção ``empresas``.

    Parameters
    ----------
    collection:
        Coleção pymongo (ou compatível) injetada. Se ``None``, resolve a coleção
        real de produção via :func:`get_empresas_collection`.
    """

    def __init__(self, collection: Collection | None = None) -> None:
        self._collection = collection if collection is not None else get_empresas_collection()

    def add(self, empresa: Empresa) -> Empresa:
        try:
            self._collection.insert_one(empresa.to_document())
        except DuplicateKeyError as exc:
            raise EmpresaJaExisteError(
                f"Empresa com CNPJ {empresa.cnpj} já cadastrada."
            ) from exc
        return empresa

    def get_by_cnpj(self, cnpj: str) -> Empresa | None:
        doc = self._collection.find_one({"_id": normalizar_cnpj(cnpj)})
        return Empresa.from_document(doc) if doc else None

    def list_all(self) -> list[Empresa]:
        return [Empresa.from_document(doc) for doc in self._collection.find({})]

    def update(self, empresa: Empresa) -> Empresa:
        doc = empresa.to_document()
        # Não recria created_at em updates; substitui os demais campos.
        self._collection.replace_one({"_id": empresa.cnpj}, doc, upsert=False)
        return empresa

    def remove(self, cnpj: str) -> bool:
        resultado = self._collection.delete_one({"_id": normalizar_cnpj(cnpj)})
        return resultado.deleted_count > 0

    def upsert_many(self, empresas: list[Empresa]) -> int:
        """Insere/atualiza em lote de forma idempotente por CNPJ (``_id``).

        Usa ``bulk_write`` com ``UpdateOne(upsert=True)``: reexecutar com os
        mesmos dados não duplica documentos.
        """
        if not empresas:
            return 0
        operacoes: list[Any] = [
            UpdateOne({"_id": e.cnpj}, {"$set": e.to_document()}, upsert=True)
            for e in empresas
        ]
        self._collection.bulk_write(operacoes, ordered=False)
        return len(operacoes)
