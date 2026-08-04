"""Contratos (interfaces) de repositório — camada domain, sem IO.

O domínio depende de **abstração**, não de pymongo (ADR-001: repositórios
abstraem o MongoDB). A infraestrutura (``EmpresaRepository``) implementa este
Protocol; os testes usam um fake in-memory. Isso permite trocar o banco sem
tocar em ``application``/``domain`` (Dependency Inversion / SOLID).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from contract_parser.domain.empresa import Empresa


@runtime_checkable
class EmpresaRepositoryProtocol(Protocol):
    """Persistência de :class:`Empresa`, endereçada por CNPJ normalizado."""

    def add(self, empresa: Empresa) -> Empresa:
        """Insere uma empresa. Deve falhar se o CNPJ já existir."""
        ...

    def get_by_cnpj(self, cnpj: str) -> Empresa | None:
        """Busca por CNPJ (normalizado internamente). ``None`` se ausente."""
        ...

    def list_all(self) -> list[Empresa]:
        """Lista todas as empresas persistidas."""
        ...

    def update(self, empresa: Empresa) -> Empresa:
        """Atualiza uma empresa existente (match por CNPJ)."""
        ...

    def remove(self, cnpj: str) -> bool:
        """Remove por CNPJ. Retorna ``True`` se algo foi removido."""
        ...

    def upsert_many(self, empresas: list[Empresa]) -> int:
        """Insere/atualiza em lote, idempotente por CNPJ. Retorna nº processado."""
        ...
