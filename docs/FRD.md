# FRD — Documento de Requisitos Funcionais

| Campo | Valor |
|---|---|
| Documento | FRD — Functional Requirements Document |
| Projeto | Leitor Inteligente de Contratos de Locação (AI Contract Parser) |
| Versão do produto | 0.2.0 |
| Versão do documento | 1.0 |
| Data | 2026-11-24 |
| Status | Rascunho para revisão |

**Documentos relacionados:** [BRD](BRD.md) · [SRS](SRS.md) · [TRD](TRD.md)

> Este documento descreve o comportamento funcional **implementado na v0.2.0**. Cada
> requisito `RF-xx` remete às necessidades (`NB-xx`) e regras (`RN-xx`) do [BRD](BRD.md)
> e aos testes que o comprovam. Exemplos usam somente dados fictícios (FULANO DE TAL,
> CPF 111.111.111-11, CNPJ 11.111.111/0001-11).

---

## 1. Visão geral dos módulos

| Módulo | RFs | Camadas envolvidas |
|---|---|---|
| M1 — Empresas / Portfólio | RF-01 a RF-03 | `application/empresa_importer.py`, `empresa_service.py`; `presentation` (aba Empresas + diálogo de importação) |
| M2 — Ingestão & OCR | RF-04 a RF-08 | `application/document_ingestor.py`; `infrastructure/text_extractors.py` |
| M3 — Extração | RF-09 a RF-18 | `domain/regras_extracao.py`, `parsing_ptbr.py`; `application/contract_extraction_service.py` |
| M4 — Regras jurídicas | RF-19 | `domain/regras_juridicas.py` |
| M5 — IRRF | RF-20 | `domain/irrf.py`; `application/relatorio_service.py` |
| M6 — Próximo reajuste | RF-21, RF-22 | `domain/reajuste_calc.py`; `contract_extraction_service.py`; `presentation/controllers.py` |
| M7 — Painel / GUI | RF-23 a RF-28 | `presentation/controllers.py`, `views/main_window.py`; `infrastructure/contrato_repository.py` |
| M8 — Relatórios / Exportação | RF-29 a RF-31 | `domain/relatorio.py`; `infrastructure/report_exporters.py` |
| M9 — Conformidade | RF-32, RF-33 | `domain/match_portfolio.py`; `application/portfolio_validation_service.py` |
| M10 — Ambiente | RF-34 | `infrastructure/environment_check.py` |

## 2. Telas e ações

Janela principal: título "AI Contract Parser — Leitor de Contratos de Locação", 1180×760,
banner de status do banco no topo e quatro abas.

| Tela / aba | Elementos | Ações | RF |
|---|---|---|---|
| Banner de status | Texto de estado do banco SQLite | Mostra OK ou falha com orientação (nunca derruba a janela) | RF-27 |
| **Empresas** | Botão "Importar .xlsx/.csv/.ods…"; campos "CNPJ" e "Razão Social"; botões "Adicionar", "Salvar edição", "Remover"; tabela "Portfólio cadastrado" (CNPJ, Razão Social, Ativo, Origem) | Importar planilha, cadastrar, editar razão social, remover (com confirmação) | RF-01 a RF-03 |
| Diálogo "Confirmar importação de empresas" | Seletor "Aba:" (só `.ods`), "Linha de header:", prévia das primeiras linhas, combos "Coluna de CNPJ:" e "Coluna de Razão Social:", barra de progresso; botões "Cancelar" e "Confirmar importação" | Ajustar aba, linha de cabeçalho e mapeamento antes de importar; acompanhar progresso; cancelar | RF-01 |
| **Carregar Contratos** | Botões "Selecionar pasta e processar…" e "Selecionar arquivo(s) e processar…"; contadores (Arquivos, Processados, Duplicados, Erros); log com erros por arquivo; barra de progresso indeterminada | Processar pasta ou arquivos avulsos | RF-04 a RF-08 |
| **Painel de Contratos** | Filtros "Índice:", "Só reajuste automático", busca "Buscar (locatário/locador)…"; botões "Filtrar", "Limpar", "Atualizar Próx. Reajuste", "Limpar tudo", "Excluir selecionado"; tabela "Relatório 01 — Contratos processados" (15 colunas); tooltip na coluna "Revisão" | Filtrar, recalcular reajustes, excluir um ou vários contratos, excluir todos | RF-22 a RF-28 |
| **Conformidade** | Botões "Exportar Excel…" e "Exportar PDF…"; cartões de totais (Empresas cadastradas, Contratos localizados, Empresas com contrato, Pendências); lista "Pendências — contratos não encontrados" | Ver conformidade; exportar relatórios | RF-30, RF-31, RF-33 |
| CLI `contract-parser-envcheck` | Relatório PASS/FAIL em texto | Verificar pré-requisitos (modo desenvolvimento) | RF-34 |

---

## 3. Requisitos funcionais

### M1 — Empresas / Portfólio

