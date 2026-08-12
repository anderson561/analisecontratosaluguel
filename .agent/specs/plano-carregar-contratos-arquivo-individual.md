# Plano — Renomear aba "Processamento" para "Carregar Contratos" + selecionar arquivo individual

## Contexto
Pedido do usuário: na aba hoje chamada "Processamento", (1) renomear o
rótulo para "Carregar Contratos" e (2) acrescentar a possibilidade de
escolher um arquivo (ou arquivos) individualmente, em vez de só poder
selecionar uma pasta inteira.

Hoje o fluxo (`presentation/views/main_window.py::_construir_aba_processamento`)
só oferece "Selecionar pasta e processar…", que chama
`filedialog.askdirectory` → `AppController.processar_pasta(pasta)` →
`ProcessamentoController.processar_pasta` → `DirectoryIngestor.ingerir(pasta)`
(`application/document_ingestor.py`), que varre `pasta.iterdir()` e exige um
diretório (`DiretorioIngestaoError` se não for). Não existe hoje um caminho
para processar um ou mais arquivos escolhidos individualmente.

## Escopo

### 1. Renomear o rótulo da aba (só texto visível ao usuário)
- `main_window.py`: `self._tabs.add("Processamento")` → `self._tabs.add("Carregar Contratos")`.
- `messagebox.showerror("Processamento", ...)` (mesmo arquivo, handler de
  erro do processamento) → `"Carregar Contratos"`, por consistência.
- **Não renomear** identificadores internos (`_tab_processamento`,
  `_construir_aba_processamento`, `_on_processar`, `processar_pasta` em
  `ProcessamentoController`/`AppController`, `ProcessamentoResultado`) — são
  detalhes de implementação sem valor de renomear, e o método
  `processar_pasta` continua existindo tal como está (só ganha um
  companheiro para arquivos, ver §2).

### 2. Selecionar arquivo(s) individual(is)
Reaproveitar ao máximo o pipeline existente (extração híbrida, matching de
portfólio, persistência, Painel/Conformidade) — a única peça nova é a
ingestão a partir de uma lista de arquivos em vez de uma varredura de pasta.

- **`application/document_ingestor.py`** (`DirectoryIngestor`):
  - Extrair o laço de extração/dedup de `ingerir()` para um método privado
    compartilhado, ex. `_processar(self, arquivos: list[Path]) -> IngestaoResumo`.
  - Novo método público `ingerir_arquivos(self, caminhos: list[str | Path]) -> IngestaoResumo`:
    valida cada caminho (existe, é arquivo, extensão em
    `EXTENSOES_SUPORTADAS`) — caminho inválido entra como `ErroArquivo` no
    resumo, **sem abortar o lote** (mesmo princípio já usado em `ingerir`,
    onde erro por arquivo não aborta o restante); caminhos válidos vão para
    `_processar`.
- **`presentation/controllers.py`**:
  - `ProcessamentoController.processar_arquivos(self, caminhos: list[str | Path]) -> ProcessamentoResultado`
    — espelha `processar_pasta`, delega a `self._ingestor.ingerir_arquivos(caminhos)`.
  - `AppController.processar_arquivos(self, caminhos: list[str | Path]) -> ProcessamentoResultado`
    — espelha `AppController.processar_pasta`: chama
    `self.processamento.processar_arquivos(caminhos)`, depois
    `self.relatorio.definir_contratos(resultado.contratos, documentos=resultado.ingestao.documentos)`.
    Reaproveita 100% do fluxo de persistência/Painel/Conformidade já
    existente — nenhum código novo de persistência é necessário.
- **`presentation/views/main_window.py`**:
  - Novo botão "Selecionar arquivo(s) e processar…" na aba, ao lado do
    botão de pasta já existente (as duas opções coexistem — a pasta
    continua funcionando exatamente como hoje).
  - Handler `_on_processar_arquivos`: `filedialog.askopenfilenames`
    (permite escolher um único arquivo OU vários de uma vez, filtro
    `*.pdf *.docx`), chama `self._c.processar_arquivos(lista)`.
  - Extrair o bloco de exibição de resultado (atualizar label, log,
    `_recarregar_painel()`, `_recarregar_conformidade()`) de `_on_processar`
    para um helper privado compartilhado entre os dois handlers, evitando
    duplicar essa lógica.

## Fora de escopo
- Drag-and-drop de arquivos (não pedido).
- Mudar o comportamento do fluxo de pasta existente.
- Renomear identificadores internos/nomes de método além do texto visível
  ao usuário (§1).
- Suporte a outros formatos de arquivo além dos já suportados (`.pdf`/`.docx`).

## Fases
1. **Backend** (`document_ingestor.py` + `controllers.py`), TDD estrito —
   delegado a `xp-coach`: testes cobrindo `ingerir_arquivos` (arquivo válido,
   arquivo inexistente, extensão não suportada, mistura de válidos/inválidos
   no mesmo lote, deduplicação por hash igual à de `ingerir`) e
   `processar_arquivos` nos dois controllers.
2. **UI** (`main_window.py`: renomear aba/dialog + botão novo + refactor do
   bloco de exibição de resultado) — sem testes automatizados (views não são
   testadas por pytest neste projeto sem display, mesma convenção já
   estabelecida) — delegado a `xp-coach`, mudança cirúrgica.
3. **Verificação pessoal** (PM): `pytest -q`, `ruff check src tests`, rebuild
   do `.exe`, smoke test real capturando a janela (técnica de `PrintWindow`
   já validada nesta máquina) para confirmar visualmente o rótulo novo e o
   botão de arquivo funcionando.

## Status
- **Fase 1 (backend) concluída**: `DirectoryIngestor._processar`/`ingerir_arquivos`
  em `application/document_ingestor.py` e `ProcessamentoController.processar_arquivos`/
  `AppController.processar_arquivos` em `presentation/controllers.py`, com testes
  TDD cobrindo arquivo válido único/múltiplos, caminho inexistente, pasta em vez
  de arquivo, extensão não suportada, mix válidos/inválidos e deduplicação por
  hash. `pytest -q` (503 passed, 1 skip pré-existente por Tesseract ausente na
  máquina, não relacionado) e `ruff check src tests` (all checks passed) OK.
- Fase 2 (UI em `main_window.py`) e Fase 3 (verificação pessoal do PM) ainda
  pendentes.
