# ADR-003 — Redutor de IRRF 2026 (Lei nº 15.270/2025) sobre Aluguel

> **Data:** 2026-08-06 · **Status:** Aceito (§1, §2, §4-redutor) · **Revisado por [[adr-004-desconto-simplificado-aluguel|ADR-004]]** (§3 e a tabela de referência) · **Complementa:** ADR-001 (D5), tabela padrão da Lei nº 15.191/2025
>
> **⚠️ Nota de revisão (2026-08-07):** a conclusão do §3 abaixo — de que o desconto simplificado de R$607,20 não se aplica ao aluguel — **estava errada** (baseada em fonte secundária). O ADR-004 corrige isso com fonte primária (MAFON 2025, código 3208) e traz a tabela de referência atualizada. O redutor da Lei nº 15.270/2025 em si (fórmula, uso do rendimento bruto) continua válido e inalterado.

## 1. Contexto

O motor de IRRF (`domain/irrf.py`) já implementa a tabela progressiva mensal padrão 2026 (Lei nº 15.191/2025). A Lei nº 15.270/2025 (que inclui o Art. 3º-A na Lei nº 9.250/1995) criou, a partir de jan/2026, uma **redução adicional do imposto já calculado**, para reduzir a zero o IR de quem ganha até R$5.000,00 e reduzir progressivamente até R$7.350,00. Esse redutor existia no código apenas como stub desligado (`aplicar_redutor_15270`, não chamado por `calcular_irrf`).

## 2. Pesquisa e fonte primária

Texto literal obtido diretamente de `planalto.gov.br` (Art. 3º-A da Lei nº 9.250/1995, incluído pela Lei nº 15.270/2025):

> **Art. 3º-A.** A partir do mês de janeiro do ano-calendário de 2026, será concedida redução do imposto sobre os rendimentos tributáveis sujeitos à incidência mensal do Imposto sobre a Renda das Pessoas Físicas, de acordo com a seguinte tabela:
>
> | Rendimentos tributáveis sujeitos ao ajuste mensal | Redução do imposto de renda |
> |---|---|
> | até R$ 5.000,00 | até R$ 312,89 (de modo que o imposto devido seja zero) |
> | de R$ 5.000,01 até R$ 7.350,00 | R$ 978,62 − (0,133145 × rendimentos tributáveis sujeitos à incidência mensal) (decrescente até zerar em R$ 7.350,00) |
>
> **§1º** O valor da redução fica limitado ao valor do imposto determinado pela tabela progressiva mensal (nunca gera imposto negativo).
> **§2º** Rendimento mensal superior a R$ 7.350,00: sem redução.

Fonte: https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15270.htm

Confirmação cruzada com os **5 exemplos numéricos oficiais da RFB** (https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/exemplos-de-aplicacao-da-lei-15-270-2025), todos sobre **salário**.

## 3. A decisão — por que aluguel NÃO fica isento até R$5.000,00

Os exemplos oficiais da RFB deixam explícito que a redução usa o **rendimento bruto** para escolher a faixa/calcular a fórmula, mas o `imposto pela tabela padrão` continua sendo calculado sobre a **base de cálculo líquida** (bruto menos deduções). Para salário, o desconto simplificado (R$607,20, Lei nº 14.663/2023) sempre reduz essa base o suficiente para que o imposto-padrão fique ≤ R$312,89 — por isso "isenção até R$5.000" é sempre verdadeira para salário.

**Aluguel pago por PJ a PF não tem direito a esse desconto simplificado** (confirmado: ele é exclusivo da retenção sobre rendimento do trabalho assalariado). Sem ele, a base de cálculo do aluguel é o valor cheio, e o imposto-padrão em R$5.000,00 de aluguel é R$466,27 — **acima** do teto de redução de R$312,89. Resultado: sobra um resíduo de imposto devido.

| Aluguel mensal | Imposto pela tabela padrão | Redução aplicável (Art. 3º-A) | **Imposto final (retido)** |
|---|---|---|---|
| R$ 5.000,00 | R$466,27 | min(466,27; 312,89) = R$312,89 | **R$153,38** |
| R$ 5.000,01 | R$466,27 | min(466,27; 978,62−0,133145×5000,01) ≈ R$312,89 | **R$153,38** (sem descontinuidade) |
| R$ 6.000,00 | R$741,27 | 978,62−0,133145×6000 = R$179,75 | **R$561,52** |
| R$ 7.350,00 | R$1.112,52 | ≈ R$0,00 | **R$1.112,52** |
| > R$ 7.350,00 | tabela padrão | nenhuma | tabela padrão, sem redução (ex.: contratos reais BONI/SOHO, R$7.800,00 — resultado não muda) |

A continuidade da fórmula em R$5.000,00→R$5.000,01 (sem salto) é evidência adicional de que esta leitura mecânica está correta.

**Ressalva documentada:** não existe exemplo oficial da RFB específico para aluguel (só para salário), e há divergência entre contadores em fóruns profissionais especificamente sobre este ponto (ex.: https://www.contabeis.com.br/forum/tributos-federais/412153/). Diante disso, o usuário (PM/stakeholder, contexto de escritório de contabilidade) optou explicitamente por implementar esta leitura técnica/mecânica — decisão registrada aqui para não ser reaberta sem novo motivo concreto (ex.: uma Solução de Consulta Cosit específica sobre aluguel).

## 4. Decisão

- Ativar `aplicar_redutor_15270` com a fórmula acima, operando sobre o **imposto já calculado pela tabela padrão** (nunca sobre a base) — mantém a assinatura já prevista no stub.
- Redução = R$312,89 fixo para rendimento ≤ R$5.000,00; `978,62 − (0,133145 × rendimento)` para R$5.000,01–R$7.350,00; zero acima de R$7.350,00.
- `rendimento` = `base_mensal` (valor do aluguel) — não há dedução prévia equivalente ao desconto simplificado nesta modalidade.
- Redução nunca deixa o imposto negativo (`max(0, imposto_padrão − redução)`).
- **Fora de escopo (decisão explícita):** desconto simplificado de R$607,20 — não se aplica à retenção de aluguel PJ→PF, não será implementado.

## 5. Consequências

- **Positivo:** cálculo de IRRF sobre aluguel fica fiscalmente correto para 2026, alinhado à lei vigente e a exemplos oficiais da RFB (por analogia mecânica).
- **Risco aceito:** ausência de exemplo oficial específico de aluguel — documentado e aceito conscientemente pelo usuário (§3).
- **CA-03** (`.agent/specs/contract-parser-requirements.md` §7, base R$5.000,00) precisa ser atualizado: o resultado esperado deixa de ser "tabela progressiva padrão, sem redutor" e passa a ser **R$153,38** (com o redutor ativo).