#### RF-01 — Importar portfólio de empresas por planilha
- **Descrição:** importa empresas de `.xlsx`, `.csv` ou `.ods`, com confirmação prévia do mapeamento.
- **Entradas:** arquivo escolhido; aba (só `.ods`), linha de cabeçalho e colunas CNPJ/Razão Social sugeridas pelo sistema e ajustáveis pelo operador.
- **Processamento:**
  1. `inspecionar()` sugere a aba com mais linhas úteis, detecta a linha de cabeçalho (pula títulos mesclados) e mapeia as colunas.
  2. Mapeamento automático por cabeçalho: CNPJ = cabeçalho contendo "cnpj"; Razão Social = "razao", "social", "empresa" ou "nome" (sem acento).
  3. Fallback por valor: coluna em que ≥ 60% das células viram 14 dígitos é o CNPJ; a coluna textual restante é a Razão Social.
  4. Cada linha: normaliza o CNPJ (RN-15), valida a razão social, deduplica por CNPJ dentro do arquivo.
  5. Persistência em lote por `upsert_many` (idempotente por CNPJ); `origem_import` = nome do arquivo.
  6. Roda numa thread de trabalho, com progresso determinado (linha a linha) e cancelamento cooperativo.
- **Saídas:** resumo com total de linhas, importados, duplicados e erros por linha (número 1-based e motivo).
- **Regras:** RN-15, RN-21. `.csv` detecta o delimitador (`,`, `;` ou tab). `.ods` expande células repetidas e ignora a cauda vazia; conteúdo real repetido acima de 5.000 vezes é rejeitado.
- **Exceções:** arquivo inexistente, extensão não suportada, planilha corrompida ou sem colunas identificáveis → mensagem "Não foi possível importar o arquivo: …". Aba ≠ 0 em `.xlsx`/`.csv` → erro. Banco inacessível → mensagem padrão de banco. Linha com CNPJ inválido ou razão vazia → erro de linha, o lote continua. Cancelar → para no início da próxima linha e grava o que já foi processado.
- **Critérios de aceite:**
  - Dado um `.xlsx` com 50 empresas válidas e distintas, quando o operador confirma a importação, então 50 empresas são gravadas e listadas (CA-01).
  - Dado um `.csv` com uma linha de CNPJ inválido e uma linha repetida, quando importado, então o resumo informa 1 erro e 1 duplicado e as demais linhas são gravadas.
  - Dado um `.ods` com título mesclado antes do cabeçalho, quando inspecionado, então a linha de cabeçalho real é sugerida e o título nunca vira dado.
  - Dado um arquivo já importado, quando importado de novo, então nenhuma empresa é duplicada.

#### RF-02 — Cadastrar, editar e remover empresa manualmente
- **Entradas:** CNPJ (com ou sem máscara), razão social; para edição, o CNPJ identifica a empresa.
- **Processamento:** validação pelo modelo `Empresa` (CNPJ com 14 dígitos, razão social não vazia); `origem_import = "manual"`. A remoção pede confirmação ("Remover a empresa <CNPJ>?").
- **Saídas:** tabela do portfólio atualizada.
- **Exceções:** CNPJ duplicado → mensagem do repositório; CNPJ ou razão inválidos → "Dados inválidos: …" em texto amigável; editar CNPJ inexistente → "Empresa não encontrada"; remover inexistente → "Nenhuma empresa com esse CNPJ."
- **Critérios de aceite:**
  - Dado o CNPJ "11.111.111/0001-11" e a razão "FULANO DE TAL LTDA", quando o operador clica "Adicionar", então a empresa aparece com CNPJ `11111111000111`.
  - Dado um CNPJ com 13 dígitos, quando o operador tenta adicionar, então é exibido "Dados inválidos" e nada é gravado.

#### RF-03 — Listar o portfólio
- **Processamento:** lista todas as empresas ordenadas por razão social (sem diferenciar maiúsculas), com Ativo = "Sim"/"Não" e a origem. Mostra estado vazio quando não há empresas.
- **Critério de aceite:** Dado um portfólio com "BETA" e "alfa", quando a aba é exibida, então "alfa" aparece antes de "BETA".

### M2 — Ingestão & OCR

#### RF-04 — Processar uma pasta de contratos
- **Entradas:** diretório escolhido.
- **Processamento:** lista os arquivos `.pdf` e `.docx` **do próprio diretório** (sem subpastas), em ordem alfabética sem diferenciar maiúsculas; extrai o texto de cada um (RF-06/RF-07), deduplica por hash (RF-08), extrai os campos (M3), persiste cada contrato por *upsert* de hash (reprocessar atualiza o registro e preserva o `id`) e recarrega o Painel com o histórico completo.
- **Saídas:** contadores Arquivos, Processados, Duplicados, Erros; log com "Contratos extraídos: N" e "⚠ <arquivo>: <motivo>".
- **Exceções:** caminho inexistente ou que não é pasta → "Pasta inválida: …". Falha de gravação de um item não derruba o Painel (o item fica sem `id`).
- **Critérios de aceite:**
  - Dada uma pasta com 1 PDF, 1 DOCX e 1 `.txt`, quando processada, então 2 arquivos são considerados e o `.txt` é ignorado.
  - Dados contratos processados num lote anterior, quando um novo lote é processado, então o Painel mostra os dois lotes.

#### RF-05 — Processar arquivos escolhidos individualmente
- **Entradas:** um ou mais caminhos de arquivo.
- **Processamento:** cada caminho é validado (existe, é arquivo, extensão suportada); os válidos seguem o fluxo do RF-04. **Diferença deliberada:** arquivo cujo hash já está persistido **não é regravado**; vira erro "Contrato já carregado anteriormente (duplicado)."
- **Critérios de aceite:**
  - Dado um arquivo já processado antes, quando anexado de novo, então ele aparece nos erros como duplicado e o histórico não muda.
  - Dado um caminho inexistente e um PDF válido, quando processados juntos, então o inexistente vira "Arquivo não encontrado." e o PDF é processado.

