"""Importador em lote de empresas (.xlsx / .csv / .ods) — camada application.

Ingestão robusta (skill python-automation-pro): desacopla leitura de arquivo
(I/O isolado em ``_ler_linhas``) da regra de negócio (auto-mapeamento + dedup).
Depende da abstração ``EmpresaRepositoryProtocol``, nunca de pymongo.

Auto-mapeamento de colunas (RF01):
1. Por cabeçalho: CNPJ = header contendo "cnpj"; Razão Social = header contendo
   "razao"/"social"/"empresa"/"nome" (acentos são normalizados).
2. Fallback por padrão de valor: se o cabeçalho não resolver o CNPJ, escolhe a
   coluna cuja maioria dos valores vira 14 dígitos (``parece_cnpj``); a Razão
   Social cai na coluna textual restante com mais valores não-numéricos.

Estratégia de memória: ``openpyxl`` em ``read_only=True`` (streaming de linhas);
CSV via ``csv`` stdlib. Volumetria-alvo da Fase 2 é modesta (portfólio), mas o
padrão de streaming evita OOM se a base crescer.
"""
from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from odf import teletype
from odf.opendocument import load as load_ods
from odf.table import Table, TableCell, TableRow
from openpyxl import load_workbook
from pydantic import ValidationError

from contract_parser.domain.cnpj import CNPJInvalidoError, normalizar_cnpj, parece_cnpj
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.repositories import EmpresaRepositoryProtocol
from contract_parser.domain.validation_messages import formatar_erro_validacao

# Palavras-chave de cabeçalho, em ordem de prioridade, para a Razão Social.
_RAZAO_KEYWORDS = ("razao", "social", "empresa", "nome")
_CNPJ_KEYWORDS = ("cnpj",)

# Limiar da heurística de valor: fração mínima de células que "parecem CNPJ".
_LIMIAR_CNPJ_POR_VALOR = 0.6


class ArquivoImportacaoError(Exception):
    """Arquivo ausente, com extensão não suportada, corrompido ou sem colunas."""


@dataclass
class ErroLinha:
    """Erro atribuível a uma linha específica da planilha (1-based, com header)."""

    linha: int
    motivo: str


@dataclass
class ImportResumo:
    """Resumo do resultado de uma importação em lote."""

    total_linhas: int = 0
    importados: int = 0
    duplicados: int = 0
    erros: list[ErroLinha] = field(default_factory=list)

    @property
    def total_erros(self) -> int:
        return len(self.erros)


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalizar_header(valor: object) -> str:
    return _sem_acento(str(valor or "").strip().lower())


def _celula_str(valor: object) -> str:
    """Converte célula em string limpa; ``None`` → ``""``."""
    if valor is None:
        return ""
    return str(valor).strip()


