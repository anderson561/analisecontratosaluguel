"""Modelo de domínio dos relatórios (RF06) — camada domain, sem IO.

Estruturas puras que descrevem o CONTEÚDO dos dois relatórios do PRD,
desacopladas de qualquer formato de saída (Excel/PDF ficam em infrastructure):

- **Relatório 01 — contratos encontrados** (:class:`RelatorioContratos`): uma
  :class:`LinhaContrato` por contrato processado, com o IRRF já calculado (a
  memória de cálculo completa, :class:`~contract_parser.domain.irrf.ResultadoIRRF`,
  fica anexada à linha; a retenção em reais é derivada dela).
- **Relatório 02 — resumo de conformidade** (:class:`ResumoConformidade`): totais
  do portfólio + lista de pendências com a mensagem EXATA do PRD (produzida por
  :func:`~contract_parser.domain.match_portfolio.mensagem_pendencia`).

Os valores são guardados em tipos "crus" (``Decimal``, ``date``, ``str``): a
formatação pt-BR (R$ 1.234,56 / dd/mm/aaaa) é responsabilidade da APRESENTAÇÃO
(os exportadores), não deste modelo — mantendo montagem e formato desacoplados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol, runtime_checkable

from contract_parser.domain.irrf import ResultadoIRRF

_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class LinhaContrato:
    """Uma linha do Relatório 01 (um contrato processado).

    ``irrf`` carrega a memória de cálculo completa quando foi possível calcular
    (valor do aluguel e tipo do locador presentes); fica ``None`` quando faltam
    dados — a coluna vira "revisão"/vazio na apresentação, sem quebrar o lote.
    """

    locatario_nome: str | None
    locatario_cnpj: str | None
    locador_nome: str | None
    valor_aluguel: Decimal | None
    irrf: ResultadoIRRF | None
    indice: str | None
    proximo_reajuste: str | None
    reajuste_automatico: bool
    vencimento: date | None  # data_fim_vigencia (§4: "Vencimento" = fim da vigência)

    @property
    def irrf_retido(self) -> Decimal:
        """Valor do IRRF retido em reais (R$ 0,00 quando não calculado/PJ)."""
        return self.irrf.imposto if self.irrf is not None else _ZERO

    @property
    def dados_incompletos(self) -> bool:
        """``True`` quando faltou dado essencial para o IRRF (revisão manual)."""
        return self.valor_aluguel is None or self.irrf is None


@dataclass(frozen=True)
class RelatorioContratos:
    """Relatório 01 completo: as linhas + a versão da tabela IRRF aplicada."""

    linhas: list[LinhaContrato] = field(default_factory=list)
    tabela_vigencia: str = ""

    @property
    def total_contratos(self) -> int:
        return len(self.linhas)

    @property
    def total_irrf_retido(self) -> Decimal:
        """Somatório do IRRF retido de todas as linhas (para rodapé/total)."""
        total = _ZERO
        for linha in self.linhas:
            total += linha.irrf_retido
        return total


@dataclass(frozen=True)
class ResumoConformidade:
    """Relatório 02: totais do portfólio + pendências (mensagem exata do PRD)."""

    total_empresas_cadastradas: int
    total_contratos_localizados: int
    total_encontrados: int
    pendencias: list[str] = field(default_factory=list)

    @property
    def total_pendencias(self) -> int:
        return len(self.pendencias)


@dataclass(frozen=True)
class Relatorio:
    """Agregado dos dois relatórios do PRD, pronto para qualquer exportador."""

    contratos: RelatorioContratos
    conformidade: ResumoConformidade


@runtime_checkable
class RelatorioExporter(Protocol):
    """Interface simples de exportação (implementada na camada infrastructure).

    Recebe o :class:`Relatorio` de domínio e materializa um arquivo em
    ``destino``, devolvendo o caminho efetivamente escrito. As libs pesadas
    (openpyxl/reportlab) ficam atrás desta abstração, com import preguiçoso.
    """

    def exportar(self, relatorio: Relatorio, destino: Path) -> Path:
        """Escreve o relatório em ``destino`` e retorna o caminho gerado."""
        ...