#### RF-06 — Extrair texto de PDF (nativo com fallback OCR)
- **Processamento:** lê a camada de texto nativa (PyMuPDF). Com 20 caracteres ou mais, usa esse texto (`metodo = "nativo"`). Abaixo disso, assume PDF escaneado: renderiza as páginas a 300 DPI e aplica o Tesseract no idioma `por` (`metodo = "ocr"`). Média de confiança do OCR < 60 marca `baixa_confianca` no documento.
- **Resolução do Tesseract:** `TESSERACT_CMD` configurado tem prioridade; senão, no `.exe`, usa o binário embutido; senão, o `PATH` do sistema.
- **Exceções:** PDF corrompido → erro "Falha ao abrir/ler PDF: …"; falha do OCR → "Falha no OCR: …". Nenhuma das duas aborta o lote.
- **Limitação:** `baixa_confianca` não é propagada para a revisão do contrato (BRD L-05).
- **Critérios de aceite:**
  - Dado um PDF com texto nativo, quando extraído, então o OCR não é acionado.
  - Dado um PDF sem camada de texto, quando extraído, então o OCR é acionado e o método registrado é "ocr".
  - Dado um PDF corrompido, quando extraído, então retorna erro estruturado sem exceção.

#### RF-07 — Extrair texto de DOCX
- **Processamento:** concatena os parágrafos não vazios e, depois, cada linha de tabela como células unidas por " | " (quadros de partes costumam estar em tabelas).
- **Critério de aceite:** Dado um DOCX com o valor do aluguel numa tabela, quando extraído, então o texto da tabela está presente.

#### RF-08 — Deduplicar e isolar falhas por arquivo
- **Processamento:** hash SHA-256 do conteúdo binário; dois arquivos com o mesmo conteúdo, mesmo com nomes diferentes, contam como 1 processado + 1 duplicado. Exceção inesperada de um backend vira "Erro inesperado na extração: …".
- **Regras:** RN-20, RN-21.
- **Critério de aceite:** Dadas duas cópias idênticas com nomes distintos, quando processadas, então `processados = 1` e `duplicados = 1`.

### M3 — Extração de campos

Princípios comuns a M3 (detalhados no [TRD](TRD.md)):
- cada extrator devolve `ResultadoCampo(valor, confianca, origem, detalhe)`;
- confiança ALTA = 0,9, MÉDIA = 0,7, BAIXA = 0,45; **limiar de revisão = 0,6**;
- um campo vai para revisão quando a origem é `NAO_ENCONTRADO` ou quando a confiança é < 0,6;
- nenhum extrator lança exceção por texto ausente.

#### RF-09 — Identificar as partes
- **Processamento:**
  - **Locador / Locatário:** primeiro o quadro rotulado ("LOCADOR:", "LOCADORA (A/S) –", "LOCATÁRIO(A):", com variações de gênero, plural e acento, e separador `:`, `-` ou `–`). O bloco termina em linha em branco, no rótulo oposto ou em "CLÁUSULA", "PARÁGRAFO", "PARTES CONTRATANTES" ou "OBJETO". Fallback: redação narrativa ("…como LOCADORA, aqui denominada, <NOME>, inscrita no CNPJ…"), com confiança máxima MÉDIA.
  - **Nome:** texto até o primeiro marcador de qualificação (vírgula, "brasileiro", "portador", "inscrito", "CPF", "CNPJ", "residente", "com sede"). Linhas de assinatura ("LOCADOR: ____") não contam como nome.
  - **Tipo PF/PJ:** CPF → PF; CNPJ → PJ; sem documento, termo societário no nome (LTDA, S/A, EIRELI, ME, EPP…) → PJ.
  - **Confiança:** nome e documento = ALTA; só um dos dois = MÉDIA.
  - **Locadores adicionais:** todos os demais blocos "LOCADOR:" rotulados, deduplicados por documento ou, na falta dele, por nome normalizado, excluindo o principal. Nenhum adicional é o caso normal (lista vazia, confiança ALTA).
- **Saídas:** `locador`, `locadores_adicionais`, `locatario` (tipo, nome, documento só com dígitos).
- **Exceções:** rótulo ausente → `NAO_ENCONTRADO` ("rótulo LOCADOR não encontrado") → revisão.
- **Critérios de aceite:**
  - Dado "LOCADOR: FULANO DE TAL, brasileiro, CPF 111.111.111-11", quando extraído, então locador = PF, nome "FULANO DE TAL", documento `11111111111`, confiança 0,9.
  - Dados dois blocos "LOCADOR:" separados por linha em branco, sem "LOCATÁRIO" entre eles, quando extraídos, então o segundo aparece em `locadores_adicionais` e o contrato não é marcado para revisão por isso.
  - Dado "LOCADOR: ________", quando extraído, então o bloco não é aceito como nome.

