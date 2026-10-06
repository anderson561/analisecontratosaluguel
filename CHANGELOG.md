# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

Suíte de testes: 562 → 679 aprovados (4 skips esperados; 1 falha pré-existente e
não relacionada, `test_ocr_real_tesseract`, que só falha com a suíte inteira
porque depende do Tesseract no PATH).

### Adicionado
- **Painel e relatórios — Despesas e Prorrogação:** novas colunas "Despesas"
  (tipo de despesa → responsável: locador/locatário) e "Prorrogação"
  (automática, com prazo quando explícito) no Painel e nas exportações Excel/PDF.
- **Múltiplos locadores:** coluna "Locador(es) Adicional(is)" no Painel e nas
  exportações. O locador principal continua sendo o único usado no cálculo do
  IRRF (decisão deliberada: múltiplos locadores só são identificados por ora).
- **Índice de reajuste completo:** nova coluna "Fonte do Índice" (ex.: "FGV" em
  "IGP-M/FGV"), campo separado do índice para não fragmentar o filtro do Painel.
- **Carência:** leitura da cláusula de carência (em meses) e nova coluna
  "Carência" no Painel e nas exportações. Carência expressa em dias vai para
  revisão manual, sem conversão automática para meses.
- **Próximo reajuste calculado:** quando o contrato não traz a data explícita,
  ela é calculada a partir da data de início, assumindo reajuste anual (ou a
  periodicidade extraída), rolando até a primeira data igual ou posterior a hoje.
  O valor é marcado como calculado (`REGRA_CALCULADA`, baixa confiança) e vai
  para revisão; datas lidas do texto nunca são sobrescritas.
- **Botão "Atualizar Próx. Reajuste"** na aba Painel: recalcula e persiste as
  datas calculadas de todos os contratos do Painel e informa quantos mudaram.

### Corrigido
- **Segundo locador não identificado:** contratos com dois ou mais blocos
  "LOCADOR:" só tinham o primeiro lido, porque a extração usava a primeira
  ocorrência do rótulo. Agora todos os blocos são lidos e deduplicados por
  documento/nome, sem marcar contratos de locador único para revisão.
- **Prazo em anos não lido:** "05 (cinco) anos" não era reconhecido (só "meses");
  agora é convertido para meses.
- **Data de início não lida em "iniciando-se":** o padrão só reconhecia o
  substantivo "início"; agora cobre também as formas verbais.
- **PDF descartando colunas:** com 13+ colunas, o relatório PDF perdia
  silenciosamente o conteúdo que ultrapassava a largura da página. A tabela
  passou a usar larguras fixas somando a área útil (verificado por teste).
