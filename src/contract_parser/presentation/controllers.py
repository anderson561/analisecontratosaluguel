"""Controllers / ViewModels da GUI (RF06) — camada presentation, SEM Tkinter.

Toda a lógica de apresentação vive aqui, em objetos 100% testáveis headless
(padrão MVVM): recebem os serviços de ``application``/``infrastructure`` por
injeção de dependência e expõem métodos de alto nível que as views CustomTkinter
apenas disparam. **Este módulo NÃO importa ``customtkinter``/``tkinter``** — a
suíte de testes roda sem display e sem a lib gráfica instalada.

Princípios (ADR-001 + ADR-002 + skills UX/Python):
- **Degradação graciosa (§6):** falha de banco (``RepositoryError``) ou de
  arquivo nunca derruba a UI — vira uma :class:`ControllerError` com mensagem
  legível que a view exibe. ``status_conexao`` reporta o estado do banco SQLite
  sem lançar.
- **Reuso, não reimplementação:** a formatação pt-BR (R$/dd-mm-aaaa) e a montagem
  de relatórios/exportadores são REusadas da Fase 6/7A, não reescritas.
- **Camadas:** presentation → application/infrastructure por injeção; nenhuma
  regra de negócio é implementada aqui (só orquestração + apresentação). Desde
  a migração ADR-002, esta camada captura apenas ``RepositoryError`` (nunca uma
  exceção de driver de banco — antes ``PyMongoError``, hoje ``sqlite3.Error``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contract_parser.application.contract_extraction_service import ExtratorContrato
from contract_parser.application.document_ingestor import (
    DiretorioIngestaoError,
    IngestaoResumo,
)
from contract_parser.application.empresa_importer import (
    ArquivoImportacaoError,
    EmpresaImporter,
    ImportResumo,
)
from contract_parser.application.empresa_service import EmpresaService
from contract_parser.application.relatorio_service import RelatorioService
from contract_parser.domain.contrato import Contrato
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.relatorio import LinhaContrato, Relatorio, ResumoConformidade
from contract_parser.domain.repositories import EmpresaRepositoryProtocol
from contract_parser.infrastructure.database import HealthResult, RepositoryError, check_health
from contract_parser.infrastructure.report_exporters import (
    ExcelRelatorioExporter,
    PdfRelatorioExporter,
    formatar_data_br,
    formatar_moeda_brl,
)


class ControllerError(Exception):
    """Erro de apresentação já traduzido para exibição amigável na GUI.

    As views capturam esta exceção e mostram ``str(erro)`` num banner/diálogo —
    nunca um stack trace cru. Envolve exceções de banco/arquivo/validação.
    """


def _sim_nao(valor: bool) -> str:
    return "Sim" if valor else "Não"


# --------------------------------------------------------------------------- #
# DTOs de apresentação (linhas de tabela)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LinhaEmpresa:
    """Uma linha da tabela de portfólio (aba Empresas), já apresentável."""

    cnpj: str
    razao_social: str
    ativo: str
    origem: str


@dataclass(frozen=True)
class LinhaPainel:
    """Uma linha do Painel de Contratos (Relatório 01), já formatada pt-BR.

    ``revisao`` sinaliza destaque visual: contrato com dado incompleto (IRRF não
    calculável) ou qualquer campo marcado para conferência manual (§6).
    """

    locatario: str
    locador: str
    valor: str
    irrf: str
    indice: str
    proximo_reajuste: str
    automatico: str
    vencimento: str
    revisao: bool


@dataclass(frozen=True)
class StatusConexao:
    """Estado do banco de dados para o banner de status da GUI (nunca lança)."""

    ok: bool
    detalhe: str


@dataclass
class ProcessamentoResultado:
    """Feedback estruturado de um processamento de pasta (aba Processamento)."""

    ingestao: IngestaoResumo
    contratos: list[Contrato] = field(default_factory=list)

    @property
    def total_arquivos(self) -> int:
        return self.ingestao.total_arquivos

    @property
    def processados(self) -> int:
        return self.ingestao.processados

    @property
    def duplicados(self) -> int:
        return self.ingestao.duplicados

    @property
    def erros(self) -> list[tuple[str, str]]:
        """Lista ``(arquivo, motivo)`` — feedback de erro por arquivo (§6)."""
        return [(e.arquivo, e.motivo) for e in self.ingestao.erros]


# --------------------------------------------------------------------------- #
# Empresas (importação + CRUD manual)
# --------------------------------------------------------------------------- #
class EmpresasController:
    """ViewModel da aba Empresas: importação em lote + CRUD manual (RF01)."""

    def __init__(
        self,
        repository: EmpresaRepositoryProtocol,
        *,
        importer: EmpresaImporter | None = None,
        service: EmpresaService | None = None,
    ) -> None:
        self._repo = repository
        self._importer = importer if importer is not None else EmpresaImporter(repository)
        self._service = service if service is not None else EmpresaService(repository)

    def importar_planilha(self, caminho: str | Path) -> ImportResumo:
        """Importa um ``.xlsx``/``.csv`` e devolve o resumo (importados/dup/erros)."""
        try:
            return self._importer.importar(caminho)
        except ArquivoImportacaoError as exc:
            raise ControllerError(f"Não foi possível importar o arquivo: {exc}") from exc
        except RepositoryError as exc:
            raise ControllerError(_MSG_BANCO) from exc

    def empresas(self) -> list[Empresa]:
        """Portfólio cadastrado (modelos de domínio)."""
        try:
            return self._repo.list_all()
        except RepositoryError as exc:
            raise ControllerError(_MSG_BANCO) from exc

    def linhas_empresas(self) -> list[LinhaEmpresa]:
        """Portfólio já formatado para a tabela da GUI (ordenado por razão social)."""
        empresas = sorted(self.empresas(), key=lambda e: e.razao_social.lower())
        return [
            LinhaEmpresa(
                cnpj=e.cnpj,
                razao_social=e.razao_social,
                ativo=_sim_nao(e.ativo),
                origem=e.origem_import or "",
            )
            for e in empresas
        ]

    def adicionar_empresa(
        self,
        cnpj: str,
        razao_social: str,
        *,
        ativo: bool = True,
    ) -> Empresa:
        """Cadastra manualmente uma empresa (validação/normalização no domínio)."""
        try:
            return self._service.adicionar(cnpj, razao_social, ativo=ativo)
        except RepositoryError as exc:
            raise ControllerError(_MSG_BANCO) from exc
        except Exception as exc:
            raise ControllerError(f"Dados inválidos ou empresa já existente: {exc}") from exc

    def editar_empresa(
        self,
        cnpj: str,
        *,
        razao_social: str | None = None,
        ativo: bool | None = None,
    ) -> Empresa:
        """Edita uma empresa existente (match por CNPJ)."""
        try:
            return self._service.editar(cnpj, razao_social=razao_social, ativo=ativo)
        except KeyError as exc:
            raise ControllerError(f"Empresa não encontrada: {exc}") from exc
        except RepositoryError as exc:
            raise ControllerError(_MSG_BANCO) from exc
        except ValueError as exc:
            raise ControllerError(f"Dados inválidos: {exc}") from exc

    def remover_empresa(self, cnpj: str) -> bool:
        """Remove uma empresa por CNPJ. Retorna ``True`` se removeu."""
        try:
            return self._service.remover(cnpj)
        except RepositoryError as exc:
            raise ControllerError(_MSG_BANCO) from exc


_MSG_BANCO = (
    "Sem conexão com o banco. Verifique se o arquivo do banco de dados é "
    "acessível (permissão de leitura/escrita no caminho configurado) e tente "
    "novamente."
)


# --------------------------------------------------------------------------- #
# Processamento (ingestão de pasta + extração híbrida)
# --------------------------------------------------------------------------- #
class ProcessamentoController:
    """ViewModel da aba Processamento: varre a pasta e extrai os contratos (RF02/03).

    ``ingestor`` deve expor ``ingerir(pasta) -> IngestaoResumo`` (o
    :class:`~contract_parser.application.document_ingestor.DirectoryIngestor` de
    produção; um fake nos testes). ``extrator`` é o :class:`ExtratorContrato`.
    """

    def __init__(self, ingestor: object, extrator: ExtratorContrato) -> None:
        self._ingestor = ingestor
        self._extrator = extrator
        self._contratos: list[Contrato] = []

    def processar_pasta(self, pasta: str | Path) -> ProcessamentoResultado:
        """Ingere a pasta, extrai um :class:`Contrato` por documento aproveitável."""
        try:
            ingestao = self._ingestor.ingerir(pasta)
        except DiretorioIngestaoError as exc:
            raise ControllerError(f"Pasta inválida: {exc}") from exc

        contratos = [self._extrator.extrair(doc.texto) for doc in ingestao.documentos]
        self._contratos = contratos
        return ProcessamentoResultado(ingestao=ingestao, contratos=contratos)

    def contratos(self) -> list[Contrato]:
        """Contratos extraídos no último processamento (vazio antes de processar)."""
        return list(self._contratos)


# --------------------------------------------------------------------------- #
# Relatório (Painel de contratos + Conformidade + Exportação)
# --------------------------------------------------------------------------- #
class RelatorioController:
    """ViewModel do Painel (Relatório 01) e da Conformidade (Relatório 02).

    Recebe os contratos processados via :meth:`definir_contratos`, monta o
    :class:`Relatorio` de domínio (delegando ao :class:`RelatorioService`) e
    expõe as linhas formatadas, os filtros e a exportação PDF/Excel (7A).
    """

    def __init__(
        self,
        service: RelatorioService,
        excel_exporter: ExcelRelatorioExporter,
        pdf_exporter: PdfRelatorioExporter,
    ) -> None:
        self._service = service
        self._excel = excel_exporter
        self._pdf = pdf_exporter
        self._contratos: list[Contrato] = []
        self._relatorio: Relatorio | None = None
        # Pares (linha do relatório, contrato de origem) para filtragem/destaque.
        self._pares: list[tuple[LinhaContrato, Contrato]] = []

    def definir_contratos(self, contratos: list[Contrato]) -> None:
        """Recalcula os relatórios a partir dos contratos processados."""
        self._contratos = list(contratos)
        try:
            self._relatorio = self._service.montar(self._contratos)
        except RepositoryError as exc:
            self._relatorio = None
            self._pares = []
            raise ControllerError(_MSG_BANCO) from exc
        self._pares = list(zip(self._relatorio.contratos.linhas, self._contratos, strict=True))

    def tem_dados(self) -> bool:
        return self._relatorio is not None

    # -- Painel (Relatório 01) --------------------------------------------- #
    @staticmethod
    def _linha_painel(linha: LinhaContrato, contrato: Contrato) -> LinhaPainel:
        revisao = linha.dados_incompletos or contrato.necessita_revisao
        return LinhaPainel(
            locatario=linha.locatario_nome or "",
            locador=linha.locador_nome or "",
            valor=formatar_moeda_brl(linha.valor_aluguel),
            irrf=formatar_moeda_brl(linha.irrf_retido),
            indice=linha.indice or "",
            proximo_reajuste=linha.proximo_reajuste or "",
            automatico=_sim_nao(linha.reajuste_automatico),
            vencimento=formatar_data_br(linha.vencimento),
            revisao=revisao,
        )

    def linhas_painel(self) -> list[LinhaPainel]:
        """Todas as linhas do Painel (ordem de entrada dos contratos)."""
        return [self._linha_painel(linha, c) for linha, c in self._pares]

    def indices_disponiveis(self) -> list[str]:
        """Índices de reajuste distintos presentes (para o dropdown de filtro)."""
        indices = {linha.indice for linha, _ in self._pares if linha.indice}
        return sorted(indices)

    def filtrar(
        self,
        *,
        indice: str | None = None,
        apenas_automatico: bool | None = None,
        texto: str | None = None,
    ) -> list[LinhaPainel]:
        """Filtra o Painel por índice, flag de reajuste automático e/ou texto livre.

        - ``indice``: igualdade case-insensitive (``None`` = todos).
        - ``apenas_automatico``: ``True`` só automáticos, ``False`` só manuais,
          ``None`` ambos.
        - ``texto``: substring case-insensitive em locatário/locador/índice/CNPJ.
        """
        alvo = (texto or "").strip().lower()
        indice_alvo = (indice or "").strip().lower()
        resultado: list[LinhaPainel] = []
        for linha, contrato in self._pares:
            if indice_alvo and (linha.indice or "").lower() != indice_alvo:
                continue
            if apenas_automatico is not None and linha.reajuste_automatico != apenas_automatico:
                continue
            if alvo:
                campos = " ".join(
                    filter(
                        None,
                        [
                            linha.locatario_nome,
                            linha.locador_nome,
                            linha.indice,
                            linha.locatario_cnpj,
                        ],
                    )
                ).lower()
                if alvo not in campos:
                    continue
            resultado.append(self._linha_painel(linha, contrato))
        return resultado

    # -- Conformidade (Relatório 02) --------------------------------------- #
    def resumo_conformidade(self) -> ResumoConformidade:
        """Totais + pendências (mensagem exata do PRD) do Relatório 02."""
        if self._relatorio is None:
            raise ControllerError("Processe uma pasta de contratos antes de ver a conformidade.")
        return self._relatorio.conformidade

    # -- Exportação (7A) --------------------------------------------------- #
    def exportar(self, formato: str, destino: str | Path) -> Path:
        """Exporta o relatório completo para ``excel``/``xlsx`` ou ``pdf``."""
        if self._relatorio is None:
            raise ControllerError("Nada para exportar: processe uma pasta de contratos antes.")
        fmt = (formato or "").strip().lower()
        exporter: ExcelRelatorioExporter | PdfRelatorioExporter
        if fmt in ("excel", "xlsx"):
            exporter = self._excel
        elif fmt == "pdf":
            exporter = self._pdf
        else:
            raise ValueError(f"Formato de exportação não suportado: {formato!r} (use excel/pdf).")
        try:
            return exporter.exportar(self._relatorio, Path(destino))
        except OSError as exc:
            raise ControllerError(f"Falha ao gravar o arquivo de saída: {exc}") from exc


# --------------------------------------------------------------------------- #
# Controller raiz (compõe as abas + status de conexão)
# --------------------------------------------------------------------------- #
def _default_extractors() -> list[object]:
    """Backends de extração de produção (imports pesados são lazy dentro deles)."""
    from contract_parser.infrastructure.text_extractors import DocxExtractor, PdfExtractor

    return [PdfExtractor(), DocxExtractor()]


class AppController:
    """ViewModel raiz: injeta o repositório e compõe os controllers das abas.

    Tudo é injetável (fakes nos testes; serviços reais em ``app.main``). A criação
    do banco NÃO é feita aqui — o repositório vem pronto de fora (degradação
    graciosa: a GUI abre mesmo com o banco fora do ar).
    """

    def __init__(
        self,
        repository: EmpresaRepositoryProtocol,
        *,
        ingestor: object | None = None,
        extrator: ExtratorContrato | None = None,
        relatorio_service: RelatorioService | None = None,
        excel_exporter: ExcelRelatorioExporter | None = None,
        pdf_exporter: PdfRelatorioExporter | None = None,
        health_fn=check_health,
    ) -> None:
        from contract_parser.application.document_ingestor import DirectoryIngestor

        self._repo = repository
        self._health_fn = health_fn

        self.empresas = EmpresasController(repository)
        self.processamento = ProcessamentoController(
            ingestor if ingestor is not None else DirectoryIngestor(_default_extractors()),
            extrator if extrator is not None else ExtratorContrato(),
        )
        self.relatorio = RelatorioController(
            relatorio_service if relatorio_service is not None else RelatorioService(repository),
            excel_exporter if excel_exporter is not None else ExcelRelatorioExporter(),
            pdf_exporter if pdf_exporter is not None else PdfRelatorioExporter(),
        )

    def processar_pasta(self, pasta: str | Path) -> ProcessamentoResultado:
        """Processa a pasta E realimenta o Painel/Conformidade com os contratos."""
        resultado = self.processamento.processar_pasta(pasta)
        self.relatorio.definir_contratos(resultado.contratos)
        return resultado

    def status_conexao(self) -> StatusConexao:
        """Estado do banco de dados para o banner da GUI. NUNCA lança (degradação §6)."""
        try:
            health: HealthResult = self._health_fn()
            return StatusConexao(ok=health.ok, detalhe=health.detalhe)
        except Exception as exc:  # noqa: BLE001 - o banner de status jamais derruba a UI
            return StatusConexao(ok=False, detalhe=f"Falha ao checar o banco de dados: {exc!r}")