def _ler_linhas_xlsx(caminho: Path) -> list[list[object]]:
    """Lê a primeira planilha do .xlsx em modo streaming (read_only)."""
    try:
        wb = load_workbook(filename=caminho, read_only=True, data_only=True)
    except Exception as exc:
        raise ArquivoImportacaoError(f"Falha ao abrir .xlsx {caminho}: {exc!r}") from exc
    try:
        ws = wb.active
        linhas = [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return linhas


def _ler_linhas_csv(caminho: Path) -> list[list[object]]:
    """Lê um .csv detectando o delimitador (``,``/``;``/tab) via Sniffer."""
    try:
        texto = caminho.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texto = caminho.read_text(encoding="latin-1")
    except OSError as exc:
        raise ArquivoImportacaoError(f"Falha ao ler .csv {caminho}: {exc!r}") from exc

    amostra = texto[:4096]
    try:
        dialect = csv.Sniffer().sniff(amostra, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel  # fallback: vírgula padrão
    return [list(row) for row in csv.reader(texto.splitlines(), dialect)]


def _valor_celula_ods(cell: TableCell) -> object:
    """Extrai o valor de uma célula ODS: número (``office:value``) ou texto."""
    if cell.getAttribute("valuetype") == "float":
        valor_bruto = cell.getAttribute("value")
        if valor_bruto is not None:
            numero = float(valor_bruto)
            # Espelha o comportamento do openpyxl: inteiro "limpo" vira int
            # (evita, por ex., perder o CNPJ pelo ponto decimal de "x.0").
            return int(numero) if numero.is_integer() else numero
    texto = teletype.extractText(cell)
    return texto if texto else None


def _ler_celulas_linha_ods(row: TableRow) -> list[object]:
    """Expande ``table:number-columns-repeated`` para não desalinhar colunas.

    Exceção: quando a repetição é a ÚLTIMA célula da linha E está vazia, ela
    representa apenas "o resto da linha está vazio até o limite do formato"
    (o LibreOffice Calc grava isso rotineiramente com valores na casa de
    centenas de milhares) — nesse caso a expansão é capada em 1 cópia, para
    não materializar células vazias sem sentido de negócio. Qualquer outra
    repetição (no meio da linha, ou com conteúdo não vazio) é expandida
    literalmente, pois o alinhamento de coluna depende disso.
    """
    celulas = row.getElementsByType(TableCell)
    valores: list[object] = []
    for i, cell in enumerate(celulas):
        valor = _valor_celula_ods(cell)
        repeticoes = int(cell.getAttribute("numbercolumnsrepeated") or 1)
        eh_ultima = i == len(celulas) - 1
        if valor is None and eh_ultima:
            repeticoes = 1
        valores.extend([valor] * repeticoes)
    return valores


def _ler_linhas_ods(caminho: Path) -> list[list[object]]:
    """Lê a primeira planilha do .ods (odfpy), expandindo linhas/células repetidas.

    O ODS comprime linhas e células vazias repetidas via os atributos
    ``table:number-rows-repeated``/``table:number-columns-repeated``; se não
    forem expandidos aqui, o auto-mapeamento de colunas desalinha silenciosamente.

    Exceção simétrica à de ``_ler_celulas_linha_ods``: a ÚLTIMA ``TableRow`` da
    tabela, se totalmente vazia, representa a cauda vazia da grade até o
    limite do formato (o LibreOffice Calc real grava isso com repetições na
    casa de milhões) — é capada em 1 cópia para não materializar a grade
    inteira. Repetições no meio da tabela continuam expandidas literalmente.
    """
    try:
        documento = load_ods(caminho)
    except Exception as exc:
        raise ArquivoImportacaoError(f"Falha ao abrir .ods {caminho}: {exc!r}") from exc

    tabelas = documento.spreadsheet.getElementsByType(Table)
    if not tabelas:
        return []

    linhas_tabela = tabelas[0].getElementsByType(TableRow)
    linhas: list[list[object]] = []
    for i, row in enumerate(linhas_tabela):
        valores = _ler_celulas_linha_ods(row)
        repeticoes = int(row.getAttribute("numberrowsrepeated") or 1)
        eh_ultima = i == len(linhas_tabela) - 1
        linha_vazia = not any(_celula_str(v) for v in valores)
        if linha_vazia and eh_ultima:
            repeticoes = 1
        linhas.extend([list(valores) for _ in range(repeticoes)])
    return linhas


def _ler_linhas(caminho: Path) -> list[list[object]]:
    sufixo = caminho.suffix.lower()
    if sufixo == ".xlsx":
        return _ler_linhas_xlsx(caminho)
    if sufixo == ".csv":
        return _ler_linhas_csv(caminho)
    if sufixo == ".ods":
        return _ler_linhas_ods(caminho)
    raise ArquivoImportacaoError(
        f"Extensão não suportada: {sufixo!r} (use .xlsx, .csv ou .ods)."
    )


def _achar_por_header(headers: list[str], keywords: tuple[str, ...], excluir: int | None = None) -> int | None:
    """Retorna o índice da 1ª coluna cujo header casa uma keyword (por prioridade)."""
    for kw in keywords:
        for i, h in enumerate(headers):
            if i == excluir:
                continue
            if kw in h:
                return i
    return None


def _achar_cnpj_por_valor(dados: list[list[object]], n_cols: int) -> int | None:
    """Fallback: coluna cuja maioria dos valores não-vazios vira 14 dígitos."""
    melhor_idx: int | None = None
    melhor_frac = _LIMIAR_CNPJ_POR_VALOR
    for c in range(n_cols):
        valores = [linha[c] for linha in dados if c < len(linha) and _celula_str(linha[c])]
        if not valores:
            continue
        acertos = sum(1 for v in valores if parece_cnpj(v))
        frac = acertos / len(valores)
        if frac >= melhor_frac:
            melhor_frac = frac
            melhor_idx = c
    return melhor_idx


def _achar_razao_por_valor(dados: list[list[object]], n_cols: int, excluir: int) -> int | None:
    """Fallback: coluna textual (mais valores não-numéricos), excluindo a de CNPJ."""
    melhor_idx: int | None = None
    melhor_score = -1
    for c in range(n_cols):
        if c == excluir:
            continue
        valores = [_celula_str(linha[c]) for linha in dados if c < len(linha)]
        score = sum(1 for v in valores if v and not v.replace(".", "").replace("/", "").replace("-", "").isdigit())
        if score > melhor_score:
            melhor_score = score
            melhor_idx = c
    return melhor_idx if melhor_score > 0 else None


@dataclass(frozen=True)
class MapeamentoColunas:
    idx_cnpj: int
    idx_razao: int


def detectar_colunas(headers: list[object], dados: list[list[object]]) -> MapeamentoColunas:
    """Determina os índices das colunas de CNPJ e Razão Social.

    Combina heurística de cabeçalho com fallback por padrão de valor. Levanta
    ``ArquivoImportacaoError`` se não conseguir localizar a coluna de CNPJ.
    """
    headers_norm = [_normalizar_header(h) for h in headers]
    # A lista sempre tem ao menos ``len(headers_norm)``, logo max() nunca recebe vazio.
    n_cols = max([len(headers_norm), *(len(linha) for linha in dados)])

    idx_cnpj = _achar_por_header(headers_norm, _CNPJ_KEYWORDS)
    if idx_cnpj is None:
        idx_cnpj = _achar_cnpj_por_valor(dados, n_cols)
    if idx_cnpj is None:
        raise ArquivoImportacaoError(
            "Não foi possível identificar a coluna de CNPJ (nem por cabeçalho, nem por valor)."
        )

    idx_razao = _achar_por_header(headers_norm, _RAZAO_KEYWORDS, excluir=idx_cnpj)
    if idx_razao is None:
        idx_razao = _achar_razao_por_valor(dados, n_cols, excluir=idx_cnpj)
    if idx_razao is None:
        raise ArquivoImportacaoError(
            "Não foi possível identificar a coluna de Razão Social."
        )
    return MapeamentoColunas(idx_cnpj=idx_cnpj, idx_razao=idx_razao)


class EmpresaImporter:
    """Caso de uso: importar um arquivo de empresas para o repositório."""

    def __init__(self, repository: EmpresaRepositoryProtocol) -> None:
        self._repo = repository

    def importar(self, caminho: str | Path) -> ImportResumo:
        """Importa .xlsx/.csv: auto-mapeia, normaliza, deduplica e persiste.

        Erros de linha (CNPJ inválido, razão vazia) NÃO abortam o lote — são
        acumulados no resumo. Persistência via ``upsert_many`` (idempotente).
        """
        caminho = Path(caminho)
        if not caminho.is_file():
            raise ArquivoImportacaoError(f"Arquivo não encontrado: {caminho}")

        linhas = _ler_linhas(caminho)
        resumo = ImportResumo()
        if not linhas:
            return resumo

        headers, dados = linhas[0], linhas[1:]
        resumo.total_linhas = len(dados)
        mapa = detectar_colunas(headers, dados)

        vistos: set[str] = set()
        a_persistir: list[Empresa] = []
        origem = caminho.name

        for offset, linha in enumerate(dados):
            n_linha = offset + 2  # 1-based + header
            cnpj_bruto = linha[mapa.idx_cnpj] if mapa.idx_cnpj < len(linha) else None
            razao_bruto = linha[mapa.idx_razao] if mapa.idx_razao < len(linha) else None

            if not _celula_str(cnpj_bruto) and not _celula_str(razao_bruto):
                continue  # linha totalmente vazia: ignora silenciosamente

            try:
                cnpj = normalizar_cnpj(cnpj_bruto) if cnpj_bruto is not None else ""
                if not cnpj:
                    raise CNPJInvalidoError("CNPJ ausente na linha.")
            except CNPJInvalidoError as exc:
                resumo.erros.append(ErroLinha(n_linha, f"CNPJ inválido: {exc}"))
                continue

            if cnpj in vistos:
                resumo.duplicados += 1
                continue

            try:
                empresa = Empresa(
                    cnpj=cnpj,
                    razao_social=_celula_str(razao_bruto),
                    origem_import=origem,
                )
            except ValidationError as exc:
                resumo.erros.append(
                    ErroLinha(n_linha, f"Dados inválidos: {formatar_erro_validacao(exc)}")
                )
                continue
            except ValueError as exc:
                resumo.erros.append(ErroLinha(n_linha, f"Dados inválidos: {exc}"))
                continue

            vistos.add(cnpj)
            a_persistir.append(empresa)

        if a_persistir:
            self._repo.upsert_many(a_persistir)
            resumo.importados = len(a_persistir)
        return resumo
