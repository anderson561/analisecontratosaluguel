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
  ``valor_aluguel`` + ``locador.tipo`` + ``locatario.tipo`` + a
  :class:`TabelaIRRF` injetada (default: a factory oficial 2026). Só Locador
  PF × Locatário PJ retém; Locador PJ ⇒ R$ 0,00 (prevalece sobre o
  locatário); Locador PF × Locatário PF ⇒ R$ 0,00 (carnê-leão).
- **Locatário sem tipo:** se casou com uma empresa do portfólio (mesmo match
  CNPJ/fuzzy do Relatório 02, reaproveitado da única leitura do portfólio em
  :meth:`RelatorioService.montar`), é tratado como PJ; senão, ``irrf=None``.
- **Resiliência (§6):** contrato sem valor de aluguel, sem tipo de locador ou
  (Locador PF) com locatário sem tipo e fora do portfólio não quebra a
  montagem — a linha fica com ``irrf=None`` (revisão manual).
"""
from __future__ import annotations

from contract_parser.application.portfolio_validation_service import (
    PortfolioValidacaoResumo,
    PortfolioValidationService,
)
from contract_parser.domain.contrato import Contrato, TipoParte
from contract_parser.domain.irrf import TabelaIRRF, calcular_irrf, tabela_irrf_2026
from contract_parser.domain.match_portfolio import (
    ResultadoMatch,
    SimilaridadeFn,
    similaridade_padrao,
)
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
    @staticmethod
    def _tipo_locatario(contrato: Contrato, match: ResultadoMatch) -> TipoParte | None:
        """Tipo do locatário; sem tipo mas casado no portfólio ⇒ PJ (empresa)."""
        if contrato.locatario.tipo is None and match.encontrado:
            return TipoParte.PJ
        return contrato.locatario.tipo

    def _linha(self, contrato: Contrato, match: ResultadoMatch) -> LinhaContrato:
        """Monta uma linha do Relatório 01 calculando o IRRF do contrato."""
        valor = contrato.valor_aluguel
        tipo_locador = contrato.locador.tipo
        tipo_locatario = self._tipo_locatario(contrato, match)

        # IRRF exige valor de aluguel E tipo do locador (§6) e, para Locador
        # PF, também o tipo do locatário (só PF × PJ retém). Faltando qualquer
        # um, a linha vai para revisão (irrf=None). Locador PJ ⇒ R$ 0,00
        # qualquer que seja o locatário.
        irrf = None
        if (
            valor is not None
            and tipo_locador is not None
            and (tipo_locador is TipoParte.PJ or tipo_locatario is not None)
        ):
            irrf = calcular_irrf(
                base_mensal=valor,
                tipo_locador=tipo_locador,
                # Sem tipo só chega aqui com Locador PJ, que prevalece.
                tipo_locatario=tipo_locatario or TipoParte.PJ,
                tabela=self._tabela,
            )

        return LinhaContrato(
            locatario_nome=contrato.locatario.nome,
            locatario_cnpj=contrato.locatario.documento,
            locador_nome=contrato.locador.nome,
            locadores_adicionais=tuple(contrato.locadores_adicionais),
            valor_aluguel=valor,
            irrf=irrf,
            indice=contrato.reajuste.indice,
            indice_fonte=contrato.reajuste.indice_fonte,
            proximo_reajuste=contrato.reajuste.proximo_reajuste,
            reajuste_automatico=contrato.reajuste.automatico,
            despesas=contrato.despesas,
            prorrogacao_automatica=contrato.prorrogacao.automatica,
            prorrogacao_prazo_meses=contrato.prorrogacao.prazo_meses,
            vencimento=contrato.data_fim_vigencia,
            carencia_meses=contrato.carencia_meses,
        )

    def _relatorio_contratos(
        self, contratos: list[Contrato], resumo_portfolio: PortfolioValidacaoResumo
    ) -> RelatorioContratos:
        pares = zip(contratos, resumo_portfolio.matches_por_contrato, strict=True)
        return RelatorioContratos(
            linhas=[self._linha(c, m) for c, m in pares],
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
        # Uma única leitura do portfólio serve aos dois relatórios.
        resumo_portfolio = self._portfolio.validar(contratos)
        return Relatorio(
            contratos=self._relatorio_contratos(contratos, resumo_portfolio),
            conformidade=self._resumo_conformidade(resumo_portfolio),
        )
