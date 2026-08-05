"""Harness de avaliação sobre um lote de contratos REAIS (opt-in, sem dados no git).

Roda o pipeline de ingestão + extração (RF02→RF03) sobre uma pasta de PDFs reais
apontada por ``CONTRATOS_REAIS_DIR`` e afere invariantes ESTRUTURAIS de acerto —
sem embutir nenhum dado pessoal no repositório (LGPD). Se a variável não estiver
definida (o caso do CI e de qualquer clone limpo), a suíte inteira é ignorada com
``pytest.skip`` — os PDFs reais NUNCA vão para o versionamento.

Uso local (PowerShell):
    $env:CONTRATOS_REAIS_DIR = "C:\\...\\contratos_reais"
    pytest tests/application/test_harness_contratos_reais.py -s

Triagem automática (só contratos de locação com texto nativo são avaliados):
- texto nativo insuficiente  → ESCANEADO/imagem → "não avaliável offline" (sem OCR);
- sem estrutura de partes     → RECIBO / E-MAIL / outro → fora da avaliação.

O ``-s`` imprime a matriz por campo para inspeção manual (proxy de precisão).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from contract_parser.application.contract_extraction_service import ExtratorContrato
from contract_parser.infrastructure.text_extractors import PdfExtractor

_DIR = os.environ.get("CONTRATOS_REAIS_DIR")

pytestmark = pytest.mark.skipif(
    not (_DIR and Path(_DIR).is_dir()),
    reason="CONTRATOS_REAIS_DIR não definido/inexistente — lote real não versionado (LGPD).",
)

# Texto nativo mínimo para considerar o PDF legível offline (senão é escaneado).
_MIN_TEXTO = 400
# Estrutura de partes: rótulo (com/sem parentético) OU prosa "como LOCAD...".
_TEM_PARTES = re.compile(
    r"LOCADOR(?:ES|AS|A)?\s*(?:\([^)\n]{0,15}\)\s*)*[:\-–]"
    r"|LOCAT[ÁA]RI\w*\s*(?:\([^)\n]{0,15}\)\s*)*[:\-–]"
    r"|como\s+LOCADOR",
    re.IGNORECASE,
)


def _pdfs() -> list[Path]:
    # Avaliado na coleta (parametrize) ANTES do skip: precisa tolerar ausência.
    if not (_DIR and Path(_DIR).is_dir()):
        return []
    return sorted(Path(_DIR).glob("*.pdf"))


def _texto(caminho: Path) -> str:
    try:
        return PdfExtractor().extrair(caminho).texto or ""
    except Exception:  # noqa: BLE001 - harness não deve quebrar por 1 arquivo
        return ""


def _avaliaveis() -> list[Path]:
    """Contratos de locação com texto nativo (triagem determinística)."""
    return [p for p in _pdfs() if len(t := _texto(p)) >= _MIN_TEXTO and _TEM_PARTES.search(t)]


def test_ha_contratos_avaliaveis_no_lote():
    avaliaveis = _avaliaveis()
    # Imprime a triagem (visível com -s) sem vazar conteúdo pessoal.
    for p in _pdfs():
        t = _texto(p)
        classe = (
            "ESCANEADO/não-avaliável" if len(t) < _MIN_TEXTO
            else "CONTRATO(avaliável)" if _TEM_PARTES.search(t)
            else "RECIBO/E-MAIL/outro"
        )
        print(f"[triagem] {p.name}: chars={len(t)} -> {classe}")
    assert avaliaveis, "Nenhum contrato avaliável offline no lote (todos escaneados?)."


@pytest.mark.parametrize("caminho", _avaliaveis(), ids=lambda p: p.name)
def test_partes_resolvem_com_documento_valido(caminho: Path):
    """Invariante estrutural: locador e locatário resolvidos com CPF/CNPJ plausível."""
    contrato = ExtratorContrato().extrair(_texto(caminho))
    for papel, parte in (("locador", contrato.locador), ("locatario", contrato.locatario)):
        reg = contrato.memoria_extracao[papel]
        # Não imprime nome/documento reais — só o comprimento e o tipo (LGPD).
        n = len(parte.documento) if parte.documento else 0
        print(f"[{caminho.name}] {papel}: tipo={parte.tipo} doc_len={n} conf={reg.confianca:.2f}")
        assert parte.tipo is not None, f"{papel} sem tipo PF/PJ em {caminho.name}"
        assert parte.documento is not None, f"{papel} sem documento em {caminho.name}"
        assert len(parte.documento) in (11, 14), f"{papel} doc inválido em {caminho.name}"


@pytest.mark.parametrize("caminho", _avaliaveis(), ids=lambda p: p.name)
def test_tipo_locacao_resolvido(caminho: Path):
    contrato = ExtratorContrato().extrair(_texto(caminho))
    print(f"[{caminho.name}] tipo_locacao={contrato.tipo_locacao}")
    assert contrato.tipo_locacao is not None, f"tipo_locacao não resolvido em {caminho.name}"
