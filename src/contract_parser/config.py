"""Configuração central carregada de variáveis de ambiente (.env).

Plumbing de infraestrutura — sem regra de negócio. Ver ADR-001.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "contract_parser")
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "")
    ocr_lang: str = os.getenv("OCR_LANG", "por")
    llm_provider: str = os.getenv("LLM_PROVIDER", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    fuzzy_match_threshold: int = int(os.getenv("FUZZY_MATCH_THRESHOLD", "85"))


settings = Settings()
