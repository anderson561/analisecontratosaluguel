# Plano — Corrigir "contratos somem ao anexar" + bloquear duplicidade ao anexar arquivo

## Contexto
Usuário reportou, logo após o uso real da nova feature "Selecionar
arquivo(s) e processar…" (aba Carregar Contratos): ao anexar um novo
contrato, **todos os outros contratos já carregados somem da tela**. Pediu
também: ao anexar um contrato idêntico a um já carregado, mostrar mensagem
de duplicidade e não permitir carregar.

### Causa raiz do "somem da tela" (confirmada lendo o código)
`RelatorioController.definir_contratos(contratos, ...)` (`presentation/controllers.py`,
linha ~333) **substitui inteiramente** `self._contratos`/`self._pares` pelo
que for passado — não faz merge com o que já estava carregado:
```python
self._contratos = list(contratos)
...
pares = zip(self._relatorio.contratos.linhas, self._contratos, ids, strict=True)
self._pares = [...]   # reconstruído do zero, só com os itens passados agora
```
`AppController.processar_pasta`/`processar_arquivos` chamam
`definir_contratos(resultado.contratos, documentos=...)` passando **só o
lote recém-processado** — isso persiste corretamente o(s) novo(s) contrato(s)
no banco (upsert por hash, ver `ContratoRepository.salvar`), mas o Painel em
tela passa a mostrar SÓ esse lote, "esquecendo" visualmente tudo que já
existia (mesmo estando intacto no banco). **Não há perda de dado real** —
é o mesmo tipo de bug já corrigido antes nesta sessão (`commit 25de02e`):
uma tela que não reflete o estado completo já persistido. Afeta os DOIS
fluxos (pasta e arquivo individual) igualmente — só apareceu agora porque
"anexar um arquivo a um conjunto já carregado" é o cenário mais natural de
expor isso.

**Padrão já estabelecido no código para esse tipo de situação** (usado em
`excluir_contrato`/`excluir_todos_contratos`): depois de qualquer ação que
mexe no banco, recarregar a visão em tela a partir do banco via
`self.relatorio.carregar_historico()` — nunca confiar só no estado parcial
em memória.

## Escopo

### 1. Fix: Painel sempre reflete o histórico completo após processar
Em `AppController.processar_pasta` e `AppController.processar_arquivos`
(`presentation/controllers.py`), depois de `self.relatorio.definir_contratos(...)`
(que persiste o lote novo), adicionar uma chamada a
`self.relatorio.carregar_historico()` para recarregar a visão do Painel a
partir do banco completo — mesmo padrão já usado em `excluir_contrato`/
`excluir_todos_contratos`. `carregar_historico()` já é no-op seguro quando
`contrato_repo is None` (sem persistência configurada), então não quebra
nenhum uso sem banco.

### 2. Bloquear duplicidade ao anexar arquivo individual
Escopo **só do fluxo de arquivo individual** (`processar_arquivos`/botão
"Selecionar arquivo(s) e processar…") — o fluxo de pasta continua com o
comportamento de upsert já existente e deliberado (reprocessar uma pasta
inteira para recalcular IRRF após mudança de tabela, por exemplo, decisão
já tomada no plano de persistência anterior). Selecionar de novo, um por
um, o MESMO arquivo já carregado não tem esse caso de uso — faz sentido
bloquear.

- `presentation/controllers.py`:
  - `RelatorioController.ja_persistido(self, arquivo_hash: str) -> bool`:
    wrapper fino sobre `self._contrato_repo.buscar_por_hash(arquivo_hash)`
    (`is not None`) — `False` se `contrato_repo is None` ou se
    `buscar_por_hash` lançar `RepositoryError` (degradação graciosa, mesmo
    princípio já usado em todo o resto do controller).
  - `AppController.processar_arquivos`: depois de obter `resultado` de
    `self.processamento.processar_arquivos(caminhos)`, filtrar
    `resultado.ingestao.documentos`/`resultado.contratos` (pareados 1:1,
    mesma ordem — mesmo princípio já usado em `_persistir`) removendo os
    itens cujo `documento.hash` já existe no banco
    (`self.relatorio.ja_persistido(hash)`); para cada um removido, adicionar
    um `ErroArquivo(nome_do_arquivo, "Contrato já carregado anteriormente
    (duplicado).")` ao resumo — reaproveita o mecanismo de exibição de
    erros por arquivo que a tela já tem (`_log_proc`, seção "Erros por
    arquivo:"), sem precisar de nenhum código novo de UI. Só os itens
    restantes (não duplicados) seguem para `definir_contratos`/persistência.

## Fora de escopo
- Mudar o comportamento de upsert do fluxo de pasta (continua reprocessando/
  atualizando registros existentes, como já era).
- Botão ou fluxo para "forçar" o carregamento de um duplicado mesmo com o
  aviso (não pedido; se o usuário quiser reprocessar de fato, pode excluir
  o registro existente no Painel e anexar de novo).
- Deduplicação por conteúdo similar/fuzzy — só hash exato, mesmo critério
  já usado em todo o resto do sistema.

## Fases
1. **Fix do Painel + duplicidade** (`presentation/controllers.py`), TDD
   estrito — delegado a `xp-coach`: testes cobrindo (a) `processar_pasta`
   e `processar_arquivos` preservando contratos já persistidos de chamadas
   anteriores depois de processar um novo lote (o teste de regressão para
   "somem da tela"); (b) `ja_persistido` (true/false/sem repo/erro de
   banco); (c) `processar_arquivos` pulando um arquivo cujo hash já está
   persistido, com o `ErroArquivo` correspondente no resumo, e SEM pular
   quando o hash é novo.
2. **Verificação pessoal** (PM): `pytest -q`, `ruff check src tests`,
   rebuild do `.exe`, smoke test real.

## Status
Plano criado — aguardando aprovação para iniciar a Fase 1.

## Status final

Fase 1 concluída (TDD): `RelatorioController.ja_persistido()` (degradação
graciosa) e `AppController.processar_pasta`/`processar_arquivos` recarregam
o histórico completo do banco após persistir o lote novo (mesmo padrão de
`excluir_contrato`). `processar_arquivos` também filtra duplicados por hash
já persistido, virando `ErroArquivo` de duplicidade em vez de regravar —
fluxo de pasta mantém o upsert original, sem mudança. 511 testes passando
(1 falha pré-existente e não relacionada, `test_ocr_real_tesseract`) e
`ruff check src tests` limpo, confirmados pessoalmente pelo PM.

## Fase 2 (verificação pessoal) concluída

`.exe` recompilado com sucesso. Validado com dados reais (arquivos de
`L:\SETOR FISCAL\CONTRATOS DE ALUGUEL`, via simulação fiel do `.exe`
real — `sys.frozen`/`sys.executable` monkey-patched chamando
`build_controller()` de produção, banco isolado em pasta temporária):
anexar um arquivo (1 linha) → anexar um segundo arquivo diferente (2
linhas — confirma que o primeiro não sumiu) → reanexar o primeiro arquivo
de novo (bloqueado como duplicado, Painel continua com 2 linhas).

**Plano concluído.**
