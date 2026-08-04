# Plano de Ação — Leitor Inteligente de Contratos de Locação (AI Contract Parser)

> **Origem:** PRD v2.0 — "Pronto para Arquitetura"
> **Autor:** PM/Orquestrador Global (V6) — documento estratégico, sem código
> **Data:** 2026-08-04
> **Stack alvo:** Python 3.11+ · MongoDB · PyQt6 *ou* CustomTkinter · Docker / Docker Compose · Tesseract OCR

---

## 0. Estado atual e premissas

- **Projeto greenfield:** o diretório só contém a governança de agentes (`.agent/`, `.agents/`, `.claude/`). Não há código-fonte, `docker-compose.yml`, testes ou dependências — construção do zero.
- **Metodologia:** entrega iterativa por fases verticais (cada fase entrega valor testável), TDD estrito, GitOps com commits convencionais, documentação viva ao final de cada fase.
- **Rastreabilidade:** cada fase amarra a um Requisito Funcional (RF) e/ou Critério de Aceite (CA) do PRD.

---

## 1. Decisões de arquitetura em aberto (BLOQUEIAM fases posteriores)

Estas decisões precisam de definição do usuário antes das fases indicadas. O plano segue com uma **recomendação default** para cada uma.

| # | Decisão | Status | Definição |
|---|---------|--------|-----------|
| **D1** | **Motor de extração (RF03):** LLM externo × NLP local × híbrido | ✅ **DECIDIDO** | **Híbrido:** regras/regex para campos determinísticos (valores, datas, CNPJ) + LLM apenas para cláusulas ambíguas |
| **D2** | **Docker / conteinerização** | ✅ **DECIDIDO** | **Docker fica FORA do escopo por enquanto.** App e banco rodam nativamente no host. ⚠️ Ver **D2-bis** (impacto no MongoDB) e nota no CA-02 |
| **D2-bis** | **Onde roda o MongoDB sem Docker?** (consequência de D2) | ✅ **DECIDIDO** | **MongoDB Community local no Windows** (serviço). Offline, dados sob controle do usuário, sem custo — alinhado à sensibilidade dos contratos (LGPD) |
| **D3** | **Framework GUI** | ✅ **DECIDIDO** | **CustomTkinter** (MIT, leve) |
| **D4** | **Chave de match (RF05):** CNPJ × Razão Social × aliases fuzzy | ⏳ **EM ABERTO** (default assumido) | **CNPJ normalizado como chave primária** + fallback fuzzy (Razão Social/aliases) com score de confiança |
| **D5** | **Tabela IRRF 2026:** valores exatos de faixas/alíquotas/deduções | ⏳ **EM ABERTO** (data-driven) | Extrair da fonte oficial RFB no início da Fase 5 e **persistir versionada** no Mongo; nunca hardcodar |

---

## 2. Modelo de dados (MongoDB) — visão macro

Coleções propostas (a detalhar pelo Python DS Architect via `data-architecture-spec`):

- **`empresas`** — `{ cnpj (norm), razao_social, aliases[], nomes_fantasia[], ativo, origem_import, created_at }`
- **`contratos`** — metadados + JSON dinâmico: `{ arquivo_origem, hash, locador{tipo PF/PJ, nome, doc}, locatario{...}, valor_aluguel, vencimento, reajuste{indice, proximo, automatico:bool}, irrf{...}, status_match, log_auditoria[] }`
- **`tabela_irrf`** — faixas versionadas: `{ vigencia, faixas[{min, max, aliquota, deducao}], fonte_url, validado_em }`
- **`relatorios`** — histórico consolidado e status de sincronização

---

## 3. Fases de implementação

