# BRD — Documento de Requisitos de Negócio

| Campo | Valor |
|---|---|
| Documento | BRD — Business Requirements Document |
| Projeto | Leitor Inteligente de Contratos de Locação (AI Contract Parser) |
| Versão do produto | 0.2.0 |
| Versão do documento | 1.0 |
| Data | 2026-11-24 |
| Status | Rascunho para revisão |

**Documentos relacionados:** [FRD](FRD.md) · [SRS](SRS.md) · [TRD](TRD.md)

> **Convenção deste documento.** Ele descreve o produto **como ele está na versão 0.2.0**,
> conferido no código (`src/contract_parser/`) e nos testes (`tests/`). O que foi planejado
> e não está implementado aparece apenas nas seções 9 (Fora de escopo) e 11 (Limitações).
> IDs estáveis: `OBJ-xx` (objetivos), `NB-xx` (necessidades de negócio), `RN-xx` (regras de
> negócio). Os requisitos funcionais (`RF-xx`) que realizam cada NB/RN estão no [FRD](FRD.md).

---

## 1. Sumário executivo

O produto é uma aplicação desktop Windows, de uso individual e totalmente local, que lê
contratos de locação em lote (PDF nativo, PDF escaneado via OCR e DOCX), extrai os dados
críticos por regras determinísticas, calcula o IRRF sobre o aluguel conforme a legislação de
2026, cruza os contratos com um portfólio de empresas cadastrado e emite dois relatórios
(contratos e conformidade) exportáveis em PDF e Excel. É distribuída como um único
executável (`ContractParser.exe`) com o OCR Tesseract (idioma português) embutido.

## 2. Problema de negócio

| Dor | Situação sem o produto |
|---|---|
| Leitura manual de contratos | Cada contrato (às vezes escaneado) é lido a olho para achar partes, valor, vigência, reajuste e garantias. Layouts variam muito entre administradoras. |
| Retenção de IRRF | O cálculo da retenção sobre aluguel pago a locador pessoa física mudou em 2026 (nova tabela, desconto simplificado e redutor da Lei nº 15.270/2025). O cálculo manual é sujeito a erro e sem memória de cálculo auditável. |
| Controle de portfólio | Não há como saber, de forma sistemática, quais empresas do portfólio não têm contrato localizado. |
| Controle de reajustes | Muitos contratos não trazem a data do próximo reajuste por escrito; ela precisa ser deduzida da data de início. |
| Risco jurídico | Cláusulas vedadas pela Lei nº 8.245/91 (garantia dupla, índice atrelado a salário mínimo, reajuste com periodicidade inferior a 12 meses) passam despercebidas. |
| Sigilo dos dados | Contratos contêm dados pessoais (CPF, nomes, endereços). Enviá-los a serviços externos é um risco de LGPD. |

## 3. Objetivos de negócio

| ID | Objetivo | Como o produto atende (v0.2.0) |
|---|---|---|
| OBJ-01 | Reduzir o esforço de leitura e digitação de contratos de locação. | Ingestão em lote de pasta ou arquivos avulsos e extração automática de campos (NB-02, NB-03). |
| OBJ-02 | Calcular o IRRF sobre aluguel de forma correta e auditável para 2026. | Motor de IRRF com tabela 2026, desconto simplificado, redutor da Lei nº 15.270/2025 e memória de cálculo (NB-04). |
| OBJ-03 | Dar visibilidade sobre empresas do portfólio sem contrato localizado. | Match contrato × portfólio e lista de pendências (NB-05). |
| OBJ-04 | Antecipar o controle de reajustes contratuais. | Próximo reajuste extraído ou calculado, com recálculo sob demanda (NB-08). |
| OBJ-05 | Sinalizar riscos jurídicos previstos na Lei nº 8.245/91. | Flags jurídicas determinísticas calculadas e persistidas (NB-09). **Ver limitação L-03:** as flags ainda não aparecem na tela nem nos relatórios. |
| OBJ-06 | Manter todos os dados sob controle do usuário (LGPD). | Processamento 100% local, sem rede, sem LLM externo (NB-10). |
| OBJ-07 | Permitir uso sem instalação técnica. | Executável único com Tesseract embutido e banco SQLite em arquivo (NB-11). |

