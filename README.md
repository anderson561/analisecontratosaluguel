# AI Contract Parser — Leitor Inteligente de Contratos de Locação

Aplicação desktop para leitura, extração e auditoria de contratos de locação em lote (PDF/DOCX), cruzamento com portfólio de empresas, cálculo de IRRF e relatórios profissionais.

## Stack (ver [ADR-001](.agent/specs/adr-001-stack-e-arquitetura.md))
Python 3.11+ · MongoDB Community (local) · CustomTkinter · Tesseract OCR (por-BRA) · pydantic · pytest (TDD)

> ⚠️ **Docker está fora do escopo desta versão.** Ambiente roda nativamente no host.

## Pré-requisitos (setup manual no Windows)
1. **Python 3.11+**
2. **MongoDB Community** instalado como serviço local (porta padrão 27017)
3. **Tesseract-OCR** com pacote de idioma `por`

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env   # ajuste MONGO_URI, TESSERACT_CMD, etc.
```

## Testes
```bash
pytest
```

## Estrutura (arquitetura em camadas)
```
src/contract_parser/
  domain/          # modelos + regras (IRRF, match, validação jurídica) — sem IO
  application/     # casos de uso / serviços
  infrastructure/  # MongoDB, OCR, LLM, exportação
  presentation/    # GUI CustomTkinter
tests/             # pytest (unit/integração/E2E)
```

## Documentação viva (`.agent/specs/`)
- [Plano de implementação](.agent/specs/contract-parser-implementation-plan.md)
- [Requisitos & regras de negócio](.agent/specs/contract-parser-requirements.md)
- [ADR-001 — Stack & Arquitetura](.agent/specs/adr-001-stack-e-arquitetura.md)

## Roadmap (fases)
0. ✅ Fundação, Requisitos & Governança
1. Ambiente local + MongoDB
2. Dados & Gestão de Empresas (RF01) — CA-01
3. Ingestão & OCR (RF02)
4. Extração NLP híbrida (RF03)
5. Motor IRRF 2026 (RF04) — CA-03
6. Match de portfólio (RF05) — CA-04
7. GUI & Relatórios (RF06)
8. QA, Segurança & Entrega