### Fase 0 — Fundação, Requisitos & Governança
**Objetivo:** eliminar ambiguidades e fixar contratos de arquitetura antes de qualquer código.
**Agentes/Skills:** `requirements-analyst` + `requirements-elicitation-orchestrator`; `tech-lead` + `technical-governance`; `writing-plans`.
**Entregáveis:**
- Refinamento dos RFs, fechamento das decisões D1–D5.
- ADR de stack em `architecture-decision-log.md`; contratos de módulos (interfaces internas).
- Esqueleto de repositório (estrutura de pacotes, `pyproject.toml`/deps, lint, pre-commit).
- Setup GitOps (`gitarchitect`): branches, commits convencionais, CI base.

### Fase 1 — Ambiente Local & Persistência (Docker adiado)  → CA-02 *DEFERIDO*
**Objetivo:** ambiente Python + MongoDB rodando nativamente no host, sem Docker.
**Agentes/Skills:** `sre-engineer` (setup de ambiente); `python-ds-architect` (conexão/persistência).
**Entregáveis:**
- Ambiente Python 3.11+ (venv), `pyproject.toml`, Tesseract instalado no host.
- **MongoDB provisionado conforme D2-bis** (local Windows ou Atlas) + string de conexão em `.env` (fora do versionamento).
- Camada de conexão/health do banco.
- 🔸 **Docker adiado:** `Dockerfile` + `docker-compose.yml` e a **validação CA-02** ficam como *backlog* para retomada futura, quando o requisito de conteinerização voltar ao escopo.

### Fase 2 — Camada de Dados & Gestão de Empresas (RF01)  → **CA-01**
**Objetivo:** importar planilha e popular o Mongo; CRUD manual.
**Agentes/Skills:** `python-ds-architect` (modelagem, Pydantic/validação de schema); `python-automation-pro` (ingestão xlsx/csv, auto-mapeamento de colunas CNPJ/Razão Social); `pdf-office-manipulation` (leitura xlsx).
**Entregáveis:**
- Repositórios/DAO Mongo + modelos validados.
- Importador em lote `.xlsx`/`.csv` com detecção/mapeamento automático de colunas e normalização de CNPJ.
- CRUD de empresas (camada de serviço, consumível pela GUI).
- **Validação CA-01** (50 empresas).

### Fase 3 — Ingestão de Arquivos & OCR (RF02)
**Objetivo:** transformar PDFs (nativos e escaneados) e DOCX em texto processável.
**Agentes/Skills:** `python-automation-pro`; `pdf-office-manipulation`; Tesseract (via container).
**Entregáveis:**
- Ingestão de diretório com múltiplos `.pdf`/`.docx`.
- Pipeline: detecção nativo × imagem → OCR Tesseract (pt-BR) para escaneados → camada de texto normalizada + hash anti-duplicação.

### Fase 4 — Motor de Extração Cognitiva / NLP (RF03)  ⚠️ maior risco
**Objetivo:** extrair partes, valores, vigência e cláusulas de reajuste independentemente do layout.
**Agentes/Skills:** `data-scientist` + `data-science-experimentation`; `python-ds-architect`.
**Depende de:** **D1** decidida.
**Entregáveis:**
- Extração de Locador/Locatário (PF/PJ), valor base, vencimento.
- Cláusulas de reajuste: índice (IGP-M/IPCA/…), mês/data do próximo reajuste, flag booleana *Reajuste Automático*.
- Suíte de avaliação com contratos-amostra reais (precisão/recall por campo) — tratado como experimento de DS, não "achismo".

### Fase 5 — Motor de Cálculo de IRRF (RF04)  → **CA-03**
**Objetivo:** calcular IRRF (Locador PF × Locatário PJ) pela tabela progressiva oficial 2026.
**Agentes/Skills:** `python-automation-pro`; `data-math-tools` (validação numérica); `web-browser-capability`/WebFetch (RFB).
**Depende de:** **D5**.
**Entregáveis:**
- Faixas/deduções versionadas no Mongo; serviço de revalidação contra a fonte RFB (botão na GUI).
- Fórmula `IRRF = (Valor × Alíquota) − Parcela_Dedução`, com **memória de cálculo** persistida.
- Regra de negócio: Locador PJ ⇒ IRRF não retido nesta modalidade (R$ 0,00).
- **Validação CA-03.**

