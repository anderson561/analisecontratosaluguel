"""Verificador de ambiente (infraestrutura) — Fase 1.

Checa e reporta PASS/FAIL para os pre-requisitos do ambiente local (sem Docker):
- Python >= 3.11
- ``pymongo`` importavel E MongoDB acessivel (ping via camada ``database``)
- Binario do Tesseract presente (via ``settings.tesseract_cmd`` ou PATH) e idioma ``por``

Degrada graciosamente: se algo falta, reporta O QUE instalar; NUNCA tenta instalar
software de sistema e NUNCA derruba o processo por excecao nao tratada.

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
from contract_parser.infrastructure.database import HealthResult, check_health

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


def check_mongo(health_fn: Callable[[], HealthResult] = check_health) -> CheckResult:
    """Valida que ``pymongo`` importa E que o MongoDB responde ao ping."""
    try:
        import pymongo  # noqa: F401
    except ImportError as exc:
        return CheckResult(
            "MongoDB",
            False,
            f"pacote pymongo nao importavel: {exc}.",
            'Ative o venv e rode: pip install -e ".[dev]"',
        )
    health = health_fn()
    if health.ok:
        return CheckResult("MongoDB", True, health.detalhe)
    return CheckResult(
        "MongoDB",
        False,
        health.detalhe,
        (
            "Instale o MongoDB Community e inicie o servico (porta 27017), "
            "ou ajuste MONGO_URI no .env."
        ),
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
    return [check_python(), check_mongo(), check_tesseract()]


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
