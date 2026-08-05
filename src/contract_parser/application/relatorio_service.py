"""Serviço de montagem dos relatórios (camada application) — RF06.

Transforma a lista de :class:`~contract_parser.domain.contrato.Contrato`
processados (mais o portfólio cadastrado) nas estruturas de domínio dos dois
relatórios do PRD. NÃO conhece formato de saída (Excel/PDF): apenas monta os
dados; a materialização em arquivo é dos exportadores em ``infrastructure``.

Decisões de camada (espelham ``portfolio_validation_service``):

- **Reuso, não reimplementação:** o Relatório 02 (conformidade) delega ao
  :class:`PortfolioValidationService` da Fase 6 — o match de empresas e a
  mensagem exata de pendência não são reescritos aqui.
- **IRRF por linha:** cada contrato tem seu IRRF calculado por
  :func:`~contract_parser.domain.irrf.calcular_irrf` a partir de
  ``valor_aluguel`` + ``locador.tipo`` + a :class:`TabelaIRRF` injetada
  (default: a factory oficial 2026). Locador PJ ⇒ R$ 0,00 (regra do motor).
- **Resiliência (§6):** contrato sem valor de aluguel ou sem tipo de locador
  não quebra a montagem — a linha fica com ``irrf=None`` (revisão manual).
"""
from __future__ import annotations

from contract_parser.application.portfolio_validation_service import (
    PortfolioValidacaoResumo,
    PortfolioValidationService,
)
from contract_parser.domain.contrato import Contrato
from contract_parser.domain.irrf import TabelaIRRF, calcular_irrf, tabela_irrf_2026
from contract_parser.domain.match_portfolio import SimilaridadeFn, similaridade_padrao
from contract_parser.domain.relatorio import (
    LinhaContrato,
    Relatorio,
    RelatorioContratos,
    ResumoConformidade,
)
from contract_parser.domain.repositories import EmpresaRepositoryProtocol


class RelatorioService:
    """Caso de uso: montar os Relatórios 01 e 02 a partir dos contratos."""

    def __init__(
        self,
        repository: EmpresaRepositoryProtocol,
        *,
        tabela: TabelaIRRF | None = None,
        threshold: float | None = None,
        similaridade: SimilaridadeFn = similaridade_padrao,
    ) -> None:
        self._tabela = tabela if tabela is not None else tabela_irrf_2026()
        self._portfolio = PortfolioValidationService(
            repository, threshold=threshold, similaridade=similaridade
        )

    # -- Relatório 01 ------------------------------------------------------- #
    def _linha(self, contrato: Contrato) -> LinhaContrato:
        """Monta uma linha do Relatório 01 calculando o IRRF do contrato."""
        valor = contrato.valor_aluguel
        tipo_locador = contrato.locador.tipo

        # IRRF só é calculável com valor de aluguel E tipo do locador (§6):
        # o motor exige ambos; faltando qualquer um, a linha vai para revisão.
        irrf = None
        if valor is not None and tipo_locador is not None:
            irrf = calcular_irrf(
                base_mensal=valor, tipo_locador=tipo_locador, tabela=self._tabela
            )

        return LinhaContrato(
            locatario_nome=contrato.locatario.nome,
            locatario_cnpj=contrato.locatario.documento,
            locador_nome=contrato.locador.nome,
            valor_aluguel=valor,
            irrf=irrf,
            indice=contrato.reajuste.indice,
            proximo_reajuste=contrato.reajuste.proximo_reajuste,
            reajuste_automatico=contrato.reajuste.automatico,
            vencimento=contrato.data_fim_vigencia,
        )

    def _relatorio_contratos(self, contratos: list[Contrato]) -> RelatorioContratos:
        return RelatorioContratos(
            linhas=[self._linha(c) for c in contratos],
            tabela_vigencia=self._tabela.vigencia,
        )

    # -- Relatório 02 ------------------------------------------------------- #
    def _resumo_conformidade(
        self, resumo_portfolio: PortfolioValidacaoResumo
    ) -> ResumoConformidade:
        return ResumoConformidade(
            total_empresas_cadastradas=resumo_portfolio.total_empresas,
            total_contratos_localizados=resumo_portfolio.total_contratos,
            total_encontrados=resumo_portfolio.total_encontrados,
            pendencias=list(resumo_portfolio.pendencias),
        )

    # -- Orquestração ------------------------------------------------------- #
    def montar(self, contratos: list[Contrato]) -> Relatorio:
        """Monta os dois relatórios do PRD a partir dos contratos processados."""
        resumo_portfolio = self._portfolio.validar(contratos)
        return Relatorio(
            contratos=self._relatorio_contratos(contratos),
            conformidade=self._resumo_conformidade(resumo_portfolio),
        )
