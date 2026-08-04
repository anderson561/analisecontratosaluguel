---
name: rental-contract-audit-orchestrator
description: Workflow operacional completo para leitura, extração de dados, checagem de abusividades, cálculo financeiro e emissão do Parecer Executivo de Auditoria do Contrato de Aluguel.
---

# 🔄 Workflow: Orquestração de Auditoria Contratual de Locação

Este fluxo orienta o agente passo a passo na execução da auditoria técnica de um contrato de locação (minuta ou contrato assinado).

## 📋 Fase 1: Ingestão, Mapeamento e Qualificação
1. Identifique o tipo de locação: **Residencial**, **Comercial (Não Residencial)** ou **Temporada**.
2. Mapeie e extraia os dados essenciais para o quadro resumo:
   * Qualificação das partes (Locador, Locatário, Fiadores/Garantidores).
   * Descrição detalhada do Objeto (Endereço, matrícula do imóvel, vagas de garagem).
   * Prazo de Vigência (início, fim e total de meses) e regra de prorrogação.

## 🔬 Fase 2: Auditoria Financeira e de Garantias
1. **Aluguel e Encargos:** Identifique valor base, data de vencimento, forma de pagamento, taxa de condomínio, IPTU e seguros obrigatórios (ex: seguro contra incêndio).
2. **Reajuste:** Mapeie o índice estipulado (IPCA, IGP-M, etc.) e a data-base do reajuste.
3. **Garantia Locatícia:** Identifique a modalidade única adotada e verifique se o valor/limite respeita a lei (ex: caução em dinheiro limitada a no máximo 3 aluguéis depositados em poupança conjunta).

## 🛡️ Fase 3: Pente-Fino de Cláusulas Abusivas e Omissões
1. Verifique se há cláusula de multa por rescisão antecipada e se a fórmula prevê proporcionalidade ao tempo restante.
2. Analise a distribuição de responsabilidades por reformas, manutenção ordinária vs. extraordinária.
3. Em locações comerciais, verifique o direito à Ação Renovatória e restrições sobre a luva/ponto comercial.
4. Identifique se há tolerância ou penalidades moratórias abusivas (ex: juros de mora superiores a 1% ao mês ou multa moratória acima de 10%).

## 📄 Fase 4: Emissão do Parecer Jurídico-Financeiro
Gere o relatório final consolidado estruturado da seguinte forma:
1. **Resumo Executivo / Quadro-Resumo:** Dados do contrato sintetizados.
2. **Matriz de Riscos:** Classificação dos achados em *Crítico (Nulo/Ilegal)*, *Médio (Desfavorável)* e *Baixo (Alinhado)*.
3. **Redação Sugerida (Minuta Corretiva):** Sugestões de reescrita das cláusulas problemáticas apontadas no parecer.