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

# Teto de sanidade para repetição (``number-rows/columns-repeated``) de um
# elemento ODS que TEM conteúdo real. Planilhas reais nunca repetem uma
# célula/linha com dado de negócio milhares de vezes — isso é defesa em
# profundidade contra ODS malformado/adversarial (não o caso comum, que é a
# cauda vazia tratada pelo trim reverso). Valor escolhido com folga acima de
# qualquer portfólio real esperado (dezenas/centenas de empresas).
_MAX_REPETICOES_RAZOAVEL = 5000


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


def _celula_tem_conteudo_real(cell: TableCell) -> bool:
    """``True`` se a célula (1 cópia, sem considerar repetição) tem valor não vazio."""
    return bool(_celula_str(_valor_celula_ods(cell)))


def _linha_tem_conteudo_real(row: TableRow) -> bool:
    """``True`` se alguma célula da linha (1 cópia cada, sem expandir repetição) tem valor."""
    return any(_celula_tem_conteudo_real(c) for c in row.getElementsByType(TableCell))


def _trim_reverso(elementos: list, tem_conteudo_real) -> int:
    """Acha o último índice de ``elementos`` com conteúdo real, de trás pra frente.

    NÃO expande ``number-rows/columns-repeated`` — só usado para decidir até
    onde a expansão (passe 2, em ``_ler_celulas_linha_ods``/``_ler_linhas_de_tabela``)
    deve ir. Retorna -1 se nenhum elemento tem conteúdo real (todos vazios).
    """
    for i in range(len(elementos) - 1, -1, -1):
        if tem_conteudo_real(elementos[i]):
            return i
    return -1


def _ler_celulas_linha_ods(row: TableRow) -> list[object]:
    """Expande ``table:number-columns-repeated``, descartando a cauda vazia.

    Trim reverso (passe 1: ``_trim_reverso``) acha a última célula com
    conteúdo real; tudo depois dela é descartado inteiramente — não há mais
    caso especial para "a última célula", só "o que vem depois do último
    conteúdo real não existe". Células até esse ponto são expandidas
    literalmente (passe 2), pois o alinhamento de coluna depende disso.
    Teto de sanidade: uma célula com conteúdo real repetida de forma
    anormal (acima de ``_MAX_REPETICOES_RAZOAVEL``) levanta erro em vez de
    materializar silenciosamente um número absurdo de cópias de um dado real.
    """
    celulas = row.getElementsByType(TableCell)
    i_max = _trim_reverso(celulas, _celula_tem_conteudo_real)
    valores: list[object] = []
    for i in range(i_max + 1):
        cell = celulas[i]
        valor = _valor_celula_ods(cell)
        repeticoes = int(cell.getAttribute("numbercolumnsrepeated") or 1)
        if _celula_str(valor) and repeticoes > _MAX_REPETICOES_RAZOAVEL:
            raise ArquivoImportacaoError(
                f"Célula com conteúdo real repetida {repeticoes} vezes "
                f"(acima do teto de sanidade de {_MAX_REPETICOES_RAZOAVEL}) — "
                "verifique o arquivo, o dado não foi importado."
            )
        valores.extend([valor] * repeticoes)
    return valores


def _ler_linhas_de_tabela(tabela: Table) -> list[list[object]]:
    """Lê uma ``Table`` (aba) do .ods aplicando o trim reverso + teto de sanidade.

    Compartilhada por ``_ler_linhas_ods`` (leitura de uma aba específica) e
    ``listar_abas`` (leitura de todas as abas), para não duplicar a lógica de
    expansão/trim. Mesma estratégia de ``_ler_celulas_linha_ods``: acha a
    última ``TableRow`` com conteúdo real (passe 1) e só expande repetição
    literal até ali (passe 2) — a cauda vazia depois dela é descartada
    inteiramente.
    """
    linhas_tabela = tabela.getElementsByType(TableRow)
    i_max = _trim_reverso(linhas_tabela, _linha_tem_conteudo_real)
    linhas: list[list[object]] = []
    for i in range(i_max + 1):
        row = linhas_tabela[i]
        valores = _ler_celulas_linha_ods(row)
        repeticoes = int(row.getAttribute("numberrowsrepeated") or 1)
        linha_vazia = not any(_celula_str(v) for v in valores)
        if not linha_vazia and repeticoes > _MAX_REPETICOES_RAZOAVEL:
            raise ArquivoImportacaoError(
                f"Linha com conteúdo real repetida {repeticoes} vezes "
                f"(acima do teto de sanidade de {_MAX_REPETICOES_RAZOAVEL}) — "
                "verifique o arquivo, o dado não foi importado."
            )
        linhas.extend([list(valores) for _ in range(repeticoes)])
    return linhas


