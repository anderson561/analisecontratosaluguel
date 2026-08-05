# Plano de Ação — Migração MongoDB → SQLite

> **Base:** ADR-002 · **Status:** Aprovado para execução · **Data:** 2026-08-05

## Objetivo
Substituir o motor de persistência (MongoDB → SQLite embarcado), sem alterar contrato público de `application/`/`domain/`, corrigindo de passagem o vazamento de `PyMongoError` na camada de apresentação.

## Sequência de execução (etapas de migração)

### M1 — Núcleo de conexão (`infrastructure/database.py` + `config.py`)
- `config.py`: troca `mongo_uri`/`mongo_db` por `database_path` (default `data/contract_parser.db`; cria o diretório `data/` se ausente).
- `database.py`: `get_connection()` (singleton `sqlite3.Connection`, `check_same_thread=False`, `PRAGMA foreign_keys=ON`), `reset_connection()`, `check_health()` (tenta `SELECT 1`; nunca lança — mesmo contrato de hoje) e `init_schema(conn)` com `CREATE TABLE IF NOT EXISTS` das duas tabelas.
- Define `RepositoryError` (exceção de infraestrutura agnóstica de motor) para uso nas etapas seguintes.
- Testes: reescreve `test_database.py` contra `sqlite3.connect(":memory:")` — sem skip condicional.

### M2 — Repositório de Empresas
- `infrastructure/empresa_repository.py`: `EmpresaRepository` sobre a tabela `empresas` (`cnpj TEXT PRIMARY KEY, razao_social TEXT NOT NULL, aliases TEXT, nomes_fantasia TEXT, ativo INTEGER, origem_import TEXT, created_at TEXT`), mesma API pública (`add/get_by_cnpj/list_all/update/remove/upsert_many`), `aliases`/`nomes_fantasia` via `json.dumps`/`json.loads`.
- `upsert_many` via `INSERT ... ON CONFLICT(cnpj) DO UPDATE` (equivalente ao `bulk_write` upsert de hoje) — idempotente, dentro de uma transação.
- Testes: reescreve `test_empresa_repository.py` contra sqlite em memória; **reaproveita** o teste "CA-01: 50 empresas" já existente, agora capaz de rodar sem qualquer serviço externo.

### M3 — Repositório de Tabela IRRF
- `infrastructure/tabela_irrf_repository.py`: `TabelaIRRFRepository` sobre a tabela `tabela_irrf` (`vigencia TEXT PRIMARY KEY, faixas TEXT, fonte_url TEXT, base_legal TEXT, validado INTEGER, validado_em TEXT`), mesma API pública (`upsert/get_por_vigencia/get_vigente/list_all`).
- Reusa a serialização `model_dump(mode="json")` já usada para `Decimal`/`date`.
- Testes: reescreve `test_tabela_irrf_repository.py` contra sqlite em memória; mantém o teste do CA-03 com a tabela 2026 persistida e recuperada.

### M4 — Verificador de ambiente
- `infrastructure/environment_check.py`: remove a checagem "MongoDB acessível"; adiciona checagem "arquivo/diretório do banco SQLite gravável" (tenta abrir conexão + `init_schema`).
- Resultado esperado: **2 checagens** (Python, Tesseract) em vez de 3 — SQLite não é mais um serviço a verificar, é só um arquivo.

### M5 — Apresentação (GUI) e composição
- `presentation/controllers.py`: troca as 7 ocorrências de `except PyMongoError` por `except RepositoryError` (importado de `infrastructure/database.py` ou onde M1 o definir).
- `presentation/app.py`: troca a construção do `EmpresaRepository()` Mongo pela versão SQLite (a API pública não muda, só a implementação por trás — idealmente **nenhuma outra linha muda** em `app.py`/`controllers.py` além da exceção).

### M6 — Regressão completa + validação real do CA-01/CA-03
- `pytest -q` deve ficar verde, e o número de `skipped` deve **cair** (os 3 skips de `integration`/MongoDB desaparecem).
- Rodar manualmente o fluxo real: importar uma planilha de 50 empresas de verdade contra o arquivo SQLite (não mais fake) — **fecha CA-01 de fato pela primeira vez**.
- `ruff check src tests` limpo.

### M7 — Documentação viva
- `pyproject.toml`: remove `pymongo` das dependências; ajusta o texto do marker `integration` (deixa de mencionar MongoDB).
- `.env.example`: `MONGO_URI`/`MONGO_DB` → `DATABASE_PATH`.
- `README.md`: remove a seção de instalação do MongoDB Community; simplifica "Verificação de ambiente" (2 checagens); atualiza "Como rodar a aplicação".
- Atualiza `.agent/specs/adr-001-stack-e-arquitetura.md` (nota apontando para o ADR-002), `contract-parser-requirements.md`, `contract-parser-implementation-plan.md` e `checklist-aceite-final.md` (troca menções a "MongoDB"/coleção por "SQLite"/tabela; marca CA-01 como **validado de fato**, não mais só via mock).

## Critério de conclusão
- Nenhuma referência a `pymongo`/`MongoClient`/`PyMongoError` restante em `src/` ou `tests/` (exceto histórico em `.agent/specs/` como registro de decisão).
- Suíte inteira verde, sem skips de "MongoDB indisponível".
- CA-01 validado com arquivo SQLite real (não mock) pelo menos uma vez nesta sessão.
- README não menciona mais instalação de serviço de banco.

## Delegação proposta (conforme `.agents/AGENTS.md`)
Decisão já registrada no ADR-002 (função do Tech Lead, feita diretamente pelo PM dado o baixo risco/escopo contido). Execução em 2 blocos, mesmo padrão usado nas Fases 1–7:
1. **MIG-A (M1–M3):** núcleo de persistência + os dois repositórios + seus testes — trabalho de backend (skills `python-automation-pro`/`python-ds-architect`).
2. **MIG-B (M4–M7):** verificador de ambiente, fiação da GUI, regressão completa e documentação — inclui a validação real do CA-01.