**Métricas de sucesso.** O projeto não tem KPIs de negócio medidos (tempo economizado, taxa
de acerto por campo em produção). Os critérios de sucesso verificáveis hoje são os critérios
de aceite CA-01 a CA-06 (seção 8), comprovados por testes automatizados.

## 4. Stakeholders e personas

| Papel | Descrição | Interesse principal |
|---|---|---|
| Operador (persona primária) | Profissional de escritório de contabilidade, Facilities, Financeiro ou área Imobiliária. Usuário único da GUI. | Processar contratos rapidamente, conferir campos marcados para revisão, exportar relatórios. |
| Contador / responsável fiscal | Consome o Relatório 01 (IRRF retido, redução aplicada). | Retenção correta, memória de cálculo e base legal rastreáveis. |
| Gestor de portfólio | Consome o Relatório 02 (conformidade). | Saber quais empresas estão sem contrato. |
| PM / stakeholder do produto | Decide escopo e interpretações fiscais. | Decisões fiscais registradas em ADR e não reabertas sem fato novo. |
| Mantenedor técnico | Evolui o código. | Arquitetura em camadas, testes, CI verde. |

Não existem perfis de acesso: a aplicação não tem login nem multiusuário (RN de escopo, seção 9).

## 5. Necessidades de negócio (NB)

| ID | Necessidade | Objetivo | RF no FRD |
|---|---|---|---|
| NB-01 | Cadastrar o portfólio de empresas por importação de planilha (`.xlsx`, `.csv`, `.ods`) e por cadastro manual. | OBJ-03 | RF-01 a RF-03 |
| NB-02 | Ingerir contratos em PDF (nativo ou escaneado) e DOCX, por pasta ou por arquivos escolhidos. | OBJ-01 | RF-04 a RF-08 |
| NB-03 | Extrair automaticamente os campos críticos do contrato, indicando a procedência e a confiança de cada um e marcando para revisão o que não for confiável. | OBJ-01 | RF-09 a RF-18 |
| NB-04 | Calcular o IRRF mensal sobre o aluguel com memória de cálculo auditável. | OBJ-02 | RF-20 |
| NB-05 | Cruzar contratos com o portfólio e listar empresas sem contrato. | OBJ-03 | RF-32, RF-33 |
| NB-06 | Consultar os contratos processados num painel persistente, com filtros. | OBJ-01 | RF-23 a RF-28 |
| NB-07 | Exportar os relatórios em PDF e Excel. | OBJ-02, OBJ-03 | RF-29 a RF-31 |
| NB-08 | Conhecer a data do próximo reajuste mesmo quando o contrato não a informa, e mantê-la atualizada. | OBJ-04 | RF-14, RF-21, RF-22 |
| NB-09 | Sinalizar cláusulas vedadas ou potencialmente abusivas. | OBJ-05 | RF-19 |
| NB-10 | Não enviar dados de contratos a terceiros. | OBJ-06 | RF-18; RNF-01 (SRS) |
| NB-11 | Distribuir a ferramenta sem exigir Python ou Tesseract na máquina do usuário. | OBJ-07 | RT-12 a RT-14 (TRD) |
| NB-12 | Não duplicar contratos já processados. | OBJ-01 | RF-05, RF-08 |
| NB-13 | Verificar se a máquina tem os pré-requisitos (modo desenvolvimento). | OBJ-07 | RF-34 |

## 6. Regras de negócio (RN)

### 6.1 Regras jurídicas — Lei nº 8.245/1991

