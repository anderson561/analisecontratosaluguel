"""Registro persistido de um contrato processado — camada domain, sem IO.

Suporte à feature de persistência descrita em
``.agent/specs/plano-3-features-persistencia-pdf-tooltip.md`` (Fase 1): hoje o
resultado do processamento (:class:`~contract_parser.domain.contrato.Contrato`
+ :class:`~contract_parser.domain.relatorio.LinhaContrato`) vive só em memória
e se perde ao fechar o app. :class:`RegistroContrato` é o agregado que a
infraestrutura persiste/reidrata para virar um histórico auditável.

É agnóstico de onde ``arquivo_nome``/``arquivo_hash`` vêm — quem chama o
repositório (camada application/presentation, Fase 2 do plano) é responsável
por descobri-los; este módulo só modela o registro já resolvido.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from contract_parser.domain.contrato import Contrato
from contract_parser.domain.relatorio import LinhaContrato


@dataclass(frozen=True)
class RegistroContrato:
    """Um contrato processado e persistido, com metadados de origem/auditoria.

    ``arquivo_ausente`` sinaliza que o arquivo de origem não foi mais
    encontrado na pasta processada — não implica exclusão automática do
    registro (a trilha de auditoria só some por exclusão explícita).
    """

    id: str
    arquivo_nome: str
    arquivo_hash: str
    processado_em: datetime
    contrato: Contrato
    linha: LinhaContrato
    revisao: bool
    arquivo_ausente: bool = False
