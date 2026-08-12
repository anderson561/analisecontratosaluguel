"""Serviço de ingestão de diretório de contratos (camada application) — RF02.

Orquestra a varredura de uma pasta, a seleção do backend por extensão, a
extração de texto e a deduplicação por hash, acumulando erros por arquivo SEM
abortar o lote (requisitos §6). Depende apenas da abstração ``ExtratorTexto``
(``domain.extracao``) — nunca de ``fitz``/``pytesseract``/``python-docx``.

Espelha o padrão de ``empresa_importer`` (I/O de diretório isolado, erros por
item acumulados no resumo, resultado estruturado em vez de exceções).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contract_parser.domain.documento_texto import DocumentoTexto
from contract_parser.domain.extracao import ExtratorTexto

# Extensões suportadas na ingestão (RF02). Comparação sempre em minúsculas.
EXTENSOES_SUPORTADAS = (".pdf", ".docx")


class DiretorioIngestaoError(Exception):
    """Pasta inexistente ou caminho que não é um diretório."""


@dataclass
class ErroArquivo:
    """Erro atribuível a um arquivo específico do lote (não aborta o restante)."""

    arquivo: str
    motivo: str


@dataclass
class IngestaoResumo:
    """Resumo estruturado do resultado de uma ingestão de diretório."""

    total_arquivos: int = 0
    processados: int = 0
    duplicados: int = 0
    erros: list[ErroArquivo] = field(default_factory=list)
    documentos: list[DocumentoTexto] = field(default_factory=list)

    @property
    def total_erros(self) -> int:
        return len(self.erros)


class DirectoryIngestor:
    """Caso de uso: ingerir todos os contratos suportados de uma pasta.

    Recebe a lista de backends por injeção; a ordem define a prioridade de
    seleção (o primeiro cujo ``aceita`` retorna ``True`` processa o arquivo).
    """

    def __init__(self, extractors: list[ExtratorTexto]) -> None:
        self._extractors = list(extractors)

    def _selecionar(self, caminho: Path) -> ExtratorTexto | None:
        for extrator in self._extractors:
            if extrator.aceita(caminho):
                return extrator
        return None

    def _listar_arquivos(self, pasta: Path) -> list[Path]:
        """Arquivos suportados, em ordem determinística (case-insensitive)."""
        arquivos = [
            p
            for p in pasta.iterdir()
            if p.is_file() and p.suffix.lower() in EXTENSOES_SUPORTADAS
        ]
        return sorted(arquivos, key=lambda p: p.name.lower())

    def ingerir(self, pasta: str | Path) -> IngestaoResumo:
        """Varre ``pasta``, extrai cada contrato e deduplica por hash.

        - Seleciona o backend pela extensão (``.pdf``/``.docx``).
        - Falha de extração (PDF/DOCX corrompido, OCR) vira ``ErroArquivo`` no
          resumo — o lote continua.
        - Exceção inesperada de um backend também é capturada por arquivo.
        - Documentos idênticos (mesmo hash de conteúdo) contam como duplicados.
        """
        pasta = Path(pasta)
        if not pasta.is_dir():
            raise DiretorioIngestaoError(f"Diretório não encontrado: {pasta}")

        arquivos = self._listar_arquivos(pasta)
        resumo = self._processar(arquivos)
        resumo.total_arquivos = len(arquivos)
        return resumo

    def ingerir_arquivos(self, caminhos: list[str | Path]) -> IngestaoResumo:
        """Extrai e deduplica uma lista de arquivos escolhidos individualmente.

        Diferente de :meth:`ingerir`, não exige um diretório: cada item de
        ``caminhos`` é validado por si só (existe, é arquivo, extensão
        suportada) — caminho inválido vira ``ErroArquivo`` no resumo, sem
        abortar o lote (mesmo princípio de "erro por item não aborta" usado em
        :meth:`ingerir`/``_processar``).
        """
        resumo = IngestaoResumo()
        validos: list[Path] = []

        for item in caminhos:
            caminho = Path(item)
            resumo.total_arquivos += 1
            if not caminho.is_file():
                resumo.erros.append(ErroArquivo(caminho.name, "Arquivo não encontrado."))
                continue
            if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
                resumo.erros.append(
                    ErroArquivo(caminho.name, "Extensão de arquivo não suportada.")
                )
                continue
            validos.append(caminho)

        parcial = self._processar(validos)
        resumo.processados = parcial.processados
        resumo.duplicados = parcial.duplicados
        resumo.erros.extend(parcial.erros)
        resumo.documentos.extend(parcial.documentos)
        return resumo

    def _processar(self, arquivos: list[Path]) -> IngestaoResumo:
        """Extrai e deduplica ``arquivos`` (laço compartilhado por ``ingerir``/
        ``ingerir_arquivos``). NÃO conta ``total_arquivos`` — cada caller conta
        os arquivos com seu próprio critério (varredura de pasta vs. lista
        recebida, incluindo itens inválidos).
        """
        resumo = IngestaoResumo()
        vistos: set[str] = set()

        for caminho in arquivos:
            extrator = self._selecionar(caminho)
            if extrator is None:  # defensivo: filtro já restringe as extensões
                resumo.erros.append(
                    ErroArquivo(caminho.name, "Nenhum backend aceita esta extensão.")
                )
                continue

            try:
                documento = extrator.extrair(caminho)
            except Exception as exc:  # noqa: BLE001 - erro por arquivo não aborta o lote
                resumo.erros.append(
                    ErroArquivo(caminho.name, f"Erro inesperado na extração: {exc!r}")
                )
                continue

            if not documento.sucesso:
                resumo.erros.append(ErroArquivo(caminho.name, documento.erro or "Erro desconhecido."))
                continue

            if documento.hash in vistos:
                resumo.duplicados += 1
                continue

            vistos.add(documento.hash)
            resumo.processados += 1
            resumo.documentos.append(documento)

        return resumo
