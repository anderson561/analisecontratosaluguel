# Spec: Requisitos e Regras de Negócio — Leitor Inteligente de Contratos de Locação

> **Fase:** 0 — Fundação & Governança · **Base:** PRD v2.0 · **Data:** 2026-08-04
> **Enriquecido por:** skill `real-estate-contract-analyst` (Lei nº 8.245/91 + Código Civil)

## 1. Visão Geral e Objetivo do Negócio
Ler, interpretar e extrair dados críticos de contratos de locação em lote (PDF nativo/escaneado e DOCX), independentemente de layout, cruzando-os com um portfólio de empresas cadastradas, calculando o IRRF e emitindo relatórios com contratos processados e pendências. Beneficiários: Facilities, Financeiro e Imobiliário.

## 2. Atores e Permissões
- **Operador (usuário único da GUI):** importa empresas, seleciona pasta de contratos, dispara processamento, revalida tabela IRRF, exporta relatórios.
- **Sistema (engine headless):** OCR, extração NLP híbrida, cálculo IRRF, match de portfólio, persistência em SQLite local (arquivo embarcado — ver ADR-002).
- *Sem multiusuário/autenticação nesta versão (app desktop local).*

## 3. Campos de Extração (RF03) — refinados pelo domínio jurídico
Além dos campos do PRD, o especialista de Direito Imobiliário exige capturar:

| Grupo | Campo | Observação jurídica |
|-------|-------|---------------------|
| Partes | Locador (PF/PJ) · nome · CPF/CNPJ | Tipo PF/PJ define retenção de IRRF |
| Partes | Locatário (PF/PJ) · nome · CNPJ | Chave de match com portfólio |
| Objeto | **Tipo de locação: residencial × comercial** | Comercial habilita ação renovatória (Art. 51) |
| Financeiro | Valor base do aluguel | Base do IRRF |
| Financeiro | **Garantia locatícia (Art. 37): Caução × Fiança × Seguro-Fiança × Cessão Fiduciária** | ⚠️ Alertar se houver **mais de uma** modalidade (vedado) |
| Financeiro | **Multa rescisória total pactuada (Mt)** | Habilita cálculo proporcional Art. 4º |
| Vigência | Data de início · **data de fim** · prazo total (Tt em meses) | Necessário p/ multa proporcional |
| Vigência | **Dia de vencimento mensal** (distinto de fim de vigência) | Resolve ambiguidade do PRD (ver §4) |
| Reajuste | Índice (IPCA/IGP-M/INPC/…) | ⚠️ Alertar se atrelado a salário mínimo/moeda estrangeira (vedado, Art. 18) |
| Reajuste | Mês/data do próximo reajuste · periodicidade | ⚠️ Alertar se periodicidade < 12 meses (vedado, Art. 18) |
| Reajuste | Flag booleana **Reajuste Automático** (Sim/Não) | Conforme PRD |
| Risco | **Flags de cláusula abusiva** | Renúncia a benfeitorias necessárias (Arts. 35/36); cumulação de multas *bis in idem* |

## 4. Ambiguidades do PRD resolvidas
- **"Vencimento" (tabela do Relatório 01):** desmembrado em **`data_fim_vigencia`** (ex.: 10/2028) e **`dia_vencimento_mensal`** (dia do pagamento). O exemplo do PRD refere-se à vigência.
- **Chave de match (RF05, D4):** **CNPJ normalizado** (só dígitos) como chave primária; fallback *fuzzy* por Razão Social/aliases com score de confiança e faixa de revisão manual.
- **IRRF (RF04):** base = valor **mensal** do aluguel; tabela **progressiva mensal** da RFB; retenção apenas quando **Locador PF × Locatário PJ**; Locador PJ ⇒ R$ 0,00. Persistir **memória de cálculo** (faixa, alíquota, dedução, versão da tabela).
- **OCR (RF02):** idioma **por-BRA**; deduplicação por **hash** do arquivo/conteúdo.
- **Extração (RF03, D1):** **híbrida** — regras/regex para determinísticos (CNPJ, valores, datas), LLM só para cláusulas ambíguas.

