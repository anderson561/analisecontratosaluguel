# ADR-002 — Migração de Persistência: MongoDB → SQLite

> **Data:** 2026-08-05 · **Status:** Aceito · **Supersede parcialmente:** ADR-001 (decisão D2-bis)

## 1. Contexto Técnico e Forças Tecnológicas
O ADR-001 fixou **MongoDB Community local** (D2-bis) como consequência de "sem Docker" (D2). Na prática, ao longo de toda a construção (Fases 1–8), o MongoDB **nunca esteve instalado** no host de desenvolvimento — todo o trabalho foi validado com Mongo **mockado/fake**, e os critérios **CA-01** (import de 50 empresas) e a parte de persistência do **CA-03** ficaram formalmente pendentes de validação end-to-end.

O usuário decidiu trocar o motor de persistência para **SQLite**. Forças em jogo:
- **A favor do SQLite:** embarcado na stdlib do Python (`sqlite3`), **zero instalação/serviço externo**, arquivo único, adequado a um app **desktop single-user** (RF já define ator único, sem concorrência multiusuário). Resolve de vez a pendência de ambiente que vinha se arrastando desde a Fase 1.
- **A favor do que já existe:** a arquitetura em camadas (ADR-001) isola a persistência atrás de `Protocol`s (`EmpresaRepositoryProtocol`) — a camada `application/` **não importa pymongo**. Isso torna a migração um problema **contido** em `infrastructure/`, não uma reescrita.
- **Risco a mitigar:** 7 pontos em `presentation/controllers.py` capturam `PyMongoError` diretamente — vazamento do tipo de exceção da infra para a apresentação. É a única violação de camada real a corrigir durante a migração.

## 2. Decisão Arquitetural
- **D2-bis (revista):** persistência via **SQLite** (arquivo local, `sqlite3` da stdlib — nenhuma dependência nova). Substitui "MongoDB Community local".
- **Schema mínimo, sem ORM:** duas tabelas (`empresas`, `tabela_irrf`), `CREATE TABLE IF NOT EXISTS` na abertura da conexão (sem Alembic/migração versionada — YAGNI para 2 tabelas).
- **Chave natural preservada:** `cnpj` como `PRIMARY KEY` de `empresas`; `vigencia` como `PRIMARY KEY` de `tabela_irrf` (mesmo desenho lógico do Mongo, trocando `_id` por `PRIMARY KEY`).
- **Campos compostos (listas/objetos aninhados)** — `aliases`, `nomes_fantasia`, `faixas` — persistidos como **coluna TEXT com JSON serializado**, reusando a mesma estratégia de serialização já validada (`model_dump(mode="json")`, Decimal→str, date→ISO) que o `TabelaIRRFRepository` Mongo já usa.
- **Exceção de infraestrutura não deve vazar:** introduzir `RepositoryError` (camada `domain` ou `infrastructure`, mas importável sem depender de `sqlite3`/`pymongo`) envolvendo falhas de persistência; `presentation/controllers.py` passa a capturar esse tipo único, não mais `PyMongoError`.
- **Testes:** `sqlite3.connect(":memory:")` substitui os fakes/mocks de `Collection` pymongo. Efeito colateral **positivo**: os testes de repositório deixam de ser `@pytest.mark.integration` com skip condicional — passam a rodar **sempre**, sem depender de serviço externo de pé.

## 3. Consequências e Impactos na Base de Código

### Positivos
- **Fecha a maior dívida de ambiente da sessão:** CA-01 e a persistência do CA-03 finalmente ficam validáveis de ponta a ponta, sem instalar nada.
- **Onboarding trivial:** README perde toda a seção de instalação/serviço de banco.
- **Testes mais fortes:** repositórios passam a ser testados contra um banco real (mesmo que em memória), não contra um fake escrito à mão.
- **Corrige uma violação de camada** (`PyMongoError` na apresentação) como subproduto da migração.

### Negativos/Riscos aceitos
- Perde a semântica de documento flexível do Mongo (irrelevante aqui: o schema já era rígido via pydantic).
- Sem suporte nativo a acesso concorrente multi-processo robusto — aceitável (app single-user, já era premissa do RF02).
- Reescrita de ~2 repositórios + seus testes + a fiação da GUI + docs — escopo médio, mas **contido** graças ao `Protocol`.

## 4. Escopo de arquivos impactados (levantado no código atual)
| Arquivo | Mudança |
|---|---|
| `pyproject.toml` | Remove `pymongo`; nenhuma dependência nova (`sqlite3` é stdlib) |
| `.env.example` / `config.py` | `MONGO_URI`/`MONGO_DB` → `DATABASE_PATH` (ex.: `data/contract_parser.db`) |
| `infrastructure/database.py` | Reescreve: `get_connection()` (factory/singleton sqlite3), `check_health()`, criação de schema |
| `infrastructure/empresa_repository.py` | Reimplementa `EmpresaRepositoryProtocol` sobre sqlite3 (mesma API pública) |
| `infrastructure/tabela_irrf_repository.py` | Reimplementa sobre sqlite3 (mesma API pública) |
| `infrastructure/environment_check.py` | Troca checagem "MongoDB acessível" por "arquivo do banco criável/gravável" |
| `presentation/controllers.py` | Troca 7 ocorrências de `except PyMongoError` por `except RepositoryError` |
| `presentation/app.py` | Troca a instanciação do repositório Mongo pela SQLite |
| `tests/infrastructure/test_database.py`, `test_empresa_repository.py`, `test_tabela_irrf_repository.py` | Reescritos contra `sqlite3.connect(":memory:")`; **removem** o marker `integration`/skip |
| `README.md`, `.agent/specs/adr-001-*.md`, `contract-parser-requirements.md`, `contract-parser-implementation-plan.md`, `checklist-aceite-final.md` | Atualização de menções a "MongoDB" → "SQLite" |
| `pyproject.toml` (`[tool.pytest.ini_options]`) | Marker `integration` permanece (ainda serve a `pytesseract`/LLM), só perde os casos de Mongo |

**Não afetados** (confirma o isolamento arquitetural): `domain/*` inteiro, `application/empresa_importer.py`, `application/empresa_service.py`, `application/portfolio_validation_service.py`, `application/relatorio_service.py`, `application/contract_extraction_service.py`, `infrastructure/text_extractors.py`, `infrastructure/report_exporters.py`, `infrastructure/llm_interpreter.py`, `infrastructure/atualizador_rfb.py`.

## 5. Pendência a confirmar com o usuário
Não há dado de produção a migrar: em nenhum momento desta sessão o MongoDB esteve de fato instalado/rodando neste host — todo o desenvolvimento usou fakes/mocks. Se existir uma instância MongoDB com dados reais em outro ambiente (fora desta máquina), sinalizar **antes** de M3, pois exigiria um script de exportação/importação adicional fora deste plano.
