# Plano de Ação — Garantir que os Dados Persistidos Nunca "Somem"

> **Data:** 2026-08-11 · **Status:** Decisão confirmada (§3: só a correção do caminho, sem botão de backup) — pronto para Fase 1
> **Pedido do usuário:** dados cadastrados/editados/importados (empresas) e processados (contratos) não podem sumir ao fechar o software nem ao mover para outro computador.

## 1. O que JÁ está garantido (não é o problema)

Empresas (cadastro/edição/importação, incl. `.ods` recém-adicionado) e contratos processados **já são persistidos em SQLite**, não em memória (ADR-002; Fases 1-2 do plano de persistência de contratos, `.agent/specs/plano-3-features-persistencia-pdf-tooltip.md`). Fechar e reabrir o app no MESMO lugar já preserva os dados — isso já foi validado. O schema é aditivo (`CREATE TABLE IF NOT EXISTS`), então substituir o `.exe` por uma versão nova não apaga nem corrompe o banco existente.

## 2. O problema real — encontrado ao investigar (root cause)

`config.py` define `database_path: str = os.getenv("DATABASE_PATH", "data/contract_parser.db")` — um caminho **relativo**. `database.py` (`_abrir_conexao`) resolve esse caminho contra o **diretório de trabalho atual (CWD) do processo no momento em que ele inicia**, não contra a pasta onde o `ContractParser.exe` está de fato salvo.

Na prática, isso **parece** funcionar hoje porque um duplo-clique no `.exe` pelo Explorer do Windows normalmente define o CWD como a própria pasta do executável — é por isso que `dist/data/contract_parser.db` existe e já acumula os dados dos testes desta sessão. Mas essa coincidência **quebra** em qualquer um destes cenários, todos plausíveis no uso real:

- **Mover só o `ContractParser.exe`** para outro computador/pasta, sem levar a subpasta `data/` junto → na primeira execução lá, o app cria silenciosamente um banco **novo e vazio** no lugar (nenhum erro, nenhum aviso) — para o usuário, parece que "os dados sumiram".
- **Atalho na Área de Trabalho/barra de tarefas com "Iniciar em" apontando para outra pasta**, ou executar via linha de comando/rede de um diretório diferente → o CWD muda, o app silenciosamente lê/cria um banco em outro lugar, "perdendo" o que já estava cadastrado (que continua existindo, só que no lugar "errado").

Ou seja: o risco não é o SQLite em si (isso já funciona), é o **caminho do arquivo do banco depender de como o `.exe` foi iniciado**, em vez de depender de onde ele está fisicamente salvo. Confirmado: não há `.env` no projeto nem embutido no build fixando `DATABASE_PATH` — o padrão relativo vale tanto em dev quanto no `.exe` empacotado.

## 3. Decisão que preciso de você antes da Fase 2

A Fase 1 (correção do caminho) resolve o problema do CWD variável — mas **não resolve sozinha** o caso de alguém copiar só o `.exe` sem a pasta `data/` para outra máquina (isso é fundamentalmente impossível de "adivinhar": o dado só existe onde foi gravado). Para esse caso, tem duas abordagens, não excludentes:

1. **Documentar claramente** (README + talvez um aviso na GUI) que a pasta `data/`, ao lado do `.exe`, contém TODOS os dados e precisa ser copiada junto ao mover/fazer backup — mesmo espírito de "artefato autossuficiente" já usado para o Tesseract embutido.
2. **Adicionar um botão "Fazer backup do banco de dados…"** na GUI (copia o arquivo `.db` atual para onde o usuário escolher, via diálogo "Salvar como") — não depende do usuário saber/lembrar que existe uma pasta `data/` escondida; é a via mais à prova de erro para levar os dados para outra máquina ou simplesmente ter uma cópia de segurança.

**Decisão do usuário (2026-08-11):** só a Fase 1 (correção do caminho) + documentação. Sem botão de backup — migrar para outro computador continua exigindo copiar a pasta `data/` junto do `.exe`, e isso será documentado claramente no README.

## 4. Fases

### Fase 1 — Ancorar o caminho do banco à pasta do executável (correção do bug)
- `config.py`: quando `DATABASE_PATH` não estiver definida via variável de ambiente, o padrão passa a ser calculado dinamicamente: se `sys.frozen` (rodando como `.exe` PyInstaller), ancora em `Path(sys.executable).resolve().parent / "data" / "contract_parser.db"` (a pasta onde o `.exe` está de fato salvo — não o CWD, nem o `_MEIPASS` temporário do onefile). Em modo dev (não frozen), mantém o comportamento atual (raiz do repo, onde `data/contract_parser.db` já vive hoje) para não quebrar nada em desenvolvimento/testes.
- `DATABASE_PATH` explícita (variável de ambiente) continua tendo prioridade — preserva o caso de uso avançado (ex.: apontar para uma pasta compartilhada de rede), só o *padrão* muda.
- **Nenhuma migração de dados necessária**: para o build atual (`dist/ContractParser.exe` + `dist/data/`), o novo cálculo padrão já aponta para o mesmo lugar onde os dados de hoje estão — a correção é sobre a ROBUSTEZ do cálculo (deixar de depender do CWD), não sobre mudar onde os dados ficam nesta máquina.
- **Agente sugerido:** `xp-coach` (TDD — testar `_caminho_banco_padrao()` isolado com `monkeypatch` de `sys.frozen`/`sys.executable`, sem precisar de um `.exe` de verdade).

### Fase 2 — Testes + regressão
- Cobrir: `sys.frozen=False` (dev) → caminho relativo de hoje preservado; `sys.frozen=True` com `sys.executable` simulado → caminho ancorado na pasta do executável, independente de qual seja o CWD do processo no teste; `DATABASE_PATH` explícita → sempre vence, nos dois modos.
- Suíte completa + `ruff` (verificado por mim, PM).
- Rebuild do `.exe` + teste manual (ver Fase 5).

### Fase 3 — Documentação
- README: seção explícita "seus dados ficam em `data/contract_parser.db`, ao lado do `.exe` — copie essa pasta junto ao mover o programa ou fazer backup".
- `.agent/specs/contract-parser-requirements.md`: nota sobre a garantia de persistência (novo CA ou nota em RF01/RF04, a definir na implementação).

### Fase 4 — Rebuild e validação manual (eu, PM, faço pessoalmente)
- Reconstruir o `.exe`.
- Validar cenário real: copiar a pasta `dist/` inteira (exe + data) para um caminho diferente (ou renomear a pasta) e confirmar que os dados continuam lá ao abrir de lá — é o teste que efetivamente prova a correção, mais fiel que só rodar a suíte.

## 5. Critério de pronto
- Suíte verde + `ruff` limpo.
- Copiar a pasta inteira do `.exe` para outro caminho (simulando "mover para outro computador") preserva os dados.
- Rodar o `.exe` a partir de um atalho com "Iniciar em" diferente da pasta do `.exe` também preserva os dados (prova que não depende mais do CWD).
- README atualizado.
