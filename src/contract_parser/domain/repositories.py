"""Contratos (interfaces) de repositório — camada domain, sem IO.

O domínio depende de **abstração**, não de pymongo (ADR-001: repositórios
abstraem o MongoDB). A infraestrutura (``EmpresaRepository``) implementa este
Protocol; os testes usam um fake in-memory. Isso permite trocar o banco sem
tocar em ``application``/``domain`` (Dependency Inversion / SOLID).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from contract_parser.domain.contrato import Contrato
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.registro_contrato import RegistroContrato
from contract_parser.domain.relatorio import LinhaContrato


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


@runtime_checkable
class ContratoRepositoryProtocol(Protocol):
    """Persistência de :class:`RegistroContrato`, endereçada por ``id``.

    ``salvar`` é um *upsert* por ``arquivo_hash`` (ver plano §2): reprocessar o
    mesmo arquivo atualiza o registro existente (mesmo ``id``) em vez de
    duplicar. As demais operações endereçam por ``id``.
    """

    def salvar(
        self,
        *,
        arquivo_nome: str,
        arquivo_hash: str,
        contrato: Contrato,
        linha: LinhaContrato,
        revisao: bool,
    ) -> RegistroContrato:
        """Insere um novo registro ou atualiza o existente com o mesmo hash."""
        ...

    def listar(self) -> list[RegistroContrato]:
        """Lista todos os contratos persistidos (mais recentes primeiro)."""
        ...

    def buscar_por_hash(self, arquivo_hash: str) -> RegistroContrato | None:
        """Busca por ``arquivo_hash``. ``None`` se ausente."""
        ...

    def excluir(self, id: str) -> bool:
        """Remove por ``id``. Retorna ``True`` se algo foi removido."""
        ...

    def excluir_todos(self) -> int:
        """Remove todos os registros. Retorna a quantidade removida."""
        ...
