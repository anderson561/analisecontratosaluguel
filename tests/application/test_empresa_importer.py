"""Testes do importador em lote: auto-mapeamento, dedup, erros e CA-01."""
from __future__ import annotations

from pathlib import Path

import pytest

from contract_parser.application.empresa_importer import (
    ArquivoImportacaoError,
    EmpresaImporter,
    detectar_colunas,
)
from tests.support.fakes import FakeEmpresaRepository
from tests.support.fixture_builders import (
    construir_xlsx_50_empresas,
    construir_xlsx_header_sujo,
    construir_xlsx_sem_header_cnpj,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def importer() -> EmpresaImporter:
    return EmpresaImporter(FakeEmpresaRepository())


# --------------------------------------------------------------------------- #
# Auto-mapeamento de colunas (unit, sem IO de arquivo)
# --------------------------------------------------------------------------- #
def test_detectar_colunas_por_header_limpo():
    mapa = detectar_colunas(
        ["CNPJ", "Razão Social"],
        [["11222333000181", "Alpha"]],
    )
    assert (mapa.idx_cnpj, mapa.idx_razao) == (0, 1)


def test_detectar_colunas_header_sujo_e_ordem_invertida():
    mapa = detectar_colunas(
        ["Empresa", "  Nº do CNPJ  ", "Cidade"],
        [["Alpha LTDA", "11.222.333/0001-81", "SP"]],
    )
    assert mapa.idx_cnpj == 1
    assert mapa.idx_razao == 0


def test_detectar_colunas_fallback_por_valor_quando_header_nao_ajuda():
    # Cabeçalhos genéricos sem palavras-chave → usa padrão de valor.
    mapa = detectar_colunas(
        ["Documento", "Cliente"],
        [["99887766000105", "Gamma"], ["12345678000195", "Delta"]],
    )
    assert mapa.idx_cnpj == 0
    assert mapa.idx_razao == 1


def test_detectar_colunas_sem_cnpj_levanta():
    with pytest.raises(ArquivoImportacaoError):
        detectar_colunas(["Nome", "Cidade"], [["Alpha", "SP"], ["Beta", "RJ"]])


def test_detectar_colunas_sem_razao_levanta():
    # Só a coluna de CNPJ existe → não há coluna de Razão Social.
    with pytest.raises(ArquivoImportacaoError):
        detectar_colunas(["CNPJ"], [["11222333000181"], ["45566778000109"]])


# --------------------------------------------------------------------------- #
# Importação end-to-end (.csv committed)
# --------------------------------------------------------------------------- #
def test_importar_csv_header_sujo(importer):
    resumo = importer.importar(FIXTURES / "empresas_sujo.csv")

    assert resumo.importados == 3
    assert resumo.duplicados == 0
    assert resumo.total_erros == 0
    cnpjs = {e.cnpj for e in importer._repo.list_all()}
    assert cnpjs == {"11222333000181", "45566778000109", "99887766000105"}


def test_importar_csv_ponto_virgula(importer):
    resumo = importer.importar(FIXTURES / "empresas_ponto_virgula.csv")
    assert resumo.importados == 2


def test_importar_csv_sem_header_cnpj_usa_fallback(importer):
    resumo = importer.importar(FIXTURES / "empresas_sem_header_cnpj.csv")
    assert resumo.importados == 2


def test_importar_csv_com_erros_e_duplicados(importer):
    resumo = importer.importar(FIXTURES / "empresas_com_erros.csv")

    # 2 válidos (Alpha, Beta); 1 duplicado (Alpha repetido); 2 erros (curto + sem CNPJ)
    assert resumo.importados == 2
    assert resumo.duplicados == 1
    assert resumo.total_erros == 2
    # o lote NÃO abortou apesar dos erros
    assert len(importer._repo.list_all()) == 2


def test_importar_registra_origem(importer):
    importer.importar(FIXTURES / "empresas_ponto_virgula.csv")
    for e in importer._repo.list_all():
        assert e.origem_import == "empresas_ponto_virgula.csv"


# --------------------------------------------------------------------------- #
# Importação .xlsx (fixtures programáticas)
# --------------------------------------------------------------------------- #
def test_importar_xlsx_header_sujo(importer, tmp_path):
    caminho = construir_xlsx_header_sujo(tmp_path / "sujo.xlsx")
    resumo = importer.importar(caminho)
    assert resumo.importados == 2


def test_importar_xlsx_sem_header_cnpj(importer, tmp_path):
    caminho = construir_xlsx_sem_header_cnpj(tmp_path / "sem_cnpj.xlsx")
    resumo = importer.importar(caminho)
    assert resumo.importados == 2


# --------------------------------------------------------------------------- #
# CA-01 — importar .xlsx com 50 empresas → repositório contém 50
# --------------------------------------------------------------------------- #
def test_ca01_importar_50_empresas(importer, tmp_path):
    caminho = construir_xlsx_50_empresas(tmp_path / "portfolio50.xlsx")

    resumo = importer.importar(caminho)

    assert resumo.total_linhas == 50
    assert resumo.importados == 50
    assert resumo.duplicados == 0
    assert resumo.total_erros == 0
    assert len(importer._repo.list_all()) == 50


def test_upsert_idempotente_reimportacao(importer, tmp_path):
    caminho = construir_xlsx_50_empresas(tmp_path / "portfolio50.xlsx")
    importer.importar(caminho)
    importer.importar(caminho)  # reimportar não duplica
    assert len(importer._repo.list_all()) == 50


# --------------------------------------------------------------------------- #
# Erros de arquivo
# --------------------------------------------------------------------------- #
def test_importar_arquivo_inexistente(importer):
    with pytest.raises(ArquivoImportacaoError):
        importer.importar(FIXTURES / "nao_existe.xlsx")


def test_importar_extensao_nao_suportada(importer, tmp_path):
    ruim = tmp_path / "dados.txt"
    ruim.write_text("qualquer coisa", encoding="utf-8")
    with pytest.raises(ArquivoImportacaoError):
        importer.importar(ruim)


def test_importar_planilha_vazia_retorna_resumo_zerado(importer, tmp_path):
    from openpyxl import Workbook

    caminho = tmp_path / "vazia.xlsx"
    Workbook().save(caminho)
    resumo = importer.importar(caminho)
    assert resumo.total_linhas == 0
    assert resumo.importados == 0


def test_importar_xlsx_corrompido_levanta(importer, tmp_path):
    caminho = tmp_path / "corrompido.xlsx"
    caminho.write_bytes(b"isto nao e um xlsx valido")
    with pytest.raises(ArquivoImportacaoError):
        importer.importar(caminho)


# --------------------------------------------------------------------------- #
# Mensagem de erro legível (sem jargão técnico do pydantic) — mesmo bug do
# ``EmpresasController`` (ver tests/presentation/test_controllers.py), só que
# aqui a ``ValidationError`` é capturada dentro do ``except ValueError`` do
# importador e cai no ``ErroLinha.motivo`` exibido na aba de importação.
# --------------------------------------------------------------------------- #
_JARGAO_TECNICO_PROIBIDO = (
    "validation error",
    "value_error",
    "input_value",
    "For further information visit",
    "errors.pydantic.dev",
)


def test_importar_linha_com_razao_social_vazia_mensagem_amigavel(importer, tmp_path):
    from openpyxl import Workbook

    caminho = tmp_path / "razao_vazia.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["CNPJ", "Razão Social"])
    ws.append(["11222333000181", ""])
    wb.save(caminho)

    resumo = importer.importar(caminho)

    assert resumo.total_erros == 1
    motivo = resumo.erros[0].motivo.lower()
    for jargao in _JARGAO_TECNICO_PROIBIDO:
        assert jargao.lower() not in motivo
