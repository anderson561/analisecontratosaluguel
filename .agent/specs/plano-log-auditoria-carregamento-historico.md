# Plano — Log de auditoria do carregamento do histórico (Painel vazio intermitente)

## Contexto
Usuário reportou (com prints) que o Painel de Contratos aparece vazio após
fechar e reabrir o `.exe`, mesmo com o banco (`dist\data\contract_parser.db`)
contendo os registros corretamente e passando health check (`SELECT 1` ok).
Investigação em `C:\python\analisecontratosaluguel` (mesma máquina) não
reproduziu a falha por simulação direta — hipótese líder é uma falha
intermitente (ex.: lock transitório do SQLite entre o processo anterior
fechando e o novo abrindo rápido demais), difícil de reproduzir sob controle.

Decisão (aprovada pelo usuário via pergunta direta): em vez de continuar só
tentando reproduzir, adicionar um log de auditoria leve e permanente que
registra, a cada chamada de `carregar_historico()` (inclui abertura do app),
quantos contratos foram carregados e qualquer erro — para capturar evidência
real na próxima ocorrência.

## Escopo
1. `config.py`: `Settings.log_path`, mesmo padrão de ancoragem de
   `database_path` (`sys.executable`/`sys.frozen` vs. raiz do repo em dev),
   override via `LOG_PATH` no `.env`. Arquivo `app.log` ao lado do banco.
2. Novo módulo `infrastructure/audit_log.py`: função `registrar_evento(mensagem, *, log_path=None)` —
   apenas `append` de uma linha com timestamp ISO. **Nunca lança** (falha de
   log não pode derrubar a UI — mesmo princípio de degradação graciosa já
   usado em `check_health`).
3. `controllers.py` — `RelatorioController.carregar_historico()`:
   - Sucesso: loga `"N contrato(s) carregado(s) do histórico"`.
   - `RepositoryError` ao listar: loga a mensagem do erro (já degradava
     graciosamente, agora também loga).
   - **Endurecimento correlato**: hoje, uma exceção inesperada durante a
     desserialização (`_from_row` → `Contrato.model_validate_json` /
     `ResultadoIRRF.model_validate`) NÃO é `RepositoryError` e propagaria sem
     ser capturada, quebrando a garantia de "app nunca cai por falha de
     banco/histórico" documentada no próprio docstring do método. Ampliar o
     `except` para também capturar isso, logar e degradar graciosamente
     (Painel abre vazio, com o motivo registrado no log) em vez de crashar.

## Fora de escopo
- Rotação/limite de tamanho do log (YAGNI — arquivo de texto simples,
  problema real do dia a dia não justifica logging estruturado).
- Exibir o log na UI (é uma ferramenta de diagnóstico para o PM, não uma
  feature de usuário final).

## Fases
1. **Implementação + testes** (TDD, delegado a `xp-coach`): `config.py` +
   `audit_log.py` + endurecimento de `carregar_historico()`, com testes
   cobrindo sucesso, `RepositoryError` e exceção inesperada (corrupção de
   linha), todos garantindo que nada propaga.
2. **Verificação pessoal** (PM): `pytest -q`, `ruff check src tests`, rebuild
   do `.exe`, smoke test real.

## Status
Fase 1 concluída (implementação + testes, TDD): `config.py` (`Settings.log_path`
+ `_caminho_log_padrao()`), `infrastructure/audit_log.py` (`registrar_evento`,
nunca lança) e `RelatorioController.carregar_historico()` endurecido para
capturar tanto `RepositoryError` quanto qualquer exceção inesperada (ex.:
`ValidationError` de linha corrompida), sempre logando e degradando
graciosamente. `pytest -q` (493 passed, 4 skipped — falha pré-existente e não
relacionada em `test_ocr_real_tesseract`, dependente do Tesseract do
ambiente) e `ruff check src tests` (all checks passed) executados pelo
desenvolvedor. Fase 2 (verificação pessoal do PM) concluída, `.exe`
recompilado e testado ao vivo.

## Fase 3 (2026-08-12) — o bug ocorreu de novo, log do controller não pegou

Usuário reprocessou os mesmos 9 contratos, fechou, esperou, reabriu — Painel
apareceu vazio de novo. `dist\data\app.log` mostra 4 aberturas (incluindo
3 de hoje, cobrindo antes/depois da reescrita), **todas** logando
"9 contrato(s) carregado(s) do histórico" — nenhuma falha registrada em
`carregar_historico()`. `processado_em` mais recente no banco bate
exatamente com a gravação da reescrita. Ou seja: o controller está
carregando os dados corretamente em toda abertura capturada — a suspeita
agora é a camada de **exibição** (`presentation/views/main_window.py`,
`_recarregar_painel`/`_desenhar_painel`), não a persistência. Hipótese do
filtro "Índice" resetando sozinho foi descartada lendo o código-fonte do
CustomTkinter (`ctk_optionmenu.py`: `configure(values=...)` não toca em
`_current_value`).

**Próxima ação:** estender `registrar_evento` para `_recarregar_painel()`
em `main_window.py`, logando `tem_dados()`, os valores de filtro (índice/
busca/auto) e `len(linhas)` resultante — isola exatamente em qual ponto da
cadeia a contagem cai para zero na próxima ocorrência.
