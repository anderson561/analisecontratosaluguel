# ADR-004 — Desconto Simplificado (R$607,20) também se aplica ao Aluguel PF→PJ

> **Data:** 2026-08-07 · **Status:** Aceito · **Revisa:** ADR-003 §3 e §4 (mantém o restante do ADR-003 válido — redutor da Lei nº 15.270/2025 continua em vigor e usando o rendimento bruto)

## 1. Contexto

O ADR-003 concluiu, com base em fontes secundárias (fóruns de contadores), que o desconto simplificado de R$607,20 (Lei nº 14.663/2023, art. 6º, alterando o art. 4º §2º da Lei nº 9.250/1995) é "exclusivo da retenção sobre rendimento do trabalho assalariado" e por isso **não** foi aplicado ao cálculo de IRRF sobre aluguel (`domain/irrf.py`, commits `bb5491e`/`2bc3caa`).

O usuário pediu, em 2026-08-07, um plano para usar obrigatoriamente o desconto de R$607,20 quando o aluguel ultrapassasse R$7.350,00. Uma pesquisa focada (fonte primária: **MAFON 2025 — Manual do Imposto de Renda Retido na Fonte, da própria Receita Federal**, seção do código de retenção **3208 "Aluguéis, Royalties e Juros Pagos a Pessoa Física"**) encontrou que:

- **A premissa do ADR-003 §3 estava errada**: o desconto simplificado de R$607,20 **é sim aplicável** à base de cálculo do IRRF sobre aluguel pago a pessoa física (código 3208), como alternativa às deduções detalhadas (dependentes, pensão, etc.) — exatamente como para salário.
- **O gatilho ">R$7.350,00" proposto pelo usuário não tem base legal.** O desconto é incondicional em valor (aplicável a qualquer rendimento, inclusive abaixo de R$5.000,00) — R$7.350,00 é o teto do redutor da Lei nº 15.270/2025 (mecanismo diferente, já implementado), não uma condição do desconto simplificado.

## 2. Decisão

1. **Revisar o ADR-003 §3/§4**: o desconto simplificado de R$607,20 passa a ser aplicado **incondicionalmente** (não há dado de dependentes/deduções detalhadas por contrato no sistema, e o desconto simplificado é sempre mais benéfico que não aplicar nenhuma dedução) sobre a base de cálculo do aluguel, sempre que `tipo_locador is PF` — mesmo gate já usado para a retenção em si.
2. **Ordem de aplicação dos dois mecanismos** (compõem, não substituem um ao outro):
   - `base_tributavel = max(R$0,00; base_mensal_aluguel − R$607,20)` → usada para localizar a faixa da tabela progressiva e calcular o imposto pela tabela padrão.
   - O redutor da Lei nº 15.270/2025 (`calcular_reducao_lei_15270`, ADR-003) **continua** a ser calculado sobre o **rendimento bruto** (`base_mensal_aluguel`, sem o desconto) — não muda, já validado no ADR-003 contra os exemplos oficiais da RFB.
   - `imposto_final = max(R$0,00; imposto_tabela(base_tributavel) − reducao(base_bruta))`.
3. **Nova tabela de referência** (substitui a tabela do ADR-003 §3):

| Aluguel mensal | Base tributável (após −R$607,20) | Imposto pela tabela | Redução (Lei 15.270, s/ bruto) | **Imposto final** |
|---|---|---|---|---|
| R$ 500,00 / R$ 1.000,00 | R$0,00 / R$392,80 | R$0,00 (faixa isenta) | — | **R$0,00** (sem mudança) |
| R$ 5.000,00 | R$4.392,80 | R$312,89 | R$312,89 | **R$0,00** (era R$153,38) |
| R$ 6.000,00 | R$5.392,80 | R$574,29 | R$179,75 | **R$394,54** (era R$561,52) |
| R$ 7.350,00 | R$6.742,80 | R$945,54 | ≈R$0,00 | **R$945,54** (era R$1.112,52) |
| R$ 7.800,00 (BONI/SOHO, reais) | R$7.192,80 | R$1.069,29 | R$0,00 (>7.350 bruto) | **R$1.069,29** (era R$1.236,27) |

Todos os 4 valores conferidos à mão antes de codificar (regra estabelecida em [[projeto-contract-parser]] — "Rigor em cálculo fiscal/legal").

## 3. Consequências

- **Reduz** o IRRF retido sobre aluguel de locador PF em praticamente todos os casos (inclusive nos 2 contratos reais já processados, BONI/SOHO: R$1.236,27 → R$1.069,29/mês).
- `ResultadoIRRF` ganha 2 campos novos para manter a memória de cálculo auditável: `rendimento_bruto` (valor cheio do aluguel, usado no redutor) e `desconto_simplificado_aplicado` (R$607,20 quando PF, R$0,00 quando PJ). O campo já existente `base_calculo` passa a representar a **base tributável** (após o desconto) — é o valor que efetivamente localiza a faixa/calcula o imposto pela tabela, mais fiel ao nome do campo.
- **CA-03** (`.agent/specs/contract-parser-requirements.md` §7, base R$5.000,00) muda de R$153,38 (ADR-003) para **R$0,00**.
- ADR-003 permanece válido quanto ao redutor da Lei nº 15.270/2025 em si (fórmula, uso do rendimento bruto, teto R$7.350) — só a interpretação de "aluguel não tem desconto simplificado" (§3) e a tabela de referência (que dependia dela) são substituídas por este ADR.
- Nenhuma mudança para locador PJ (desconto/redutor não se aplicam, retenção continua R$0,00).

## 4. Fonte

MAFON 2025 (Manual do Imposto de Renda Retido na Fonte), Receita Federal do Brasil, seção do código de retenção 3208 — "Aluguéis, Royalties e Juros Pagos a Pessoa Física". Lei nº 14.663/2023, art. 6º (valor do desconto simplificado, R$607,20/mês, alterando o art. 4º §2º da Lei nº 9.250/1995).