| ID | Regra | Efeito no sistema | Evidência |
|---|---|---|---|
| RN-01 | **Art. 37, parágrafo único:** é vedada mais de uma modalidade de garantia no mesmo contrato (caução, fiança, seguro-fiança, cessão fiduciária). | Se mais de uma modalidade **distinta** for detectada, liga `violacao_art37_multiplas_garantias` e gera alerta. Modalidade repetida não conta. "Seguro-fiança" não conta como "fiança". | `domain/regras_juridicas.py`; `tests/domain/test_regras_juridicas.py`; `tests/domain/test_regras_extracao.py::test_garantia_seguro_fianca_nao_conta_como_fianca_pura` |
| RN-02 | **Arts. 17/18:** o reajuste não pode ser atrelado a salário mínimo nem a moeda estrangeira. | Índice "salário mínimo" ou "moeda estrangeira" é extraído mesmo assim e liga `indice_vedado_art18`. | `tests/domain/test_regras_juridicas.py::test_art18_indice_salario_minimo_vedado` |
| RN-03 | Periodicidade de reajuste inferior a 12 meses é vedada. O sistema rotula o alerta como "Art. 18"; a anualidade mínima também decorre da Lei nº 10.192/2001. | Periodicidade extraída < 12 liga `periodicidade_inferior_12m_art18`. | `test_art18_periodicidade_inferior_12m`, `test_art18_periodicidade_12m_ok` |
| RN-04 | **Arts. 35/36:** renúncia à indenização por benfeitorias necessárias é sinalizada como potencialmente abusiva. | Detecção por redação ("renuncia", "abre mão", "não terá direito"… próximo de "benfeitoria"). Alerta para conferência, sem juízo de nulidade. | `test_renuncia_benfeitorias_necessarias`, `test_renuncia_variante_abre_mao` |
| RN-05 | Cumulação de multas pelo mesmo fato (*bis in idem*) é sinalizada como potencialmente abusiva. | Detecção por redação ("cumulativa…multa", "multa compensatória … multa moratória/penal/rescisória"). | `test_cumulacao_multas_bis_in_idem` |
| RN-06 | "Vencimento" no Relatório 01 é a **data de fim da vigência**; o dia de pagamento mensal é outro campo (`dia_vencimento_mensal`). | Coluna "Vencimento" = `data_fim_vigencia`. | `domain/relatorio.py` (`LinhaContrato.vencimento`) |

### 6.2 Regras fiscais — IRRF sobre aluguel (2026)