### Fase 6 — Validação de Portfólio / Match de Empresas (RF05)  → **CA-04**
**Objetivo:** cruzar cadastro × contratos lidos e marcar *Encontrado*/*Não Encontrado*.
**Agentes/Skills:** `python-automation-pro`.
**Depende de:** **D4**.
**Entregáveis:**
- Motor de match (CNPJ normalizado + fallback fuzzy com score).
- Status estrito por empresa + geração de pendências.
- **Validação CA-04.**

### Fase 7 — Interface & Relatórios Profissionais (RF06)
**Objetivo:** GUI com painel interativo, alertas de conformidade e exportação.
**Agentes/Skills:** `ux-ui-designer-pro` + `interface-design-systematizer` (fluxos/heurísticas); `materialarchitect` (visual); `python-automation-pro` (GUI + export).
**Depende de:** **D2, D3**.
**Entregáveis:**
- Telas: cadastro/importação de empresas, seleção de pasta, painel de contratos com filtros.
- Alertas: `"Contrato da Empresa [Razão Social / CNPJ] não encontrado"`.
- Relatório 01 (contratos encontrados) e Relatório 02 (conformidade do portfólio).
- Exportação consolidada **PDF e Excel**.

### Fase 8 — QA, Segurança, Documentação & Entrega
**Objetivo:** blindar qualidade, segurança e entregabilidade.
**Agentes/Skills:** `qa-automation-expert` + `testerengine` + `tddmaster`; `cybersecurity-architect` + `securitysentinel`; `verification-before-completion`; `docarchitect`/`tech-writer-pro`; `deploy`.
**Entregáveis:**
- Pirâmide de testes (unit/integração/E2E) + teste de carga/estresse.
- Auditoria de segurança: sem segredos hardcoded, credenciais Mongo protegidas, tratamento de dados sensíveis (LGPD).
- README, documentação técnica, ADRs; memória viva (`memoria-obsidian`).
- Checklist final de aceite (CA-01 a CA-04) via `verification-before-completion`.

---

## 4. Práticas transversais (todas as fases)

- **TDD estrito** (`xp-coach`/`tddmaster`): Red-Green-Refactor.
- **GitOps** (`gitarchitect`): commits convencionais, PRs, CI.
- **Fluxo ágil** (`scrum-master` + `scrum-flow-metrics`): fases como sprints, métricas de vazão/lead time.
- **Documentação viva** ao encerrar cada fase (gatilho obrigatório do `AGENTS.md`).

---

## 5. Mapa de Critérios de Aceite → Fase

| Critério | Fase responsável |
|----------|------------------|
| CA-01 — Importação de Planilha (50 empresas) | Fase 2 |
| CA-02 — Ambiência Docker (`docker-compose up`) | 🔸 **DEFERIDO** (Docker fora do escopo por ora) |
| CA-03 — Tabela IRRF 2026 + memória de cálculo | Fase 5 |
| CA-04 — Contrato ausente (alerta de pendência) | Fase 6 |

---

## 6. Riscos principais

1. **Extração NLP (Fase 4)** — maior incerteza técnica; mitigar com abordagem híbrida e suíte de avaliação quantitativa.
2. **Privacidade de contratos** — se D1 for LLM externo, dados sensíveis saem do ambiente; avaliar LGPD e opção on-prem.
3. **GUI em Docker (D2)** — atrito real; recomendação de serviço headless + GUI no host.
4. **Tabela IRRF 2026 (D5)** — valores oficiais mudaram; obrigatório validar na fonte e versionar.

---

## 7. Próximo passo imediato

Decisões travadas: **D1 = Híbrido · D2 = sem Docker · D2-bis = MongoDB local Windows · D3 = CustomTkinter**. D4/D5 seguem com defaults (fecham nas Fases 6 e 5).

Sem bloqueios restantes. **Sequência:** Fase 0 (refinamento de requisitos + ADR de stack) → Fase 1 (venv + Tesseract + MongoDB local) → Fase 2.
