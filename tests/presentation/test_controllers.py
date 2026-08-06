"""Testes headless dos controllers/viewmodels da GUI (RF06).

Cobrem a lógica de apresentação SEM display e SEM customtkinter: importação,
CRUD de empresa, processamento de pasta (via fake ingestor + fixtures reais de
contrato), montagem/filtragem do painel, exportação (para ``tmp_path``),
conformidade com a mensagem exata do PRD, e a degradação graciosa quando o
banco de dados não responde.

Dados 100% fictícios (sem PII real).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contract_parser.application.contract_extraction_service import ExtratorContrato
from contract_parser.application.document_ingestor import (
    ErroArquivo,
    IngestaoResumo,
)
from contract_parser.application.relatorio_service import RelatorioService
from contract_parser.domain.contrato import Contrato, Parte, Reajuste, TipoParte
from contract_parser.domain.documento_texto import DocumentoTexto
from contract_parser.domain.empresa import Empresa
from contract_parser.infrastructure.database import HealthResult, RepositoryError
from contract_parser.infrastructure.report_exporters import (
    ExcelRelatorioExporter,
    PdfRelatorioExporter,
)
from contract_parser.presentation.controllers import (
    AppController,
    ControllerError,
    EmpresasController,
    ProcessamentoController,
    RelatorioController,
    StatusConexao,
)
from tests.support.contract_fixtures import RESIDENCIAL_PF_PJ, carregar_contrato
from tests.support.fakes import FakeEmpresaRepository
from tests.support.fixture_builders import cnpj_valido_sequencial

CNPJ_A = cnpj_valido_sequencial(1)
CNPJ_B = cnpj_valido_sequencial(2)
CNPJ_C = cnpj_valido_sequencial(3)
CNPJ_X = cnpj_valido_sequencial(9)


# --------------------------------------------------------------------------- #
# Fakes locais
# --------------------------------------------------------------------------- #
class FakeIngestor:
    """Ingestor que devolve um :class:`IngestaoResumo` pré-montado (sem IO)."""

    def __init__(self, resumo: IngestaoResumo) -> None:
        self._resumo = resumo
        self.chamadas: list[str] = []

    def ingerir(self, pasta) -> IngestaoResumo:
        self.chamadas.append(str(pasta))
        return self._resumo


class RepoQueFalha:
    """Repositório que simula o banco de dados fora do ar em toda operação."""

    def list_all(self):
        raise RepositoryError("banco de dados indisponivel")

    def add(self, empresa):
        raise RepositoryError("banco de dados indisponivel")

    def get_by_cnpj(self, cnpj):
        raise RepositoryError("banco de dados indisponivel")

    def update(self, empresa):
        raise RepositoryError("banco de dados indisponivel")

    def remove(self, cnpj):
        raise RepositoryError("banco de dados indisponivel")

    def upsert_many(self, empresas):
        raise RepositoryError("banco de dados indisponivel")


def _repo_portfolio() -> FakeEmpresaRepository:
    repo = FakeEmpresaRepository()
    repo.add(Empresa(cnpj=CNPJ_A, razao_social="Alpha Comercio LTDA"))
    repo.add(Empresa(cnpj=CNPJ_B, razao_social="Beta Servicos ME"))
    repo.add(Empresa(cnpj=CNPJ_C, razao_social="Gamma Holding SA"))
    return repo


def _contrato_pf_pj() -> Contrato:
    return Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="João da Silva", documento="11111111111"),
        locatario=Parte(tipo=TipoParte.PJ, nome="Alpha Comercio LTDA", documento=CNPJ_A),
        valor_aluguel=Decimal("5000.00"),
        data_fim_vigencia=date(2028, 10, 10),
        reajuste=Reajuste(indice="IPCA", proximo_reajuste="10/2026", automatico=True),
    )


def _contrato_locador_pj() -> Contrato:
    return Contrato(
        locador=Parte(tipo=TipoParte.PJ, nome="Imobiliaria XPTO LTDA", documento=CNPJ_X),
        locatario=Parte(tipo=TipoParte.PJ, nome="Beta Servicos ME", documento=CNPJ_B),
        valor_aluguel=Decimal("8000.00"),
        data_fim_vigencia=date(2027, 5, 1),
        reajuste=Reajuste(indice="IGP-M", proximo_reajuste="05/2026", automatico=False),
    )


def _contrato_incompleto() -> Contrato:
    """Sem valor de aluguel → IRRF não calculável → linha marcada p/ revisão."""
    return Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="Fulano"),
        locatario=Parte(tipo=TipoParte.PJ, nome="Delta ME", documento=CNPJ_X),
        valor_aluguel=None,
    )


def _relatorio_controller(contratos) -> RelatorioController:
    ctrl = RelatorioController(
        RelatorioService(_repo_portfolio()),
        ExcelRelatorioExporter(),
        PdfRelatorioExporter(),
    )
    ctrl.definir_contratos(contratos)
    return ctrl


# --------------------------------------------------------------------------- #
# Empresas: importação
# --------------------------------------------------------------------------- #
def test_importar_planilha_resume_importados_duplicados_e_erros(tmp_path):
    csv = tmp_path / "empresas.csv"
    csv.write_text(
        "cnpj,razao_social\n"
        f"{cnpj_valido_sequencial(10)},Alpha LTDA\n"
        f"{cnpj_valido_sequencial(11)},Beta ME\n"
        f"{cnpj_valido_sequencial(10)},Alpha Duplicada\n"  # duplicado
        "123,CNPJ Invalido\n",  # erro
        encoding="utf-8",
    )
    ctrl = EmpresasController(FakeEmpresaRepository())
    resumo = ctrl.importar_planilha(csv)

    assert resumo.importados == 2
    assert resumo.duplicados == 1
    assert resumo.total_erros == 1


def test_importar_arquivo_inexistente_vira_controller_error(tmp_path):
    ctrl = EmpresasController(FakeEmpresaRepository())
    with pytest.raises(ControllerError):
        ctrl.importar_planilha(tmp_path / "nao_existe.csv")


# --------------------------------------------------------------------------- #
# Empresas: CRUD manual
# --------------------------------------------------------------------------- #
def test_crud_empresa_completo():
    ctrl = EmpresasController(FakeEmpresaRepository())
    ctrl.adicionar_empresa(CNPJ_A, "Alpha Comercio LTDA")

    linhas = ctrl.linhas_empresas()
    assert len(linhas) == 1
    assert linhas[0].cnpj == CNPJ_A
    assert linhas[0].razao_social == "Alpha Comercio LTDA"
    assert linhas[0].ativo == "Sim"

    ctrl.editar_empresa(CNPJ_A, razao_social="Alpha Renomeada LTDA")
    assert ctrl.linhas_empresas()[0].razao_social == "Alpha Renomeada LTDA"

    assert ctrl.remover_empresa(CNPJ_A) is True
    assert ctrl.linhas_empresas() == []


def test_adicionar_com_cnpj_invalido_vira_controller_error():
    ctrl = EmpresasController(FakeEmpresaRepository())
    with pytest.raises(ControllerError):
        ctrl.adicionar_empresa("123", "Razao Qualquer")


def test_editar_empresa_inexistente_vira_controller_error():
    ctrl = EmpresasController(FakeEmpresaRepository())
    with pytest.raises(ControllerError):
        ctrl.editar_empresa(CNPJ_A, razao_social="Nova")


_JARGAO_TECNICO_PROIBIDO = (
    "validation error",
    "value_error",
    "input_value",
    "For further information visit",
    "errors.pydantic.dev",
)


def test_adicionar_empresa_com_campos_vazios_mensagem_amigavel():
    """Regressão: dump técnico do pydantic não pode vazar para a mensagem da GUI.

    Reproduz o bug relatado pelo usuário (screenshot): clicar em "Adicionar" com
    CNPJ e Razão Social vazios mostrava o ``str()`` bruto de um
    ``pydantic.ValidationError`` (jargão + URL de documentação da lib).
    """
    ctrl = EmpresasController(FakeEmpresaRepository())
    with pytest.raises(ControllerError) as exc_info:
        ctrl.adicionar_empresa("", "")
    mensagem = str(exc_info.value)

    for jargao in _JARGAO_TECNICO_PROIBIDO:
        assert jargao not in mensagem, f"Jargão técnico vazou para a UI: {jargao!r}"
    assert "CNPJ" in mensagem
    assert "razão social" in mensagem.lower()


def test_editar_empresa_com_razao_social_vazia_mensagem_amigavel():
    """Mesmo bug em ``editar_empresa``: ``ValidationError`` é subclasse de
    ``ValueError`` e caía no ``except ValueError`` genérico sem tradução."""
    ctrl = EmpresasController(FakeEmpresaRepository())
    ctrl.adicionar_empresa(CNPJ_A, "Alpha Comercio LTDA")

    with pytest.raises(ControllerError) as exc_info:
        ctrl.editar_empresa(CNPJ_A, razao_social="")
    mensagem = str(exc_info.value)

    for jargao in _JARGAO_TECNICO_PROIBIDO:
        assert jargao not in mensagem, f"Jargão técnico vazou para a UI: {jargao!r}"
    assert "razão social" in mensagem.lower()


def test_linhas_empresas_ordenadas_por_razao_social():
    repo = FakeEmpresaRepository()
    repo.add(Empresa(cnpj=CNPJ_B, razao_social="Zeta"))
    repo.add(Empresa(cnpj=CNPJ_A, razao_social="Alpha"))
    linhas = EmpresasController(repo).linhas_empresas()
    assert [linha.razao_social for linha in linhas] == ["Alpha", "Zeta"]


# --------------------------------------------------------------------------- #
# Processamento
# --------------------------------------------------------------------------- #
def test_processar_pasta_extrai_um_contrato_por_documento():
    texto = carregar_contrato(RESIDENCIAL_PF_PJ)
    resumo = IngestaoResumo(
        total_arquivos=1,
        processados=1,
        documentos=[DocumentoTexto(caminho="c1.pdf", hash="h1", texto=texto, metodo="nativo")],
    )
    ctrl = ProcessamentoController(FakeIngestor(resumo), ExtratorContrato())
    resultado = ctrl.processar_pasta("qualquer")

    assert resultado.total_arquivos == 1
    assert resultado.processados == 1
    assert len(resultado.contratos) == 1
    # A extração real (motor determinístico) rodou sobre o texto da fixture.
    assert isinstance(resultado.contratos[0], Contrato)
    assert ctrl.contratos() == resultado.contratos


def test_processar_pasta_propaga_erros_por_arquivo():
    resumo = IngestaoResumo(
        total_arquivos=2,
        processados=0,
        erros=[ErroArquivo("corrompido.pdf", "Falha ao abrir PDF")],
    )
    ctrl = ProcessamentoController(FakeIngestor(resumo), ExtratorContrato())
    resultado = ctrl.processar_pasta("x")
    assert resultado.erros == [("corrompido.pdf", "Falha ao abrir PDF")]
    assert resultado.contratos == []


# --------------------------------------------------------------------------- #
# Painel (Relatório 01)
# --------------------------------------------------------------------------- #
def test_linhas_painel_formatadas_ptbr():
    ctrl = _relatorio_controller([_contrato_pf_pj()])
    linha = ctrl.linhas_painel()[0]

    assert linha.locatario == "Alpha Comercio LTDA"
    assert linha.locador == "João da Silva"
    assert linha.valor == "R$ 5.000,00"
    assert linha.irrf == "R$ 466,27"
    assert linha.indice == "IPCA"
    assert linha.automatico == "Sim"
    assert linha.vencimento == "10/10/2028"
    assert linha.revisao is False


def test_linha_incompleta_marca_revisao():
    ctrl = _relatorio_controller([_contrato_incompleto()])
    assert ctrl.linhas_painel()[0].revisao is True


def test_filtrar_por_indice():
    ctrl = _relatorio_controller([_contrato_pf_pj(), _contrato_locador_pj()])
    apenas_ipca = ctrl.filtrar(indice="IPCA")
    assert len(apenas_ipca) == 1
    assert apenas_ipca[0].indice == "IPCA"


def test_filtrar_por_reajuste_automatico():
    ctrl = _relatorio_controller([_contrato_pf_pj(), _contrato_locador_pj()])
    autos = ctrl.filtrar(apenas_automatico=True)
    assert [linha.automatico for linha in autos] == ["Sim"]


def test_filtrar_por_texto_livre():
    ctrl = _relatorio_controller([_contrato_pf_pj(), _contrato_locador_pj()])
    beta = ctrl.filtrar(texto="beta")
    assert len(beta) == 1
    assert beta[0].locatario == "Beta Servicos ME"


def test_indices_disponiveis_ordenados():
    ctrl = _relatorio_controller([_contrato_pf_pj(), _contrato_locador_pj()])
    assert ctrl.indices_disponiveis() == ["IGP-M", "IPCA"]


# --------------------------------------------------------------------------- #
# Conformidade (Relatório 02) + Exportação (7A)
# --------------------------------------------------------------------------- #
def test_resumo_conformidade_pendencia_mensagem_exata():
    ctrl = _relatorio_controller([_contrato_pf_pj(), _contrato_locador_pj()])
    resumo = ctrl.resumo_conformidade()
    assert resumo.total_empresas_cadastradas == 3
    assert resumo.total_encontrados == 2
    assert resumo.pendencias == [
        f"Contrato da Empresa Gamma Holding SA / {CNPJ_C} não encontrado"
    ]


def test_exportar_excel_grava_arquivo(tmp_path):
    ctrl = _relatorio_controller([_contrato_pf_pj()])
    destino = ctrl.exportar("excel", tmp_path / "relatorio.xlsx")
    assert destino.exists() and destino.stat().st_size > 0


def test_exportar_pdf_grava_arquivo(tmp_path):
    ctrl = _relatorio_controller([_contrato_pf_pj()])
    destino = ctrl.exportar("pdf", tmp_path / "relatorio.pdf")
    assert destino.exists() and destino.stat().st_size > 0


def test_exportar_formato_invalido_levanta_value_error(tmp_path):
    ctrl = _relatorio_controller([_contrato_pf_pj()])
    with pytest.raises(ValueError):
        ctrl.exportar("json", tmp_path / "x.json")


def test_exportar_sem_dados_vira_controller_error(tmp_path):
    ctrl = RelatorioController(
        RelatorioService(_repo_portfolio()), ExcelRelatorioExporter(), PdfRelatorioExporter()
    )
    with pytest.raises(ControllerError):
        ctrl.exportar("excel", tmp_path / "x.xlsx")


# --------------------------------------------------------------------------- #
# AppController: orquestração + status de conexão (degradação graciosa)
# --------------------------------------------------------------------------- #
def test_app_processar_pasta_realimenta_painel_e_conformidade():
    texto = carregar_contrato(RESIDENCIAL_PF_PJ)
    resumo = IngestaoResumo(
        total_arquivos=1,
        processados=1,
        documentos=[DocumentoTexto(caminho="c1.pdf", hash="h1", texto=texto, metodo="nativo")],
    )
    app = AppController(_repo_portfolio(), ingestor=FakeIngestor(resumo))
    app.processar_pasta("qualquer")

    assert app.relatorio.tem_dados() is True
    assert len(app.relatorio.linhas_painel()) == 1


def test_status_conexao_ok():
    app = AppController(
        _repo_portfolio(), health_fn=lambda: HealthResult(ok=True, detalhe="pong")
    )
    status = app.status_conexao()
    assert isinstance(status, StatusConexao)
    assert status.ok is True


def test_status_conexao_degrada_quando_banco_indisponivel():
    app = AppController(
        _repo_portfolio(),
        health_fn=lambda: HealthResult(ok=False, detalhe="Banco SQLite inacessivel"),
    )
    status = app.status_conexao()
    assert status.ok is False
    assert "inacessivel" in status.detalhe


def test_status_conexao_nunca_lanca_mesmo_se_health_fn_falhar():
    def _boom() -> HealthResult:
        raise RuntimeError("falha inesperada")

    app = AppController(_repo_portfolio(), health_fn=_boom)
    status = app.status_conexao()
    assert status.ok is False


def test_empresas_degrada_quando_repo_falha():
    ctrl = EmpresasController(RepoQueFalha())
    with pytest.raises(ControllerError):
        ctrl.linhas_empresas()
