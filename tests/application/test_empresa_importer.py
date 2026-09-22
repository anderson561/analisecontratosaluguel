"""Testes do importador em lote: auto-mapeamento, dedup, erros e CA-01."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from contract_parser.application.empresa_importer import (
    ArquivoImportacaoError,
    EmpresaImporter,
    detectar_colunas,
    detectar_linha_header,
    inspecionar,
    listar_abas,
)
from tests.support.fakes import FakeEmpresaRepository
from tests.support.fixture_builders import (
    cnpj_valido_sequencial,
    construir_ods_50_empresas,
    construir_ods_celula_conteudo_repetida_acima_do_limite,
    construir_ods_com_cauda_vazia_gigante,
    construir_ods_com_linhas_e_celulas_repetidas,
    construir_ods_com_multiplos_blocos_vazios_no_fim,
    construir_ods_header_sujo,
    construir_ods_multiplas_abas,
    construir_ods_titulo_antes_do_header,
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
# Importação .ods (fixtures programáticas via odfpy)
# --------------------------------------------------------------------------- #
def test_ca01_importar_ods_50_empresas(importer, tmp_path):
    caminho = construir_ods_50_empresas(tmp_path / "portfolio50.ods")

    resumo = importer.importar(caminho)

    assert resumo.total_linhas == 50
    assert resumo.importados == 50
    assert resumo.duplicados == 0
    assert resumo.total_erros == 0
    assert len(importer._repo.list_all()) == 50


def test_importar_ods_header_sujo_e_ordem_invertida(importer, tmp_path):
    caminho = construir_ods_header_sujo(tmp_path / "sujo.ods")
    resumo = importer.importar(caminho)
    assert resumo.importados == 2
    cnpjs = {e.cnpj for e in importer._repo.list_all()}
    assert cnpjs == {"11222333000181", "45566778000109"}


def test_importar_ods_linhas_e_celulas_repetidas_nao_desalinha(importer, tmp_path):
    caminho = construir_ods_com_linhas_e_celulas_repetidas(tmp_path / "lacunas.ods")

    resumo = importer.importar(caminho)

    # 3 empresas válidas; as linhas totalmente vazias (repetidas) são ignoradas.
    assert resumo.importados == 3
    assert resumo.total_erros == 0
    por_cnpj = {e.cnpj: e.razao_social for e in importer._repo.list_all()}
    # A 2ª empresa tem 2 células vazias compactadas (number-columns-repeated)
    # antes da Razão Social: se a expansão falhar, isso viria vazio/errado.
    assert por_cnpj[cnpj_valido_sequencial(101)] == "Empresa Um LTDA"
    assert por_cnpj[cnpj_valido_sequencial(102)] == "Empresa Dois LTDA"
    assert por_cnpj[cnpj_valido_sequencial(103)] == "Empresa Tres LTDA"


def test_importar_ods_cauda_vazia_gigante_nao_materializa_grade_inteira(importer, tmp_path):
    """Reproduz o comportamento real do LibreOffice Calc: a última linha (e a
    última célula de uma linha real) usam number-rows/columns-repeated na casa
    de centenas de milhares/milhões para comprimir "o resto da grade está
    vazio". Expandir isso literalmente materializaria ~1 milhão de linhas —
    aqui garantimos que a importação (a) termina rápido, sem alocar a grade
    inteira, e (b) o resumo reflete só as linhas reais, não a contagem bruta
    do atributo."""
    caminho = construir_ods_com_cauda_vazia_gigante(tmp_path / "cauda_gigante.ods")

    inicio = time.perf_counter()
    resumo = importer.importar(caminho)
    duracao = time.perf_counter() - inicio

    assert duracao < 5, f"importação demorou {duracao:.1f}s — cauda vazia foi materializada literalmente"
    assert resumo.importados == 3
    assert resumo.total_erros == 0
    # Não pode refletir a contagem literal do atributo (~1_000_000): no máximo
    # as 3 linhas reais + 1 linha vazia "cauda" (capada em 1 cópia).
    assert resumo.total_linhas <= 4
    por_cnpj = {e.cnpj: e.razao_social for e in importer._repo.list_all()}
    assert por_cnpj[cnpj_valido_sequencial(201)] == "Empresa Um LTDA"
    assert por_cnpj[cnpj_valido_sequencial(202)] == "Empresa Dois LTDA"
    assert por_cnpj[cnpj_valido_sequencial(203)] == "Empresa Tres LTDA"


def test_importar_ods_multiplos_blocos_vazios_no_fim_nao_materializa(importer, tmp_path):
    """Variante do bug real: VÁRIOS blocos SEPARADOS de linha vazia perto do
    fim (não um só bloco final) — o código antigo só tratava o último
    elemento XML como cauda vazia, então os blocos anteriores a ele eram
    expandidos literalmente."""
    caminho = construir_ods_com_multiplos_blocos_vazios_no_fim(tmp_path / "multi_bloco.ods")

    inicio = time.perf_counter()
    resumo = importer.importar(caminho)
    duracao = time.perf_counter() - inicio

    assert duracao < 5, f"importação demorou {duracao:.1f}s — algum bloco vazio foi materializado"
    assert resumo.importados == 3
    assert resumo.total_erros == 0
    assert resumo.total_linhas <= 4
    por_cnpj = {e.cnpj: e.razao_social for e in importer._repo.list_all()}
    assert por_cnpj[cnpj_valido_sequencial(301)] == "Empresa Um LTDA"
    assert por_cnpj[cnpj_valido_sequencial(302)] == "Empresa Dois LTDA"
    assert por_cnpj[cnpj_valido_sequencial(303)] == "Empresa Tres LTDA"

    # A inspeção (listar_abas/inspecionar) também não pode refletir a
    # contagem bruta dos blocos vazios (200 + 5_000 + 50_000 = 55_200 linhas
    # fantasmas) — só as 4 linhas reais (header + 3 empresas).
    abas = listar_abas(caminho)
    assert len(abas) == 1
    assert abas[0].n_linhas_uteis == 4

    info = inspecionar(caminho)
    assert info.aba_sugerida == 0
    assert info.linha_header_sugerida == 0
    assert info.total_linhas_estimado == 3


def test_importar_ods_celula_conteudo_repetido_acima_do_teto_levanta(importer, tmp_path):
    """Teto de sanidade (item 2): uma célula com CONTEÚDO REAL repetida de
    forma anormal (``number-columns-repeated`` acima do limite) deve levantar
    erro em vez de truncar/duplicar silenciosamente um dado real — isso é
    defesa contra ODS malformado/adversarial, diferente da cauda vazia."""
    caminho = construir_ods_celula_conteudo_repetida_acima_do_limite(tmp_path / "repetida.ods")
    with pytest.raises(ArquivoImportacaoError):
        importer.importar(caminho)


# --------------------------------------------------------------------------- #
# detectar_linha_header / listar_abas / inspecionar (superfície nova, ainda
# sem uso em ``EmpresaImporter.importar()`` — ligada em fase futura).
# --------------------------------------------------------------------------- #
def test_detectar_linha_header_sem_titulo_assume_linha_0():
    linhas = [["CNPJ", "Razão Social"], ["11222333000181", "Alpha"]]
    assert detectar_linha_header(linhas) == 0


def test_detectar_linha_header_nenhuma_linha_pontua_assume_linha_0():
    linhas = [["a", "b"], ["c", "d"]]
    assert detectar_linha_header(linhas) == 0


def test_detectar_linha_header_pula_titulo_mesclado():
    linhas = [
        ["MAPA DE ALUGUÉIS PESSOA FÍSICA 2024", None, None],
        ["CNPJ", "Razão Social"],
        ["11222333000181", "Alpha"],
    ]
    assert detectar_linha_header(linhas) == 1


def test_importar_ods_titulo_antes_do_header_inspecionar_acha_header_real(importer, tmp_path):
    caminho = construir_ods_titulo_antes_do_header(tmp_path / "titulo.ods")

    info = inspecionar(caminho)

    assert info.linha_header_sugerida == 1
    assert info.mapa_sugerido is not None
    assert info.mapa_sugerido.idx_cnpj == 0
    assert info.mapa_sugerido.idx_razao == 1
    assert info.total_linhas_estimado == 2


def test_listar_abas_ods_multiplas_abas(tmp_path):
    caminho = construir_ods_multiplas_abas(tmp_path / "multi_aba.ods")

    abas = listar_abas(caminho)

    assert [a.nome for a in abas] == ["Pessoa Fisica", "Pessoa Juridica"]
    assert [a.indice for a in abas] == [0, 1]
    assert abas[0].n_linhas_uteis == 3  # header + 2 empresas
    assert abas[1].n_linhas_uteis == 2  # header + 1 empresa


def test_listar_abas_xlsx_retorna_uma_unica_aba(tmp_path):
    caminho = construir_xlsx_50_empresas(tmp_path / "portfolio50.xlsx")

    abas = listar_abas(caminho)

    assert len(abas) == 1
    assert abas[0].indice == 0
    assert abas[0].n_linhas_uteis == 51  # header + 50 empresas


def test_inspecionar_sugere_aba_com_mais_linhas_uteis(tmp_path):
    caminho = construir_ods_multiplas_abas(tmp_path / "multi_aba.ods")

    info = inspecionar(caminho)

    assert info.aba_sugerida == 0  # "Pessoa Fisica" tem mais linhas úteis (3 > 2)
    assert len(info.abas) == 2
    assert info.linha_header_sugerida == 0
    assert info.mapa_sugerido is not None
    assert info.mapa_sugerido.idx_cnpj == 0
    assert info.mapa_sugerido.idx_razao == 1


def test_importar_ods_corrompido_levanta(importer, tmp_path):
    caminho = tmp_path / "corrompido.ods"
    caminho.write_bytes(b"isto nao e um ods valido")
    with pytest.raises(ArquivoImportacaoError):
        importer.importar(caminho)


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
