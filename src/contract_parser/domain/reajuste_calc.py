"""Cálculo puro da próxima data de reajuste (camada domain — sem IO, sem relógio).

A "data de hoje" é sempre o parâmetro ``referencia``; quem decide qual é fica com o chamador.
"""
from __future__ import annotations

import calendar
from datetime import date


def _somar_meses(base: date, meses: int) -> date:
    indice = base.year * 12 + (base.month - 1) + meses
    ano, mes = divmod(indice, 12)
    mes += 1
    return date(ano, mes, min(base.day, calendar.monthrange(ano, mes)[1]))


def calcular_proximo_reajuste_anual(
    data_inicio: date, periodicidade_meses: int, referencia: date
) -> date | None:
    """Primeira data ``data_inicio + k * periodicidade`` (k >= 1) que seja ``>= referencia``.

    Devolve ``None`` se a periodicidade não for positiva.
    """
    if periodicidade_meses <= 0:
        return None
    meses_ate_referencia = (referencia.year - data_inicio.year) * 12 + (
        referencia.month - data_inicio.month
    )
    k = max(1, meses_ate_referencia // periodicidade_meses)
    # Sempre a partir do início original: encadear candidatas ajustadas derivaria o dia
    # (31/jan +1 mês = 29/fev, e daí 29/mar em vez de 31/mar).
    candidata = _somar_meses(data_inicio, k * periodicidade_meses)
    while candidata < referencia:
        k += 1
        candidata = _somar_meses(data_inicio, k * periodicidade_meses)
    return candidata
