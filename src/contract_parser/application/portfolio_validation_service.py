"""Serviço de validação de portfólio (camada application) — RF05 → CA-04.

Cruza o portfólio cadastrado (via ``EmpresaRepositoryProtocol``) com o conjunto
de contratos processados e produz um resumo estruturado:

- status por empresa cadastrada (``ENCONTRADO`` × ``NAO_ENCONTRADO``);
- lista de **pendências** — empresas sem NENHUM contrato correspondente, com a
  mensagem exata do PRD (``mensagem_pendencia``);
- contratos cujo locatário não casou com nenhuma empresa (diagnóstico).

Espelha o padrão de ``document_ingestor``/``empresa_importer``: depende apenas
da abstração de repositório (nunca de pymongo), acumula resultado em um resumo
estruturado (em vez de exceções) e a ordem de saída é determinística (segue a
ordem de ``list_all`` do repositório).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from contract_parser.config import settings
from contract_parser.domain.contrato import Contrato
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.match_portfolio import (
    MetodoMatch,
    ResultadoMatch,
    SimilaridadeFn,
    StatusMatch,
    casar_contrato,
    mensagem_pendencia,
    similaridade_padrao,
)
from contract_parser.domain.repositories import EmpresaRepositoryProtocol


@dataclass
class EmpresaStatus:
    """Status de uma empresa cadastrada frente aos contratos processados."""

    empresa: Empresa
    status: StatusMatch
    metodo: MetodoMatch
    score: float
    contratos_correspondentes: int

    @property
    def encontrado(self) -> bool:
        return self.status is StatusMatch.ENCONTRADO


@dataclass
class ContratoSemEmpresa:
    """Contrato cujo locatário não casou com nenhuma empresa do portfólio."""

    locatario_nome: str | None
    locatario_documento: str | None
    melhor_score: float


@dataclass
class PortfolioValidacaoResumo:
    """Resumo estruturado da validação de portfólio (CA-04)."""

    threshold: float
    total_contratos: int = 0
    empresas_status: list[EmpresaStatus] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    contratos_sem_empresa: list[ContratoSemEmpresa] = field(default_factory=list)

    @property
    def total_empresas(self) -> int:
        return len(self.empresas_status)

    @property
    def total_encontrados(self) -> int:
        return sum(1 for e in self.empresas_status if e.encontrado)

    @property
    def total_pendencias(self) -> int:
        return len(self.pendencias)


def _prioridade(resultado: ResultadoMatch) -> tuple[int, float]:
    """Chave de desempate: match por CNPJ vence fuzzy; depois, maior score."""
    return (1 if resultado.metodo is MetodoMatch.CNPJ else 0, resultado.score)


class PortfolioValidationService:
    """Caso de uso: validar o portfólio cadastrado contra contratos processados."""

    def __init__(
        self,
        repository: EmpresaRepositoryProtocol,
        *,
        threshold: float | None = None,
        similaridade: SimilaridadeFn = similaridade_padrao,
    ) -> None:
        self._repo = repository
        self._threshold = (
            threshold if threshold is not None else float(settings.fuzzy_match_threshold)
        )
        self._similaridade = similaridade

    def validar(self, contratos: list[Contrato]) -> PortfolioValidacaoResumo:
        """Cruza portfólio × contratos e devolve o resumo estruturado.

        Para CADA empresa cadastrada, verifica se há ao menos um contrato
        correspondente; as sem contrato viram pendências. Contratos cujo
        locatário não casa com nenhuma empresa são listados à parte.
        """
        empresas = self._repo.list_all()
        resumo = PortfolioValidacaoResumo(
            threshold=self._threshold, total_contratos=len(contratos)
        )

        # Agrupa os matches por CNPJ da empresa casada (chave canônica única).
        matches_por_cnpj: dict[str, list[ResultadoMatch]] = defaultdict(list)
        for contrato in contratos:
            resultado = casar_contrato(
                contrato,
                empresas,
                threshold=self._threshold,
                similaridade=self._similaridade,
            )
            if resultado.empresa is not None:
                matches_por_cnpj[resultado.empresa.cnpj].append(resultado)
            else:
                resumo.contratos_sem_empresa.append(
                    ContratoSemEmpresa(
                        locatario_nome=contrato.locatario.nome,
                        locatario_documento=contrato.locatario.documento,
                        melhor_score=resultado.score,
                    )
                )

        # Status por empresa cadastrada (ordem determinística do repositório).
        for empresa in empresas:
            matches = matches_por_cnpj.get(empresa.cnpj, [])
            if matches:
                melhor = max(matches, key=_prioridade)
                resumo.empresas_status.append(
                    EmpresaStatus(
                        empresa=empresa,
                        status=StatusMatch.ENCONTRADO,
                        metodo=melhor.metodo,
                        score=melhor.score,
                        contratos_correspondentes=len(matches),
                    )
                )
            else:
                resumo.empresas_status.append(
                    EmpresaStatus(
                        empresa=empresa,
                        status=StatusMatch.NAO_ENCONTRADO,
                        metodo=MetodoMatch.NENHUM,
                        score=0.0,
                        contratos_correspondentes=0,
                    )
                )
                resumo.pendencias.append(mensagem_pendencia(empresa))

        return resumo
