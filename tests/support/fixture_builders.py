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
