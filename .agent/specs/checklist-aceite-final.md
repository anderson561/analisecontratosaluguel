# Checklist de Aceite Final — Fase 8 (QA, Segurança, Documentação & Entrega)

> **Autor:** Engenheiro Sênior (Fase 8) · **Skills aplicadas:** `cybersecurity-architect` →
> `qa-automation-expert` → `verification-before-completion`
> **Data:** 2026-08-05 · **Base:** `.agent/specs/contract-parser-requirements.md` §7

Mapeia CADA Critério de Aceitação (CA-01 a CA-06, incluindo os 2 jurídicos
adicionados pelo domínio `real-estate-contract-analyst`) para: descrição,
status, prova (teste/arquivo) e commit onde foi implementado.

**Legenda de status**
- ✅ **provado com mock** — comportamento verificado por teste automatizado
  determinístico, sem depender de serviço externo vivo (roda em qualquer clone
  limpo, inclusive CI sem Mongo/Tesseract).
- ⏳ **requer Mongo/Tesseract reais** — caminho de infraestrutura correspondente
  existe e tem teste de integração dedicado, mas o teste faz `skip` automático
  quando o serviço real (MongoDB/Tesseract) não está disponível no host —
  precisa ser executado manualmente com o serviço de pé para prova final.
- ✅ **validado com contrato real** — adicionalmente exercitado sobre um lote de
  contratos PDF reais (fora do versionamento, `CONTRATOS_REAIS_DIR`), não só
  sobre fixtures sintéticas.

---

## CA-01 — Importação de planilha (50 empresas)

> "Importar `.xlsx` com 50 empresas → 50 documentos no Mongo + listagem na GUI."

| Camada | Status | Prova |
|---|---|---|
| Parsing/auto-mapeamento/dedup (domain+application) | ✅ provado com mock | `tests/application/test_empresa_importer.py::test_ca01_importar_50_empresas`, usando `tests/support/fixture_builders.py::construir_xlsx_50_empresas` (gera 50 CNPJs válidos e distintos, sem planilha real versionada) |
| Persistência real no Mongo (`empresas`) | ⏳ requer Mongo real | `tests/infrastructure/test_empresa_repository.py` (`upsert_many`/`list_all`) — skip automático com `MongoDB indisponivel...` quando o serviço local não está de pé |
| Listagem na GUI | ✅ provado com mock | `tests/presentation/test_controllers.py::test_importar_planilha_resume_importados_duplicados_e_erros`, `EmpresasController.linhas_empresas()` |

**Commit:** `c0c9d0a` — feat(empresas): Fase 2 — gestão de empresas e importação em lote (RF01)

---

## CA-02 — Ambiência Docker (`docker-compose up`)

> 🔸 **DEFERIDO** por decisão de arquitetura (ADR-001, decisão D2): Docker fica
> fora do escopo desta versão; app e MongoDB rodam nativamente no host Windows.
> Não há regressão de teste associada — não é uma pendência esquecida, é uma
> decisão documentada e comunicada no README (seção "Escopo atual vs. backlog").

**Commit:** N/A (decisão registrada em `.agent/specs/adr-001-stack-e-arquitetura.md`, linha D2)

---

## CA-03 — Tabela IRRF 2026 + memória de cálculo

> "Aluguel PF→PJ de R$ 5.000,00 → alíquota + dedução da tabela 2026 + memória
> de cálculo."

| Camada | Status | Prova |
|---|---|---|
| Cálculo puro (domain, sem IO) | ✅ provado com mock | `tests/domain/test_irrf.py` — caso exato `("5000.00", "0.275", "908.73", "466.27")`, faixas/limites de fronteira, locador PJ ⇒ R$ 0,00, memória de cálculo (`ResultadoIRRF`) auditável |
| Integração IRRF + Relatório 01 | ✅ provado com mock | `tests/application/test_relatorio_service.py::test_ca03_irrf_pf_pj_base_5000` |
| Persistência/versão da tabela no Mongo | ⏳ requer Mongo real | `tests/infrastructure/test_tabela_irrf_repository.py` — skip automático sem Mongo vivo |
| Cross-fase (IRRF real dentro do pipeline completo até exportação) | ✅ provado com mock | `tests/presentation/test_pipeline_integracao_cross_fase.py` (base R$ 3.500,00 → R$ 130,84, releitura do `.xlsx` exportado) |

**Commit:** `463caeb` — feat(irrf): Fase 5 — motor de cálculo de IRRF 2026 (RF04)

> **Risco residual documentado:** o redutor da Lei nº 15.270/2025 (rendimentos
> ≤ R$ 7.350,00) permanece **desligado** — coeficientes ainda não validados na
> fonte oficial da RFB. O CA-03 é atendido pela tabela progressiva padrão, que
> é o que o RF04 exige; o redutor é ponto de extensão documentado (`domain/irrf.py::aplicar_redutor_15270`).

---

## CA-04 — Contrato ausente (alerta de pendência)

> "Empresas A, B, C cadastradas; só A, B na pasta → status individual + alerta
> de ausência de C."

