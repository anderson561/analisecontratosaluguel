# AI Contract Parser — Leitor Inteligente de Contratos de Locação

Aplicação desktop para leitura, extração e auditoria de contratos de locação em lote (PDF/DOCX), cruzamento com portfólio de empresas, cálculo de IRRF e relatórios profissionais.

## Stack (ver [ADR-001](.agent/specs/adr-001-stack-e-arquitetura.md) + [ADR-002](.agent/specs/adr-002-migracao-mongodb-sqlite.md))
Python 3.11+ · SQLite (embarcado) · CustomTkinter · Tesseract OCR (por-BRA) · pydantic · pytest (TDD)

> ⚠️ **Docker está fora do escopo desta versão.** Ambiente roda nativamente no host.

## Pré-requisitos (setup manual no Windows)
1. **Python 3.11+**
2. **Tesseract-OCR** com pacote de idioma `por`

O banco de dados é **SQLite** (arquivo local, embarcado na stdlib do Python) —
não há serviço externo de banco para instalar ou manter em execução.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env   # ajuste DATABASE_PATH, TESSERACT_CMD, etc.
```

## Verificação de ambiente (Fase 1)
Antes de rodar a aplicação, confirme que o host está pronto:
```bash
contract-parser-envcheck          # se o pacote foi instalado com pip install -e .
# ou, sem instalar o pacote:
set PYTHONPATH=src && python -m contract_parser.infrastructure.environment_check
```
Reporta PASS/FAIL para Python ≥ 3.11, banco de dados SQLite gravável e Tesseract
(idioma `por`), com instruções do que corrigir quando algo falta. Exit code 0 =
tudo OK, 1 = há pendências. A checagem do banco é praticamente sempre PASS —
SQLite é um arquivo, não um serviço; só falha em caso de permissão negada ou
disco cheio no caminho configurado em `DATABASE_PATH`.

### Instalação manual do Tesseract (não automatizada)
| Serviço | Instalação (Windows) | Como verificar |
|---------|----------------------|----------------|
| **Tesseract-OCR** | Instalador UB-Mannheim + pacote de idioma `por`; ajuste `TESSERACT_CMD` no `.env` | `tesseract --version` e `tesseract --list-langs` (deve listar `por`) |

## Como rodar a aplicação (GUI)
Com o ambiente pronto (venv ativo, `.env` configurado):
```bash
contract-parser-gui                # se o pacote foi instalado com pip install -e .
# ou, sem instalar o pacote:
set PYTHONPATH=src && python -m contract_parser.presentation.app
```
O arquivo do banco SQLite (`DATABASE_PATH`) é criado automaticamente na
primeira execução, se ainda não existir. Se o caminho configurado não for
gravável, a GUI ainda abre (degradação graciosa — banner de status avisa e as
abas que dependem do banco falham com mensagem amigável, sem derrubar o
processo).

## Testes
```bash
pytest                          # suíte completa (unit + integração + E2E headless)
pytest -q --cov                 # com relatório de cobertura no terminal
ruff check src tests            # lint (zero warnings é o padrão do projeto)
```
Testes marcados `integration` (ex.: OCR real via Tesseract, provedor de LLM)
fazem `skip` automático quando o recurso não está disponível — não é falha, é
ambiente incompleto. Os testes de persistência (repositórios) NÃO precisam
mais desse marker: rodam sempre, contra SQLite embarcado (`sqlite3`), sem
nenhum serviço externo de pé (ver ADR-002). Alguns skips são esperados em
clone limpo/CI: `pytesseract` não instalado, provedor de LLM não configurado
(decisão adiada, ver Backlog) e o harness de contratos reais
(`CONTRATOS_REAIS_DIR` não definida — ver abaixo).

### Harness opcional sobre contratos reais (não versionado)
`tests/application/test_harness_contratos_reais.py` roda o pipeline de
ingestão+extração sobre uma pasta de PDFs reais fora do repositório (LGPD: os
arquivos NUNCA são commitados). Uso local:
```bash
set CONTRATOS_REAIS_DIR=C:\caminho\para\contratos_reais
pytest tests/application/test_harness_contratos_reais.py -s
```
Sem a variável definida, a suíte é ignorada (`skip`) automaticamente.

## Gerando o executável (.exe)
Para distribuir a aplicação sem exigir Python instalado na máquina de destino,
basta rodar (na raiz do repositório, no Windows):
```bash
build.bat
```
O script cria/reaproveita o venv em `.venv`, instala o projeto com o grupo
opcional `[build]` (adiciona `pyinstaller` às dependências normais) e empacota
tudo com PyInstaller (`contract_parser.spec`), gerando um único arquivo:
```
dist\ContractParser.exe
```
Copie esse `.exe` para a máquina de destino — **basta esse arquivo, sem mais
nada**. Desde que o Tesseract-OCR passou a ser **embutido no executável**
(binário + DLLs de runtime + pacote de idioma português `por.traineddata`),
a máquina que só EXECUTA o `.exe` pronto não precisa mais instalar o
Tesseract manualmente nem configurar `TESSERACT_CMD` — o OCR de PDFs
escaneados funciona out-of-the-box. Só o idioma português é embutido por
padrão (escopo fechado; outro idioma exigiria um pedido separado).

Se quiser apontar para um Tesseract do sistema com outros idiomas instalados,
configure `TESSERACT_CMD` via `.env` (ou variável de ambiente) normalmente —
isso continua tendo prioridade sobre o Tesseract embutido.

**Requisito só para quem RECOMPILA o `.exe`:** a máquina de build precisa ter
o Tesseract-OCR instalado localmente (ver
[Instalação manual do Tesseract](#instalação-manual-do-tesseract-não-automatizada)),
pois o `contract_parser.spec` copia `tesseract.exe` + DLLs + `por.traineddata`
de lá para dentro do bundle no momento da compilação. Por padrão ele procura
em `C:\Program Files\Tesseract-OCR` (instalação padrão do instalador
UB-Mannheim); para usar outro caminho, defina a variável de ambiente
`TESSERACT_BUILD_DIR` antes de rodar `build.bat`. Se o Tesseract não for
encontrado, o `.spec` interrompe a compilação com uma mensagem explicando o
que instalar/configurar — não é necessário na máquina que só executa o
`.exe` já pronto.

> **Licença do Tesseract OCR:** o binário embutido é do projeto
> [Tesseract OCR](https://github.com/tesseract-ocr/tesseract), licenciado
> sob Apache License 2.0.

## Estrutura (arquitetura em camadas)
```
src/contract_parser/
  domain/          # modelos + regras (IRRF, match, validação jurídica) — sem IO
  application/     # casos de uso / serviços (orquestram domain + infra)
  infrastructure/  # SQLite, OCR, LLM (stub), exportação PDF/Excel, RFB (stub)
  presentation/    # controllers/viewmodels (headless) + views CustomTkinter
    views/         # widgets CustomTkinter (não testados por pytest sem display)
