"""Match de contrato × portfólio de empresas (RF05 / D4) — camada domain, sem IO.

Regra de negócio central da Fase 6 (ver requisitos §4/§6 e ADR-001 D4):

- **Primário — CNPJ:** o CNPJ do locatário (``Contrato.locatario.documento``),
  normalizado para 14 dígitos, é comparado a ``Empresa.cnpj`` (já normalizado).
- **Fallback — fuzzy:** quando não há CNPJ utilizável (ausente, CPF de PF ou
  ilegível) OU quando o CNPJ não casa com nenhuma empresa, compara o *nome* do
  locatário contra ``razao_social`` + ``aliases`` + ``nomes_fantasia`` de cada
  empresa. Só considera match se o melhor score for ``>= threshold``.

Módulo **puro**: não faz IO de rede/banco. A biblioteca de similaridade
(rapidfuzz) fica isolada atrás do parâmetro ``similaridade`` (com default
determinístico), mantendo o domínio 100% testável sem depender do rapidfuzz.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum

from pydantic import BaseModel, ConfigDict

from contract_parser.domain.cnpj import CNPJInvalidoError, normalizar_cnpj
from contract_parser.domain.contrato import Contrato
from contract_parser.domain.empresa import Empresa

# Similaridade textual: recebe (nome_a, nome_b) e devolve score em [0, 100].
SimilaridadeFn = Callable[[str, str], float]

# Score atribuído a um match determinístico por CNPJ (certeza total).
SCORE_CNPJ = 100.0


class StatusMatch(str, Enum):
    """Status estrito de um match (RF05)."""

    ENCONTRADO = "ENCONTRADO"
    NAO_ENCONTRADO = "NAO_ENCONTRADO"


class MetodoMatch(str, Enum):
    """Como o match foi (ou não foi) obtido — rastreabilidade do resultado."""

    CNPJ = "cnpj"
    FUZZY = "fuzzy"
    NENHUM = "nenhum"


def similaridade_padrao(a: str, b: str) -> float:
    """Similaridade textual default (rapidfuzz ``token_sort_ratio``, escala 0–100).

    Isola a dependência de rapidfuzz: o domínio só conhece esta assinatura
    (``SimilaridadeFn``). ``default_process`` normaliza caixa, acentuação de
    pontuação e ordena tokens — robustez adequada a variações de razão social
    e ruído de OCR (ex.: "Alpha Comercio LTDA" × "COMERCIO ALPHA ltda").
    """
    from rapidfuzz import fuzz
    from rapidfuzz.utils import default_process

    return float(fuzz.token_sort_ratio(a, b, processor=default_process))


class ResultadoMatch(BaseModel):
    """Resultado do match de UM contrato contra o portfólio.

    ``empresa`` é a empresa casada (ou ``None`` se ``NAO_ENCONTRADO``); ``score``
    é 100 para match por CNPJ e o melhor score fuzzy caso contrário (mesmo quando
    abaixo do limiar, para fins de diagnóstico/faixa de revisão manual).
    """

    model_config = ConfigDict(frozen=True)

    empresa: Empresa | None
    status: StatusMatch
    metodo: MetodoMatch
    score: float = 0.0

    @property
    def encontrado(self) -> bool:
        return self.status is StatusMatch.ENCONTRADO


def mensagem_pendencia(empresa: Empresa) -> str:
    """Mensagem EXATA de pendência do PRD/CA-04 para uma empresa sem contrato.

    Template do PRD: ``"Contrato da Empresa [Razão Social / CNPJ] não encontrado"``,
    com o placeholder substituído pela razão social e pelo CNPJ da empresa.
    """
    return f"Contrato da Empresa {empresa.razao_social} / {empresa.cnpj} não encontrado"


def _cnpj_utilizavel(documento: str | None) -> str | None:
    """Devolve o CNPJ normalizado se ``documento`` for um CNPJ válido; senão ``None``.

    Um CPF (11 dígitos) ou lixo de OCR não normaliza para 14 dígitos e cai aqui
    como ``None`` — sinalizando que o match deve tentar o fallback fuzzy.
    """
    if not documento:
        return None
    try:
        return normalizar_cnpj(documento)
    except CNPJInvalidoError:
        return None


def _nomes_candidatos(empresa: Empresa) -> list[str]:
    """Todos os nomes comparáveis de uma empresa (razão social + apelidos)."""
    return [empresa.razao_social, *empresa.aliases, *empresa.nomes_fantasia]


def casar_contrato(
    contrato: Contrato,
    empresas: Sequence[Empresa],
    *,
    threshold: float,
    similaridade: SimilaridadeFn = similaridade_padrao,
) -> ResultadoMatch:
    """Casa um contrato ao portfólio: CNPJ primeiro, fuzzy como fallback.

    Args:
        contrato: contrato processado (usa ``locatario.documento`` e ``.nome``).
        empresas: portfólio a comparar. A ORDEM importa: empates de score no
            fuzzy são resolvidos deterministicamente pela primeira ocorrência.
        threshold: score mínimo (inclusive) para aceitar um match fuzzy.
        similaridade: função de similaridade injetável (default: rapidfuzz).

    Returns:
        ``ResultadoMatch`` com status estrito, método e score.
    """
    locatario = contrato.locatario

    # 1) Match primário por CNPJ normalizado (determinístico, score 100).
    cnpj = _cnpj_utilizavel(locatario.documento)
    if cnpj is not None:
        for empresa in empresas:
            if empresa.cnpj == cnpj:
                return ResultadoMatch(
                    empresa=empresa,
                    status=StatusMatch.ENCONTRADO,
                    metodo=MetodoMatch.CNPJ,
                    score=SCORE_CNPJ,
                )

    # 2) Fallback fuzzy pelo nome (razão social + aliases + nomes fantasia).
    melhor_score = 0.0
    nome = (locatario.nome or "").strip()
    if nome:
        melhor_empresa: Empresa | None = None
        for empresa in empresas:
            for candidato in _nomes_candidatos(empresa):
                score = similaridade(nome, candidato)
                if score > melhor_score:
                    melhor_score = score
                    melhor_empresa = empresa
        if melhor_empresa is not None and melhor_score >= threshold:
            return ResultadoMatch(
                empresa=melhor_empresa,
                status=StatusMatch.ENCONTRADO,
                metodo=MetodoMatch.FUZZY,
                score=melhor_score,
            )

    # 3) Nem CNPJ nem fuzzy resolveram → status estrito NAO_ENCONTRADO.
    return ResultadoMatch(
        empresa=None,
        status=StatusMatch.NAO_ENCONTRADO,
        metodo=MetodoMatch.NENHUM,
        score=melhor_score,
    )