def _carregar_tabelas_ods(caminho: Path) -> list[Table]:
    """Abre o .ods e retorna suas abas (``Table``), ou levanta ``ArquivoImportacaoError``."""
    try:
        documento = load_ods(caminho)
    except Exception as exc:
        raise ArquivoImportacaoError(f"Falha ao abrir .ods {caminho}: {exc!r}") from exc
    return documento.spreadsheet.getElementsByType(Table)


def _ler_linhas_ods(caminho: Path, indice_aba: int = 0) -> list[list[object]]:
    """Lê uma aba (``Table``) do .ods (odfpy), expandindo linhas/células repetidas.

    O ODS comprime linhas e células vazias repetidas via os atributos
    ``table:number-rows-repeated``/``table:number-columns-repeated``; se não
    forem expandidos aqui, o auto-mapeamento de colunas desalinha silenciosamente.
    Ver ``_ler_linhas_de_tabela`` para o trim reverso da cauda vazia.
    """
    tabelas = _carregar_tabelas_ods(caminho)
    if not tabelas:
        return []
    if not (0 <= indice_aba < len(tabelas)):
        raise ArquivoImportacaoError(
            f"Aba {indice_aba} não existe (arquivo tem {len(tabelas)} aba(s))."
        )
    return _ler_linhas_de_tabela(tabelas[indice_aba])


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


def detectar_linha_header(linhas: list[list[object]], max_linhas_busca: int = 10) -> int:
    """Acha, entre as primeiras ``max_linhas_busca`` linhas, a que mais parece
    um cabeçalho real (headers+dados já juntos, como vem de ``_ler_linhas*``).

    Reaproveita a mesma heurística de palavras-chave de ``detectar_colunas``
    (``_achar_por_header``/``_normalizar_header``): cada linha candidata
    pontua 0, 1 ou 2 conforme encontra keyword de CNPJ e/ou de Razão Social.
    Maior pontuação vence; empate → menor índice; nenhuma linha pontua →
    retorna 0 (preserva o comportamento atual de assumir a linha 0 como
    header, sem quebrar os testes existentes).

    Motivo de negócio: planilhas reais às vezes têm uma linha de título
    mesclado antes do header de verdade (ex.: "MAPA DE ALUGUÉIS ..." na linha
    0) — sem isso, o header real vira "linha de dado" e gera um erro espúrio
    de CNPJ inválido.
    """
    melhor_idx = 0
    melhor_pontos = 0
    limite = min(max_linhas_busca, len(linhas))
    for i in range(limite):
        headers_norm = [_normalizar_header(v) for v in linhas[i]]
        pontos = 0
        if _achar_por_header(headers_norm, _CNPJ_KEYWORDS) is not None:
            pontos += 1
        if _achar_por_header(headers_norm, _RAZAO_KEYWORDS) is not None:
            pontos += 1
        if pontos > melhor_pontos:
            melhor_pontos = pontos
            melhor_idx = i
    return melhor_idx


# Nº de linhas de amostra guardadas por aba em ``AbaInfo.amostra``.
_TAMANHO_AMOSTRA = 20


@dataclass(frozen=True)
class AbaInfo:
    """Metadados de uma aba de planilha, para uma futura tela de confirmação."""

    indice: int
    nome: str
    n_linhas_uteis: int
    amostra: list[list[object]]


