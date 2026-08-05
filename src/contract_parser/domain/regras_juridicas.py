"""Regras jurídicas de conformidade (camada domain — puras, sem IO) — RF03/§3.

Calcula as :class:`~contract_parser.domain.contrato.FlagsJuridicas` a partir dos
campos já extraídos e do texto bruto (para detectar cláusulas abusivas por
redação). Determinístico e auditável — a base legal de cada flag está documentada.

Base legal (Lei nº 8.245/91):
- **Art. 37, parágrafo único:** é vedada mais de uma modalidade de garantia no
  mesmo contrato → ``violacao_art37_multiplas_garantias``.
- **Art. 17/18:** reajuste não pode ser atrelado a salário mínimo ou moeda
  estrangeira, nem ter periodicidade inferior a 12 meses.
- **Arts. 35/36:** benfeitorias necessárias são indenizáveis; cláusula de
  renúncia é reputada abusiva (Súmula 335 do STJ ressalva a validade contratual,
  mas o sistema sinaliza para conferência do operador).
- Cumulação de multa compensatória/rescisória com outra multa pelo mesmo fato
  (*bis in idem*) é sinalizada como abusiva.
"""
from __future__ import annotations

import re

from contract_parser.domain.contrato import (
    FlagsJuridicas,
    ModalidadeGarantia,
    Reajuste,
)

# Cláusula de renúncia a benfeitorias necessárias (Arts. 35/36).
_RE_RENUNCIA_BENFEITORIAS = re.compile(
    r"(?:ren[úu]ncia\w*|renuncia\w*|abre\s+m[ãa]o|n[ãa]o\s+(?:ter[áa]|far[áa]\s+jus|caber[áa]))"
    r"[^.\n]{0,80}?benfeitoria",
    re.IGNORECASE,
)
# Cumulação explícita de multas pelo mesmo fato (bis in idem).
_RE_CUMULACAO_MULTAS = re.compile(
    r"cumulativ\w*[^.\n]{0,40}?multa|multa[^.\n]{0,40}?cumulativ\w*"
    r"|multa\s+compensat[óo]ria[^.\n]{0,60}?multa\s+(?:morat[óo]ria|penal|rescis[óo]ria)",
    re.IGNORECASE,
)


def _indice_vedado(indice: str | None) -> bool:
    if not indice:
        return False
    alvo = indice.strip().lower()
    return "mínimo" in alvo or "minimo" in alvo or "estrangeira" in alvo


def avaliar_flags(
    *,
    garantias: list[ModalidadeGarantia] | None,
    reajuste: Reajuste,
    texto: str,
) -> FlagsJuridicas:
    """Calcula as flags jurídicas de forma determinística.

    Não infere nada probabilístico: cada flag decorre de uma condição objetiva
    sobre os campos extraídos ou de um padrão de redação inequívoco.
    """
    alertas: list[str] = []
    garantias = garantias or []

    # Art. 37: mais de uma modalidade de garantia.
    multiplas_garantias = len(set(garantias)) > 1
    if multiplas_garantias:
        nomes = ", ".join(sorted(g.value for g in set(garantias)))
        alertas.append(
            f"Art. 37: vedada a cumulação de garantias — {len(set(garantias))} "
            f"modalidades detectadas ({nomes})."
        )

    # Art. 18: índice vedado.
    indice_vedado = _indice_vedado(reajuste.indice)
    if indice_vedado:
        alertas.append(
            f"Art. 18: índice de reajuste vedado ('{reajuste.indice}') — "
            "salário mínimo/moeda estrangeira são proibidos."
        )

    # Art. 18: periodicidade inferior a 12 meses.
    periodicidade_curta = (
        reajuste.periodicidade_meses is not None and reajuste.periodicidade_meses < 12
    )
    if periodicidade_curta:
        alertas.append(
            f"Art. 18: periodicidade de reajuste inferior a 12 meses "
            f"({reajuste.periodicidade_meses} meses)."
        )

    # Arts. 35/36: renúncia a benfeitorias necessárias.
    renuncia = bool(_RE_RENUNCIA_BENFEITORIAS.search(texto or ""))
    if renuncia:
        alertas.append(
            "Cláusula potencialmente abusiva: renúncia a indenização por "
            "benfeitorias necessárias (Arts. 35/36)."
        )

    # Cumulação de multas (bis in idem).
    cumulacao = bool(_RE_CUMULACAO_MULTAS.search(texto or ""))
    if cumulacao:
        alertas.append(
            "Cláusula potencialmente abusiva: cumulação de multas pelo mesmo "
            "fato (bis in idem)."
        )

    return FlagsJuridicas(
        violacao_art37_multiplas_garantias=multiplas_garantias,
        indice_vedado_art18=indice_vedado,
        periodicidade_inferior_12m_art18=periodicidade_curta,
        renuncia_benfeitorias_necessarias=renuncia,
        cumulacao_multas_bis_in_idem=cumulacao,
        alertas=alertas,
    )
