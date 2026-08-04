"""Contratos (Protocols) da extração de texto — camada domain, sem IO.

O domínio define **o que** é um extrator e um motor de OCR; a infraestrutura
implementa **como** (tocando ``fitz``/``pytesseract``/``python-docx``). Assim a
orquestração (``application``) e os testes dependem apenas destas abstrações,
podendo usar fakes sem exigir Tesseract/poppler (ver ADR-001: parsers/OCR atrás
de interfaces; Dependency Inversion / SOLID).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from contract_parser.domain.documento_texto import DocumentoTexto


@dataclass(frozen=True)
class ResultadoOcr:
    """Saída de um motor de OCR sobre um documento (resultado puro, sem IO).

    ``baixa_confianca`` sinaliza que os campos derivados devem ir para revisão
    manual (requisitos §6).
    """

    texto: str
    paginas: int
    baixa_confianca: bool


@runtime_checkable
class ExtratorTexto(Protocol):
    """Backend plugável de extração de texto de um arquivo de contrato."""

    def aceita(self, caminho: Path) -> bool:
        """Indica se este backend sabe processar o arquivo (por extensão)."""
        ...

    def extrair(self, caminho: Path) -> DocumentoTexto:
        """Extrai o texto. NÃO deve lançar por arquivo inválido: retorna um
        :class:`DocumentoTexto` com ``erro`` preenchido (o lote não aborta)."""
        ...


@runtime_checkable
class OcrEngine(Protocol):
    """Motor de OCR que reconhece texto a partir do binário de um PDF."""

    def reconhecer(self, dados: bytes) -> ResultadoOcr:
        """Renderiza as páginas e aplica OCR, retornando texto + confiança."""
        ...