| ID | Regra | Fonte | Evidência |
|---|---|---|---|
| RN-07 | Há retenção apenas em **Locador PF × Locatário PJ**. Locador PJ ⇒ IRRF = R$ 0,00, sem desconto nem redutor, qualquer que seja o locatário. Locador PF × Locatário PF ⇒ R$ 0,00 com a nota "o locador recolhe via carnê-leão". Locatário sem tipo identificado é tratado como PJ se casou com uma empresa do portfólio; caso contrário, o IRRF fica vazio e a linha vai para revisão (L-01 resolvida). | Requisitos §4; `domain/irrf.py`; `application/relatorio_service.py` | `tests/domain/test_irrf.py`; `tests/application/test_relatorio_service.py` |
| RN-08 | Tabela progressiva **mensal** 2026, versionada, com fonte e base legal (Lei nº 15.191/2025): isento até R$ 2.428,80; 7,5% (dedução R$ 182,16) até R$ 2.826,65; 15% (R$ 394,16) até R$ 3.751,05; 22,5% (R$ 675,49) até R$ 4.664,68; 27,5% (R$ 908,73) acima. Limite superior inclusivo. | `tabela_irrf_2026()` | `test_calculo_por_faixa`, `test_fronteira_entre_faixas_seleciona_por_teto` |
| RN-09 | **Desconto simplificado** de R$ 607,20 (Lei nº 14.663/2023, art. 6º), incondicional, abatido do aluguel bruto de locador PF **antes** de localizar a faixa. Base tributável nunca negativa. | ADR-004 (MAFON 2025, código 3208) | `test_ca03_registra_memoria_de_calculo` |
| RN-10 | **Redutor da Lei nº 15.270/2025** (Art. 3º-A da Lei nº 9.250/1995), calculado sobre o rendimento **bruto** (sem o desconto): até R$ 5.000,00 → R$ 312,89; de R$ 5.000,01 a R$ 7.350,00 → R$ 978,62 − 0,133145 × rendimento; acima de R$ 7.350,00 → zero. Aplicado sobre o imposto da tabela; o imposto final nunca é negativo. | ADR-003 (fórmula) + ADR-004 (ordem) | `test_calcular_reducao_lei_15270_por_faixa`, `test_ca03_reducao_lei_15270_valores_de_referencia`, `test_reducao_nunca_deixa_imposto_negativo` |
| RN-11 | Valores monetários em `Decimal`; arredondamento a 2 casas com `ROUND_HALF_UP`. | `domain/irrf.py` | `test_arredondamento_half_up` |
| RN-12 | Toda retenção registra **memória de cálculo**: rendimento bruto, desconto aplicado, base tributável, faixa, alíquota, dedução, imposto antes da redução, redução aplicada, imposto final, vigência da tabela, base legal e URL da fonte. | ADR-001 D5; ADR-003/004 | `test_ca03_registra_memoria_de_calculo` |
| RN-13 | Com mais de um locador, **só o locador principal** entra no IRRF; os demais são identificados e exibidos. | `plano-multiplos-locadores.md` | `tests/application/test_relatorio_service.py::test_relatorio01_linha_leva_locadores_adicionais_do_contrato` |
| RN-14 | Sem valor de aluguel ou sem tipo PF/PJ do locador, o IRRF não é calculado e a linha vai para revisão (nunca quebra o lote). | Requisitos §6 | `test_contrato_sem_valor_de_aluguel_nao_calcula_irrf`, `test_contrato_sem_tipo_de_locador_vai_para_revisao` |

Valores de referência vigentes (locador PF), conferidos por teste:

| Aluguel bruto | Base tributável | Imposto pela tabela | Redução | Imposto final |
|---|---|---|---|---|
| R$ 500,00 | R$ 0,00 | R$ 0,00 | — | **R$ 0,00** |
| R$ 1.000,00 | R$ 392,80 | R$ 0,00 | — | **R$ 0,00** |
| R$ 5.000,00 (CA-03) | R$ 4.392,80 | R$ 312,89 | R$ 312,89 | **R$ 0,00** |
| R$ 6.000,00 | R$ 5.392,80 | R$ 574,29 | R$ 179,75 | **R$ 394,54** |
| R$ 7.350,00 | R$ 6.742,80 | R$ 945,54 | R$ 0,00 | **R$ 945,54** |
| R$ 7.800,00 | R$ 7.192,80 | R$ 1.069,29 | R$ 0,00 | **R$ 1.069,29** |

### 6.3 Regras de portfólio, reajuste e operação