#### RF-10 — Classificar o tipo de locação
- **Processamento:** o título ("CONTRATO DE LOCAÇÃO RESIDENCIAL", "… PARA FINS COMERCIAIS", "NÃO RESIDENCIAL") tem prioridade (ALTA). Senão, olha o corpo: só termos residenciais ("residencial", "para moradia") → residencial; só comerciais ("comercial", "não residencial", "escritório", "atividade empresarial") → comercial. Ambos ou nenhum → ambíguo.
- **Ambiguidade:** consulta o interpretador de cláusulas (RF-18); em produção não há interpretador, e o campo vai para revisão.
- **Critério de aceite:** Dado um contrato intitulado "LOCAÇÃO RESIDENCIAL" cujo corpo menciona "sala comercial", quando extraído, então tipo = residencial.

#### RF-11 — Extrair valor do aluguel e multa rescisória
- **Valor do aluguel:** âncora "aluguel", "preço mensal (da locação)" ou "valor mensal (da locação)" seguida, na mesma linha e em até 60 caracteres, de "R$ <valor>". Convertido de pt-BR para `Decimal`. Confiança ALTA.
- **Multa rescisória total (Mt):** "multa … R$ <valor>" → ALTA; ou "multa … N aluguéis" → N × valor do aluguel (MÉDIA). Sem valor do aluguel, a multa em aluguéis não é monetizada e vai para revisão.
- **Critérios de aceite:**
  - Dado "o aluguel mensal importa em R$ 6.000,00", quando extraído, então valor = 6000.00.
  - Dado "multa equivalente a 3 (três) aluguéis" e aluguel de R$ 2.000,00, quando extraído, então multa = 6000.00 com confiança 0,7.

#### RF-12 — Detectar as garantias locatícias
- **Processamento:** detecta seguro-fiança, caução, cessão fiduciária e fiança/fiador. A fiança "pura" é verificada **depois** de remover "seguro-fiança" do texto, para não contar em dobro.
- **Saídas:** lista de modalidades (pode ter mais de uma; alimenta RN-01).
- **Critério de aceite:** Dado um texto que só menciona "seguro-fiança", quando extraído, então garantias = [seguro_fianca], sem fiança.

#### RF-13 — Extrair a vigência
- **Início / fim:** padrão de período "de <data> a/até <data>" (inclui "iniciando-se em … até …") → ALTA; âncora isolada ("início…", "término/fim/encerramento…") → MÉDIA. Datas aceitas: numéricas, `mm/aaaa` e por extenso.
- **Prazo (meses), em cascata:** (1) "prazo … N meses" → ALTA; (2) "prazo … <por extenso> meses" → MÉDIA; (3) "prazo … N anos" → N×12, ALTA; (4) "prazo … <por extenso> anos" → ×12, MÉDIA; (5) "N meses" sem âncora → BAIXA (pode ser a periodicidade) → revisão.
- **Dia de vencimento mensal:** "vencimento/pagamento … dia N", "todo dia N", "dia N de cada mês"; fora de 1–31 → revisão.
- **Carência:** "carência … N meses" → ALTA; "carência" citada sem meses → revisão; sem menção → `None` sem revisão (RN-19).
- **Critérios de aceite:**
  - Dado "pelo prazo de 05 (cinco) anos", quando extraído, então prazo = 60 meses.
  - Dado "iniciando-se em 01/03/2025", quando extraído, então início = 2025-03-01.
  - Dado "carência de 15 dias", quando extraído, então carência = vazio e o campo vai para revisão.

#### RF-14 — Extrair o reajuste
- **Índice:** IGP-M, IPCA, INPC, IGP-DI, INCC (ALTA); "salário mínimo" ou "moeda estrangeira" (dólar, USD, variação cambial, euro) são capturados como índice vedado.
- **Fonte do índice:** "/FGV", "/IBGE", "/FIPE" ou "/BACEN" logo após a menção do índice (janela de 15 caracteres), em campo separado (não fragmenta o filtro). Ausência de fonte é normal e não gera revisão.
- **Periodicidade:** "a cada N meses", "periodicidade de N meses", "anual/anualmente" (12), "semestral" (6).
- **Automático:** "reajuste … automático", "automaticamente", "independentemente de aviso/notificação" → Sim (ALTA). Sem menção → Não, com confiança BAIXA (revisão: não mencionado ≠ explicitamente não).
- **Próximo reajuste:** "próximo reajuste / primeiro reajuste / reajuste em <data>" → data ISO, MÉDIA. Ausente → RF-21.
- **Critério de aceite:** Dado "reajustado anualmente pelo IGP-M/FGV", quando extraído, então índice = "IGP-M", fonte = "FGV", periodicidade = 12.

#### RF-15 — Extrair as despesas e o responsável
- **Processamento:** detecta IPTU, condomínio ordinário, condomínio extraordinário, seguro-incêndio e taxa de administração. O responsável é o rótulo LOCADOR ou LOCATÁRIO mais próximo (até 100 caracteres para cada lado), medido a partir da palavra-âncora. Empate exato ou nenhum rótulo → responsável indefinido.
- **Saídas:** mapa tipo → responsável (ou indefinido). Nenhuma despesa → revisão.
- **Critério de aceite:** Dado "o IPTU será pago pelo LOCATÁRIO", quando extraído, então IPTU → locatário.

