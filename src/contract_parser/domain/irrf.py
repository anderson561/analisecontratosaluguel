"""Motor de cálculo de IRRF sobre aluguel (RF04 → CA-03) — camada domain, sem IO.

Núcleo fiscal da Fase 5. É código de domínio **puro**: modela a tabela
progressiva mensal da RFB, calcula o imposto e produz uma **memória de cálculo**
auditável. Não faz IO, não importa infraestrutura nem rede — a tabela é injetada
(persistida/revalidada pela camada de infraestrutura).

Regras de negócio (§4 dos requisitos, D5 do ADR-001):

- IRRF sobre aluguel só é retido quando **Locador PF × Locatário PJ**. Locador
  PJ ⇒ IRRF = R$ 0,00 (não retido nesta modalidade).
- Fórmula: ``IRRF = base_mensal × alíquota − parcela_dedução`` (da faixa em que a
  base cai). Faixa isenta ⇒ R$ 0,00; resultado nunca é negativo.
- Rigor monetário: todos os valores são :class:`~decimal.Decimal`. O imposto é
  arredondado a 2 casas com ``ROUND_HALF_UP`` (padrão fiscal), nunca ``float``.
- A tabela é **versionada** (``vigencia``) e traz proveniência (``fonte_url``,
  ``base_legal``) — a memória de cálculo registra qual versão foi aplicada.

Base 2026: Lei nº 15.191/2025, vigência a partir de jan/2026 (ver
:func:`tabela_irrf_2026`). Valores fornecidos pela RFB via PM/Orquestrador.

Redutor da Lei nº 15.270/2025 (Art. 3º-A da Lei nº 9.250/1995) — ATIVO:
    A partir de jan/2026, uma **redução adicional** é aplicada sobre o imposto
    já calculado pela tabela progressiva padrão, para rendimentos mensais de
    até R$ 7.350,00 (:func:`calcular_reducao_lei_15270`). ``calcular_irrf``
    aplica essa redução automaticamente (Locador PF), antes do arredondamento
    final. A fórmula, a fonte legal e os exemplos numéricos de conferência
    estão documentados em ``.agent/specs/adr-003-redutor-irrf-2026.md``
    (decisão registrada: aluguel não tem direito ao desconto simplificado que
    o salário tem, então o CA-03 em base R$ 5.000,00 é R$ 153,38 — não R$ 0,00
    nem R$ 466,27).
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contract_parser.domain.contrato import TipoParte

# Quantum monetário: 2 casas decimais (centavos).
_CENTAVO = Decimal("0.01")
_ZERO = Decimal("0.00")


def _arredondar_moeda(valor: Decimal) -> Decimal:
    """Arredonda para 2 casas com ROUND_HALF_UP (padrão fiscal brasileiro)."""
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


class Faixa(BaseModel):
    """Uma faixa da tabela progressiva mensal.

    ``maximo=None`` marca a **última** faixa (aberta, "acima de"). ``aliquota`` é
    uma fração (ex.: ``Decimal("0.275")`` para 27,5%); ``deducao`` é a parcela a
    deduzir em reais.
    """

    model_config = ConfigDict(extra="forbid")

    minimo: Decimal
    maximo: Decimal | None
    aliquota: Decimal = Field(ge=0)
    deducao: Decimal = Field(ge=0)

    @property
    def isenta(self) -> bool:
        return self.aliquota == 0

    @property
    def descricao(self) -> str:
        """Rótulo legível para a memória de cálculo/relatório."""
        pct = (self.aliquota * 100).normalize()
        if self.maximo is None:
            return f"acima de {self.minimo} — {pct}%"
        return f"de {self.minimo} até {self.maximo} — {pct}%"

    def contem(self, base: Decimal) -> bool:
        """``True`` se ``base`` cai nesta faixa (limite superior inclusivo)."""
        if base < self.minimo:
            return False
        return self.maximo is None or base <= self.maximo


class TabelaIRRF(BaseModel):
    """Tabela progressiva mensal versionada do IRRF (persistível no Mongo).

    As faixas são mantidas ordenadas por ``minimo`` e a última deve ser aberta
    (``maximo=None``), cobrindo qualquer base ≥ 0 sem lacunas.
    """

    model_config = ConfigDict(extra="forbid")

    vigencia: str = Field(min_length=1)  # ex.: "2026"
    faixas: list[Faixa] = Field(min_length=1)
    fonte_url: str
    base_legal: str
    validado: bool = False
    validado_em: date | None = None

    @model_validator(mode="after")
    def _validar_faixas(self) -> TabelaIRRF:
        # Ordena por mínimo (determinístico) e valida a topologia da tabela.
        self.faixas.sort(key=lambda f: f.minimo)
        if self.faixas[-1].maximo is not None:
            raise ValueError("A última faixa da tabela deve ser aberta (maximo=None).")
        for anterior in self.faixas[:-1]:
            if anterior.maximo is None:
                raise ValueError("Apenas a última faixa pode ter maximo=None.")
        return self

    def faixa_para(self, base: Decimal) -> Faixa:
        """Retorna a faixa em que ``base`` cai (primeira cujo teto a cobre).

        Seleciona pelo limite superior (inclusivo) para não deixar lacuna nos
        centavos de fronteira entre faixas.
        """
        if base < 0:
            raise ValueError("Base de cálculo do IRRF não pode ser negativa.")
        for faixa in self.faixas:
            if faixa.maximo is None or base <= faixa.maximo:
                return faixa
        # Inatingível: a última faixa é aberta (garantido pelo validador).
        return self.faixas[-1]


class ResultadoIRRF(BaseModel):
    """Resultado do cálculo + **memória de cálculo** auditável (persistível).

    Serializável (pydantic/Decimal) para embutir em ``contratos.irrf`` no Mongo.
    """

    model_config = ConfigDict(extra="forbid")

    retido: bool
    imposto: Decimal
    base_calculo: Decimal
    aliquota: Decimal
    deducao: Decimal
    faixa_descricao: str
    tabela_vigencia: str
    base_legal: str
    fonte_url: str
    observacao: str = ""
    # Memória de cálculo do redutor da Lei nº 15.270/2025 (ADR-003): o imposto
    # da tabela padrão ANTES da redução e o valor efetivamente reduzido.
    # `imposto == imposto_antes_reducao - reducao_aplicada` sempre que retido.
    imposto_antes_reducao: Decimal = _ZERO
    reducao_aplicada: Decimal = _ZERO


def calcular_irrf(
    *,
    base_mensal: Decimal,
    tipo_locador: TipoParte,
    tabela: TabelaIRRF,
) -> ResultadoIRRF:
    """Calcula o IRRF retido sobre o aluguel e devolve a memória de cálculo.

    Parameters
    ----------
    base_mensal:
        Valor mensal do aluguel (base de cálculo). ``Decimal`` — nunca ``float``.
    tipo_locador:
        ``TipoParte.PF`` ou ``TipoParte.PJ``. Só PF (locador) → PJ (locatário)
        gera retenção; Locador PJ ⇒ R$ 0,00.
    tabela:
        :class:`TabelaIRRF` vigente (injetada pela infraestrutura).

    Redutor da Lei nº 15.270/2025: para Locador PF, o redutor progressivo para
    rendimentos ≤ R$ 7.350,00 (:func:`calcular_reducao_lei_15270`) é aplicado
    sobre o imposto da tabela padrão, antes do arredondamento final. Ver
    ADR-003 para a fórmula e os valores de referência.
    """
    base = _arredondar_moeda(base_mensal)

    # Regra de negócio: retenção só em Locador PF × Locatário PJ.
    if tipo_locador is TipoParte.PJ:
        return ResultadoIRRF(
            retido=False,
            imposto=_ZERO,
            base_calculo=base,
            aliquota=_ZERO,
            deducao=_ZERO,
            faixa_descricao="não aplicável (locador PJ)",
            tabela_vigencia=tabela.vigencia,
            base_legal=tabela.base_legal,
            fonte_url=tabela.fonte_url,
            observacao=(
                "IRRF não retido: aluguel pago a locador PJ não sofre retenção "
                "nesta modalidade (RF04)."
            ),
            imposto_antes_reducao=_ZERO,
            reducao_aplicada=_ZERO,
        )

    faixa = tabela.faixa_para(base)
    bruto = base * faixa.aliquota - faixa.deducao
    # Nunca negativo (faixa isenta ou arredondamento de fronteira).
    imposto_antes_reducao = _arredondar_moeda(max(_ZERO, bruto))

    # Redutor da Lei nº 15.270/2025 (Art. 3º-A) — aplicado ao imposto já
    # calculado pela tabela padrão, nunca gera imposto negativo (ADR-003).
    reducao_teorica = calcular_reducao_lei_15270(base)
    imposto = _arredondar_moeda(max(_ZERO, imposto_antes_reducao - reducao_teorica))
    reducao_aplicada = imposto_antes_reducao - imposto

    if faixa.isenta:
        observacao = "Faixa isenta: IRRF = R$ 0,00."
    elif reducao_aplicada > _ZERO:
        observacao = (
            f"IRRF = {base} × {faixa.aliquota} − {faixa.deducao} = "
            f"{imposto_antes_reducao}; reduzido em {reducao_aplicada} pela "
            f"Lei nº 15.270/2025 → {imposto}."
        )
    else:
        observacao = f"IRRF = {base} × {faixa.aliquota} − {faixa.deducao} = {imposto}."

    return ResultadoIRRF(
        retido=imposto > 0,
        imposto=imposto,
        base_calculo=base,
        aliquota=faixa.aliquota,
        deducao=faixa.deducao,
        faixa_descricao=faixa.descricao,
        tabela_vigencia=tabela.vigencia,
        base_legal=tabela.base_legal,
        fonte_url=tabela.fonte_url,
        observacao=observacao,
        imposto_antes_reducao=imposto_antes_reducao,
        reducao_aplicada=reducao_aplicada,
    )


_TETO_REDUCAO_INTEGRAL = Decimal("5000.00")
_TETO_REDUCAO_PROGRESSIVA = Decimal("7350.00")
_REDUCAO_MAXIMA = Decimal("312.89")
_REDUCAO_COEFICIENTE_FIXO = Decimal("978.62")
_REDUCAO_COEFICIENTE_LINEAR = Decimal("0.133145")


def calcular_reducao_lei_15270(rendimento: Decimal) -> Decimal:
    """Redutor de IRRF da Lei nº 15.270/2025 (Art. 3º-A da Lei nº 9.250/1995).

    Redução do imposto mensal, calculada sobre o **rendimento tributável**
    (aqui, ``base_mensal`` do aluguel — sem desconto simplificado prévio, que
    não se aplica a esta modalidade; ver ADR-003 §3):

    - ``rendimento <= R$ 5.000,00``: redução fixa de R$ 312,89.
    - ``R$ 5.000,01 <= rendimento <= R$ 7.350,00``:
      ``978,62 − (0,133145 × rendimento)`` (decrescente até zerar em R$ 7.350).
    - ``rendimento > R$ 7.350,00``: sem redução (R$ 0,00).

    Retorna o valor **teórico** da tabela do Art. 3º-A — quem garante que o
    imposto final nunca fica negativo é :func:`calcular_irrf` (``max(0, ...)``,
    §1º do artigo). Fonte e exemplos de conferência:
    ``.agent/specs/adr-003-redutor-irrf-2026.md``.
    """
    if rendimento <= _TETO_REDUCAO_INTEGRAL:
        return _REDUCAO_MAXIMA
    if rendimento <= _TETO_REDUCAO_PROGRESSIVA:
        bruto = _REDUCAO_COEFICIENTE_FIXO - (_REDUCAO_COEFICIENTE_LINEAR * rendimento)
        return _arredondar_moeda(max(_ZERO, bruto))
    return _ZERO


def tabela_irrf_2026() -> TabelaIRRF:
    """Factory da tabela progressiva MENSAL oficial do IRRF 2026.

    Valores EXATOS fornecidos pela RFB (via PM), base legal Lei nº 15.191/2025,
    vigência a partir de jan/2026. ``validado=True`` porque conferida contra a
    fonte oficial no início da Fase 5 (D5 do ADR-001).

    Fonte: https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026
    """
    return TabelaIRRF(
        vigencia="2026",
        fonte_url=(
            "https://www.gov.br/receitafederal/pt-br/assuntos/"
            "meu-imposto-de-renda/tabelas/2026"
        ),
        base_legal="Lei nº 15.191/2025",
        validado=True,
        validado_em=date(2026, 1, 1),
        faixas=[
            Faixa(
                minimo=Decimal("0.00"),
                maximo=Decimal("2428.80"),
                aliquota=Decimal(0),
                deducao=Decimal("0.00"),
            ),
            Faixa(
                minimo=Decimal("2428.81"),
                maximo=Decimal("2826.65"),
                aliquota=Decimal("0.075"),
                deducao=Decimal("182.16"),
            ),
            Faixa(
                minimo=Decimal("2826.66"),
                maximo=Decimal("3751.05"),
                aliquota=Decimal("0.15"),
                deducao=Decimal("394.16"),
            ),
            Faixa(
                minimo=Decimal("3751.06"),
                maximo=Decimal("4664.68"),
                aliquota=Decimal("0.225"),
                deducao=Decimal("675.49"),
            ),
            Faixa(
                minimo=Decimal("4664.69"),
                maximo=None,
                aliquota=Decimal("0.275"),
                deducao=Decimal("908.73"),
            ),
        ],
    )


@runtime_checkable
class AtualizadorTabelaRFB(Protocol):
    """Contrato (Protocol) do serviço de revalidação da tabela contra a RFB.

    Peça do fluxo "botão de revalidar tabela IRRF" (RF04/§6). O domínio define
    apenas *o quê* (buscar/validar e devolver uma :class:`TabelaIRRF`); *como*
    (rede, scraping da página oficial) fica na infraestrutura, atrás desta
    abstração. A produção é um stub que documenta a fonte e falha explicitamente
    até a integração de rede ser habilitada; os testes injetam um FAKE.
    """

    def buscar_tabela_vigente(self) -> TabelaIRRF:
        """Busca e valida a tabela vigente na fonte oficial da RFB."""
        ...
