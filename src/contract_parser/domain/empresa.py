"""Modelo de domínio ``Empresa`` (pydantic v2 — camada domain, sem IO).

Representa uma empresa do portfólio (coleção Mongo ``empresas``, ver plano §2).
A validação/normalização de CNPJ é delegada ao módulo ``cnpj`` (regra pura).

Campos (RF01):
- ``cnpj``: chave de match, normalizada para 14 dígitos.
- ``razao_social``: razão social (obrigatória, não vazia após strip).
- ``aliases`` / ``nomes_fantasia``: apoios ao match fuzzy futuro (RF05).
- ``ativo``: soft-flag de portfólio.
- ``origem_import``: rastreabilidade da ingestão (nome do arquivo, ``manual`` etc.).
- ``created_at``: timestamp de criação (UTC, default determinístico no construtor).
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contract_parser.domain.cnpj import normalizar_cnpj


def _utcnow() -> datetime:
    """Timestamp UTC (isolado para permitir monkeypatch determinístico em teste)."""
    return datetime.now(UTC)


class Empresa(BaseModel):
    """Empresa do portfólio imobiliário.

    ``cnpj`` é sempre persistido normalizado (14 dígitos). A igualdade de negócio
    é definida pelo CNPJ — dedup do importador e ``upsert_many`` usam essa chave.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    cnpj: str
    razao_social: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    nomes_fantasia: list[str] = Field(default_factory=list)
    ativo: bool = True
    origem_import: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("cnpj")
    @classmethod
    def _normalizar_cnpj(cls, valor: str) -> str:
        # Propaga CNPJInvalidoError (subclasse de ValueError) → pydantic ValidationError.
        return normalizar_cnpj(valor)

    @field_validator("razao_social")
    @classmethod
    def _razao_nao_vazia(cls, valor: str) -> str:
        limpo = (valor or "").strip()
        if not limpo:
            raise ValueError("razao_social não pode ser vazia.")
        return limpo

    @field_validator("aliases", "nomes_fantasia")
    @classmethod
    def _limpar_lista(cls, valores: list[str]) -> list[str]:
        # Remove vazios e duplicatas preservando ordem de primeira ocorrência.
        vistos: set[str] = set()
        resultado: list[str] = []
        for item in valores:
            limpo = (item or "").strip()
            if limpo and limpo not in vistos:
                vistos.add(limpo)
                resultado.append(limpo)
        return resultado

    def to_document(self) -> dict:
        """Serializa para documento Mongo (usa ``cnpj`` como ``_id`` natural)."""
        doc = self.model_dump()
        doc["_id"] = self.cnpj
        return doc

    @classmethod
    def from_document(cls, doc: dict) -> Empresa:
        """Reidrata a partir de um documento Mongo (ignora ``_id`` redundante)."""
        dados = {k: v for k, v in doc.items() if k != "_id"}
        return cls(**dados)
