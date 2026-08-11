# Plano de Ação — Importação de Portfólio via .ods (LibreOffice Calc)

> **Data:** 2026-08-10 · **Status:** Pronto para Fase 1
> **Pedido do usuário:** na aba Empresas (cadastro de portfólio), permitir importar também arquivos `.ods` (OpenDocument Spreadsheet, formato nativo do LibreOffice Calc), além de `.xlsx`/`.csv` já suportados.

## 1. Estado atual (levantado antes de planejar)

`application/empresa_importer.py` já é desenhado para múltiplos formatos: `_ler_linhas(caminho)` despacha por extensão (`_ler_linhas_xlsx` via `openpyxl`, `_ler_linhas_csv` via `csv` da stdlib) para `list[list[object]]`; todo o resto do pipeline (`detectar_colunas` — auto-mapeamento de CNPJ/Razão Social por header ou por padrão de valor —, normalização, dedup, validação `Empresa`, persistência via `upsert_many`) já é **agnóstico de formato**. Adicionar `.ods` é, na essência, só mais um `_ler_linhas_<formato>`.

Pontos que hoje mencionam explicitamente só `.xlsx`/`.csv` e precisam mudar:
- `empresa_importer.py`: docstring do módulo, mensagem de erro de `_ler_linhas` ("Extensão não suportada... use .xlsx ou .csv").
- `presentation/views/main_window.py:128`: rótulo do botão `"Importar .xlsx/.csv…"`.
- `presentation/views/main_window.py:178`: filtro do diálogo de arquivo, `filetypes=[("Planilhas", "*.xlsx *.csv"), ("Todos", "*.*")]`.
- `.agent/specs/contract-parser-requirements.md` §CA-01 (menciona só `.xlsx`).
- `pyproject.toml`: nenhuma lib lê `.ods` hoje.

## 2. Decisão técnica (baixo impacto, decido e registro — sem ambiguidade fiscal/financeira)

**Biblioteca: `odfpy`** (não `pandas`+engine `odf`). Motivo: `pandas` seria uma dependência pesada nova só para ler uma planilha; `odfpy` é puro Python, sem extensão C, mesmo perfil de leveza que as libs já usadas neste projeto (`openpyxl`, `python-docx`) e compatível com o objetivo já validado de `.exe` 100% autossuficiente (embutir é trivial, é só bytecode Python — diferente do caso do Tesseract, que é um binário nativo).

`odfpy` exige parsing manual da estrutura de tabela (`odf.opendocument.load` + `odf.table.Table/TableRow/TableCell`), incluindo tratamento de `table:number-columns-repeated`/`table:number-rows-repeated` (o ODS comprime células/linhas repetidas vazias — se isso não for tratado, o desalinhamento de colunas quebra o auto-mapeamento). Este é o único ponto de atenção real da implementação.

## 3. Fases

### Fase 1 — Leitor `.ods` (`application/empresa_importer.py`)
- Adicionar `odfpy` a `pyproject.toml` (`dependencies`).
- Nova função `_ler_linhas_ods(caminho: Path) -> list[list[object]]`, mesma assinatura/contrato de `_ler_linhas_xlsx`/`_ler_linhas_csv` (lista de linhas cruas, primeira linha = header) — expandindo `number-columns-repeated`/`number-rows-repeated` para não desalinhar colunas, e convertendo o valor da célula para `str`/`float` conforme o tipo declarado (`office:value-type`), espelhando o que `openpyxl` já entrega hoje (célula numérica vira número, texto vira string).
- `_ler_linhas` passa a despachar `.ods` para essa função; mensagem de erro atualizada para `"use .xlsx, .csv ou .ods"`.
- Atualizar o docstring do módulo (linha 1: hoje diz "Importador em lote de empresas (.xlsx / .csv)").
- Envolver falhas de parsing em `ArquivoImportacaoError` (mesmo padrão dos outros dois leitores — nunca deixar uma exceção crua de `odfpy` vazar).
- **Agente sugerido:** `xp-coach` (TDD estrito).

### Fase 2 — Testes
- `tests/support/fixture_builders.py`: nova `construir_ods_50_empresas(caminho) -> Path` (espelhando `construir_xlsx_50_empresas`, usando `odfpy` para escrever), e pelo menos uma variante com header "sujo"/ordem invertida (espelhando `construir_xlsx_header_sujo`) para provar que o auto-mapeamento funciona igual independente do formato de origem.
- `tests/application/test_empresa_importer.py`: casos novos usando essas fixtures — happy path (50 empresas → 50 importadas, equivalente ao CA-01), header sujo/fallback por valor, e um `.ods` corrompido/inválido → `ArquivoImportacaoError`.
- Suíte completa + `ruff` (verificado por mim, PM, antes de commitar).
- **Ponto de atenção para o PM (Fase de empacotamento, fora desta rodada):** ao gerar o próximo `.exe`, confirmar que o PyInstaller inclui `odfpy` sem hook adicional — é puro Python, mas vale checar o log de build por qualquer `WARNING` relacionado (mesmo hábito já usado para outras libs).

### Fase 3 — GUI e documentação
- `main_window.py:128`: rótulo do botão vira `"Importar planilha…"` (ou `"Importar .xlsx/.csv/.ods…"` — decisão de UX menor, avaliar durante a implementação qual fica mais limpo no layout).
- `main_window.py:178`: filtro do diálogo vira `filetypes=[("Planilhas", "*.xlsx *.csv *.ods"), ("Todos", "*.*")]`.
- `.agent/specs/contract-parser-requirements.md` §CA-01: nota indicando que `.ods` também é suportado (mesmo comportamento/auto-mapeamento).
- README: se houver menção a formatos suportados na importação de portfólio, atualizar.

## 4. Critério de pronto
- Suíte verde + `ruff` limpo.
- Importar um `.ods` com 50 empresas produz o mesmo resultado (50 registros, mesmo dedup/validação) que o `.xlsx` equivalente já testado (CA-01).
- Botão/diálogo da GUI aceitam `.ods` visivelmente.
- `.exe` reconstruído e testado manualmente por você com uma planilha `.ods` real (ex.: exportada do LibreOffice Calc) antes de considerar a feature fechada.

## 5. Fora de escopo (a menos que peça)
- Suporte a `.ods` em qualquer outro fluxo do sistema (só a importação de portfólio de empresas foi pedida — não os relatórios exportados, que continuam Excel/PDF).
- Leitura de múltiplas planilhas/abas dentro do mesmo `.ods` (mesmo comportamento hoje do `.xlsx`: só a planilha ativa/primeira).