tests/             # pytest — unit (domain), integração (application/infra),
                   # E2E headless (presentation/controllers)
```

## Escopo atual vs. backlog
Entregue (RF01–RF06, CA-01, CA-03 a CA-06 — ver
[checklist de aceite final](.agent/specs/checklist-aceite-final.md)):
- Gestão de empresas (importação em lote + CRUD), ingestão PDF/DOCX + OCR,
  extração híbrida (regras/regex) de partes/valores/vigência/reajuste, motor
  de IRRF 2026 com memória de cálculo, match de portfólio (CNPJ + fuzzy),
  flags jurídicas (Art. 18/37 da Lei 8.245/91), GUI CustomTkinter e exportação
  PDF/Excel.
- O motor de IRRF aplica automaticamente, para locador Pessoa Física, o
  redutor da Lei nº 15.270/2025 (Art. 3º-A da Lei nº 9.250/1995) sobre o
  imposto calculado pela tabela progressiva padrão — o valor reduzido fica
  visível no Painel e nos relatórios exportados (coluna "Redução IRRF"), ao
  lado do IRRF Retido já com a redução aplicada. Fórmula, fonte legal e
  ressalvas: [ADR-003](.agent/specs/adr-003-redutor-irrf-2026.md).

Fora do escopo desta versão (decisão deliberada, não pendência esquecida):
- **Docker/`docker-compose`** (CA-02) — adiado; app e banco (SQLite) rodam
  nativos no host Windows (ver ADR-001, decisão D2).
- **Provedor de LLM externo** — adiado por LGPD (minimização de dados
  sensíveis); o motor de extração é 100% determinístico (regras/regex) e o
  `StubInterpretadorLLM` recusa-se a operar até um provedor ser escolhido e
  aprovado. Campos ambíguos vão para revisão manual em vez de sair via LLM.
  Consequência: `LLM_PROVIDER`/`LLM_API_KEY` no `.env` ficam vazios em
  produção — não é uma variável esquecida.
- **Revalidação online da tabela IRRF contra a RFB** — o botão/fluxo é
  suportado pela interface (`AtualizadorTabelaRFB`), mas o adaptador de
  produção (`StubAtualizadorTabelaRFB`) ainda não integra rede; a aplicação
  usa a última tabela persistida.

## Documentação viva (`.agent/specs/`)
- [Plano de implementação](.agent/specs/contract-parser-implementation-plan.md)
- [Requisitos & regras de negócio](.agent/specs/contract-parser-requirements.md)
- [ADR-001 — Stack & Arquitetura](.agent/specs/adr-001-stack-e-arquitetura.md)
- [ADR-002 — Migração de Persistência MongoDB → SQLite](.agent/specs/adr-002-migracao-mongodb-sqlite.md)
- [ADR-003 — Redutor de IRRF 2026 (Lei nº 15.270/2025)](.agent/specs/adr-003-redutor-irrf-2026.md)
- [Checklist de aceite final (CA-01 a CA-06)](.agent/specs/checklist-aceite-final.md)

## Roadmap (fases)
0. ✅ Fundação, Requisitos & Governança
1. ✅ Ambiente local + persistência (originalmente MongoDB; migrado para SQLite — ver ADR-002)
2. ✅ Dados & Gestão de Empresas (RF01) — CA-01
3. ✅ Ingestão & OCR (RF02)
4. ✅ Extração NLP híbrida (RF03) — CA-05, CA-06
5. ✅ Motor IRRF 2026 (RF04) — CA-03
6. ✅ Match de portfólio (RF05) — CA-04
7. ✅ GUI & Relatórios (RF06)
8. ✅ QA, Segurança & Entrega — ver [checklist de aceite final](.agent/specs/checklist-aceite-final.md)
