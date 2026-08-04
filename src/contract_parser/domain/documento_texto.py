"""Modelo de resultado de extração de texto (camada domain — sem IO).

Representa a saída normalizada da ingestão de um contrato (RF02), qualquer que
seja o método usado para obtê-la (PDF nativo, OCR ou DOCX). É um DTO puro: não
importa bibliotecas pesadas (``fitz``/``pytesseract``/``python-docx``) nem toca
o sistema de arquivos — quem faz IO é a camada de infraestrutura.

Campos (ver requisitos §3–§6):
- ``caminho``: caminho de origem do arquivo (string, para rastreabilidade/log).
- ``hash``: sha256 do **conteúdo binário** do arquivo — chave de deduplicação.
- ``texto``: camada de texto extraída (pode ser vazia em falha).
- ``metodo``: como o texto foi obtido (``nativo``/``ocr``/``docx``); ``None`` se
  a extração falhou antes de produzir texto.
- ``paginas``: nº de páginas processadas (0 quando não aplicável, ex.: DOCX).
- ``baixa_confianca``: sinaliza revisão manual (ex.: OCR de baixa confiança, §6).
- ``erro``: mensagem legível quando o arquivo falhou (PDF corrompido etc.). Um
  arquivo com ``erro`` preenchido NÃO deve abortar o lote (ver §6).
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

MetodoExtracao = Literal["nativo", "ocr", "docx"]


def calcular_hash(dados: bytes) -> str:
    """Retorna o sha256 (hexdigest) do conteúdo binário — função pura.

    Usado como chave de deduplicação de arquivos na ingestão de diretório (§6).
    Depende apenas do conteúdo, então cópias com nomes diferentes colidem no hash.
    """
    return hashlib.sha256(dados).hexdigest()


class DocumentoTexto(BaseModel):
    """Resultado da extração de texto de um único arquivo de contrato.

    ``sucesso`` (derivado de ``erro is None``) é o predicado de negócio usado pela
    ingestão para separar documentos aproveitáveis de falhas registradas.
    """

    model_config = ConfigDict(extra="forbid")

    caminho: str
    hash: str
    texto: str = ""
    metodo: MetodoExtracao | None = None
    paginas: int = 0
    baixa_confianca: bool = False
    erro: str | None = None

    @property
    def sucesso(self) -> bool:
        """``True`` quando a extração produziu resultado sem erro registrado."""
        return self.erro is None
