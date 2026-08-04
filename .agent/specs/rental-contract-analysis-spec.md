# 📐 Spec: Critérios de Prontidão e Qualidade da Análise Contratual (Lease Audit Readiness)

Esta especificação define a folha de requisitos e o checklist de aceitação técnica que todo parecer de contrato de aluguel gerado pelo agente deve cumprir antes de ser entregue.

## 1. Mapeamento Obrigatório do Quadro-Resumo
Toda análise precisa conter, no cabeçalho do parecer, a tabela estruturada com os atributos chave:

| Atributo Contratual | Valor Identificado | Status / Conformidade |
| :--- | :--- | :--- |
| **Tipo de Locação** | Residencial / Comercial / Temporada | ✅ / ⚠️ |
| **Prazo de Vigência** | XX meses (Início: DD/MM/AAAA) | ✅ / ⚠️ |
| **Valor Inicial do Aluguel** | R$ X.XXX,XX | ✅ / ⚠️ |
| **Índice de Reajuste** | IPCA / IGP-M (Anual) | ✅ / ⚠️ |
| **Modalidade de Garantia** | Caução / Fiador / Seguro-Fiança | ✅ / ⚠️ |
| **Multa Rescisória Total** | X aluguéis (Proporcional) | ✅ / ⚠️ |

## 2. Matriz de Classificação de Riscos
O agente deve obrigatoriamente classificar os achados segundo os níveis de severidade:

* **Nível 1 - CRÍTICO (Ação Imediata Necessária):** Cláusulas nulas de pleno direito por violação direta da Lei 8.245/91 (ex: dupla garantia, reajuste semestral, cobrança de obras extraordinárias do inquilino).
* **Nível 2 - MÉDIO (Necessita Negociação):** Cláusulas desequilibradas ou desfavoráveis (ex: multa rescisória máxima sem isenção após 12 meses; foro de eleição inadequado; prazos curtos para notificações).
* **Nível 3 - BAIXO (Padrão de Mercado):** Cláusulas alinhadas com o Código Civil e praxe imobiliária.

## 🏁 Checklist de Aceitação (Definition of Done)
- [ ] O relatório confirmou explicitamente a existência de apenas **uma** modalidade de garantia locatícia.
- [ ] Foi apresentada a memória de cálculo da multa proporcional em caso de rescisão antecipada.
- [ ] Foram verificadas as obrigações relativas ao seguro contra incêndio e laudo de vistoria.
- [ ] Foi entregue uma proposta textual com a nova redação (*cláusulas sugeridas*) para substituição dos itens críticos identificados.