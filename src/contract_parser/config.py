"""Configuração central carregada de variáveis de ambiente (.env).

Plumbing de infraestrutura — sem regra de negócio. Ver ADR-001 e ADR-002
(migração de persistência MongoDB → SQLite).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _caminho_banco_padrao() -> str:
    """Caminho padrao do banco SQLite, ancorado na localizacao real do app.

    Quando empacotado (PyInstaller, ``sys.frozen``), ancora em
    ``sys.executable`` — a pasta onde o ``.exe`` esta fisicamente salvo —
    para que copiar essa pasta inteira para outra maquina (ou usar um atalho
    com "Iniciar em" diferente) preserve os dados. Em desenvolvimento
    (``sys.frozen`` ausente), mantem o comportamento de hoje: relativo a
    raiz do repositorio, onde ``data/contract_parser.db`` ja vive.

    NUNCA usar ``sys._MEIPASS`` aqui — e a pasta de extracao temporaria do
    onefile, recriada e apagada a cada execucao (perderia os dados a cada
    fechamento do app, exatamente o problema que esta funcao resolve).
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        # config.py fica em src/contract_parser/ — 3 parents sobe ate a raiz
        # do repo (mesma pasta onde data/contract_parser.db ja existe hoje).
        base = Path(__file__).resolve().parent.parent.parent
    return str(base / "data" / "contract_parser.db")


@dataclass(frozen=True)
class Settings:
    database_path: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH") or _caminho_banco_padrao()
    )
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "")
    ocr_lang: str = os.getenv("OCR_LANG", "por")
    llm_provider: str = os.getenv("LLM_PROVIDER", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    fuzzy_match_threshold: int = int(os.getenv("FUZZY_MATCH_THRESHOLD", "85"))


settings = Settings()