#### RF-16 — Extrair a prorrogação
- **Processamento:** "prorrog…/renova… automática", "automaticamente prorrogado" ou "prazo indeterminado" → automática = Sim. Prazo da prorrogação só quando explícito junto à âncora ("prorrogado por N meses"); **nunca** é inferido do prazo original. Sem menção → Não, com confiança BAIXA (revisão).
- **Critério de aceite:** Dado "prorrogado automaticamente por igual período", quando extraído, então automática = Sim e prazo = vazio.

#### RF-17 — Registrar a memória de extração e a necessidade de revisão
- **Processamento:** para cada campo lógico (`locador`, `locadores_adicionais`, `locatario`, `valor_aluguel`, `multa_rescisoria_total`, `garantias`, `data_inicio_vigencia`, `data_fim_vigencia`, `prazo_meses`, `carencia_meses`, `dia_vencimento_mensal`, `reajuste_indice`, `reajuste_indice_fonte`, `reajuste_periodicidade`, `reajuste_proximo`, `reajuste_automatico`, `prorrogacao_automatica`, `prorrogacao_prazo_meses`, `despesas`, `tipo_locacao`, `flags_juridicas`) grava origem, confiança, necessidade de revisão e detalhe. O contrato precisa de revisão se **qualquer** campo precisar.
- **Critério de aceite:** Dado um texto vazio, quando extraído, então o contrato é devolvido sem exceção e os campos obrigatórios estão marcados para revisão.

#### RF-18 — Interpretador de cláusulas ambíguas (desligado, fail-secure)
- **Processamento:** só para `tipo_locacao` ambíguo, envia ao interpretador **apenas um recorte de até 400 caracteres** em torno de "destina", "finalidade", "objeto" ou "imóvel" (minimização LGPD). Em produção **nenhum interpretador é injetado**; o stub `StubInterpretadorLLM` lança `NotImplementedError` se for usado, e o campo cai em revisão.
- **Critérios de aceite:**
  - Dado um tipo ambíguo e nenhum interpretador, quando extraído, então tipo = vazio com detalhe "ambíguo e sem interpretador de LLM".
  - Dado o stub de produção, quando acionado, então a extração não quebra e o campo vai para revisão.

### M4 — Regras jurídicas

#### RF-19 — Calcular as flags jurídicas
- **Processamento:** a partir das garantias, do reajuste e do texto, calcula de forma determinística `violacao_art37_multiplas_garantias`, `indice_vedado_art18`, `periodicidade_inferior_12m_art18`, `renuncia_benfeitorias_necessarias`, `cumulacao_multas_bis_in_idem` e uma lista de alertas legíveis (ex.: "Art. 37: vedada a cumulação de garantias — 2 modalidades detectadas (caucao, fianca).").
- **Regras:** RN-01 a RN-05.
- **Saídas:** `Contrato.flags`, persistidas no histórico.
- **Limitação:** as flags não são exibidas no Painel nem nas exportações (BRD L-03).
- **Critérios de aceite:**
  - Dado um contrato com caução e fiador, quando avaliado, então a flag do Art. 37 é ligada (CA-06).
  - Dado o índice "salário mínimo", quando avaliado, então a flag do Art. 18 é ligada (CA-05).
  - Dada a periodicidade de 12 meses, quando avaliado, então nenhum alerta de periodicidade é gerado.

### M5 — IRRF

#### RF-20 — Calcular o IRRF com memória de cálculo
- **Entradas:** valor mensal do aluguel, tipo do locador principal, tipo do locatário (ou, se ausente, o resultado do casamento com o portfólio), tabela vigente (factory 2026).
- **Processamento:**
  - locador PJ ⇒ imposto R$ 0,00, base preservada, observação "não aplicável (locador PJ)", qualquer que seja o locatário;
  - locador PF × locatário PF ⇒ imposto R$ 0,00, observação "não aplicável (locatário PF)" com a nota de carnê-leão do locador;
  - locatário sem tipo ⇒ tratado como PJ se casou com uma empresa do portfólio (CNPJ ou nome); senão, IRRF não calculado e linha em revisão;
  - locador PF ⇒ base tributável = máx(0; bruto − 607,20); faixa pela base tributável; imposto da tabela = base × alíquota − dedução (mínimo 0); redução = redutor(bruto); imposto final = máx(0; tabela − redução), arredondado com HALF_UP.
- **Saídas:** `ResultadoIRRF` com `retido`, `imposto`, `base_calculo` (tributável), `aliquota`, `deducao`, `faixa_descricao`, `tabela_vigencia`, `base_legal`, `fonte_url`, `observacao`, `imposto_antes_reducao`, `reducao_aplicada`, `rendimento_bruto` e `desconto_simplificado_aplicado`.
- **Regras:** RN-07 a RN-14.
- **Exceções:** base negativa → `ValueError`; valor ou tipo do locador ausentes → IRRF não calculado e linha em revisão.
- **Critérios de aceite:**
  - Dado um aluguel de R$ 6.000,00 de locador PF para locatário PF, quando calculado, então imposto = 0,00 e a observação cita o carnê-leão (L-01).
  - Dado um locatário sem tipo que não casou com o portfólio e locador PF, quando calculado, então o IRRF fica vazio e a linha vai para revisão.
  - Dado um aluguel de R$ 5.000,00 de locador PF, quando calculado, então base tributável = 4.392,80, alíquota 22,5%, dedução 675,49, imposto antes da redução = 312,89, redução = 312,89 e imposto = 0,00 (CA-03).
  - Dado um aluguel de R$ 6.000,00 de locador PF, quando calculado, então imposto = 394,54.
  - Dado um locador PJ, quando calculado, então imposto = 0,00 e desconto simplificado = 0,00.

