"""Extratores determinísticos por campo (camada domain — puros, sem IO) — RF03.

Núcleo do "determinístico primeiro" (D1). Cada função recebe o texto do contrato
e devolve um :class:`ResultadoCampo` com o valor, a confiança e a origem. São
regras/regex ancoradas em vocabulário jurídico; nunca lançam por texto ausente —
devolvem ``ResultadoCampo.nao_encontrado`` (resiliência §6, campos ausentes vão
para revisão sem quebrar o lote).

Escala de confiança (heurística calibrável na Fase de validação com dados reais):
- ``CONF_ALTA``  (0.9): casamento por âncora forte e inequívoca.
- ``CONF_MEDIA`` (0.7): casamento plausível porém dependente de layout.
- ``CONF_BAIXA`` (0.45): valor derivado/fraco → cai abaixo do limiar → revisão.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Generic, TypeVar

from contract_parser.domain.contrato import (
    ModalidadeGarantia,
    OrigemExtracao,
    Parte,
    TipoLocacao,
    TipoParte,
)
from contract_parser.domain.parsing_ptbr import (
    DATA_REGEX,
    brl_para_decimal,
    detectar_documento,
    numero_por_extenso,
    parse_data,
)

T = TypeVar("T")

# Escala de confiança.
CONF_ALTA = 0.9
CONF_MEDIA = 0.7
CONF_BAIXA = 0.45

# Abaixo deste limiar um campo é marcado para revisão manual (§6).
LIMIAR_REVISAO = 0.6


@dataclass(frozen=True)
class ResultadoCampo(Generic[T]):
    """Valor de um campo + proveniência (unidade de saída de cada extrator)."""

    valor: T | None
    confianca: float
    origem: OrigemExtracao = OrigemExtracao.REGRA
    detalhe: str | None = None

    @classmethod
    def nao_encontrado(cls, detalhe: str | None = None) -> ResultadoCampo[T]:
        return cls(None, 0.0, OrigemExtracao.NAO_ENCONTRADO, detalhe)

    @property
    def resolvido(self) -> bool:
        """``True`` quando há valor e a confiança atinge o limiar de revisão."""
        return self.valor is not None and self.confianca >= LIMIAR_REVISAO


# --------------------------------------------------------------------------- #
# Partes (Locador / Locatário) — nome, documento e dedução PF/PJ
# --------------------------------------------------------------------------- #
_TERMOS_PJ = re.compile(
    r"\b(?:LTDA|S\.?A\.?|S/A|EIRELI|ME|EPP|MEI|EMPRESA|COMPANHIA|CIA|"
    r"ASSOCIA[ÇC][ÃA]O|CONDOM[ÍI]NIO|SOCIEDADE)\b",
    re.IGNORECASE,
)

# --- Rótulos das partes -----------------------------------------------------
# Raiz do rótulo + gênero/plural. Cobre LOCADOR/LOCADORA/LOCADORES/LOCADORAS e
# LOCATÁRIO/LOCATÁRIA/LOCATÁRIOS/LOCATÁRIAS (com ou sem acento no OCR).
_RAIZ_LOCADOR = r"LOCADOR(?:ES|AS|A)?"
_RAIZ_LOCATARIO = r"LOCAT[ÁA]RI(?:OS|AS|O|A)?"
# Parentéticos de flexão que aparecem em layouts reais, um ou mais em sequência:
# "(A)", "(A/S)", "(A/S/ES)", "(O/S) (A/S)" — capturados e descartados.
_SUFIXO_ROTULO = r"(?:\s*\([^)\n]{0,15}\))*"
# Separador rótulo→bloco (dois-pontos, hífen ou travessão).
_SEP_ROTULO = r"\s*[:\-–]\s*"
# Fim do bloco de qualificação: linha em branco, rótulo oposto ou cabeçalho de
# seção. Ancorar aqui evita capturar o contrato inteiro. Limite de 800 chars
# cobre blocos longos (nome + doc ficam sempre no início).
_FRONTEIRAS = r"CL[ÁA]USULA|CLAUSULA|PAR[ÁA]GRAFO|PARTES\s+CONTRATANTES|OBJETO\b"


def _re_rotulada(raiz: str, oposto: str) -> re.Pattern[str]:
    return re.compile(
        raiz + _SUFIXO_ROTULO + _SEP_ROTULO
        + r"(.{1,800}?)"
        + r"(?=\n[ \t]*\n|" + oposto + r"|" + _FRONTEIRAS + r"|\Z)",
        re.IGNORECASE | re.DOTALL,
    )


_RE_LOCADOR = _re_rotulada(_RAIZ_LOCADOR, _RAIZ_LOCATARIO)
_RE_LOCATARIO = _re_rotulada(_RAIZ_LOCATARIO, _RAIZ_LOCADOR)

# Conectores narrativos ("de um lado, como LOCADORA e aqui doravante assim
# denominada, <NOME> ...") descartados antes de isolar o nome. Generaliza o
# estilo "considerandos" comum em contratos redigidos em prosa (sem quadro de
# partes rotulado).
_FILLER_NARRATIVA = re.compile(
    r"^[\s,;:.–\-]*"
    r"(?:como\s+)?"
    r"(?:e\s+)?(?:aqui\s+)?(?:doravante\s+)?(?:assim\s+)?"
    r"(?:denominad[oa]s?\s*[,;]?\s*)?"
    r"(?:qualificad[oa]s?\s*[,;]?\s*)?"
    r"(?:a\s+seguir\s+)?"
    r"(?:o\s+|a\s+|os\s+|as\s+)?"
    r"(?:sociedade\s+empres\w*\s+)?"
    r"(?:pessoa\s+jur\w*(?:\s+de\s+direito\s+\w+)?\s+)?"
    r"(?:empresa\s+)?",
    re.IGNORECASE,
)

# Corta o nome no primeiro marcador de qualificação.
_CORTE_NOME = re.compile(
    r"[,;]|\bbrasileir|\bportador|\binscrit|\bCPF\b|\bCNPJ\b|\bnº|\bn\.º|\bresidente|\bcom sede",
    re.IGNORECASE,
)


def _parse_parte(bloco: str) -> ResultadoCampo[Parte]:
    """Extrai nome, documento e tipo PF/PJ de um bloco de qualificação."""
    if not bloco or not bloco.strip():
        return ResultadoCampo.nao_encontrado()

    corte = _CORTE_NOME.search(bloco)
    nome = (bloco[: corte.start()] if corte else bloco).strip(" \t\n\r-–—:.,;_/|")
    nome = re.sub(r"\s+", " ", nome).strip()
    # Nome precisa ter letras: blocos de assinatura ("LOCADOR: ______") ou linhas
    # pontilhadas não são nomes — descarta para não mascarar a parte real.
    if not nome or not re.search(r"[A-Za-zÀ-ÿ]", nome):
        nome = None

    doc = detectar_documento(bloco)
    tipo: TipoParte | None = None
    documento: str | None = None
    if doc is not None:
        tipo = TipoParte(doc[0])
        documento = doc[1]
    elif nome and _TERMOS_PJ.search(nome):
        # Sem documento, mas o nome carrega termo societário → provável PJ.
        tipo = TipoParte.PJ

    if nome is None and documento is None:
        return ResultadoCampo.nao_encontrado()

    # Documento + nome = alta; só um dos dois = média.
    confianca = CONF_ALTA if (documento and nome) else CONF_MEDIA
    parte = Parte(tipo=tipo, nome=nome, documento=documento)
    return ResultadoCampo(parte, confianca)


def _extrair_narrativa(texto: str, raiz: str, oposto: str) -> ResultadoCampo[Parte] | None:
    """Fallback em prosa: rótulo SEM separador seguido do nome/documento.

    Estilo "considerandos" ("...como LOCADORA e aqui denominada, <NOME>, inscrita
    no CNPJ..."). Menos determinístico que o quadro rotulado: teto de confiança
    ``CONF_MEDIA`` e origem sinalizada para revisão preferencial. Nomes de PJ com
    vírgulas internas podem sair truncados (limitação conhecida) — mas o par
    PF/PJ + documento (crítico para o IRRF) é capturado com segurança.
    """
    m = re.search(r"\b" + raiz + r"\b(?!" + _SEP_ROTULO + r")", texto, re.IGNORECASE)
    if not m:
        return None
    janela = texto[m.end() : m.end() + 350]
    # Não deixa o bloco vazar para a parte oposta.
    mo = re.search(r"\b" + oposto + r"\b", janela, re.IGNORECASE)
    if mo:
        janela = janela[: mo.start()]
    janela = _FILLER_NARRATIVA.sub("", janela, count=1)
    res = _parse_parte(janela)
    if res.valor is None:
        return None
    return ResultadoCampo(
        res.valor, min(res.confianca, CONF_MEDIA), res.origem, "parte em redação narrativa"
    )


def _extrair_parte(
    texto: str, regex: re.Pattern[str], raiz: str, oposto: str, rotulo: str
) -> ResultadoCampo[Parte]:
    """Quadro rotulado primeiro (D1 forte); prosa narrativa como fallback."""
    texto = texto or ""
    rotulada = None
    m = regex.search(texto)
    if m:
        rotulada = _parse_parte(m.group(1))
        if rotulada.resolvido:
            return rotulada
    narrativa = _extrair_narrativa(texto, raiz, oposto)
    if narrativa is not None:
        return narrativa
    if rotulada is not None:
        return rotulada
    return ResultadoCampo.nao_encontrado(f"rótulo {rotulo} não encontrado")


def extrair_locador(texto: str) -> ResultadoCampo[Parte]:
    return _extrair_parte(texto, _RE_LOCADOR, _RAIZ_LOCADOR, _RAIZ_LOCATARIO, "LOCADOR")


def extrair_locatario(texto: str) -> ResultadoCampo[Parte]:
    return _extrair_parte(texto, _RE_LOCATARIO, _RAIZ_LOCATARIO, _RAIZ_LOCADOR, "LOCATÁRIO")


# --------------------------------------------------------------------------- #
# Tipo de locação (residencial × comercial) — pode ser ambíguo (fallback LLM)
# --------------------------------------------------------------------------- #
_RE_RESIDENCIAL = re.compile(
    r"\bresidenci(?:al|ais)\b|para\s+moradia|fins?\s+de\s+moradia", re.IGNORECASE
)
_RE_COMERCIAL = re.compile(
    r"\bcomerci(?:al|ais)\b|n[ãa]o[-\s]residencial|fins?\s+(?:\w+\s+){0,2}comerci(?:al|ais)"
    r"|atividade\s+(?:empresarial|comercial)|escrit[óo]rio",
    re.IGNORECASE,
)
# Tipo declarado no TÍTULO/cabeçalho ("CONTRATO DE LOCAÇÃO RESIDENCIAL ...",
# "INSTRUMENTO ... DE LOCAÇÃO COMERCIAL", "... PARA FINS RESIDENCIAIS"). O título
# é sinal jurídico forte e PRECEDE o corpo — resolve casos em que o corpo cita a
# outra palavra por acaso (ex.: contrato residencial que menciona "sala
# comercial" ao descrever o imóvel).
_RE_TITULO_TIPO = re.compile(
    r"loca[çc][ãa]o\s+(?:para\s+fins\s+|com\s+fins\s+|de\s+fins\s+|para\s+)?"
    r"(?P<tipo>residenci(?:al|ais)|comerci(?:al|ais)|n[ãa]o[-\s]residencial)",
    re.IGNORECASE,
)


def extrair_tipo_locacao(texto: str) -> ResultadoCampo[TipoLocacao]:
    t = texto or ""
    # 1) Título/cabeçalho tem prioridade (âncora jurídica forte).
    mt = _RE_TITULO_TIPO.search(t)
    if mt:
        rotulo = mt.group("tipo").lower()
        if rotulo.startswith("comerci"):
            return ResultadoCampo(TipoLocacao.COMERCIAL, CONF_ALTA, detalhe="tipo pelo título")
        return ResultadoCampo(TipoLocacao.RESIDENCIAL, CONF_ALTA, detalhe="tipo pelo título")

    # 2) Corpo do contrato (finalidade/uso).
    tem_res = bool(_RE_RESIDENCIAL.search(t))
    tem_com = bool(_RE_COMERCIAL.search(t))
    if tem_res and not tem_com:
        return ResultadoCampo(TipoLocacao.RESIDENCIAL, CONF_ALTA)
    if tem_com and not tem_res:
        return ResultadoCampo(TipoLocacao.COMERCIAL, CONF_ALTA)
    # Nenhum ou ambos → ambíguo: deixa para o interpretador (LLM) desambiguar.
    return ResultadoCampo.nao_encontrado("tipo de locação não explícito/ambíguo")


# --------------------------------------------------------------------------- #
# Valor do aluguel
# --------------------------------------------------------------------------- #
# ATENÇÃO: a lacuna entre a âncora e "R$" usa ``[^\n]`` (fica na mesma linha),
# NÃO ``[^R\n]``. Sob ``re.IGNORECASE`` uma classe negada ``[^R]`` exclui também
# o 'r' minúsculo — corriqueiro em pt-BR ("impo(r)ta em", "co(r)responde a") —,
# o que fazia a extração do valor falhar sempre que houvesse um 'r' no conector.
#
# Além de "aluguel", alguns contratos comerciais (ex.: modelos "BONI
# ADMINISTRAÇÃO", "SOHO") descrevem o valor como "preço mensal da locação" ou
# "valor mensal da locação", sem usar a palavra "aluguel". A palavra "mensal"
# é exigida logo após "preço"/"valor" (não basta "valor" sozinho) para não
# casar com outras menções de "valor" na mesma frase que não são o valor do
# aluguel (ex.: "taxa condominial no valor de R$ ...", "IPTU no valor de
# R$ ..." — nenhuma tem "valor mensal" adjacente).
_RE_VALOR_ALUGUEL = re.compile(
    r"(?:alugu[eé]l"
    r"|pre[çc]o\s+mensal(?:\s+da\s+loca[çc][ãa]o)?"
    r"|valor\s+mensal(?:\s+da\s+loca[çc][ãa]o)?)"
    r"[^\n]{0,60}?R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)",
    re.IGNORECASE,
)


def extrair_valor_aluguel(texto: str) -> ResultadoCampo[Decimal]:
    m = _RE_VALOR_ALUGUEL.search(texto or "")
    if not m:
        return ResultadoCampo.nao_encontrado("valor de aluguel não localizado")
    valor = brl_para_decimal(m.group(1))
    if valor is None:
        return ResultadoCampo.nao_encontrado("valor de aluguel ilegível")
    return ResultadoCampo(valor, CONF_ALTA)


# --------------------------------------------------------------------------- #
# Multa rescisória total (Mt): valor direto OU "N aluguéis" (× valor base)
# --------------------------------------------------------------------------- #
_RE_MULTA_VALOR = re.compile(
    r"multa[^.\n]{0,90}?R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)",
    re.IGNORECASE,
)
_RE_MULTA_ALUGUEIS = re.compile(
    r"multa[^.\n]{0,90}?(\d{1,2})\s*\(?[a-zçãêé\s]*\)?\s*(?:alug|mes)",
    re.IGNORECASE,
)


def extrair_multa_rescisoria(
    texto: str, valor_aluguel: Decimal | None = None
) -> ResultadoCampo[Decimal]:
    """Extrai a multa rescisória total pactuada (Mt).

    Aceita valor monetário direto (alta confiança) ou expressão "N aluguéis";
    neste caso, se ``valor_aluguel`` for conhecido, calcula ``N × valor`` (média
    confiança). Sem valor base, a multa em nº de aluguéis não pode ser monetizada.
    """
    t = texto or ""
    m = _RE_MULTA_VALOR.search(t)
    if m:
        valor = brl_para_decimal(m.group(1))
        if valor is not None:
            return ResultadoCampo(valor, CONF_ALTA)

    m = _RE_MULTA_ALUGUEIS.search(t)
    if m:
        n = int(m.group(1))
        if valor_aluguel is not None:
            return ResultadoCampo(
                Decimal(n) * valor_aluguel,
                CONF_MEDIA,
                detalhe=f"{n} aluguéis × valor base",
            )
        return ResultadoCampo.nao_encontrado(
            f"multa de {n} aluguéis sem valor base para monetizar"
        )

    return ResultadoCampo.nao_encontrado("multa rescisória não localizada")


# --------------------------------------------------------------------------- #
# Garantia locatícia (Art. 37): detecta modalidade(s) presentes
# --------------------------------------------------------------------------- #
_RE_SEGURO_FIANCA = re.compile(r"seguro[-\s]?fian[çc]a", re.IGNORECASE)
_RE_CAUCAO = re.compile(r"cau[çc][ãa]o", re.IGNORECASE)
_RE_CESSAO_FID = re.compile(r"cess[ãa]o\s+fiduci[áa]ria", re.IGNORECASE)
# Fiança "pura" (fiador) — verificada DEPOIS de remover "seguro-fiança" do texto,
# senão o substrato "fiança" de "seguro-fiança" contaria como uma garantia extra.
_RE_FIANCA = re.compile(r"\bfian[çc]a\b|\bfiador(?:a|es)?\b", re.IGNORECASE)


def extrair_garantias(texto: str) -> ResultadoCampo[list[ModalidadeGarantia]]:
    t = texto or ""
    encontradas: list[ModalidadeGarantia] = []

    if _RE_SEGURO_FIANCA.search(t):
        encontradas.append(ModalidadeGarantia.SEGURO_FIANCA)
    if _RE_CAUCAO.search(t):
        encontradas.append(ModalidadeGarantia.CAUCAO)
    if _RE_CESSAO_FID.search(t):
        encontradas.append(ModalidadeGarantia.CESSAO_FIDUCIARIA)

    # Remove seguro-fiança antes de checar fiança pura (evita falso positivo).
    sem_seguro = _RE_SEGURO_FIANCA.sub(" ", t)
    if _RE_FIANCA.search(sem_seguro):
        encontradas.append(ModalidadeGarantia.FIANCA)

    if not encontradas:
        return ResultadoCampo.nao_encontrado("nenhuma modalidade de garantia detectada")
    return ResultadoCampo(encontradas, CONF_ALTA)


# --------------------------------------------------------------------------- #
# Vigência: início, fim, prazo (meses), dia de vencimento mensal
# --------------------------------------------------------------------------- #
_RE_PERIODO = re.compile(
    rf"(?:de|in[íi]cio\w*)\s+(?P<inicio>{DATA_REGEX})\s+(?:a|at[ée]|ao)\s+(?P<fim>{DATA_REGEX})",
    re.IGNORECASE,
)
_RE_INICIO = re.compile(rf"in[íi]cio\w*[^.\n]{{0,30}}?(?P<d>{DATA_REGEX})", re.IGNORECASE)
_RE_FIM = re.compile(
    rf"(?:t[ée]rmino|t[ée]rmin\w*|fim|final|encerr\w*)[^.\n]{{0,30}}?(?P<d>{DATA_REGEX})",
    re.IGNORECASE,
)
# Prazo em meses: preferir SEMPRE o valor ancorado em "prazo" (numérico ou por
# extenso) antes de recorrer ao genérico "<n> meses". O genérico, isolado,
# captura indevidamente a periodicidade do reajuste ("a cada 6 meses") como se
# fosse o prazo total — por isso é o último recurso e com confiança baixa.
_RE_PRAZO_MESES_ANCORADO = re.compile(
    r"prazo[^.\n]{0,40}?(\d{1,3})\s*\(?[a-zçãêé\s]*\)?\s*meses",
    re.IGNORECASE,
)
_RE_MESES_GENERICO = re.compile(
    r"(\d{1,3})\s*\(?[a-zçãêé\s]*\)?\s*meses",
    re.IGNORECASE,
)
_RE_PRAZO_EXTENSO = re.compile(
    r"prazo[^.\n]{0,40}?(?:de\s+)?([a-zçãêé]+(?:\s+e\s+[a-zçãêé]+)?)\s+meses",
    re.IGNORECASE,
)
_RE_VENCIMENTO = re.compile(
    r"(?:venciment\w*|pagamento|pagar\w*|at[ée]\s+o)[^.\n]{0,40}?dia\s+(\d{1,2})"
    r"|todo(?:\s+o)?\s+dia\s+(\d{1,2})"
    r"|dia\s+(\d{1,2})\s+de\s+cada\s+m[êe]s",
    re.IGNORECASE,
)


def extrair_data_inicio(texto: str) -> ResultadoCampo[date]:
    t = texto or ""
    m = _RE_PERIODO.search(t)
    if m:
        d = parse_data(m.group("inicio"))
        if d is not None:
            return ResultadoCampo(d, CONF_ALTA)
    m = _RE_INICIO.search(t)
    if m:
        d = parse_data(m.group("d"))
        if d is not None:
            return ResultadoCampo(d, CONF_MEDIA)
    return ResultadoCampo.nao_encontrado("data de início não localizada")


def extrair_data_fim(texto: str) -> ResultadoCampo[date]:
    t = texto or ""
    m = _RE_PERIODO.search(t)
    if m:
        d = parse_data(m.group("fim"))
        if d is not None:
            return ResultadoCampo(d, CONF_ALTA)
    m = _RE_FIM.search(t)
    if m:
        d = parse_data(m.group("d"))
        if d is not None:
            return ResultadoCampo(d, CONF_MEDIA)
    return ResultadoCampo.nao_encontrado("data de fim não localizada")


def extrair_prazo_meses(texto: str) -> ResultadoCampo[int]:
    t = texto or ""
    # 1. Ancorado em "prazo" + dígito → sinal forte e inequívoco.
    m = _RE_PRAZO_MESES_ANCORADO.search(t)
    if m:
        return ResultadoCampo(int(m.group(1)), CONF_ALTA)
    # 2. Ancorado em "prazo" + número por extenso ("vinte e quatro meses").
    m = _RE_PRAZO_EXTENSO.search(t)
    if m:
        n = numero_por_extenso(m.group(1))
        if n is not None:
            return ResultadoCampo(n, CONF_MEDIA)
    # 3. Genérico "<n> meses" SEM âncora — último recurso. Pode ser a
    #    periodicidade do reajuste, não o prazo: confiança baixa → revisão.
    m = _RE_MESES_GENERICO.search(t)
    if m:
        return ResultadoCampo(
            int(m.group(1)),
            CONF_BAIXA,
            detalhe="'N meses' sem âncora 'prazo' — confirmar (pode ser periodicidade)",
        )
    return ResultadoCampo.nao_encontrado("prazo em meses não localizado")


def extrair_dia_vencimento(texto: str) -> ResultadoCampo[int]:
    m = _RE_VENCIMENTO.search(texto or "")
    if not m:
        return ResultadoCampo.nao_encontrado("dia de vencimento não localizado")
    bruto = next((g for g in m.groups() if g), None)
    if bruto is None:
        return ResultadoCampo.nao_encontrado("dia de vencimento não localizado")
    dia = int(bruto)
    if not 1 <= dia <= 31:
        return ResultadoCampo.nao_encontrado(f"dia de vencimento fora de faixa: {dia}")
    return ResultadoCampo(dia, CONF_ALTA)


# --------------------------------------------------------------------------- #
# Reajuste: índice, periodicidade, próximo, flag automático
# --------------------------------------------------------------------------- #
_INDICES = (
    ("IGP-M", re.compile(r"IGP[-\s]?M", re.IGNORECASE)),
    ("IPCA", re.compile(r"\bIPCA\b", re.IGNORECASE)),
    ("INPC", re.compile(r"\bINPC\b", re.IGNORECASE)),
    ("IGP-DI", re.compile(r"IGP[-\s]?DI", re.IGNORECASE)),
    ("INCC", re.compile(r"\bINCC\b", re.IGNORECASE)),
)
_RE_SALARIO_MINIMO = re.compile(r"sal[áa]rio[-\s]?m[íi]nimo", re.IGNORECASE)
_RE_MOEDA_ESTRANGEIRA = re.compile(
    r"d[óo]lar|moeda\s+estrangeira|varia[çc][ãa]o\s+cambial|\bUS\$|\bUSD\b|\beuro\b",
    re.IGNORECASE,
)
_RE_PERIODICIDADE_MESES = re.compile(
    r"(?:a\s+cada|periodicidade\s+de|reajust\w+[^.\n]{0,25}?a\s+cada)\s+(\d{1,2})\s+meses",
    re.IGNORECASE,
)
_RE_ANUAL = re.compile(r"reajust\w*[^.\n]{0,30}?anual|anualmente|a\s+cada\s+12\s+meses", re.IGNORECASE)
_RE_SEMESTRAL = re.compile(r"semestral|a\s+cada\s+6\s+meses", re.IGNORECASE)
_RE_AUTOMATICO = re.compile(
    r"reajuste[^.\n]{0,40}?autom[áa]tic|automaticamente|independente\w*\s+de\s+"
    r"(?:aviso|notifica[çc][ãa]o)",
    re.IGNORECASE,
)
_RE_PROXIMO = re.compile(
    rf"(?:pr[óo]ximo\s+reajuste|primeiro\s+reajuste|reajuste\s+em)[^.\n]{{0,30}}?(?P<d>{DATA_REGEX})",
    re.IGNORECASE,
)


def extrair_indice_reajuste(texto: str) -> ResultadoCampo[str]:
    """Índice de reajuste. Índices vedados (salário mínimo/moeda estrangeira) são
    capturados como texto (a flag jurídica é responsabilidade de ``regras_juridicas``)."""
    t = texto or ""
    for nome, regex in _INDICES:
        if regex.search(t):
            return ResultadoCampo(nome, CONF_ALTA)
    if _RE_SALARIO_MINIMO.search(t):
        return ResultadoCampo("salário mínimo", CONF_ALTA, detalhe="índice vedado (Art. 18)")
    if _RE_MOEDA_ESTRANGEIRA.search(t):
        return ResultadoCampo("moeda estrangeira", CONF_ALTA, detalhe="índice vedado (Art. 18)")
    return ResultadoCampo.nao_encontrado("índice de reajuste não localizado")


def extrair_periodicidade_meses(texto: str) -> ResultadoCampo[int]:
    t = texto or ""
    m = _RE_PERIODICIDADE_MESES.search(t)
    if m:
        return ResultadoCampo(int(m.group(1)), CONF_ALTA)
    if _RE_ANUAL.search(t):
        return ResultadoCampo(12, CONF_ALTA)
    if _RE_SEMESTRAL.search(t):
        return ResultadoCampo(6, CONF_ALTA)
    return ResultadoCampo.nao_encontrado("periodicidade de reajuste não localizada")


def extrair_reajuste_automatico(texto: str) -> ResultadoCampo[bool]:
    """Flag booleana. Ausência de menção é interpretada como ``False`` (confiança
    baixa → sinaliza revisão, pois "não mencionado" ≠ "explicitamente não")."""
    if _RE_AUTOMATICO.search(texto or ""):
        return ResultadoCampo(True, CONF_ALTA)
    return ResultadoCampo(False, CONF_BAIXA, detalhe="reajuste automático não mencionado")


def extrair_proximo_reajuste(texto: str) -> ResultadoCampo[str]:
    m = _RE_PROXIMO.search(texto or "")
    if not m:
        return ResultadoCampo.nao_encontrado("próximo reajuste não localizado")
    d = parse_data(m.group("d"))
    if d is None:
        return ResultadoCampo.nao_encontrado("data de próximo reajuste ilegível")
    return ResultadoCampo(d.isoformat(), CONF_MEDIA)