| Camada | Status | Prova |
|---|---|---|
| Match CNPJ + fuzzy + pendências (domain+application) | ✅ provado com mock | `tests/application/test_portfolio_validation_service.py::test_ca04_empresa_sem_contrato_vira_pendencia_com_mensagem_exata` (cenário A/B/C), `tests/domain/test_match_portfolio.py` (mensagem exata de pendência) |
| Integração com Relatório 02 (conformidade) | ✅ provado com mock | `tests/application/test_relatorio_service.py::test_relatorio02_totais_e_pendencia_com_mensagem_exata` |
| Exposição na GUI (aba Conformidade) | ✅ provado com mock | `tests/presentation/test_controllers.py::test_resumo_conformidade_pendencia_mensagem_exata` |
| Cross-fase (pendência sobrevivendo à exportação real) | ✅ provado com mock | `tests/presentation/test_pipeline_integracao_cross_fase.py::test_pipeline_completo_exportacao_excel_sobrevive_a_releitura` |

**Commit:** `0552f3b` — feat(portfolio): Fase 6 — validação de portfólio e match de empresas (RF05)

---

## CA-05 (novo, jurídico) — Índice de reajuste vedado (Art. 18)

> "Contrato com índice atrelado a salário mínimo → flag de cláusula vedada
> (Art. 18)."

| Camada | Status | Prova |
|---|---|---|
| Regra pura (domain) | ✅ provado com mock | `tests/domain/test_regras_juridicas.py::test_art18_indice_salario_minimo_vedado`, `test_art18_indice_moeda_estrangeira_vedado`, `test_art18_periodicidade_inferior_12m` |
| Integração ponta-a-ponta (extração real sobre fixture completa) | ✅ provado com mock | `tests/application/test_contract_extraction_service.py::test_fixture_completa_monta_contrato_e_marca_campos_ausentes` sobre `tests/fixtures/contrato_residencial_pj_pf_reajuste_vedado.txt` (índice = salário mínimo nacional + periodicidade semestral) |
| Validado com contrato real | ⏳ não realizado nesta fase | Nenhum contrato real do lote de validação (Fase 4) trazia essa cláusula vedada especificamente; a regra está coberta apenas por fixture sintética. Risco residual: baixo (regra é puramente léxica/determinística sobre o campo já extraído, não depende de layout) |

**Commit:** `c8fdff9` — feat(extracao): Fase 4 — motor de extração NLP híbrida (RF03) (endurecido em `4255021`)

---

## CA-06 (novo, jurídico) — Cumulação de garantias (Art. 37)

> "Contrato com 2 garantias → flag de violação do Art. 37."

| Camada | Status | Prova |
|---|---|---|
| Regra pura (domain) | ✅ provado com mock | `tests/domain/test_regras_juridicas.py::test_art37_multiplas_garantias`, `test_art37_garantia_duplicada_nao_conta_como_multipla` (não conta modalidade repetida) |
| Integração ponta-a-ponta (extração real sobre fixture completa) | ✅ provado com mock | `tests/application/test_extracao_fixtures_matriz.py` — fixture `contrato_comercial_pj_pj_abusivo.txt` (caução **e** fiança cumulativas) → `violacao_art37_multiplas_garantias=True` |
| Validado com contrato real | ⏳ não realizado nesta fase | Mesma observação do CA-05: cobertura só por fixture sintética nesta fase |

**Commit:** `c8fdff9` — feat(extracao): Fase 4 — motor de extração NLP híbrida (RF03) (endurecido em `4255021`)

---

## Resumo executivo

| CA | Descrição | Status | Commit |
|---|---|---|---|
| CA-01 | Importação 50 empresas | ✅ mock · ⏳ Mongo real p/ persistência | `c0c9d0a` |
| CA-02 | Docker | 🔸 deferido (ADR-001 D2) | — |
| CA-03 | IRRF 2026 + memória de cálculo | ✅ mock (puro, sem dependência externa) | `463caeb` |
| CA-04 | Alerta de pendência de portfólio | ✅ mock | `0552f3b` |
| CA-05 | Índice vedado (Art. 18) | ✅ mock (fixture sintética) | `c8fdff9` |
| CA-06 | Cumulação de garantias (Art. 37) | ✅ mock (fixture sintética) | `c8fdff9` |

**386 → 389 testes passam, 8 skips — todos ambientais e esperados** (ver seção
QA do relatório de entrega da Fase 8): MongoDB indisponível (×3), `pytesseract`
não instalado (×1), provedor de LLM não configurado por decisão de LGPD (×1),
harness de contratos reais sem `CONTRATOS_REAIS_DIR` definida (×3). Nenhum skip
mascara um bug — cada um tem uma causa raiz de ambiente/decisão documentada.

## Riscos residuais aceitos (fora do escopo desta fase)

1. **CA-05/CA-06 sem validação em contrato real** — cobertos apenas por
   fixtures sintéticas; recomenda-se rodar o harness (`CONTRATOS_REAIS_DIR`)
   sobre um lote real assim que disponível e anexar o resultado a este
   checklist.
2. **Redutor da Lei nº 15.270/2025 (IRRF)** — pendente de validação da fórmula
   na fonte oficial da RFB; desligado por padrão (ver CA-03).
3. **Revalidação online da tabela IRRF contra a RFB** e **provedor de LLM**
   — ambos com stub de produção que falha explicitamente (fail-secure) em vez
   de simular sucesso; nenhuma integração de rede ativa nesta versão.
4. **CA-02 (Docker)** — backlog, sem impacto na operação atual (app nativo).