### M6 — Próximo reajuste

#### RF-21 — Calcular o próximo reajuste na extração
- **Processamento:** se o texto não traz data **e** há data de início **e** há relógio injetado (a GUI injeta `date.today`), calcula `calcular_proximo_reajuste_anual(início, periodicidade ou 12, hoje)`: a menor data início + k × periodicidade (k ≥ 1) que seja ≥ hoje, sempre somando a partir do início original e ajustando ao último dia do mês quando necessário (31/jan + 1 mês = 28 ou 29/fev). Origem `REGRA_CALCULADA`, confiança BAIXA (revisão), com detalhe "calculado a partir da data de início (dd/mm/aaaa), assumindo reajuste a cada N meses".
- **Regras:** RN-18.
- **Critérios de aceite:**
  - Dado início 15/03/2024, sem data de próximo reajuste no texto e hoje 2026-01-10, quando extraído, então próximo reajuste = 2026-03-15 com origem calculada.
  - Dada uma data explícita no texto, quando extraído, então ela é usada e o cálculo não acontece.
  - Sem relógio injetado, quando extraído, então o campo fica ausente (extração puramente determinística).

#### RF-22 — Botão "Atualizar Próx. Reajuste"
- **Processamento:** para cada contrato do Painel com origem `REGRA_CALCULADA`, data de início e `id` persistido, recalcula com a data de hoje e grava **apenas** o próximo reajuste (o resto do registro, inclusive a origem, fica intacto). Datas lidas do contrato nunca mudam. O Painel é recarregado sempre, mesmo se o banco falhar no meio.
- **Saídas:** "Nenhum contrato precisou de atualização: …", "1 contrato atualizado." ou "N contratos atualizados."
- **Critérios de aceite:**
  - Dado um contrato com data calculada vencida, quando o botão é acionado, então a nova data é gravada e o contador é 1.
  - Acionado o botão duas vezes seguidas, a segunda devolve 0.
  - Dado um contrato com data extraída do texto, quando o botão é acionado, então ela não muda.

### M7 — Painel / GUI

#### RF-23 — Painel persistente de contratos
- **Processamento:** ao abrir, o Painel carrega todo o histórico do banco (mais recentes primeiro). O IRRF de cada linha é **recalculado** a partir do contrato salvo, com a tabela vigente. Linhas sem locatário, sem locador **e** sem valor são ocultadas do Painel, mas continuam no relatório exportado e na conformidade.
- **Colunas (15):** Locatário, Locador, Locador(es) Adicional(is), Valor, IRRF, Redução IRRF, Índice, Fonte do Índice, Próx. Reajuste, Auto?, Vencimento, Carência, Despesas, Prorrogação, Revisão. Formatação pt-BR (R$ 1.234,56; dd/mm/aaaa; "N meses"; "IPTU → locatário").
- **Critério de aceite:** Dado um banco com contratos salvos, quando o app é aberto, então o Painel já mostra esses contratos sem reprocessar.

#### RF-24 — Filtros do Painel
- **Processamento:** índice (igualdade sem diferenciar maiúsculas; a lista é montada com os índices presentes); "Só reajuste automático"; texto livre (substring sem diferenciar maiúsculas em locatário, locador, índice e CNPJ do locatário). Os filtros se combinam (E). "Limpar" restaura.
- **Critério de aceite:** Dados contratos IPCA e IGP-M, quando filtrado por "IPCA", então só as linhas IPCA aparecem.

#### RF-25 — Indicador e motivo de revisão
- **Processamento:** Revisão = dados incompletos para o IRRF **ou** algum campo com revisão. O tooltip explica: "dados incompletos para o IRRF (…)" e/ou "campo(s) extraído(s) com baixa confiança: <lista>".
- **Critério de aceite:** Dada uma linha sem valor de aluguel e com `reajuste_automatico` de baixa confiança, quando o mouse passa na coluna Revisão, então os dois motivos aparecem.

#### RF-26 — Excluir contratos
- **Processamento:** "Excluir selecionado" (um ou vários) e "Limpar tudo" pedem confirmação ("Esta ação não pode ser desfeita"), excluem do banco e recarregam o Painel.
- **Exceções:** id inexistente → "Contrato não encontrado (já pode ter sido removido)."; nada selecionado → aviso.
- **Critério de aceite:** Dado um contrato selecionado, quando excluído e confirmado, então ele some do Painel e do banco.

#### RF-27 — Banner de status do banco
- **Processamento:** executa `SELECT 1`; o resultado vai para o banner. Nunca lança exceção.
- **Critério de aceite:** Dado o banco inacessível, quando a janela abre, então ela abre normalmente e o banner mostra a falha com orientação.

#### RF-28 — Recarga do histórico após toda escrita
- **Processamento:** processar pasta, processar arquivos, excluir, limpar tudo e atualizar reajustes terminam com `carregar_historico()`. Falha ao listar ou desserializar → o Painel abre vazio e o evento é gravado em `app.log`.
- **Critério de aceite:** Dado um lote novo processado, quando concluído, então os lotes anteriores continuam visíveis.

### M8 — Relatórios / Exportação

