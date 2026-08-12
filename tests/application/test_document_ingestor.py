"""Testes da ingestão de diretório (application): seleção, dedup, erros, mix."""
from __future__ import annotations

import pytest

from contract_parser.application.document_ingestor import (
    DirectoryIngestor,
    DiretorioIngestaoError,
)
from contract_parser.domain.documento_texto import DocumentoTexto
from tests.support.fakes import FakeExtractor


def _tocar(pasta, *nomes):
    for nome in nomes:
        (pasta / nome).write_bytes(nome.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Seleção de backend por extensão
# --------------------------------------------------------------------------- #
def test_seleciona_backend_por_extensao(tmp_path):
    _tocar(tmp_path, "a.pdf", "b.docx")
    pdf = FakeExtractor(".pdf", metodo="nativo")
    docx = FakeExtractor(".docx", metodo="docx")

    resumo = DirectoryIngestor([pdf, docx]).ingerir(tmp_path)

    assert resumo.processados == 2
    assert [c.name for c in pdf.chamadas] == ["a.pdf"]
    assert [c.name for c in docx.chamadas] == ["b.docx"]


def test_ignora_extensoes_nao_suportadas(tmp_path):
    _tocar(tmp_path, "a.pdf", "notas.txt", "planilha.xlsx", "imagem.png")
    pdf = FakeExtractor(".pdf")

    resumo = DirectoryIngestor([pdf]).ingerir(tmp_path)

    assert resumo.total_arquivos == 1  # só o .pdf entra no lote
    assert resumo.processados == 1


# --------------------------------------------------------------------------- #
# Deduplicação por hash
# --------------------------------------------------------------------------- #
def test_deduplica_por_hash(tmp_path):
    _tocar(tmp_path, "a.pdf", "copia.pdf")
    # Backend que devolve SEMPRE o mesmo hash → segundo arquivo é duplicado.
    duplicador = FakeExtractor(
        ".pdf",
        resultado=DocumentoTexto(caminho="x", hash="MESMO_HASH", texto="t", metodo="nativo"),
    )

    resumo = DirectoryIngestor([duplicador]).ingerir(tmp_path)

    assert resumo.processados == 1
    assert resumo.duplicados == 1
    assert len(resumo.documentos) == 1


def test_arquivos_distintos_nao_sao_duplicados(tmp_path):
    _tocar(tmp_path, "a.pdf", "b.pdf")
    pdf = FakeExtractor(".pdf")  # hash sintético por nome → distintos

    resumo = DirectoryIngestor([pdf]).ingerir(tmp_path)

    assert resumo.processados == 2
    assert resumo.duplicados == 0


# --------------------------------------------------------------------------- #
# Erros por arquivo NÃO abortam o lote (requisitos §6)
# --------------------------------------------------------------------------- #
def test_erro_de_extracao_nao_aborta_lote(tmp_path):
    _tocar(tmp_path, "bom.pdf", "ruim.pdf")

    class PdfMisto:
        extensao = ".pdf"

        def aceita(self, caminho):
            return caminho.suffix.lower() == ".pdf"

        def extrair(self, caminho):
            if caminho.name == "ruim.pdf":
                return DocumentoTexto(
                    caminho=str(caminho), hash=f"h-{caminho.name}", erro="PDF corrompido"
                )
            return DocumentoTexto(
                caminho=str(caminho), hash=f"h-{caminho.name}", texto="ok", metodo="nativo"
            )

    resumo = DirectoryIngestor([PdfMisto()]).ingerir(tmp_path)

    assert resumo.processados == 1
    assert resumo.total_erros == 1
    assert resumo.erros[0].arquivo == "ruim.pdf"
    assert "corrompido" in resumo.erros[0].motivo


def test_excecao_inesperada_do_backend_e_capturada_por_arquivo(tmp_path):
    _tocar(tmp_path, "bom.pdf", "explode.pdf")

    class PdfExplosivo:
        def aceita(self, caminho):
            return caminho.suffix.lower() == ".pdf"

        def extrair(self, caminho):
            if caminho.name == "explode.pdf":
                raise RuntimeError("boom inesperado")
            return DocumentoTexto(
                caminho=str(caminho), hash=f"h-{caminho.name}", texto="ok", metodo="nativo"
            )

    resumo = DirectoryIngestor([PdfExplosivo()]).ingerir(tmp_path)

    assert resumo.processados == 1
    assert resumo.total_erros == 1
    assert resumo.erros[0].arquivo == "explode.pdf"


# --------------------------------------------------------------------------- #
# Pasta com mix de arquivos (.pdf + .docx) e cenários de fronteira
# --------------------------------------------------------------------------- #
def test_pasta_mista_pdf_e_docx(tmp_path):
    _tocar(tmp_path, "c1.pdf", "c2.docx", "c3.pdf", "leia-me.txt")
    pdf = FakeExtractor(".pdf")
    docx = FakeExtractor(".docx")

    resumo = DirectoryIngestor([pdf, docx]).ingerir(tmp_path)

    assert resumo.total_arquivos == 3
    assert resumo.processados == 3
    assert len(pdf.chamadas) == 2
    assert len(docx.chamadas) == 1


def test_pasta_vazia_retorna_resumo_zerado(tmp_path):
    resumo = DirectoryIngestor([FakeExtractor(".pdf")]).ingerir(tmp_path)
    assert resumo.total_arquivos == 0
    assert resumo.processados == 0
    assert resumo.total_erros == 0


def test_diretorio_inexistente_levanta(tmp_path):
    with pytest.raises(DiretorioIngestaoError):
        DirectoryIngestor([FakeExtractor(".pdf")]).ingerir(tmp_path / "nao_existe")


def test_caminho_que_e_arquivo_levanta(tmp_path):
    arquivo = tmp_path / "algum.pdf"
    arquivo.write_bytes(b"x")
    with pytest.raises(DiretorioIngestaoError):
        DirectoryIngestor([FakeExtractor(".pdf")]).ingerir(arquivo)


# --------------------------------------------------------------------------- #
# ingerir_arquivos: lista de arquivos individuais (em vez de varrer uma pasta)
# --------------------------------------------------------------------------- #
def test_ingerir_arquivos_arquivo_valido_unico(tmp_path):
    _tocar(tmp_path, "a.pdf")
    pdf = FakeExtractor(".pdf")

    resumo = DirectoryIngestor([pdf]).ingerir_arquivos([tmp_path / "a.pdf"])

    assert resumo.total_arquivos == 1
    assert resumo.processados == 1
    assert resumo.total_erros == 0
    assert [c.name for c in pdf.chamadas] == ["a.pdf"]


def test_ingerir_arquivos_multiplos_arquivos_validos(tmp_path):
    _tocar(tmp_path, "a.pdf", "b.docx")
    pdf = FakeExtractor(".pdf")
    docx = FakeExtractor(".docx")

    resumo = DirectoryIngestor([pdf, docx]).ingerir_arquivos(
        [tmp_path / "a.pdf", tmp_path / "b.docx"]
    )

    assert resumo.total_arquivos == 2
    assert resumo.processados == 2
    assert [c.name for c in pdf.chamadas] == ["a.pdf"]
    assert [c.name for c in docx.chamadas] == ["b.docx"]


def test_ingerir_arquivos_caminho_inexistente_vira_erro_sem_abortar(tmp_path):
    inexistente = tmp_path / "fantasma.pdf"

    resumo = DirectoryIngestor([FakeExtractor(".pdf")]).ingerir_arquivos([inexistente])

    assert resumo.total_arquivos == 1
    assert resumo.processados == 0
    assert resumo.total_erros == 1
    assert resumo.erros[0].arquivo == "fantasma.pdf"


def test_ingerir_arquivos_caminho_que_e_pasta_vira_erro(tmp_path):
    subpasta = tmp_path / "subpasta"
    subpasta.mkdir()

    resumo = DirectoryIngestor([FakeExtractor(".pdf")]).ingerir_arquivos([subpasta])

    assert resumo.total_arquivos == 1
    assert resumo.processados == 0
    assert resumo.total_erros == 1
    assert resumo.erros[0].arquivo == "subpasta"


def test_ingerir_arquivos_extensao_nao_suportada_vira_erro(tmp_path):
    _tocar(tmp_path, "notas.txt")

    resumo = DirectoryIngestor([FakeExtractor(".pdf")]).ingerir_arquivos(
        [tmp_path / "notas.txt"]
    )

    assert resumo.total_arquivos == 1
    assert resumo.processados == 0
    assert resumo.total_erros == 1
    assert resumo.erros[0].arquivo == "notas.txt"


def test_ingerir_arquivos_mix_validos_e_invalidos(tmp_path):
    _tocar(tmp_path, "a.pdf", "notas.txt")
    pdf = FakeExtractor(".pdf")
    inexistente = tmp_path / "fantasma.docx"

    resumo = DirectoryIngestor([pdf]).ingerir_arquivos(
        [tmp_path / "a.pdf", tmp_path / "notas.txt", inexistente]
    )

    assert resumo.total_arquivos == 3
    assert resumo.processados == 1
    assert resumo.total_erros == 2
    erros_nomes = {e.arquivo for e in resumo.erros}
    assert erros_nomes == {"notas.txt", "fantasma.docx"}
    assert [c.name for c in pdf.chamadas] == ["a.pdf"]


def test_ingerir_arquivos_deduplica_por_hash(tmp_path):
    _tocar(tmp_path, "a.pdf", "copia.pdf")
    duplicador = FakeExtractor(
        ".pdf",
        resultado=DocumentoTexto(caminho="x", hash="MESMO_HASH", texto="t", metodo="nativo"),
    )

    resumo = DirectoryIngestor([duplicador]).ingerir_arquivos(
        [tmp_path / "a.pdf", tmp_path / "copia.pdf"]
    )

    assert resumo.processados == 1
    assert resumo.duplicados == 1
    assert len(resumo.documentos) == 1
