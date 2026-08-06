# Plano de Ação — Redutor de IRRF 2026 (Lei nº 15.270/2025)

> **Data:** 2026-08-06 · **Status:** Plano concluído — Fases 0–4 (commits `bb5491e`, e este)
> **Decisão do usuário:** implementar **apenas** o redutor da Lei nº 15.270/2025 (aplicado ao imposto). O "desconto simplificado" de R$607,20 (base de cálculo) **não** será implementado — confirmado que não se aplica à retenção de aluguel PJ→PF (ver ADR-003 §3).
> **Decisão do usuário (pós-Fase 0):** a fórmula oficial, quando aplicada ao aluguel (sem o desconto simplificado que só existe para salário), resulta em imposto residual entre R$5.000,00 e R$7.350,00 (ex.: R$153,38 em R$5.000,00 exatos) — NÃO isenção total. Usuário optou por implementar essa leitura técnica/mecânica, ciente da ressalva de que não há exemplo oficial da RFB específico para aluguel (ver ADR-003 §3).

## 1. Contexto e o que está em vigor hoje

`domain/irrf.py` implementa apenas a tabela progressiva mensal padrão (`tabela_irrf_2026()`, base legal Lei nº 15.191/2025). Existe um stub documentado e **desligado** (`aplicar_redutor_15270`, não chamado por `calcular_irrf`) reservado exatamente para este redutor — a assinatura já assume que ele opera sobre o **imposto calculado**, não sobre a base, o que está alinhado com a decisão tomada acima.

## 2. O que a pesquisa já confirmou (fonte primária: texto da Lei nº 15.270/2025, Art. 3º-A)

- A redução se aplica sobre o **imposto já calculado** pela tabela progressiva padrão.
- Fórmula da faixa de transição: `Redutor = R$ 978,62 − (0,133145 × rendimento tributável mensal)`.
- Válida para rendimento mensal entre **R$ 5.000,01 e R$ 7.350,00**.
- Acima de R$ 7.350,00: **nenhuma redução** — tabela progressiva padrão aplicada normalmente (é o caso dos 2 contratos reais BONI/SOHO, ambos R$ 7.800,00 — não deveria mudar o resultado atual deles).
- É **obrigatória** (não uma opção do contribuinte), limitada ao valor do próprio imposto (não pode gerar imposto negativo).

## 3. Risco/lacuna identificado — PRECISA ser resolvido antes de codificar

Ao simular a fórmula acima manualmente para uma base de **R$ 5.000,00** (o exato valor do CA-03 já validado), o resultado dá **R$ 153,38** de imposto — não R$ 0,00. Isso contradiz a narrativa amplamente divulgada na imprensa de "isenção total para quem ganha até R$ 5 mil". Duas explicações possíveis, ainda não resolvidas:

1. A "isenção até R$ 5.000" divulgada na imprensa é uma simplificação jornalística e o efeito real, para rendimento *exatamente* R$5.000,00 (sem outras deduções), não é R$0,00 — o redutor apenas *suaviza* a transição, não zera no limite inferior.
2. Existe uma condição adicional no Art. 3º-A (ou em ato normativo complementar da RFB) que estabelece isenção total para rendimento ≤ R$ 5.000,00 *separadamente* do redutor, e o texto que recebi (via resumo de IA sobre o HTML da lei, não o PDF oficial linha a linha) pode ter omitido essa cláusula.

**Este é o item de maior risco do plano.** Implementar a fórmula sem resolver essa lacuna pode gerar retenção incorreta para todo aluguel de locador PF na faixa R$5.000–R$7.350 — o que é o cenário mais comum de contrato residencial de valor médio, não uma borda rara.

## 4. Fases

### Fase 0 — Validação legal definitiva (bloqueia as Fases 1+)
- Obter o texto oficial completo e literal da Lei nº 15.270/2025 (Art. 3º-A e parágrafos), preferencialmente do Diário Oficial/planalto.gov.br, não de agregador.
- Confirmar explicitamente o comportamento para rendimento ≤ R$ 5.000,00 (resolve o item §3).
- Validar a fórmula com **pelo menos 3 exemplos numéricos** batendo à mão: R$ 5.000,00 (limite inferior), R$ 6.000,00 (meio da faixa — já tenho um exemplo de fonte secundária dando R$561,52, usar para conferência), R$ 7.350,00 (limite superior — redutor deve zerar exatamente aqui).
- Confirmar por que (ou se) o desconto simplificado de R$607,20 não se aplica a esta modalidade de retenção (documentar a decisão para não reabrir a dúvida).
- Produzir um `adr-003-redutor-irrf-2026.md` documentando fórmula validada + fonte oficial + os 3 exemplos de conferência.
- **Agente sugerido:** `requirements-analyst` (tem WebSearch/WebFetch, não escreve código de produção).

### Fase 1 — Implementação no domínio (`domain/irrf.py`)
- Substituir o stub `aplicar_redutor_15270` pela fórmula validada na Fase 0.
- Ativar a chamada dentro de `calcular_irrf()`, aplicada **antes do arredondamento final**, só quando `tipo_locador is PF` (regra de retenção já existente) e a base cair na faixa aplicável.
- Estender `ResultadoIRRF` com campos auditáveis (ex.: `imposto_antes_redutor`, `redutor_aplicado`) — mantém o princípio de memória de cálculo já estabelecido (ADR-001).
- Atualizar `base_legal`/docstrings citando Lei nº 15.270/2025 (além da 15.191/2025, que segue valendo para a tabela em si).
- **Agente sugerido:** `xp-coach` (TDD estrito, como nos últimos bug fixes desta sessão).

### Fase 2 — Testes
- Casos de fronteira: R$5.000,00, R$5.000,01, meio da faixa, R$7.350,00 (redutor→0), R$7.350,01 (sem redutor), e os valores reais já processados (R$500, R$1.000, R$7.800×2) como regressão — nenhum desses 4 últimos deveria mudar de resultado.
- Atualizar CA-03 em `.agent/specs/contract-parser-requirements.md` §7 (hoje documentado como "tabela progressiva padrão, sem redutor" para base R$5.000 — precisa refletir o novo valor esperado).
- Suíte completa + `ruff` + reprocessamento dos 7 contratos reais (mesmo hábito já estabelecido nesta sessão).

### Fase 3 — GUI/Relatórios
- Conferir se o Painel/exportador PDF já expõe a memória de cálculo de forma suficiente ou se vale a pena mostrar o redutor aplicado explicitamente (decisão de UX menor, avaliar durante a implementação).

### Fase 4 — Documentação
- Atualizar README, ADR-001 (nota apontando para o novo ADR-003, no mesmo padrão da nota que já aponta pro ADR-002), `checklist-aceite-final.md`.

## 5. Critério de pronto
- Fórmula validada contra fonte oficial + 3 exemplos numéricos conferidos à mão (Fase 0 assinada antes de prosseguir).
- Suíte verde, `ruff` limpo, regressão dos 7 contratos reais sem mudança nos 4 que já processam corretamente.
- CA-03 atualizado e documentado.

## 6. Fora de escopo (por decisão explícita do usuário)
- Desconto simplificado de R$ 607,20 (base de cálculo) — não implementado nesta rodada.
