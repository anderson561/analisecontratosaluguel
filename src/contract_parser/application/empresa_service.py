"""Serviço de aplicação para gestão manual de empresas (CRUD).

Caso de uso consumível pela futura GUI (CustomTkinter). Orquestra o domínio
(``Empresa``) e depende apenas da **abstração** de repositório
(``EmpresaRepositoryProtocol``) — nunca de pymongo. Não importa ``presentation``.
"""
from __future__ import annotations

from contract_parser.domain.cnpj import normalizar_cnpj
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.repositories import EmpresaRepositoryProtocol


class EmpresaService:
    """Casos de uso de gestão manual de empresas (add/edit/remove/list)."""

    def __init__(self, repository: EmpresaRepositoryProtocol) -> None:
        self._repo = repository

    def adicionar(
        self,
        cnpj: str,
        razao_social: str,
        *,
        aliases: list[str] | None = None,
        nomes_fantasia: list[str] | None = None,
        ativo: bool = True,
        origem_import: str | None = "manual",
    ) -> Empresa:
        """Cria e persiste uma empresa. Validação/normalização via modelo."""
        empresa = Empresa(
            cnpj=cnpj,
            razao_social=razao_social,
            aliases=aliases or [],
            nomes_fantasia=nomes_fantasia or [],
            ativo=ativo,
            origem_import=origem_import,
        )
        return self._repo.add(empresa)

    def editar(
        self,
        cnpj: str,
        *,
        razao_social: str | None = None,
        aliases: list[str] | None = None,
        nomes_fantasia: list[str] | None = None,
        ativo: bool | None = None,
    ) -> Empresa:
        """Edita campos de uma empresa existente (match por CNPJ).

        Levanta ``KeyError`` se o CNPJ não existir. ``created_at`` é preservado.
        """
        chave = normalizar_cnpj(cnpj)
        atual = self._repo.get_by_cnpj(chave)
        if atual is None:
            raise KeyError(f"Empresa com CNPJ {chave} não encontrada.")

        atualizado = atual.model_copy(
            update={
                "razao_social": razao_social if razao_social is not None else atual.razao_social,
                "aliases": aliases if aliases is not None else atual.aliases,
                "nomes_fantasia": (
                    nomes_fantasia if nomes_fantasia is not None else atual.nomes_fantasia
                ),
                "ativo": ativo if ativo is not None else atual.ativo,
            }
        )
        # Revalida via construtor (model_copy não roda validators).
        atualizado = Empresa(**atualizado.model_dump())
        return self._repo.update(atualizado)

    def remover(self, cnpj: str) -> bool:
        """Remove uma empresa por CNPJ. Retorna ``True`` se removeu."""
        return self._repo.remove(normalizar_cnpj(cnpj))

    def listar(self) -> list[Empresa]:
        """Lista todas as empresas."""
        return self._repo.list_all()

    def obter(self, cnpj: str) -> Empresa | None:
        """Obtém uma empresa por CNPJ (ou ``None``)."""
        return self._repo.get_by_cnpj(normalizar_cnpj(cnpj))
