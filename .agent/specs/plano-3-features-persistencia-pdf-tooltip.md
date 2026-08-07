# Plano de Ação — 3 Features Novas (Persistência de Contratos, Relatório PDF, Tooltip "Revisar")

> **Data:** 2026-08-07 · **Status:** Decisões confirmadas pelo usuário (§2) — pronto para iniciar Fase 1
> **Pedido do usuário:** (1) contratos analisados devem ficar gravados (dados persistentes), com opção de exclusão; (2) botão para gerar relatório em PDF; (3) tooltip ao passar o mouse sobre "Revisar" explicando o que significa.

## 0. Levantamento factual (feito antes de planejar, só leitura)

- **Feature 1 (persistência):** confirmado — **não existe hoje**. Só há SQLite para `empresas` (portfólio) e `tabela_irrf` (`infrastructure/database.py:90-119`). Contratos processados vivem só em memória (`ProcessamentoController._contratos`, `RelatorioController._relatorio/_pares` em `controllers.py`) e são perdidos ao fechar o app. Feature genuinamente nova.
- **Feature 2 (relatório PDF):** **já existe e já funciona**, ligado a um botão real. Aba "Conformidade" → botão "Exportar PDF…" (`main_window.py:319-321`) → `RelatorioController.exportar("pdf", destino)` (`controllers.py:400-415`) → `PdfRelatorioExporter` (`infrastructure/report_exporters.py:178-286`, usa `reportlab`), com diálogo "Salvar como" para escolher o destino. Ver §2 — preciso entender o que falta/difere do que já existe antes de escrever a fase de implementação.
- **Feature 3 (tooltip "Revisar"):** o texto "Revisar" é uma célula de status na tabela do Painel (`main_window.py:298`, coluna "Revisão"), sem nenhum tooltip/hover hoje. **Não existe nenhum mecanismo de tooltip no projeto** (`grep` por `tooltip|hover|bind\(.<Enter>` não retorna nada) — será a primeira implementação desse tipo na GUI. O flag que dispara "⚠ revisar" vem de dois motivos distintos e hoje indiferenciados na UI: `LinhaContrato.dados_incompletos` (faltou valor do aluguel ou IRRF não calculável) OU `Contrato.necessita_revisao` (algum campo extraído com baixa confiança, lista em `Contrato.campos_para_revisao`).

## 1. Arquitetura/camadas envolvidas (para a matriz de delegação)

- `domain/relatorio.py`, `domain/contrato.py`, `domain/repositories.py` — modelos e Protocols (camada pura, sem IO).
- `infrastructure/database.py` (schema SQLite), novo `infrastructure/contrato_repository.py` (CRUD), `infrastructure/report_exporters.py` (já existe, feature 2).
- `presentation/controllers.py` (`ProcessamentoController`, `RelatorioController`), `presentation/views/main_window.py` (única view).

## 2. Decisões confirmadas pelo usuário (2026-08-07)

1. **Feature 2 (PDF):** usuário não sabia que já existia — **nenhuma mudança de código nesta feature**. O botão "Exportar PDF…" (aba Conformidade) já atende; Fase 4 abaixo vira só uma demonstração/validação, não implementação.
2. **Reprocessamento:** **atualizar o registro existente** (mesmo arquivo = 1 registro só, sempre a versão mais recente) — opção recomendada, confirmada.
3. **Exclusão:** **linha a linha E "limpar tudo"** — ambas as opções ficam disponíveis na UI (usuário pediu explicitamente as duas, não só a recomendada).

## 3. Fases (assumindo as decisões recomendadas abaixo — ajusto conforme sua resposta em §2)

### Fase 1 — Persistência de contratos (domain + infrastructure)
- Nova tabela `contratos` no SQLite (`infrastructure/database.py`, mesmo padrão híbrido já usado em `tabela_irrf`: colunas indexáveis para filtro/listagem + coluna(s) JSON para o detalhe completo/auditável):
  - Colunas relacionais: `id` (PK, UUID), `arquivo_nome`, `arquivo_hash` (sha256 do conteúdo — chave de dedup para a decisão §2.2), `processado_em`, `locador_nome`, `locatario_nome`, `valor_aluguel`, `irrf_valor`, `empresa_cnpj_match` (nullable), `revisao` (bool), `arquivo_ausente` (bool, ver nota abaixo).
  - Coluna JSON: `contrato_json` (serialização completa do `Contrato` pydantic + `ResultadoIRRF` + resultado do match de portfólio) — preserva a memória de cálculo/extração completa para reexibir ou reexportar sem reprocessar.
- Novo Protocol `ContratoRepositoryProtocol` (`domain/repositories.py`, ao lado de `EmpresaRepositoryProtocol`) + implementação `ContratoRepository` (`infrastructure/contrato_repository.py`): `salvar(...)`, `listar() -> list[...]`, `excluir(id)`, e (se §2.2 = "atualizar") `buscar_por_hash(hash)`.
- **Nota de design:** o registro persistido é histórico/auditável — se o arquivo original for movido/apagado da pasta de origem depois, o registro no banco **não** deve sumir sozinho (isso apagaria uma trilha de auditoria fiscal sem ação explícita do usuário); a UI pode sinalizar "arquivo de origem não encontrado" (campo `arquivo_ausente`), mas só a exclusão explícita (feature pedida) remove o registro.
- **Agente sugerido:** `xp-coach` (TDD estrito, mesmo padrão dos fixes anteriores).