| ID | Regra | Evidência |
|---|---|---|
| RN-15 | A chave de match é o **CNPJ normalizado** (14 dígitos, sem máscara). Os dígitos verificadores **não** são exigidos (tolerância a bases legadas e OCR). | `domain/cnpj.py`; `tests/domain/test_cnpj.py` |
| RN-16 | Sem CNPJ utilizável no locatário (ausente, CPF, ilegível) ou sem CNPJ cadastrado, aplica-se **match aproximado** do nome do locatário contra razão social, aliases e nomes fantasia; aceito se score ≥ limiar (padrão 85, configurável). Empate: vence a primeira empresa na ordem do portfólio. | `domain/match_portfolio.py`; `tests/domain/test_match_portfolio.py` |
| RN-17 | Empresa cadastrada sem nenhum contrato correspondente gera pendência com a mensagem exata: `Contrato da Empresa <Razão Social> / <CNPJ> não encontrado`. | `test_mensagem_pendencia_formato_exato` |
| RN-18 | A data do próximo reajuste **lida do contrato sempre prevalece** e nunca é sobrescrita. Só quando ausente ela é **calculada**: data de início + k × periodicidade (periodicidade extraída ou 12 meses), primeira data ≥ hoje. A data calculada fica marcada para revisão. | `domain/reajuste_calc.py`; `test_data_explicita_do_texto_prevalece_sobre_o_calculo` |
| RN-19 | Carência é registrada em meses. Carência expressa em dias vai para revisão manual, **sem conversão**. Ausência da cláusula é o caso normal e não gera revisão. | `test_carencia_mencionada_sem_valor_em_meses_dispara_revisao`, `test_carencia_sem_mencao_e_caso_normal_confiante` |
| RN-20 | Arquivos idênticos (mesmo SHA-256 do conteúdo) são processados uma vez só. Reprocessar uma pasta atualiza o registro existente; anexar arquivo avulso já persistido é bloqueado como duplicado. | `test_deduplica_por_hash`, `test_reprocessar_mesmo_hash_atualiza_em_vez_de_duplicar`, `test_app_processar_arquivos_bloqueia_duplicado_e_nao_persiste_de_novo` |
| RN-21 | Falha em um arquivo (corrompido, OCR falhou) ou em uma linha de planilha (CNPJ inválido) é registrada e **não aborta o lote**. | `test_erro_de_extracao_nao_aborta_lote`, `test_importar_csv_com_erros_e_duplicados` |
| RN-22 | Campo ambíguo ou de baixa confiança vai para **revisão manual**; o sistema não "chuta" valores. Nenhum dado é enviado a LLM externo. | `test_ambiguo_sem_interpretador_marca_revisao_sem_quebrar` |
| RN-23 | Exclusão de contratos do histórico é permanente e exige confirmação explícita do operador. | `views/main_window.py` (`_on_excluir_contrato`, `_on_limpar_tudo`) |

## 7. Escopo

### 7.1 Dentro do escopo (entregue na v0.2.0)

- Gestão de empresas: importação `.xlsx`/`.csv`/`.ods` com tela de confirmação de mapeamento, progresso e cancelamento; cadastro, edição e remoção manual.
- Ingestão de contratos: pasta inteira ou arquivos avulsos; PDF nativo, PDF escaneado (OCR Tesseract `por`) e DOCX.
- Extração determinística: partes (locador, locadores adicionais, locatário), tipo de locação, valor do aluguel, multa rescisória, garantias, vigência (início, fim, prazo, dia de vencimento, carência), reajuste (índice, fonte do índice, periodicidade, próximo reajuste, automático), despesas e responsável, prorrogação.
- Flags jurídicas (RN-01 a RN-05), calculadas e persistidas.
- IRRF 2026 com desconto simplificado, redutor e memória de cálculo.
- Próximo reajuste calculado e botão "Atualizar Próx. Reajuste".
- Match de portfólio e pendências.
- Painel persistente (SQLite local) com filtros, indicador de revisão e motivo, exclusão.
- Relatórios 01 e 02 exportáveis em Excel e PDF.
- Executável Windows único com Tesseract embutido; CI no GitHub Actions.

### 7.2 Fora do escopo — ver seção 9.

## 8. Critérios de sucesso (aceite de negócio)

