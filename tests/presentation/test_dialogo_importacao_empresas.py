"""Testes do diálogo de confirmação de importação de empresas (Fase 3).

Segue o mesmo padrão de ``test_view_smoke.py``: a suíte roda headless (sem
display), então NÃO instancia ``ctk.CTkToplevel``/nenhum widget real — só
garante que o módulo importa (``importorskip("customtkinter")``) e testa a
LÓGICA pura (sem Tk) extraída para funções de nível de módulo: formatação de
tamanho de arquivo, rótulos/índices dos seletores de coluna e o recálculo de
mapa de colunas + total estimado ao trocar aba/linha de header.
"""
from __future__ import annotations

import pytest

pytest.importorskip("customtkinter")

from contract_parser.application.empresa_importer import (
    AbaInfo,
    MapeamentoColunas,
    inspecionar,
)
from contract_parser.presentation.views.dialogo_importacao_empresas import (
    DialogoImportacaoEmpresas,
    formatar_tamanho_arquivo,
    indice_da_opcao,
    opcoes_colunas,
    recalcular_mapa_e_total,
    sugerir_para_aba,
)
from tests.support.fixture_builders import (
    cnpj_valido_sequencial,
    construir_ods_multiplas_abas,
    construir_ods_titulo_antes_do_header,
    construir_xlsx_50_empresas,
)


# --------------------------------------------------------------------------- #
# Smoke: módulo importável, classe exposta (mesmo padrão de test_view_smoke)
# --------------------------------------------------------------------------- #
def test_modulo_importavel_e_expoe_classe():
    assert hasattr(DialogoImportacaoEmpresas, "__init__")
    assert issubclass(DialogoImportacaoEmpresas, object)


# --------------------------------------------------------------------------- #
# formatar_tamanho_arquivo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("tamanho_bytes", "esperado"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (62_259, "60.8 KB"),
        (1024 * 1024, "1.0 MB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
    ],
)
def test_formatar_tamanho_arquivo(tamanho_bytes, esperado):
    assert formatar_tamanho_arquivo(tamanho_bytes) == esperado


# --------------------------------------------------------------------------- #
# opcoes_colunas / indice_da_opcao
# --------------------------------------------------------------------------- #
def test_opcoes_colunas_usa_texto_do_header():
    amostra = [["CNPJ", "Razão Social", None], ["11222333000181", "Alpha", "obs"]]
    assert opcoes_colunas(amostra, linha_header=0) == [
        "0 — CNPJ",
        "1 — Razão Social",
        "2 — Coluna 2",
    ]


def test_opcoes_colunas_header_fora_da_amostra_usa_rotulo_generico():
    amostra = [["11222333000181", "Alpha"]]
    assert opcoes_colunas(amostra, linha_header=5) == ["0 — Coluna 0", "1 — Coluna 1"]


def test_opcoes_colunas_amostra_vazia():
    assert opcoes_colunas([], linha_header=0) == []


def test_indice_da_opcao_extrai_prefixo_numerico():
    assert indice_da_opcao("0 — CNPJ") == 0
    assert indice_da_opcao("12 — Coluna 12") == 12


# --------------------------------------------------------------------------- #
# recalcular_mapa_e_total
# --------------------------------------------------------------------------- #
def test_recalcular_mapa_e_total_sucesso():
    amostra = [
        ["CNPJ", "Razão Social"],
        ["11222333000181", "Alpha"],
        ["45566778000109", "Beta"],
    ]
    mapa, total = recalcular_mapa_e_total(amostra, linha_header=0, n_linhas_uteis=3)
    assert mapa == MapeamentoColunas(idx_cnpj=0, idx_razao=1)
    assert total == 2


def test_recalcular_mapa_e_total_header_fora_da_amostra_mapa_none():
    amostra = [["CNPJ", "Razão Social"], ["11222333000181", "Alpha"]]
    mapa, total = recalcular_mapa_e_total(amostra, linha_header=10, n_linhas_uteis=2)
    assert mapa is None
    # total_estimado usa n_linhas_uteis (contagem real), não a amostra.
    assert total == 0