### Fase 2 — Wiring no controller (persistir ao processar, carregar ao abrir)
- **Como resolver a perda de identidade do arquivo (o risco note em §0):** não precisa mudar `Contrato`/`ProcessamentoResultado`. `ProcessamentoController.processar_pasta` já constrói `contratos` iterando `ingestao.documentos` **na mesma ordem**, 1:1 — então `zip(resultado.ingestao.documentos, resultado.contratos, strict=True)` já dá o pareamento certo (arquivo → contrato) no ponto onde `AppController.processar_pasta` tem os dois. `DocumentoTexto.hash` (sha256 do conteúdo, já calculado na ingestão) vira `arquivo_hash`; `Path(doc.caminho).name` vira `arquivo_nome`.
- `RelatorioController.definir_contratos` ganha um parâmetro opcional `documentos: list[DocumentoTexto] | None` — quando presente (fluxo normal de processamento) e o controller tiver um `ContratoRepositoryProtocol` injetado, persiste cada linha via `salvar(...)` (upsert por hash, decisão §2.2). Falha de persistência de um item **não aborta** o restante nem quebra o Painel em memória (mesmo espírito de "erro por arquivo" do `IngestaoResumo`) — fica coletada numa lista exposta por um novo getter, não estoura `ControllerError`.
- `RelatorioController` ganha `carregar_historico()`: chama `contrato_repo.listar()` e alimenta `definir_contratos([r.contrato for r in registros])` (sem `documentos` → não repersiste o que já está salvo). `AppController`/`app.build_controller()` chama isso uma vez ao montar o controller, se um `contrato_repo` foi injetado — é isso que faz o Painel já nascer com o histórico.
- **Consequência aceita (vale saber):** carregar o histórico **recalcula** IRRF/match de portfólio com as regras/tabela ATUAIS (reusa o mesmo `RelatorioService.montar`), não reexibe os valores exatamente como foram calculados na época. Para uma ferramenta fiscal isso tende a ser desejável (ex.: contratos antigos passam a refletir a correção do ADR-004 automaticamente), mas é uma escolha explícita, não um detalhe escondido.
- **Fora desta fase (fica para a Fase 3):** o `id` do registro persistido ainda não é exposto em `LinhaPainel`/`_pares` — é isso que a Fase 3 (botão Excluir por linha) vai precisar adicionar.
- **Agente sugerido:** `xp-coach`.

### Fase 3 — UI de exclusão
- Botão/ícone "Excluir" por linha na tabela do Painel de Contratos (`main_window.py`), com `messagebox.askyesno` de confirmação antes de chamar `RelatorioController.excluir(id)`.
- Botão "Limpar tudo" (exclusão em massa), com confirmação reforçada (ex.: `messagebox.askyesno` com aviso explícito de que a ação não pode ser desfeita) antes de chamar `RelatorioController.excluir_todos()`.
- **Agente sugerido:** `xp-coach`.

### Fase 4 — Relatório PDF
- Sem implementação — feature já existe (botão "Exportar PDF…", aba Conformidade). Só validar com você, ao testar o `.exe` rebuildado desta rodada, que o botão atual atende.

### Fase 5 — Tooltip em "Revisar"
- Implementação manual (bind `<Enter>`/`<Leave>` + `Toplevel` sem decoração, padrão comum em Tkinter/CustomTkinter) na célula "Revisão" do Painel (`main_window.py:298`) — **recomendado não adicionar dependência nova** (ex. `CTkToolTip`) para uma única tooltip; ajusto se preferir a lib.
- Texto do tooltip precisa diferenciar os dois motivos (hoje indiferenciados, ver §0): algo como "Revisar: {campos incompletos: valor do aluguel/IRRF} e/ou {campos extraídos com baixa confiança: lista de `Contrato.campos_para_revisao`}" — vou usar os dados que já existem (`LinhaContrato.dados_incompletos`, `Contrato.campos_para_revisao`) para montar o texto específico de cada linha, não um texto genérico fixo.
- **Agente sugerido:** `xp-coach`.

## 4. Critério de pronto
- Suíte verde + `ruff` limpo em cada fase (verificado por mim, PM, antes de commitar).
- Reprocessamento dos 7 contratos reais sem regressão (hábito já estabelecido no projeto).
- CA novo em `.agent/specs/contract-parser-requirements.md` para persistência/exclusão (a definir o número, ex. CA-06/07).
- `.exe` rebuildado e testado manualmente por você antes de considerar a feature fechada (schema SQLite novo = migração a testar num banco já existente, não só banco novo).

## 5. Fora de escopo (a menos que você peça)
- Edição manual de um contrato já persistido (só leitura + exclusão, não há CRUD de edição pedido).
- Versionamento/histórico de reprocessamentos se a decisão §2.2 for "atualizar" (nesse caso, a versão anterior é sobrescrita, não arquivada).
- Exportação em lote de múltiplos PDFs individuais (só se a Fase 4 pedir relatório por contrato).
