---
name: security-audit-orchestrator
description: Workflow operacional de 4 fases para auditoria end-to-end de segurança de aplicações, cobrindo modelagem de ameaças, varredura automatizada, auditoria manual profunda e relatório técnico executivo.
---

# 🔄 Workflow: Orquestração de Auditoria de Segurança Trail of Bits

Este fluxo orienta o agente passo a passo na execução de uma auditoria completa de segurança técnica.

## 📋 Fase 1: Discovery, Arquitetura e Modelagem de Ameaças
1. **Mapeamento de Superfície de Ataque:** Identifique todas as APIs, rotas, interfaces CLI, bancos de dados, integrações de terceiros e pontos de entrada de dados.
2. **Definição de Atores:** Mapeie os níveis de privilégio (Usuário Anônimo, Autenticado, Admin, Sistema).
3. **Modelagem STRIDE:** Identifique os riscos por componente e registre as principais ameaças no diagrama de fluxo de dados (DFD).

## 🔬 Fase 2: Varredura Automatizada e Análise Estática/SCA
1. Executar análise de dependências (Software Composition Analysis - SCA) para detectar CVEs conhecidas nas bibliotecas utilizadas.
2. Configurar e executar ferramentas de SAST customizadas conforme a linguagem do projeto.
3. Triar os falsos positivos e listar os achados preliminares que demandam verificação manual.

## 🧠 Fase 3: Auditoria Manual Profunda e Invariant Testing
1. **Revisão Manual de Código (Linha por Linha):**
   * Audit de Controle de Acesso (IDOR, BOLA, BFLA).
   * Verificação de Lógica de Negócios e Manipulação de Estado.
   * Checagem de Sanitização de Inputs (SQLi, XSS, Command Injection, SSRF).
2. **Fuzzing & Invariantes:**
   * Definir propriedades fundamentais do sistema (ex: "O saldo total de tokens nunca pode ultrapassar o valor emitido").
   * Executar/simular testes de estresse baseados em propriedades para tentar quebrar os invariantes.
3. **Elaboração de PoC:** Para cada falha confirmada, redigir o script/payload que comprova a explorabilidade.

## 📄 Fase 4: Relatório Executivo e Plano de Remediação
Consolidar a auditoria no relatório final contendo:
1. **Resumo Executivo para C-Level:** Visão geral da postura de segurança e gráfico de severidade dos achados.
2. **Tabela de Vulnerabilidades:** Lista numerada com CVSS v3.1, localização exata no código e vetor de ataque.
3. **Fichas de Vulnerabilidade:** Descrição detalhada, PoC explicativo e Patch Sugerido.