#### RF-29 — Montar o Relatório 01 (contratos)
- **Processamento:** uma linha por contrato com locatário, CNPJ, locador, valor, IRRF retido, redução IRRF, índice, fonte, próximo reajuste, automático, vencimento (fim da vigência), carência, despesas, prorrogação e locadores adicionais; totais de IRRF retido e de redução; vigência da tabela aplicada.
- **Critério de aceite:** Dados N contratos, quando montado, então há N linhas na ordem de entrada e o total de IRRF é a soma das linhas.

#### RF-30 — Exportar para Excel
- **Saídas:** `.xlsx` com a aba "Contratos" (15 cabeçalhos em negrito, linhas e rodapé "TOTAL" nas colunas IRRF Retido e Redução IRRF) e a aba "Conformidade" (título, 4 totais e lista de pendências ou "Nenhuma pendência."). Cria a pasta de destino se não existir.
- **Exceções:** nada processado → "Nada para exportar: …"; erro de gravação → "Falha ao gravar o arquivo de saída: …".
- **Critério de aceite:** Dado o relatório exportado, quando o `.xlsx` é relido, então as pendências e os valores estão presentes.

#### RF-31 — Exportar para PDF
- **Saídas:** PDF A4 paisagem, título "Relatório de Contratos de Locação", seção "Relatório 01 — Contratos processados (IRRF tabela 2026)" com tabela de 15 colunas de **largura fixa somando 785 pt** (área útil) e cabeçalho repetido por página, seguida do bloco de conformidade.
- **Critério de aceite:** Dado um relatório com 15 colunas preenchidas, quando exportado, então nenhuma coluna é descartada e o texto esperado está no PDF.

### M9 — Conformidade

#### RF-32 — Cruzar contratos com o portfólio
- **Processamento:** para cada contrato, match por CNPJ normalizado do locatário (score 100); senão, fuzzy (`rapidfuzz.token_sort_ratio` com normalização) do nome do locatário contra razão social, aliases e nomes fantasia; aceito se score ≥ limiar (`FUZZY_MATCH_THRESHOLD`, padrão 85, inclusivo). Status por empresa: ENCONTRADO ou NAO_ENCONTRADO; havendo vários matches, CNPJ vence fuzzy e depois o maior score; conta os contratos correspondentes. Contratos sem empresa ficam listados à parte (diagnóstico).
- **Regras:** RN-15 a RN-17.
- **Critérios de aceite:**
  - Dado o locatário com CNPJ "11.111.111/0001-11" e a empresa cadastrada `11111111000111`, quando cruzado, então ENCONTRADO por CNPJ, score 100.
  - Dado o locatário PF (CPF), quando cruzado, então o sistema tenta o fuzzy pelo nome.
  - Dado o score exatamente igual ao limiar, quando cruzado, então é considerado ENCONTRADO.

#### RF-33 — Relatório 02 e aba Conformidade
- **Saídas:** Empresas cadastradas, Contratos localizados, Empresas com contrato, Pendências e a lista de pendências com a mensagem exata (RN-17), na ordem do portfólio.
- **Limitação:** o status por empresa (método e score) não é exibido (BRD L-04).
- **Critério de aceite:** Dadas as empresas A, B, C e contratos só de A e B, quando a conformidade é exibida, então há 1 pendência: "Contrato da Empresa C / <CNPJ de C> não encontrado" (CA-04).

### M10 — Ambiente

#### RF-34 — Verificação de ambiente (CLI)
- **Processamento:** três checagens: Python ≥ 3.11; banco SQLite criável e gravável no caminho configurado (abre e inicializa o schema); Tesseract presente (via `TESSERACT_CMD` ou `PATH`) com o idioma `por`. Cada falha traz a ação sugerida. Não instala nada.
- **Saídas:** relatório PASS/FAIL; código de saída 0 (tudo OK) ou 1.
- **Escopo:** console-script do modo desenvolvimento; não faz parte do `.exe`.
- **Critério de aceite:** Dado o Tesseract sem o idioma `por`, quando executado, então o relatório mostra FAIL com orientação e o código de saída é 1.

---

## 4. Matriz de rastreabilidade RF → NB/RN → evidência