def listar_abas(caminho: str | Path) -> list[AbaInfo]:
    """Lista as abas de um arquivo, com contagem de linhas úteis e amostra.

    ``.ods``: uma ``AbaInfo`` por ``Table`` real do documento (reaproveita
    ``_ler_linhas_de_tabela``, o mesmo trim reverso usado na leitura normal —
    não materializa a cauda vazia). ``.xlsx``/``.csv``: esses formatos não
    têm o conceito de múltiplas abas neste importador hoje, então sempre
    retornam uma lista com 1 único ``AbaInfo(indice=0, ...)``.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ArquivoImportacaoError(f"Arquivo não encontrado: {caminho}")

    sufixo = caminho.suffix.lower()
    if sufixo == ".ods":
        tabelas = _carregar_tabelas_ods(caminho)
        abas: list[AbaInfo] = []
        for indice, tabela in enumerate(tabelas):
            nome = tabela.getAttribute("name") or f"Aba {indice + 1}"
            linhas = _ler_linhas_de_tabela(tabela)
            abas.append(
                AbaInfo(
                    indice=indice,
                    nome=str(nome),
                    n_linhas_uteis=len(linhas),
                    amostra=linhas[:_TAMANHO_AMOSTRA],
                )
            )
        return abas

    if sufixo in (".xlsx", ".csv"):
        linhas = _ler_linhas(caminho)
        return [
            AbaInfo(
                indice=0,
                nome=caminho.stem,
                n_linhas_uteis=len(linhas),
                amostra=linhas[:_TAMANHO_AMOSTRA],
            )
        ]

    raise ArquivoImportacaoError(
        f"Extensão não suportada: {sufixo!r} (use .xlsx, .csv ou .ods)."
    )


@dataclass(frozen=True)
class PlanilhaInfo:
    """Resultado de ``inspecionar``: sugestões para uma tela de confirmação."""

    abas: list[AbaInfo]
    aba_sugerida: int
    linha_header_sugerida: int
    mapa_sugerido: MapeamentoColunas | None
    total_linhas_estimado: int


def inspecionar(caminho: str | Path) -> PlanilhaInfo:
    """Inspeção read-only e barata: sugere aba, linha de header e mapeamento.

    Não altera nem persiste nada; é consumida por uma tela de confirmação
    (fora de escopo aqui). ``aba_sugerida`` = a de maior ``n_linhas_uteis``
    (empate → menor índice). ``mapa_sugerido`` nunca propaga
    ``ArquivoImportacaoError`` — se não conseguir mapear, fica ``None`` (é só
    uma sugestão; quem decide de fato é a tela de confirmação).
    """
    caminho = Path(caminho)
    abas = listar_abas(caminho)
    if not abas:
        return PlanilhaInfo(
            abas=[],
            aba_sugerida=0,
            linha_header_sugerida=0,
            mapa_sugerido=None,
            total_linhas_estimado=0,
        )

    aba_sugerida = max(abas, key=lambda a: (a.n_linhas_uteis, -a.indice)).indice

    sufixo = caminho.suffix.lower()
    linhas = (
        _ler_linhas_ods(caminho, indice_aba=aba_sugerida)
        if sufixo == ".ods"
        else _ler_linhas(caminho)
    )

    linha_header_sugerida = detectar_linha_header(linhas)

    mapa_sugerido: MapeamentoColunas | None = None
    if linha_header_sugerida < len(linhas):
        headers = linhas[linha_header_sugerida]
        dados = linhas[linha_header_sugerida + 1 :]
        try:
            mapa_sugerido = detectar_colunas(headers, dados)
        except ArquivoImportacaoError:
            mapa_sugerido = None

    total_linhas_estimado = max(len(linhas) - linha_header_sugerida - 1, 0)

    return PlanilhaInfo(
        abas=abas,
        aba_sugerida=aba_sugerida,
        linha_header_sugerida=linha_header_sugerida,
        mapa_sugerido=mapa_sugerido,
        total_linhas_estimado=total_linhas_estimado,
    )


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