def test_recalcular_mapa_e_total_nao_consegue_mapear_cnpj_mapa_none():
    amostra = [["Nome", "Cidade"], ["Alpha", "SP"], ["Beta", "RJ"]]
    mapa, total = recalcular_mapa_e_total(amostra, linha_header=0, n_linhas_uteis=3)
    assert mapa is None
    assert total == 2


def test_recalcular_mapa_e_total_linha_header_negativa_mapa_none():
    amostra = [["CNPJ", "Razão Social"]]
    mapa, total = recalcular_mapa_e_total(amostra, linha_header=-1, n_linhas_uteis=1)
    assert mapa is None
    assert total == 1


# --------------------------------------------------------------------------- #
# sugerir_para_aba
# --------------------------------------------------------------------------- #
def test_sugerir_para_aba_sem_titulo():
    aba = AbaInfo(
        indice=0,
        nome="Aba1",
        n_linhas_uteis=3,
        amostra=[
            ["CNPJ", "Razão Social"],
            ["11222333000181", "Alpha"],
            ["45566778000109", "Beta"],
        ],
    )
    linha_header, mapa, total = sugerir_para_aba(aba)
    assert linha_header == 0
    assert mapa == MapeamentoColunas(idx_cnpj=0, idx_razao=1)
    assert total == 2


def test_sugerir_para_aba_pula_titulo_mesclado():
    aba = AbaInfo(
        indice=0,
        nome="Aba1",
        n_linhas_uteis=3,
        amostra=[
            ["MAPA DE ALUGUÉIS 2024", None],
            ["CNPJ", "Razão Social"],
            ["11222333000181", "Alpha"],
        ],
    )
    linha_header, mapa, total = sugerir_para_aba(aba)
    assert linha_header == 1
    assert mapa == MapeamentoColunas(idx_cnpj=0, idx_razao=1)
    assert total == 1


def test_sugerir_para_aba_amostra_vazia():
    aba = AbaInfo(indice=0, nome="Vazia", n_linhas_uteis=0, amostra=[])
    linha_header, mapa, total = sugerir_para_aba(aba)
    assert linha_header == 0
    assert mapa is None
    assert total == 0


# --------------------------------------------------------------------------- #
# Paridade com inspecionar(): recalcular_mapa_e_total()/sugerir_para_aba()
# sobre uma aba real de ``inspecionar()`` deve bater com o que ``inspecionar``
# já sugeriu para ela — prova que a tela não reinventa a heurística.
# --------------------------------------------------------------------------- #
def test_recalcular_bate_com_inspecionar_xlsx(tmp_path):
    caminho = construir_xlsx_50_empresas(tmp_path / "portfolio50.xlsx")
    info = inspecionar(caminho)
    aba = info.abas[info.aba_sugerida]

    mapa, total = recalcular_mapa_e_total(
        aba.amostra, info.linha_header_sugerida, aba.n_linhas_uteis
    )

    assert mapa == info.mapa_sugerido
    assert total == info.total_linhas_estimado


def test_recalcular_bate_com_inspecionar_ods_titulo_antes_do_header(tmp_path):
    caminho = construir_ods_titulo_antes_do_header(tmp_path / "titulo.ods")
    info = inspecionar(caminho)
    aba = info.abas[info.aba_sugerida]

    linha_header, mapa, total = sugerir_para_aba(aba)

    assert linha_header == info.linha_header_sugerida == 1
    assert mapa == info.mapa_sugerido
    assert total == info.total_linhas_estimado


def test_sugerir_para_aba_segunda_aba_de_ods_multiplas_abas(tmp_path):
    caminho = construir_ods_multiplas_abas(tmp_path / "multi_aba.ods")
    info = inspecionar(caminho)
    # A aba sugerida por inspecionar() é a de mais linhas úteis (índice 0);
    # aqui simulamos o usuário trocando manualmente para a aba 1.
    assert info.aba_sugerida == 0
    aba_1 = info.abas[1]

    linha_header, mapa, total = sugerir_para_aba(aba_1)

    assert linha_header == 0
    assert mapa == MapeamentoColunas(idx_cnpj=0, idx_razao=1)
    assert total == 1
    cnpj_esperado = cnpj_valido_sequencial(503)
    assert aba_1.amostra[linha_header + 1][mapa.idx_cnpj] == cnpj_esperado
