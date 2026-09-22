"""Builders programáticos de planilhas .xlsx/.ods para os testes.

Gera arquivos deterministicamente (sem binários versionados). Inclui o gerador
de 50 empresas do cenário CA-01 e variantes de cabeçalho "sujo", tanto em
.xlsx (openpyxl) quanto em .ods (odfpy).
"""
from __future__ import annotations

from pathlib import Path

from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P
from openpyxl import Workbook

from contract_parser.domain.cnpj import calcular_dv_cnpj


def cnpj_valido_sequencial(n: int) -> str:
    """CNPJ sintético com dígitos verificadores válidos, indexado por ``n``."""
    base = f"{n:012d}"
    return base + calcular_dv_cnpj(base)


def escrever_xlsx(caminho: Path, headers: list[str], linhas: list[list[object]]) -> Path:
    """Escreve uma planilha .xlsx simples (header + linhas) e retorna o caminho."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for linha in linhas:
        ws.append(linha)
    wb.save(caminho)
    wb.close()
    return caminho


def construir_xlsx_50_empresas(caminho: Path) -> Path:
    """Cenário CA-01: .xlsx com 50 empresas (CNPJs válidos e distintos)."""
    linhas = [
        [cnpj_valido_sequencial(i + 1), f"Empresa Exemplo {i + 1:02d} LTDA"]
        for i in range(50)
    ]
    return escrever_xlsx(caminho, ["CNPJ", "Razão Social"], linhas)


def construir_xlsx_header_sujo(caminho: Path) -> Path:
    """Cabeçalhos "sujos"/variados + máscaras de CNPJ para testar auto-mapeamento."""
    headers = ["  Nº do CNPJ  ", "RAZÃO SOCIAL / NOME EMPRESARIAL", "Observação"]
    linhas = [
        ["11.222.333/0001-81", "Alpha Comercio LTDA", "ok"],
        ["45.566.778/0001-09", "Beta Servicos ME", "ok"],
    ]
    return escrever_xlsx(caminho, headers, linhas)


def construir_xlsx_sem_header_cnpj(caminho: Path) -> Path:
    """Sem palavra-chave de CNPJ no cabeçalho → força fallback por valor."""
    headers = ["Documento", "Cliente"]
    linhas = [
        ["99887766000105", "Gamma Holding SA"],
        ["12345678000195", "Delta Participacoes"],
    ]
    return escrever_xlsx(caminho, headers, linhas)


# --------------------------------------------------------------------------- #
# .ods (odfpy) — mesmo contrato dos builders .xlsx acima.
# --------------------------------------------------------------------------- #
def _celula_ods(valor: object = None) -> TableCell:
    """Célula ODS simples; texto vira parágrafo, ``None``/"" fica vazia."""
    cell = TableCell()
    if valor is not None and str(valor) != "":
        cell.addElement(P(text=str(valor)))
    return cell


def escrever_ods(caminho: Path, headers: list[str], linhas: list[list[object]]) -> Path:
    """Escreve uma planilha .ods simples (header + linhas) e retorna o caminho."""
    doc = OpenDocumentSpreadsheet()
    tabela = Table(name="Planilha1")

    def _linha(valores: list[object]) -> TableRow:
        row = TableRow()
        for v in valores:
            row.addElement(_celula_ods(v))
        return row

    tabela.addElement(_linha(headers))
    for linha in linhas:
        tabela.addElement(_linha(linha))

    doc.spreadsheet.addElement(tabela)
    doc.save(str(caminho))
    return caminho


def construir_ods_50_empresas(caminho: Path) -> Path:
    """Cenário CA-01 em .ods: 50 empresas (CNPJs válidos e distintos)."""
    linhas = [
        [cnpj_valido_sequencial(i + 1), f"Empresa Exemplo {i + 1:02d} LTDA"]
        for i in range(50)
    ]
    return escrever_ods(caminho, ["CNPJ", "Razão Social"], linhas)


def construir_ods_header_sujo(caminho: Path) -> Path:
    """Equivalente .ods de ``construir_xlsx_header_sujo``: cabeçalhos "sujos"/
    ordem invertida + máscaras de CNPJ, provando que o auto-mapeamento
    funciona igual independente do formato de origem."""
    headers = ["  Nº do CNPJ  ", "RAZÃO SOCIAL / NOME EMPRESARIAL", "Observação"]
    linhas = [
        ["11.222.333/0001-81", "Alpha Comercio LTDA", "ok"],
        ["45.566.778/0001-09", "Beta Servicos ME", "ok"],
    ]
    return escrever_ods(caminho, headers, linhas)


def construir_ods_com_linhas_e_celulas_repetidas(caminho: Path) -> Path:
    """.ods com linha totalmente vazia repetida (``number-rows-repeated``) e uma
    célula vazia repetida no meio de uma linha de dados
    (``number-columns-repeated``) — exercita o ponto crítico do plano: se a
    expansão desses atributos falhar, a Razão Social da 2ª empresa desalinha
    para a coluna errada."""
    doc = OpenDocumentSpreadsheet()
    tabela = Table(name="Planilha1")

    def _linha(valores: list[object]) -> TableRow:
        row = TableRow()
        for v in valores:
            row.addElement(_celula_ods(v))
        return row

    cnpj1 = cnpj_valido_sequencial(101)
    cnpj2 = cnpj_valido_sequencial(102)
    cnpj3 = cnpj_valido_sequencial(103)

    tabela.addElement(_linha(["CNPJ", "Nota1", "Nota2", "Razão Social"]))
    tabela.addElement(_linha([cnpj1, "a", "b", "Empresa Um LTDA"]))

    # Linha totalmente vazia, repetida 2x (compressão típica do LibreOffice).
    linha_vazia = TableRow(numberrowsrepeated=2)
    linha_vazia.addElement(_celula_ods())
    tabela.addElement(linha_vazia)

    # Nota1 + Nota2 vazias, compactadas em UM elemento TableCell repetido 2x.
    row2 = TableRow()
    row2.addElement(_celula_ods(cnpj2))
    row2.addElement(TableCell(numbercolumnsrepeated=2))
    row2.addElement(_celula_ods("Empresa Dois LTDA"))
    tabela.addElement(row2)

    tabela.addElement(_linha([cnpj3, "a", "b", "Empresa Tres LTDA"]))

    doc.spreadsheet.addElement(tabela)
    doc.save(str(caminho))
    return caminho


def construir_ods_com_cauda_vazia_gigante(caminho: Path) -> Path:
    """.ods com cauda vazia gigante, imitando o LibreOffice Calc real.

    O LibreOffice comprime "o resto da grade está vazio" numa última
    ``TableRow``/``TableCell`` com ``number-rows-repeated``/
    ``number-columns-repeated`` na casa de centenas de milhares (até
    1048576). Expandir esse atributo literalmente materializaria milhões de
    linhas/células vazias — este fixture prova que o importador NÃO faz isso.
    """
    doc = OpenDocumentSpreadsheet()
    tabela = Table(name="Planilha1")

    def _linha(valores: list[object]) -> TableRow:
        row = TableRow()
        for v in valores:
            row.addElement(_celula_ods(v))
        return row

    cnpj1 = cnpj_valido_sequencial(201)
    cnpj2 = cnpj_valido_sequencial(202)
    cnpj3 = cnpj_valido_sequencial(203)

    tabela.addElement(_linha(["CNPJ", "Razão Social"]))
    tabela.addElement(_linha([cnpj1, "Empresa Um LTDA"]))
    tabela.addElement(_linha([cnpj2, "Empresa Dois LTDA"]))

    # 3ª linha real, com uma célula vazia final "gigante" (number-columns-repeated
    # grande) representando a cauda vazia daquela linha até o limite da grade.
    row3 = TableRow()
    row3.addElement(_celula_ods(cnpj3))
    row3.addElement(_celula_ods("Empresa Tres LTDA"))
    row3.addElement(TableCell(numbercolumnsrepeated=100_000))
    tabela.addElement(row3)

    # Última linha da tabela: totalmente vazia, repetida ~1 milhão de vezes
    # (comportamento típico do LibreOffice Calc ao salvar um .ods real).
    linha_vazia_final = TableRow(numberrowsrepeated=1_000_000)
    linha_vazia_final.addElement(_celula_ods())
    tabela.addElement(linha_vazia_final)

    doc.spreadsheet.addElement(tabela)
    doc.save(str(caminho))
    return caminho


def construir_ods_com_multiplos_blocos_vazios_no_fim(caminho: Path) -> Path:
    """.ods com VÁRIOS blocos SEPARADOS de linhas vazias no fim (não um só).

    Reproduz o bug real (não coberto por ``construir_ods_com_cauda_vazia_gigante``):
    um .ods legítimo do LibreOffice Calc pode ter vários ``TableRow`` distintos
    perto do fim da tabela, cada um com seu próprio ``number-rows-repeated``,
    em vez de um único bloco final. O código antigo só tratava o ÚLTIMO
    elemento XML como cauda vazia especial — os blocos anteriores a ele eram
    expandidos literalmente, materializando dezenas de milhares de linhas
    fantasmas (no arquivo real do usuário, ~1.048.300 linhas vindas de 5
    blocos que não eram "o último elemento")."""
    doc = OpenDocumentSpreadsheet()
    tabela = Table(name="Planilha1")

    def _linha(valores: list[object]) -> TableRow:
        row = TableRow()
        for v in valores:
            row.addElement(_celula_ods(v))
        return row

    cnpj1 = cnpj_valido_sequencial(301)
    cnpj2 = cnpj_valido_sequencial(302)
    cnpj3 = cnpj_valido_sequencial(303)

    tabela.addElement(_linha(["CNPJ", "Razão Social"]))
    tabela.addElement(_linha([cnpj1, "Empresa Um LTDA"]))
    tabela.addElement(_linha([cnpj2, "Empresa Dois LTDA"]))
    tabela.addElement(_linha([cnpj3, "Empresa Tres LTDA"]))

    # 3 blocos SEPARADOS de linha vazia, tamanhos bem diferentes — só o
    # último tem chance de ser tratado pela regra antiga ("é o último
    # elemento XML"); os dois primeiros, não.
    for tamanho in (200, 5_000, 50_000):
        bloco_vazio = TableRow(numberrowsrepeated=tamanho)
        bloco_vazio.addElement(_celula_ods())
        tabela.addElement(bloco_vazio)

    doc.spreadsheet.addElement(tabela)
    doc.save(str(caminho))
    return caminho


def construir_ods_titulo_antes_do_header(caminho: Path) -> Path:
    """.ods com linha de título mesclado ANTES do header de verdade.

    Linha 0: célula única não vazia (título), resto ``None`` — como um
    LibreOffice Calc real grava uma célula mesclada. Linha 1: header de
    verdade (CNPJ/Razão Social). Linhas seguintes: dados reais. Sem
    ``detectar_linha_header``, a linha 0 seria tratada como header e a linha
    1 (o header de verdade) viraria "linha de dado", gerando um erro espúrio
    de CNPJ inválido (o texto "CNPJ" não vira 14 dígitos)."""
    doc = OpenDocumentSpreadsheet()
    tabela = Table(name="Planilha1")

    def _linha(valores: list[object]) -> TableRow:
        row = TableRow()
        for v in valores:
            row.addElement(_celula_ods(v))
        return row

    cnpj1 = cnpj_valido_sequencial(401)
    cnpj2 = cnpj_valido_sequencial(402)

    tabela.addElement(
        _linha(["MAPA DE ALUGUÉIS PESSOA FÍSICA 2024", None, None, None])
    )
    tabela.addElement(_linha(["CNPJ", "Razão Social"]))
    tabela.addElement(_linha([cnpj1, "Empresa Um LTDA"]))
    tabela.addElement(_linha([cnpj2, "Empresa Dois LTDA"]))

    doc.spreadsheet.addElement(tabela)
    doc.save(str(caminho))
    return caminho


def construir_ods_multiplas_abas(caminho: Path) -> Path:
    """.ods com 2 abas (``Table``) nomeadas, cada uma com dados reais distintos.

    Exercita ``listar_abas``: uma ``AbaInfo`` por aba, com nome e contagem de
    linhas úteis corretos."""
    doc = OpenDocumentSpreadsheet()

    def _linha(valores: list[object]) -> TableRow:
        row = TableRow()
        for v in valores:
            row.addElement(_celula_ods(v))
        return row

    aba1 = Table(name="Pessoa Fisica")
    aba1.addElement(_linha(["CNPJ", "Razão Social"]))
    aba1.addElement(_linha([cnpj_valido_sequencial(501), "Empresa Aba1 Um LTDA"]))
    aba1.addElement(_linha([cnpj_valido_sequencial(502), "Empresa Aba1 Dois LTDA"]))

    aba2 = Table(name="Pessoa Juridica")
    aba2.addElement(_linha(["CNPJ", "Razão Social"]))
    aba2.addElement(_linha([cnpj_valido_sequencial(503), "Empresa Aba2 Um LTDA"]))

    doc.spreadsheet.addElement(aba1)
    doc.spreadsheet.addElement(aba2)
    doc.save(str(caminho))
    return caminho


def construir_ods_celula_conteudo_repetida_acima_do_limite(
    caminho: Path, repeticoes: int = 6_000
) -> Path:
    """.ods com uma célula de CONTEÚDO REAL (não vazia) repetida acima do teto
    de sanidade (``_MAX_REPETICOES_RAZOAVEL``) — defesa em profundidade contra
    ODS malformado/adversarial: deve levantar ``ArquivoImportacaoError`` em
    vez de truncar silenciosamente um dado real sem avisar."""
    doc = OpenDocumentSpreadsheet()
    tabela = Table(name="Planilha1")

    tabela.addElement(_linha_simples(["CNPJ", "Razão Social"]))

    row = TableRow()
    row.addElement(_celula_ods(cnpj_valido_sequencial(601)))
    celula_repetida = TableCell(numbercolumnsrepeated=repeticoes)
    celula_repetida.addElement(P(text="Empresa Repetida LTDA"))
    row.addElement(celula_repetida)
    tabela.addElement(row)

    doc.spreadsheet.addElement(tabela)
    doc.save(str(caminho))
    return caminho


def _linha_simples(valores: list[object]) -> TableRow:
    """Helper interno: uma ``TableRow`` comum (sem repetição), célula a célula."""
    row = TableRow()
    for v in valores:
        row.addElement(_celula_ods(v))
    return row
