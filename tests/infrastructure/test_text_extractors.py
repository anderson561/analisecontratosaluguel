"""Testes dos backends de extração (infrastructure).

Estratégia (decisão travada): o roteamento nativo→OCR e a seleção por extensão
são testados com FAKES injetados — sem exigir PyMuPDF/Tesseract. Os caminhos com
libs REAIS são:
- DOCX: exercitado de verdade (``python-docx`` é leve, instalado).
- PDF nativo: exercitado de verdade quando ``fitz`` (PyMuPDF) está presente
  (``importorskip``); do contrário o roteamento já está coberto pelos fakes.
- OCR real (Tesseract/poppler): ``@pytest.mark.integration`` + skip automático,
  pois o binário não está instalado no host.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from contract_parser.domain.extracao import ResultadoOcr
from contract_parser.infrastructure.text_extractors import (
    DocxExtractor,
    PdfExtractor,
    TesseractOcr,
    _tesseract_embutido,
)
from tests.support.document_builders import (
    construir_docx,
    construir_pdf_nativo,
    construir_pdf_sem_texto,
)
from tests.support.fakes import FakeOcr


# --------------------------------------------------------------------------- #
# PdfExtractor — roteamento nativo × OCR com colaboradores FAKE (sem libs)
# --------------------------------------------------------------------------- #
def test_pdf_aceita_apenas_pdf():
    ext = PdfExtractor(leitor_nativo=lambda dados: ("", 0), ocr=FakeOcr())
    assert ext.aceita(Path("x.pdf")) is True
    assert ext.aceita(Path("x.PDF")) is True
    assert ext.aceita(Path("x.docx")) is False


def test_pdf_usa_camada_nativa_quando_ha_texto(tmp_path):
    arquivo = tmp_path / "nativo.pdf"
    arquivo.write_bytes(b"%PDF-fake")
    ocr = FakeOcr()
    ext = PdfExtractor(
        leitor_nativo=lambda dados: ("Texto nativo suficientemente longo do contrato", 3),
        ocr=ocr,
    )

    doc = ext.extrair(arquivo)

    assert doc.metodo == "nativo"
    assert doc.paginas == 3
    assert doc.baixa_confianca is False
    assert doc.sucesso is True
    assert ocr.chamadas == []  # OCR NÃO deve ser acionado


def test_pdf_roteia_para_ocr_quando_texto_vazio(tmp_path):
    arquivo = tmp_path / "escaneado.pdf"
    arquivo.write_bytes(b"%PDF-fake")
    ocr = FakeOcr(ResultadoOcr(texto="texto via ocr", paginas=2, baixa_confianca=True))
    ext = PdfExtractor(leitor_nativo=lambda dados: ("", 2), ocr=ocr)

    doc = ext.extrair(arquivo)

    assert doc.metodo == "ocr"
    assert doc.texto == "texto via ocr"
    assert doc.baixa_confianca is True
    assert len(ocr.chamadas) == 1  # rota OCR foi acionada


def test_pdf_roteia_para_ocr_quando_texto_abaixo_do_limiar(tmp_path):
    arquivo = tmp_path / "quase_vazio.pdf"
    arquivo.write_bytes(b"%PDF-fake")
    ocr = FakeOcr()
    ext = PdfExtractor(leitor_nativo=lambda dados: ("poucos", 1), ocr=ocr, limiar_texto=20)

    doc = ext.extrair(arquivo)

    assert doc.metodo == "ocr"
    assert len(ocr.chamadas) == 1


def test_pdf_corrompido_vira_erro_sem_excecao(tmp_path):
    arquivo = tmp_path / "corrompido.pdf"
    arquivo.write_bytes(b"nao e pdf")

    def leitor_quebra(dados):
        raise ValueError("cannot open broken document")

    ext = PdfExtractor(leitor_nativo=leitor_quebra, ocr=FakeOcr())
    doc = ext.extrair(arquivo)

    assert doc.sucesso is False
    assert doc.metodo is None
    assert "Falha ao abrir/ler PDF" in doc.erro


def test_pdf_falha_de_ocr_vira_erro_sem_excecao(tmp_path):
    arquivo = tmp_path / "escaneado.pdf"
    arquivo.write_bytes(b"%PDF-fake")

    class OcrQuebra:
        def reconhecer(self, dados):
            raise RuntimeError("tesseract not found")

    ext = PdfExtractor(leitor_nativo=lambda dados: ("", 1), ocr=OcrQuebra())
    doc = ext.extrair(arquivo)

    assert doc.sucesso is False
    assert "Falha no OCR" in doc.erro


def test_pdf_hash_depende_do_conteudo(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"conteudo identico")
    b.write_bytes(b"conteudo identico")
    ext = PdfExtractor(leitor_nativo=lambda dados: ("texto longo o suficiente aqui", 1), ocr=FakeOcr())

    assert ext.extrair(a).hash == ext.extrair(b).hash


def test_tesseract_ocr_construivel_sem_binario():
    # Construir NÃO importa pytesseract/PIL (imports lazy só em ``reconhecer``).
    motor = TesseractOcr(lang="por", tesseract_cmd="C:/x/tesseract.exe", limiar_confianca=42.0)
    assert motor._lang == "por"
    assert motor._cmd == "C:/x/tesseract.exe"
    assert motor._limiar == 42.0


def test_pdf_extractor_usa_tesseract_por_padrao():
    # Sem ``ocr`` injetado, o default é um TesseractOcr (não dispara import pesado).
    ext = PdfExtractor(leitor_nativo=lambda dados: ("", 0))
    assert isinstance(ext._ocr, TesseractOcr)


# --------------------------------------------------------------------------- #
# DocxExtractor — caminho REAL com python-docx
# --------------------------------------------------------------------------- #
def test_docx_aceita_apenas_docx():
    ext = DocxExtractor()
    assert ext.aceita(Path("x.docx")) is True
    assert ext.aceita(Path("x.DOCX")) is True
    assert ext.aceita(Path("x.pdf")) is False


def test_docx_extrai_paragrafos_reais(tmp_path):
    arquivo = construir_docx(
        tmp_path / "contrato.docx",
        paragrafos=["CONTRATO DE LOCACAO", "Locador: Fulano de Tal", "Valor: R$ 5.000,00"],
    )
    doc = DocxExtractor().extrair(arquivo)

    assert doc.sucesso is True
    assert doc.metodo == "docx"
    assert doc.paginas == 0
    assert "CONTRATO DE LOCACAO" in doc.texto
    assert "R$ 5.000,00" in doc.texto
    assert doc.hash  # sha256 do conteúdo


def test_docx_inclui_texto_de_tabelas(tmp_path):
    arquivo = construir_docx(
        tmp_path / "com_tabela.docx",
        paragrafos=["Quadro Resumo"],
        tabela=[["Campo", "Valor"], ["Aluguel", "1200"]],
    )
    doc = DocxExtractor().extrair(arquivo)

    assert "Aluguel" in doc.texto
    assert "1200" in doc.texto


def test_docx_corrompido_vira_erro_sem_excecao(tmp_path):
    arquivo = tmp_path / "corrompido.docx"
    arquivo.write_bytes(b"isto nao e um docx valido")

    doc = DocxExtractor().extrair(arquivo)

    assert doc.sucesso is False
    assert "Falha ao abrir/ler DOCX" in doc.erro


# --------------------------------------------------------------------------- #
# PDF nativo REAL (PyMuPDF) — skip se a lib não estiver instalada
# --------------------------------------------------------------------------- #
def test_pdf_nativo_real_com_pymupdf(tmp_path):
    pytest.importorskip("fitz", reason="PyMuPDF não instalado — rota nativa coberta por fakes")
    arquivo = construir_pdf_nativo(tmp_path / "real.pdf", texto="CONTRATO DE LOCACAO COMERCIAL")

    ext = PdfExtractor(ocr=FakeOcr())  # usa o leitor nativo REAL (PyMuPDF)
    doc = ext.extrair(arquivo)

    assert doc.metodo == "nativo"
    assert "CONTRATO DE LOCACAO COMERCIAL" in doc.texto
    assert doc.paginas == 1


def test_pdf_sem_texto_real_roteia_para_ocr(tmp_path):
    pytest.importorskip("fitz", reason="PyMuPDF não instalado")
    arquivo = construir_pdf_sem_texto(tmp_path / "branco.pdf", paginas=2)
    ocr = FakeOcr(ResultadoOcr(texto="ocr aplicado", paginas=2, baixa_confianca=True))

    ext = PdfExtractor(ocr=ocr)  # leitor nativo REAL retorna vazio → cai no OCR fake
    doc = ext.extrair(arquivo)

    assert doc.metodo == "ocr"
    assert len(ocr.chamadas) == 1


# --------------------------------------------------------------------------- #
# Tesseract embutido (PyInstaller) — resolução de caminho e --tessdata-dir
# --------------------------------------------------------------------------- #
def test_tesseract_embutido_none_fora_do_modo_congelado():
    # Rodando via pytest normal (não congelado) — resolução embutida é None,
    # ou seja, o comportamento fora do modo congelado não muda.
    assert _tesseract_embutido() is None


def test_tesseract_embutido_resolve_caminho_quando_congelado(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/algum/caminho/fake", raising=False)

    resultado = _tesseract_embutido()

    assert resultado is not None
    tesseract_exe, tessdata_dir = resultado
    assert tesseract_exe == Path("/algum/caminho/fake") / "tesseract" / "tesseract.exe"
    assert tessdata_dir == Path("/algum/caminho/fake") / "tesseract" / "tessdata"


def test_reconhecer_usa_embutido_quando_congelado_e_sem_tesseract_cmd(monkeypatch, tmp_path):
    pytest.importorskip("fitz")
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/algum/caminho/fake", raising=False)
    # Registra a variável para restauração automática pelo monkeypatch ao final
    # do teste, mesmo que o código sob teste a defina diretamente via
    # ``os.environ`` (sem passar por ``monkeypatch.setenv``).
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)

    chamadas: list[dict] = []

    def fake_image_to_data(imagem, lang=None, config="", output_type=None):
        chamadas.append({"lang": lang, "config": config})
        return {"text": ["ok"], "conf": ["90"]}

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    arquivo = construir_pdf_sem_texto(tmp_path / "para_ocr.pdf", paginas=1)
    motor = TesseractOcr(tesseract_cmd="")  # sem TESSERACT_CMD configurado pelo usuário

    resultado = motor.reconhecer(arquivo.read_bytes())

    caminho_esperado = str(Path("/algum/caminho/fake") / "tesseract" / "tesseract.exe")
    tessdata_esperado = str(Path("/algum/caminho/fake") / "tesseract" / "tessdata")
    assert pytesseract.pytesseract.tesseract_cmd == caminho_esperado
    assert len(chamadas) == 1
    # A resolução do tessdata é via variável de ambiente TESSDATA_PREFIX — NÃO
    # mais via parâmetro ``config`` (que no Windows passa por
    # ``shlex.split(config, posix=False)`` dentro do pytesseract, e esse modo
    # NÃO remove aspas dos tokens; era exatamente isso que quebrava o path).
    assert os.environ.get("TESSDATA_PREFIX") == tessdata_esperado
    assert "--tessdata-dir" not in chamadas[0]["config"]
    assert chamadas[0]["config"] == ""
    assert isinstance(resultado, ResultadoOcr)


def test_reconhecer_prioriza_tesseract_cmd_do_usuario_mesmo_congelado(monkeypatch, tmp_path):
    # TESSERACT_CMD configurado explicitamente pelo usuário deve continuar
    # tendo prioridade sobre o Tesseract embutido, mesmo rodando como `.exe`.
    pytest.importorskip("fitz")
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/algum/caminho/fake", raising=False)
    # Sentinela: se o código mexesse em TESSDATA_PREFIX neste caminho, este
    # valor seria sobrescrito ou removido — o teste garante que nada muda.
    monkeypatch.setenv("TESSDATA_PREFIX", "sentinela-nao-deve-mudar")

    chamadas: list[dict] = []

    def fake_image_to_data(imagem, lang=None, config="", output_type=None):
        chamadas.append({"lang": lang, "config": config})
        return {"text": ["ok"], "conf": ["90"]}

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    arquivo = construir_pdf_sem_texto(tmp_path / "para_ocr.pdf", paginas=1)
    cmd_usuario = "C:/tesseract-sistema/tesseract.exe"
    motor = TesseractOcr(tesseract_cmd=cmd_usuario)

    motor.reconhecer(arquivo.read_bytes())

    assert pytesseract.pytesseract.tesseract_cmd == cmd_usuario
    assert chamadas[0]["config"] == ""  # não força --tessdata-dir quando é cmd do usuário
    # TESSERACT_CMD do usuário tem prioridade: TESSDATA_PREFIX não é tocado,
    # para não interferir num Tesseract de sistema configurado pelo usuário.
    assert os.environ["TESSDATA_PREFIX"] == "sentinela-nao-deve-mudar"


# --------------------------------------------------------------------------- #
# OCR REAL (Tesseract) — integração, skip automático se indisponível
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_ocr_real_tesseract(tmp_path):
    pytest.importorskip("fitz")
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("binário 'tesseract' ausente no PATH — teste de OCR real pulado")

    arquivo = construir_pdf_nativo(tmp_path / "para_ocr.pdf", texto="ALUGUEL MENSAL 3000")
    resultado = TesseractOcr().reconhecer(arquivo.read_bytes())

    assert isinstance(resultado, ResultadoOcr)
    assert resultado.paginas == 1


# Instalação padrão do Tesseract no Windows (não costuma estar no PATH, mas é
# onde o instalador oficial coloca os binários por padrão).
_TESSERACT_INSTALL_DIR = Path(r"C:\Program Files\Tesseract-OCR")


@pytest.mark.integration
def test_ocr_real_tesseract_embutido_congelado_resolve_tessdata_via_env(monkeypatch, tmp_path):
    """Regressão real (SEM mock de ``pytesseract.image_to_data``) do bug de
    produção: ``--tessdata-dir "<caminho>"`` via parâmetro ``config`` chegava
    ao Tesseract com as aspas literais no token (``shlex.split(config,
    posix=False)`` no Windows não remove aspas), quebrando a resolução do
    arquivo de idioma (``TesseractError`` "Please make sure the
    TESSDATA_PREFIX..."). O teste mockado (acima) só valida a STRING de
    config — não pegaria esse bug, pois nunca chama o binário de verdade.

    Monta uma réplica mínima do bundle do PyInstaller em ``tmp_path``
    (tesseract.exe + DLLs + tessdata/por.traineddata, via hardlink quando
    possível para não copiar dezenas de MB a cada execução) e simula o modo
    congelado de verdade (``sys.frozen``/``sys._MEIPASS``), exercitando o
    subprocesso real do Tesseract.
    """
    pytest.importorskip("fitz")
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import shutil

    exe_real = _TESSERACT_INSTALL_DIR / "tesseract.exe"
    traineddata_real = _TESSERACT_INSTALL_DIR / "tessdata" / "por.traineddata"
    if not exe_real.exists() or not traineddata_real.exists():
        pytest.skip(
            "Tesseract não instalado em 'C:/Program Files/Tesseract-OCR' — "
            "teste de regressão real (bundle congelado) pulado"
        )

    def _clonar(origem: Path, destino: Path) -> None:
        try:
            os.link(origem, destino)  # hardlink: evita copiar dezenas de MB de DLLs
        except OSError:
            shutil.copy2(origem, destino)

    bundle = tmp_path / "tesseract"
    (bundle / "tessdata").mkdir(parents=True)
    _clonar(exe_real, bundle / "tesseract.exe")
    for dll in _TESSERACT_INSTALL_DIR.glob("*.dll"):
        _clonar(dll, bundle / dll.name)
    _clonar(traineddata_real, bundle / "tessdata" / "por.traineddata")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)

    arquivo = construir_pdf_nativo(tmp_path / "para_ocr_real.pdf", texto="ALUGUEL MENSAL")
    motor = TesseractOcr(tesseract_cmd="")  # sem TESSERACT_CMD -> usa o embutido

    resultado = motor.reconhecer(arquivo.read_bytes())

    assert isinstance(resultado, ResultadoOcr)
    assert resultado.texto  # não pode ficar vazio (era o sintoma do bug)
    assert "ALUGUEL" in resultado.texto.upper()
