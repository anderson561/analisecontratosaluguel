"""Builders programáticos de planilhas .xlsx para os testes.

Gera arquivos deterministicamente (sem binários versionados). Inclui o gerador
de 50 empresas do cenário CA-01 e variantes de cabeçalho "sujo".
"""
from __future__ import annotations

from pathlib import Path

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