## 5. Fluxo de Sucesso (Happy Path)
1. Dado que o operador importou o portfólio (RF01) e apontou uma pasta de contratos;
2. Quando dispara o processamento;
3. Então o sistema: extrai texto (OCR se necessário) → extrai campos (§3) → calcula IRRF → cruza com portfólio → gera Relatórios 01 e 02 e permite exportar PDF/Excel.

## 6. Fluxos de Exceção e Regras de Fronteira
- **PDF corrompido/ilegível:** registrar erro por arquivo, não abortar o lote.
- **OCR de baixa confiança:** marcar campos como "revisão manual".
- **CNPJ ausente/ilegível no contrato:** cair no match *fuzzy* por nome; se abaixo do score, status *Não Encontrado*.
- **Cláusula de reajuste inválida** (periodicidade < 12m ou índice vedado): extrair mesmo assim + **flag de alerta jurídico**.
- **Duas garantias no mesmo contrato:** extrair ambas + flag de violação do Art. 37.
- **Arquivo do banco SQLite inacessível:** falha explícita com orientação (verificar permissão/caminho de `DATABASE_PATH`; ver ADR-002 — não é mais um serviço externo).
- **Persistência ao mover/copiar o `.exe`:** o caminho padrão do banco SQLite é ancorado na pasta onde o executável está fisicamente salvo (`sys.executable`, quando empacotado via PyInstaller), não no diretório de trabalho (CWD) do processo no momento em que ele inicia. Isso garante que copiar a pasta inteira do `.exe` (incluindo a subpasta `data/`) para outro computador, ou iniciar o app por um atalho com "Iniciar em" diferente, preserva os dados já cadastrados/processados. `DATABASE_PATH` explícita (variável de ambiente) continua tendo prioridade sobre o cálculo padrão.
- **Tabela IRRF desatualizada/sem conexão à RFB:** usar última versão persistida + avisar data de validade.

## 7. Critérios de Aceitação (rastreamento ao PRD)
- [x] **CA-01** — Importar `.xlsx` com 50 empresas → 50 registros na tabela `empresas` (SQLite) + listagem na GUI. **Validado fim-a-fim com banco SQLite real** (migração ADR-002, M6). **Atualizado:** `.ods` (OpenDocument Spreadsheet, LibreOffice Calc) também é suportado — mesmo pipeline de leitura/auto-mapeamento de colunas (CNPJ/Razão Social) e mesma cobertura de teste de `.xlsx`/`.csv`, não é um formato de segunda classe.
- [ ] ~~**CA-02** — Docker~~ → **DEFERIDO** (Docker fora do escopo; ambiente local nativo).
- [ ] **CA-03** — Aluguel PF→PJ de R$ 5.000,00 → alíquota + dedução da tabela 2026 + memória de cálculo. **Atualizado (ADR-004):** o desconto simplificado de R$607,20 também se aplica ao aluguel (base tributável R$4.392,80), o que zera integralmente o imposto após o redutor da Lei nº 15.270/2025 — imposto final esperado passa a ser **R$ 0,00** (não mais R$ 153,38 do ADR-003, nem R$ 466,27 original).
- [ ] **CA-04** — Empresas A,B,C cadastradas; só A,B na pasta → status individual + alerta de ausência de C.
- [ ] **CA-05 (novo)** — Contrato com índice atrelado a salário mínimo → flag de cláusula vedada (Art. 18).
- [ ] **CA-06 (novo)** — Contrato com 2 garantias → flag de violação do Art. 37.

## 8. Referências Técnicas/Jurídicas
- [Lei nº 8.245/1991 (Lei do Inquilinato)](http://www.planalto.gov.br/ccivil_03/leis/l8245.htm) — *a validar na Fase 0*
- [Tabela IRRF RFB 2026](https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026) — *validar valores na Fase 5*