| RF | NB | RN | Testes (evidência) |
|---|---|---|---|
| RF-01 | NB-01 | RN-15, RN-21 | `tests/application/test_empresa_importer.py`; `tests/presentation/test_dialogo_importacao_empresas.py`; `tests/presentation/test_controllers.py::test_importar_planilha_*` |
| RF-02 | NB-01 | RN-15 | `tests/application/test_empresa_service.py`; `test_controllers.py::test_crud_empresa_completo`, `::test_adicionar_com_cnpj_invalido_vira_controller_error` |
| RF-03 | NB-01 | — | `test_controllers.py::test_linhas_empresas_ordenadas_por_razao_social` |
| RF-04 | NB-02 | RN-20, RN-21 | `tests/application/test_document_ingestor.py`; `test_controllers.py::test_app_processar_pasta_*` |
| RF-05 | NB-02, NB-12 | RN-20 | `test_document_ingestor.py::test_ingerir_arquivos_*`; `test_controllers.py::test_app_processar_arquivos_bloqueia_duplicado_e_nao_persiste_de_novo` |
| RF-06 | NB-02 | RN-21 | `tests/infrastructure/test_text_extractors.py` (roteamento nativo→OCR, Tesseract embutido; OCR real marcado `integration`) |
| RF-07 | NB-02 | — | `test_text_extractors.py::test_docx_*` |
| RF-08 | NB-12 | RN-20, RN-21 | `test_document_ingestor.py::test_deduplica_por_hash`, `::test_erro_de_extracao_nao_aborta_lote` |
| RF-09 | NB-03 | RN-13 | `tests/domain/test_regras_extracao.py::test_extrair_*parte*`, `::test_locadores_adicionais_*`; `tests/application/test_extracao_reais_anonimizadas.py` |
| RF-10 | NB-03 | RN-22 | `test_regras_extracao.py::test_tipo_locacao_*` |
| RF-11 | NB-03 | — | `test_regras_extracao.py::test_*valor_aluguel*`, `::test_multa_*` |
| RF-12 | NB-03, NB-09 | RN-01 | `test_regras_extracao.py::test_garantia_*` |
| RF-13 | NB-03 | RN-06, RN-19 | `test_regras_extracao.py::test_periodo_*`, `::test_prazo_*`, `::test_dia_vencimento*`, `::test_carencia_*`, `::test_inicio_por_verbo_iniciando_se` |
| RF-14 | NB-03, NB-08 | RN-02, RN-03 | `test_regras_extracao.py::test_indice_*`, `::test_periodicidade_meses`, `::test_reajuste_automatico_*` |
| RF-15 | NB-03 | — | `test_regras_extracao.py::test_despesa_*` |
| RF-16 | NB-03 | — | `test_regras_extracao.py::test_prorrogacao_*` |
| RF-17 | NB-03 | RN-22 | `tests/application/test_contract_extraction_service.py::test_toda_extracao_registra_proveniencia_por_campo`, `::test_extrair_texto_vazio_nao_quebra`; `tests/application/test_extracao_fixtures_matriz.py` |
| RF-18 | NB-10 | RN-22 | `test_contract_extraction_service.py::test_llm_*`, `::test_stub_llm_*`, `::test_ambiguo_sem_interpretador_marca_revisao_sem_quebrar` |
| RF-19 | NB-09 | RN-01 a RN-05 | `tests/domain/test_regras_juridicas.py`; `test_extracao_fixtures_matriz.py` |
| RF-20 | NB-04 | RN-07 a RN-14 | `tests/domain/test_irrf.py`; `tests/application/test_relatorio_service.py` |
| RF-21 | NB-08 | RN-18 | `tests/domain/test_reajuste_calc.py`; `test_contract_extraction_service.py::test_proximo_reajuste_*`, `::test_calculo_*`, `::test_sem_relogio_injetado_o_calculo_fica_desligado` |
| RF-22 | NB-08 | RN-18 | `test_controllers.py::test_atualizar_proximos_reajustes_*`; `tests/infrastructure/test_contrato_repository.py::test_atualizar_proximo_reajuste_*` |
| RF-23 | NB-06 | RN-06 | `test_controllers.py::test_linhas_painel_*`, `::test_app_controller_nasce_com_painel_populado_pelo_historico`; `test_contrato_repository.py::test_roundtrip_*` |
| RF-24 | NB-06 | — | `test_controllers.py::test_filtrar_*`, `::test_indices_disponiveis_ordenados` |
| RF-25 | NB-03, NB-06 | RN-14, RN-22 | `test_controllers.py::test_motivo_revisao_*`, `::test_linha_incompleta_marca_revisao` |
| RF-26 | NB-06 | RN-23 | `test_controllers.py::test_excluir_*`; `test_contrato_repository.py::test_excluir_*` |
| RF-27 | NB-06 | — | `test_controllers.py::test_status_conexao_*`; `tests/infrastructure/test_database.py::test_check_health_*` |
| RF-28 | NB-06 | — | `test_controllers.py::test_carregar_historico_*`, `::test_app_processar_*_preserva_contratos_de_lotes_anteriores`; `tests/infrastructure/test_audit_log.py` |
| RF-29 | NB-07 | RN-12 | `test_relatorio_service.py::test_relatorio01_*`, `::test_total_*`; `tests/domain/test_relatorio.py` |
| RF-30 | NB-07 | — | `tests/infrastructure/test_report_exporters.py::test_excel_*`; `tests/presentation/test_pipeline_integracao_cross_fase.py::test_pipeline_completo_exportacao_excel_sobrevive_a_releitura` |
| RF-31 | NB-07 | — | `test_report_exporters.py::test_pdf_*`; `test_pipeline_integracao_cross_fase.py::test_pipeline_completo_exportacao_pdf_nao_quebra` |
| RF-32 | NB-05 | RN-15, RN-16 | `tests/domain/test_match_portfolio.py`; `tests/application/test_portfolio_validation_service.py` |
| RF-33 | NB-05 | RN-17 | `test_portfolio_validation_service.py::test_ca04_*`; `test_relatorio_service.py::test_relatorio02_*`; `test_controllers.py::test_resumo_conformidade_pendencia_mensagem_exata` |
| RF-34 | NB-13 | — | `tests/infrastructure/test_environment_check.py` |

As views CustomTkinter (`views/*.py`) têm apenas *smoke tests* de importação
(`tests/presentation/test_view_smoke.py`) e testes das funções puras do diálogo; o
comportamento visual foi validado manualmente e não é coberto por teste automatizado.
