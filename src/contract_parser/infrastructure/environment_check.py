"""Verificador de ambiente (infraestrutura) — Fase 1 (revisto na migracao ADR-002).

Checa e reporta PASS/FAIL para os pre-requisitos do ambiente local (sem Docker):
- Python >= 3.11
- Banco de dados SQLite: arquivo/diretorio gravavel e schema inicializavel
  (ver ADR-002 — substitui a antiga checagem "MongoDB acessivel": SQLite e
  embarcado na stdlib, nao ha servico externo a verificar)
- Binario do Tesseract presente (via ``settings.tesseract_cmd`` ou PATH) e idioma ``por``

Degrada graciosamente: se algo falta, reporta O QUE instalar/corrigir; NUNCA
tenta instalar software de sistema e NUNCA derruba o processo por excecao nao
tratada.

Executavel:
    python -m contract_parser.infrastructure.environment_check
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from contract_parser.config import settings
from contract_parser.infrastructure.database import RepositoryError, get_connection, init_schema

MIN_PYTHON: tuple[int, int] = (3, 11)


@dataclass(frozen=True)
class CheckResult:
    """Resultado de uma checagem individual de ambiente."""

    nome: str
    ok: bool
    detalhe: str
    remediacao: str = ""


def check_python(version: tuple[int, int] | None = None) -> CheckResult:
    """Valida a versao do interpretador Python (>= 3.11)."""
    version = version if version is not None else sys.version_info[:2]
    ok = version >= MIN_PYTHON
    atual = f"{version[0]}.{version[1]}"
    minimo = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    if ok:
        return CheckResult("Python", True, f"versao {atual} (>= {minimo}).")
    return CheckResult(
        "Python",
        False,
        f"versao {atual} abaixo do minimo {minimo}.",
        f"Instale o Python {minimo}+ e recrie o virtualenv.",
    )


def _abrir_e_inicializar_schema(database_path: str) -> None:
    """Abre uma conexao ad-hoc no caminho dado e inicializa o schema.

    Usa ``get_connection(database_path=...)`` (conexao ad-hoc, nao afeta o
    singleton de producao) seguido de ``init_schema``. Fecha a conexao ao final
    — esta funcao so serve para *verificar* que o caminho e utilizavel.
    """
    conn = get_connection(database_path=database_path)
    try:
        init_schema(conn)
    finally:
        conn.close()


def check_banco_dados(
    database_path: str | None = None,
    abrir_fn: Callable[[str], None] = _abrir_e_inicializar_schema,
) -> CheckResult:
    """Valida que o banco SQLite e gravavel: abre o arquivo e inicializa o schema.

    Substitui a antiga checagem "MongoDB acessivel" (ADR-002): SQLite e
    embarcado na stdlib (``sqlite3``), entao nao ha servico externo a checar —
    basta o processo conseguir criar/abrir o arquivo em ``DATABASE_PATH`` e
    aplicar o ``CREATE TABLE IF NOT EXISTS``. Na pratica, esta checagem quase
    sempre passa (o unico jeito de falhar e permissao negada ou disco cheio).
    """
    path = database_path if database_path is not None else settings.database_path
    try:
        abrir_fn(path)
    except RepositoryError as exc:
        return CheckResult(
            "Banco de dados",
            False,
            f"Falha ao inicializar o schema do banco SQLite em '{path}': {exc}.",
            "Verifique se o caminho tem permissao de escrita e tente novamente.",
        )
    except OSError as exc:
        return CheckResult(
            "Banco de dados",
            False,
            f"Nao foi possivel abrir/criar o arquivo do banco SQLite em '{path}': {exc}.",
            "Verifique se o diretorio configurado em DATABASE_PATH existe e e gravavel.",
        )
    return CheckResult(
        "Banco de dados",
        True,
        f"Banco SQLite pronto em '{path}' (schema inicializado).",
    )


def check_tesseract(
    cmd: str | None = None,
    lang: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> CheckResult:
    """Valida a presenca do binario Tesseract e a disponibilidade do idioma.

    Resolucao do binario: usa ``settings.tesseract_cmd`` se apontar para um arquivo
    existente; caso contrario procura ``tesseract`` no PATH.
    """
    cmd = cmd if cmd is not None else settings.tesseract_cmd
    lang = lang if lang is not None else settings.ocr_lang

    binary: str | None = None
    if cmd and os.path.isfile(cmd):
        binary = cmd
    if binary is None:
        binary = which("tesseract")

    if not binary:
        return CheckResult(
            "Tesseract",
            False,
            "binario 'tesseract' nao encontrado (TESSERACT_CMD vazio/invalido e ausente no PATH).",
            (
                "Instale o Tesseract-OCR e configure TESSERACT_CMD no .env "
                "ou adicione-o ao PATH."
            ),
        )

    try:
        proc = runner(
            [binary, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001 - degradacao graciosa
        return CheckResult(
            "Tesseract",
            False,
            f"binario encontrado ({binary}) mas falhou ao listar idiomas: {exc!r}.",
            "Verifique a integridade da instalacao do Tesseract-OCR.",
        )

    saida = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    idiomas = {
        linha.strip()
        for linha in saida.splitlines()
        if linha.strip() and "List of available" not in linha
    }
    if lang in idiomas:
        return CheckResult(
            "Tesseract",
            True,
            f"binario {binary}; idioma '{lang}' disponivel.",
        )
    return CheckResult(
        "Tesseract",
        False,
        f"binario {binary}; idioma '{lang}' ausente (disponiveis: {sorted(idiomas)}).",
        f"Instale o pacote de idioma '{lang}' (tesseract-ocr-por) do Tesseract.",
    )


def run_all_checks() -> list[CheckResult]:
    """Executa todas as checagens. Cada checagem ja e defensiva internamente."""
    return [check_python(), check_banco_dados(), check_tesseract()]


def format_report(results: Sequence[CheckResult]) -> str:
    """Formata os resultados em texto legivel com PASS/FAIL e acoes sugeridas."""
    linhas = ["=== Verificacao de Ambiente - AI Contract Parser (Fase 1) ==="]
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        linhas.append(f"[{status}] {r.nome}: {r.detalhe}")
        if not r.ok and r.remediacao:
            linhas.append(f"        -> Acao: {r.remediacao}")
    total_ok = sum(1 for r in results if r.ok)
    linhas.append(f"--- {total_ok}/{len(results)} checagens OK ---")
    return "\n".join(linhas)


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint executavel. Retorna 0 se tudo PASS, 1 caso contrario.

    Nao lanca excecao: retorna codigo de saida para permitir uso em CI/scripts.
    """
    results = run_all_checks()
    print(format_report(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
