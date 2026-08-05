# ADR-001 — Stack e Arquitetura do AI Contract Parser

> **Fase:** 0 · **Data:** 2026-08-04 · **Status:** Aceito
>
> ⚠️ **Nota (2026-08-05):** a decisão **D2-bis** abaixo (MongoDB Community
> local) foi **revista pelo [ADR-002](adr-002-migracao-mongodb-sqlite.md)** —
> a persistência passou a ser **SQLite** (embarcado na stdlib, sem serviço
> externo). O restante desta decisão (D1, D2, D3, D4, D5 e a arquitetura em
> camadas) permanece válido; apenas D2-bis foi substituída.

## 1. Contexto Técnico e Forças Tecnológicas
App desktop para gestão de portfólio imobiliário que lê contratos (PDF/DOCX), extrai dados, calcula IRRF e cruza com um cadastro de empresas. Dados são **sensíveis** (contratos, CNPJs) → privacidade/LGPD é força dominante. PRD pedia Docker, mas o usuário retirou a conteinerização do escopo atual.

## 2. Decisões Arquiteturais

| ID | Decisão | Justificativa |
|----|---------|---------------|
| **D1** | Extração **híbrida**: regex/regras p/ campos determinísticos + LLM só p/ cláusulas ambíguas | Equilibra precisão e custo; minimiza dados enviados a LLM |
| **D2** | **Sem Docker** nesta versão | Escopo definido pelo usuário; reduz atrito no Windows. `Dockerfile`/compose ficam no backlog (CA-02 deferido) |
| **D2-bis** | **MongoDB Community local** (serviço Windows) | Offline, dados sob controle do usuário — aderente à LGPD para contratos sensíveis |
| **D3** | GUI em **CustomTkinter** | Licença MIT (sem custo comercial), leve, suficiente p/ cadastro/painel/filtros |
| **D4** | Match por **CNPJ normalizado** + fallback *fuzzy* (score) | Robusto a variações de Razão Social e OCR |
| **D5** | Tabela IRRF **versionada e data-driven** no Mongo | Corretude fiscal; base 2026 mudou → nunca hardcodar |

### Arquitetura em camadas (Clean-ish / SOLID)
```
presentation (CustomTkinter)  →  application (serviços/casos de uso)
        ↓                                   ↓
   infrastructure (MongoDB, OCR, LLM, export)  ←  domain (modelos + regras: IRRF, match, validação jurídica)
```
- **Domínio isolado** (sem dependência de framework/IO) → testável por TDD.
- **Repositórios** abstraem o MongoDB (troca futura p/ Atlas/Docker sem tocar no domínio).
- **Parsers/OCR/LLM/Export** atrás de interfaces (injeção de dependência).

### Stack consolidada
- **Runtime:** Python 3.11+ (venv)
- **Banco:** MongoDB Community local · driver `pymongo`
- **Validação:** `pydantic` (modelos/esquemas dinâmicos)
- **OCR:** Tesseract (por-BRA) · `pytesseract` + `pdf2image`/`pymupdf`
- **DOCX/XLSX:** `python-docx` · `openpyxl`
- **NLP/Regras:** regex + heurísticas; LLM sob interface plugável
- **GUI:** CustomTkinter
- **Export:** PDF (`reportlab`/`weasyprint`) + Excel (`openpyxl`)
- **Testes:** `pytest` + `pytest-cov` (TDD)

### Adendo (Fase 3) — Renderização OCR sem poppler
- **Decisão:** o OCR renderiza páginas com **PyMuPDF (`page.get_pixmap`)**, não com `pdf2image`. `pdf2image` exige o binário **poppler** (atrito de instalação no Windows); PyMuPDF já é dependência e renderiza sem ele.
- **Impactos no manifesto:** `pdf2image` **removido** de `pyproject.toml`; `pillow` **adicionado** (dependência transitiva do `pytesseract`, necessária ao caminho OCR real).

## 3. Consequências e Impactos
- **Positivos:** privacidade preservada (dados locais + extração híbrida); domínio testável; baixa dependência de infra; troca de banco/UI sem reescrita do núcleo.
- **Negativos/Riscos aceitos:**
  - **Portabilidade reduzida** sem Docker (setup manual de Mongo/Tesseract no host) → mitigar com script de setup + README.
  - **Extração NLP** é o maior risco técnico → mitigar com suíte de avaliação (precisão/recall por campo) na Fase 4.
  - **Reprodutibilidade** entre máquinas depende de instruções de ambiente rigorosas.
