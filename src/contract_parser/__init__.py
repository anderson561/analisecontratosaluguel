"""AI Contract Parser — Leitor Inteligente de Contratos de Locação.

Arquitetura em camadas (ver ADR-001):
- domain: modelos e regras (IRRF, match, validação jurídica) — sem IO.
- application: casos de uso / serviços que orquestram o domínio.
- infrastructure: MongoDB, OCR, LLM, exportação (PDF/Excel).
- presentation: GUI CustomTkinter.
"""

__version__ = "0.1.0"
