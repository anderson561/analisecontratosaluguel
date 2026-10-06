"""Testes de calcular_proximo_reajuste_anual (domain puro — referência explícita)."""
from __future__ import annotations

from datetime import date

import pytest

from contract_parser.domain.reajuste_calc import calcular_proximo_reajuste_anual

HOJE = date(2026, 10, 6)


@pytest.mark.parametrize(
    ("inicio", "meses", "referencia", "esperado"),
    [
        pytest.param(date(2024, 3, 1), 12, HOJE, date(2027, 3, 1), id="varios-anos-passados"),
        pytest.param(date(2027, 1, 15), 12, HOJE, date(2028, 1, 15), id="inicio-futuro-soma-um-periodo"),
        pytest.param(date(2024, 3, 1), 12, date(2026, 3, 1), date(2026, 3, 1), id="aniversario-inclusivo"),
        pytest.param(date(2024, 3, 1), 12, date(2026, 3, 2), date(2027, 3, 1), id="dia-apos-aniversario"),
        pytest.param(date(2024, 2, 29), 12, HOJE, date(2027, 2, 28), id="bissexto-clamp-fev"),
        pytest.param(date(2024, 2, 29), 12, date(2027, 10, 1), date(2028, 2, 29), id="bissexto-volta-dia-29"),
        pytest.param(date(2024, 3, 1), 6, HOJE, date(2027, 3, 1), id="semestral"),
        pytest.param(date(2024, 1, 31), 1, date(2024, 3, 15), date(2024, 3, 31), id="sem-deriva-fim-de-mes"),
        pytest.param(date(2010, 5, 10), 12, HOJE, date(2027, 5, 10), id="muitos-anos-decorridos"),
    ],
)
def test_proximo_reajuste(inicio, meses, referencia, esperado):
    assert calcular_proximo_reajuste_anual(inicio, meses, referencia) == esperado


@pytest.mark.parametrize("meses", [0, -12])
def test_periodicidade_invalida_devolve_none(meses):
    assert calcular_proximo_reajuste_anual(date(2024, 3, 1), meses, HOJE) is None
