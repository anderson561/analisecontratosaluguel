"""Fakes de teste: repositório in-memory e coleção pymongo simulada.

- ``FakeEmpresaRepository``: implementa ``EmpresaRepositoryProtocol`` em memória.
  Usado nos testes de application (service/importer) e no cenário CA-01, sem
  qualquer dependência de pymongo/MongoDB.
- ``FakeCollection``: emula o subconjunto da API de ``pymongo.Collection`` usado
  por ``EmpresaRepository`` (insert_one/find_one/find/replace_one/delete_one/
  bulk_write), permitindo testar a infraestrutura sem um Mongo vivo.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pymongo.errors import DuplicateKeyError

from contract_parser.domain.cnpj import normalizar_cnpj
from contract_parser.domain.documento_texto import DocumentoTexto
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.extracao import ResultadoOcr


class FakeEmpresaRepository:
    """Repositório in-memory que satisfaz ``EmpresaRepositoryProtocol``."""

    def __init__(self) -> None:
        self._store: dict[str, Empresa] = {}

    def add(self, empresa: Empresa) -> Empresa:
        if empresa.cnpj in self._store:
            raise ValueError(f"CNPJ {empresa.cnpj} já existe.")
        self._store[empresa.cnpj] = empresa
        return empresa

    def get_by_cnpj(self, cnpj: str) -> Empresa | None:
        return self._store.get(normalizar_cnpj(cnpj))

    def list_all(self) -> list[Empresa]:
        return list(self._store.values())

    def update(self, empresa: Empresa) -> Empresa:
        self._store[empresa.cnpj] = empresa
        return empresa

    def remove(self, cnpj: str) -> bool:
        return self._store.pop(normalizar_cnpj(cnpj), None) is not None

    def upsert_many(self, empresas: list[Empresa]) -> int:
        for e in empresas:
            self._store[e.cnpj] = e
        return len(empresas)


class FakeCollection:
    """Emulação in-memory de ``pymongo.Collection`` (chave natural ``_id``)."""

    def __init__(self) -> None:
        self.store: dict[Any, dict] = {}

    def insert_one(self, doc: dict) -> SimpleNamespace:
        _id = doc["_id"]
        if _id in self.store:
            raise DuplicateKeyError(f"duplicate _id {_id}")
        self.store[_id] = dict(doc)
        return SimpleNamespace(inserted_id=_id)

    def find_one(self, flt: dict) -> dict | None:
        doc = self.store.get(flt.get("_id"))
        return dict(doc) if doc is not None else None

    def find(self, flt: dict | None = None) -> list[dict]:
        return [dict(d) for d in self.store.values()]

    def replace_one(self, flt: dict, doc: dict, upsert: bool = False) -> SimpleNamespace:
        _id = flt["_id"]
        existed = _id in self.store
        if existed or upsert:
            self.store[_id] = dict(doc)
        return SimpleNamespace(
            matched_count=1 if existed else 0,
            modified_count=1 if existed else 0,
        )

    def delete_one(self, flt: dict) -> SimpleNamespace:
        _id = flt["_id"]
        existed = _id in self.store
        if existed:
            del self.store[_id]
        return SimpleNamespace(deleted_count=1 if existed else 0)

    def bulk_write(self, operations: list, ordered: bool = True) -> SimpleNamespace:
        upserts = 0
        for op in operations:
            flt = op._filter
            _id = flt["_id"]
            update = op._doc
            set_doc = update.get("$set", update)
            if _id not in self.store:
                upserts += 1
            base = self.store.get(_id, {})
            base.update(set_doc)
            self.store[_id] = dict(base)
        return SimpleNamespace(upserted_count=upserts, modified_count=len(operations) - upserts)


class FakeExtractor:
    """Extrator fake que satisfaz ``ExtratorTexto`` (sem tocar bibliotecas).

    - ``extensao``: extensão que este backend aceita (ex.: ``.pdf``).
    - ``resultado``: :class:`DocumentoTexto` a devolver (se dado); caso contrário
      um resultado sintético é montado por caminho.
    - ``chamadas``: registra os caminhos passados a ``extrair`` (verificação de
      roteamento por extensão).
    """

    def __init__(
        self,
        extensao: str,
        *,
        resultado: DocumentoTexto | None = None,
        texto: str = "conteudo fake",
        metodo: str = "nativo",
    ) -> None:
        self.extensao = extensao.lower()
        self._resultado = resultado
        self._texto = texto
        self._metodo = metodo
        self.chamadas: list[Path] = []

    def aceita(self, caminho: Path) -> bool:
        return caminho.suffix.lower() == self.extensao

    def extrair(self, caminho: Path) -> DocumentoTexto:
        self.chamadas.append(caminho)
        if self._resultado is not None:
            return self._resultado
        return DocumentoTexto(
            caminho=str(caminho),
            hash=f"hash-{caminho.name}",
            texto=self._texto,
            metodo=self._metodo,  # type: ignore[arg-type]
        )


class FakeOcr:
    """Motor de OCR fake (implementa ``OcrEngine``) sem exigir Tesseract.

    Devolve ``resultado`` fixo e registra em ``chamadas`` os bytes recebidos —
    permite verificar que a rota nativo→OCR foi de fato acionada.
    """

    def __init__(self, resultado: ResultadoOcr | None = None) -> None:
        self._resultado = resultado or ResultadoOcr(
            texto="texto reconhecido por ocr", paginas=1, baixa_confianca=True
        )
        self.chamadas: list[bytes] = []

    def reconhecer(self, dados: bytes) -> ResultadoOcr:
        self.chamadas.append(dados)
        return self._resultado