| ID | Critério | Situação v0.2.0 | Evidência |
|---|---|---|---|
| CA-01 | Importar `.xlsx` com 50 empresas resulta em 50 registros e listagem na GUI. | Atendido (também para `.ods`). | `tests/application/test_empresa_importer.py::test_ca01_importar_50_empresas`, `::test_ca01_importar_ods_50_empresas` |
| CA-02 | Ambiente via Docker. | **Deferido** por decisão (ADR-001 D2). | — |
| CA-03 | Aluguel PF→PJ de R$ 5.000,00 → faixa, alíquota, dedução da tabela 2026 e memória de cálculo. | Atendido. **Resultado vigente: R$ 0,00** (ver nota). | `tests/domain/test_irrf.py::test_ca03_base_5000_pf_para_pj`, `tests/application/test_relatorio_service.py::test_ca03_irrf_pf_pj_base_5000` |
| CA-04 | Empresas A, B, C cadastradas e só A, B na pasta → status e alerta de ausência de C. | Atendido no serviço; na GUI e nos relatórios aparecem totais e pendências (ver L-04). | `tests/application/test_portfolio_validation_service.py::test_ca04_empresa_sem_contrato_vira_pendencia_com_mensagem_exata` |
| CA-05 | Índice atrelado a salário mínimo → flag Art. 18. | Atendido no domínio (fixture sintética; ver L-03). | `tests/domain/test_regras_juridicas.py::test_art18_indice_salario_minimo_vedado` |
| CA-06 | Duas garantias → flag Art. 37. | Atendido no domínio (fixture sintética; ver L-03). | `tests/application/test_extracao_fixtures_matriz.py` |

> **Nota sobre o CA-03.** O valor esperado mudou duas vezes por decisão fiscal registrada:
> R$ 466,27 (só tabela, checklist original) → R$ 153,38 (ADR-003, redutor ativo) →
> **R$ 0,00** (ADR-004, desconto simplificado + redutor). O código e os testes refletem o
> último valor.

## 9. Fora de escopo / Backlog (decisões deliberadas)

| Item | Motivo / registro |
|---|---|
| Docker / `docker-compose` (CA-02) | ADR-001 D2. App e banco rodam nativos no Windows. |
| Provedor de LLM para cláusulas ambíguas | Adiado por LGPD. Existe apenas o ponto de extensão (`InterpretadorClausula`) e um stub que se recusa a operar. Em produção nenhum interpretador é injetado. |
| Revalidação online da tabela IRRF na RFB | Interface `AtualizadorTabelaRFB` e stub sem rede existem; não há botão nem fluxo na GUI. |
| Multiusuário, autenticação, perfis | App desktop de usuário único. |
| IRRF considerando vários locadores | `plano-multiplos-locadores.md`. |
| Cálculo de multa rescisória proporcional (Art. 4º) | O valor total pactuado (Mt) e o prazo são extraídos; o cálculo proporcional não existe. |
| Conversão de carência em dias para meses | Decisão de arredondamento não tomada. |
| Edição manual de um contrato já processado | Só leitura, exclusão e recálculo do próximo reajuste. |
| Ordenação por coluna no Painel; múltiplos locadores em redação narrativa | YAGNI registrado nos planos. |
| Paginação do Painel; rotação do log de auditoria | YAGNI registrado nos planos. |

## 10. Premissas e restrições

**Premissas**
- P-01: Um único operador usa a aplicação numa estação Windows; não há acesso concorrente de várias pessoas ao mesmo banco.
- P-02: Os contratos estão em português do Brasil e usam o vocabulário jurídico usual ("LOCADOR", "LOCATÁRIO", "aluguel", "prazo", "reajuste").
- P-03: O tipo PF/PJ de cada parte é deduzido do documento (CPF → PF, CNPJ → PJ) ou, sem documento, de termos societários no nome (LTDA, S/A, EIRELI…).
- P-04: O operador confere os campos marcados para revisão antes de usar os relatórios para decisões fiscais.
- P-05: As interpretações fiscais adotadas (ADR-003 e ADR-004) foram decididas pelo stakeholder e não são reabertas sem fato novo, como uma Solução de Consulta específica sobre aluguel.

