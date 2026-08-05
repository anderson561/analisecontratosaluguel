"""Acesso às fixtures sintéticas de contratos (``tests/fixtures/*.txt``).

Os textos são contratos de locação sintéticos (dados fictícios) com layouts e
redações distintos, cobrindo o happy path e as exceções jurídicas do §3/§6. São
a base empírica da matriz de acertos por campo (proxy de precisão do motor).
"""
from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Nomes canônicos das fixtures (para evitar strings soltas nos testes).
RESIDENCIAL_PF_PJ = "contrato_residencial_pf_pj.txt"
COMERCIAL_PJ_PJ_ABUSIVO = "contrato_comercial_pj_pj_abusivo.txt"
RESIDENCIAL_PJ_PF_REAJUSTE_VEDADO = "contrato_residencial_pj_pf_reajuste_vedado.txt"
TIPO_AMBIGUO_PF_PF = "contrato_tipo_ambiguo_pf_pf.txt"

TODAS = (
    RESIDENCIAL_PF_PJ,
    COMERCIAL_PJ_PJ_ABUSIVO,
    RESIDENCIAL_PJ_PF_REAJUSTE_VEDADO,
    TIPO_AMBIGUO_PF_PF,
)


def carregar_contrato(nome: str) -> str:
    """Lê o texto de uma fixture de contrato (UTF-8)."""
    return (FIXTURES_DIR / nome).read_text(encoding="utf-8")