**Restrições**
- R-01: Dados de contratos não saem da máquina (LGPD). Contratos reais nunca entram no repositório (`.gitignore` ignora `*.pdf`, `*.docx`, `*.xlsx`, `*.csv` e `data/`, exceto fixtures sintéticas em `tests/fixtures/`).
- R-02: Plataforma alvo Windows; Python ≥ 3.11 para quem roda a partir do código.
- R-03: Somente o idioma português é embutido no OCR.
- R-04: A tabela IRRF vigente está codificada no domínio (`tabela_irrf_2026()`); uma nova vigência exige nova versão do produto (ver L-02).

## 11. Riscos e limitações conhecidas

| ID | Risco / limitação | Impacto | Mitigação atual |
|---|---|---|---|
| L-01 | ✅ **Resolvida (2026-11-24).** O IRRF considerava só o tipo do **locador**, e um contrato PF→PF saía com imposto "retido". | — | O tipo do locatário passou a ser considerado (ver RN-07). O Painel e as exportações recalculam o IRRF ao carregar, então contratos já processados se corrigem sem reprocessar; a cópia salva em `linha_json` é só um registro do momento do processamento. |
| L-02 | A tabela IRRF de produção vem da factory `tabela_irrf_2026()`. O repositório `tabela_irrf` existe, mas não está ligado ao fluxo, e não há aviso de validade da tabela. | Mudança de tabela exige nova versão. | Tabela versionada com fonte e base legal na memória de cálculo. |
| L-03 | Flags jurídicas, tipo de locação, garantias, multa, data de início e dia de vencimento são extraídos e persistidos, mas **não aparecem no Painel nem nas exportações**. O alerta fica visível só indiretamente, quando o campo vai para revisão. | OBJ-05 é atendido apenas parcialmente para o usuário final. | Dados disponíveis no banco (`contratos.contrato_json`). Candidato a evolução. |
| L-04 | O status de cada empresa (encontrada por CNPJ ou fuzzy, score) é calculado no serviço, mas a GUI e os relatórios mostram só totais e pendências. Empresas inativas (`ativo = Não`) também geram pendência. | Menos detalhe na conformidade. | Mensagem exata de pendência por empresa. |
| L-05 | O sinal de **OCR de baixa confiança** (média < 60) é calculado na extração de texto, mas não é propagado para a revisão do contrato. | Contrato escaneado ruim pode não ser destacado. | Campos que a regra não consegue ler já vão para revisão. |
| L-06 | Extração por regras depende do vocabulário; layouts inéditos podem gerar campos ausentes ou nomes truncados (especialmente PJ em redação narrativa). | Mais revisões manuais. | Memória de extração e motivo da revisão no tooltip. |
| L-07 | Com 2+ locadores, só o principal entra no IRRF (RN-13). | Retenção calculada sobre um único beneficiário. | Locadores adicionais exibidos. |
| L-08 | Interpretação fiscal sem exemplo oficial da RFB específico para aluguel (ADR-003 §3). | Risco de divergência com outras leituras contábeis. | Decisão registrada (ADR-003/004); memória de cálculo completa. |
| L-09 | O processamento de contratos roda na thread da interface: lotes grandes deixam a janela ocupada até terminar. | Experiência de uso em lotes grandes. | Barra de progresso indeterminada; a importação de empresas já roda em thread separada. |

## 12. Referências

- Lei nº 8.245/1991 (Lei do Inquilinato) — Arts. 17, 18, 35, 36, 37.
- Lei nº 15.191/2025 (tabela progressiva 2026); Lei nº 15.270/2025 (Art. 3º-A da Lei nº 9.250/1995); Lei nº 14.663/2023, art. 6º; MAFON 2025, código 3208.
- ADR-001 (stack e arquitetura), ADR-002 (MongoDB → SQLite), ADR-003 (redutor IRRF 2026), ADR-004 (desconto simplificado no aluguel). Os ADRs e planos ficam no repositório de specs do projeto (`~/.claude/specs/`), fora da árvore versionada; antes ficavam em `.agent/specs/`.
- `README.md`, `CHANGELOG.md` (versão 0.2.0 de 2026-10-06).
