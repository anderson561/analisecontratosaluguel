"""Repositório SQLite da tabela ``contratos`` (camada infrastructure).

Implementa ``ContratoRepositoryProtocol`` sobre ``sqlite3``, mesmo padrão de
``EmpresaRepository`` (conexão injetável, ``RepositoryError`` envolvendo
``sqlite3.Error``, ``init_schema`` chamado no construtor). Suporte à Fase 1 do
plano de persistência
(``.agent/specs/plano-3-features-persistencia-pdf-tooltip.md``).

Chave natural de dedup: ``arquivo_hash`` é ``UNIQUE`` na tabela, o que torna
``salvar`` idempotente por hash via ``INSERT ... ON CONFLICT(arquivo_hash) DO
UPDATE`` — reprocessar o mesmo arquivo atualiza o registro existente (mesmo
``id``) em vez de duplicar (decisão confirmada no plano §2.2). ``id`` fica de
fora do ``DO UPDATE SET`` de propósito: é assim que o identificador original
sobrevive a um reprocessamento.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from contract_parser.domain.contrato import Contrato
from contract_parser.domain.irrf import ResultadoIRRF
from contract_parser.domain.registro_contrato import RegistroContrato
from contract_parser.domain.relatorio import LinhaContrato
from contract_parser.infrastructure.database import (
    RepositoryError,
    get_connection,
    init_schema,
)

TABLE_NAME = "contratos"


def _linha_para_dict(linha: LinhaContrato) -> dict:
    """Serializa manualmente a ``LinhaContrato`` (dataclass simples, não
    pydantic) para um dict pronto para ``json.dumps``."""
    return {
        "locatario_nome": linha.locatario_nome,
        "locatario_cnpj": linha.locatario_cnpj,
        "locador_nome": linha.locador_nome,
        "valor_aluguel": str(linha.valor_aluguel) if linha.valor_aluguel is not None else None,
        "irrf": json.loads(linha.irrf.model_dump_json()) if linha.irrf is not None else None,
        "indice": linha.indice,
        "proximo_reajuste": linha.proximo_reajuste,
        "reajuste_automatico": linha.reajuste_automatico,
        "vencimento": linha.vencimento.isoformat() if linha.vencimento is not None else None,
    }


def _dict_para_linha(dados: dict) -> LinhaContrato:
    """Reidrata a ``LinhaContrato`` a partir do dict produzido por
    :func:`_linha_para_dict` (inverso fiel, incluindo ``Decimal``/``date``)."""
    valor_aluguel = dados["valor_aluguel"]
    vencimento = dados["vencimento"]
    return LinhaContrato(
        locatario_nome=dados["locatario_nome"],
        locatario_cnpj=dados["locatario_cnpj"],
        locador_nome=dados["locador_nome"],
        valor_aluguel=Decimal(valor_aluguel) if valor_aluguel is not None else None,
        irrf=ResultadoIRRF.model_validate(dados["irrf"]) if dados["irrf"] is not None else None,
        indice=dados["indice"],
        proximo_reajuste=dados["proximo_reajuste"],
        reajuste_automatico=dados["reajuste_automatico"],
        vencimento=date.fromisoformat(vencimento) if vencimento is not None else None,
    )


def _to_row(
    *,
    id: str,
    arquivo_nome: str,
    arquivo_hash: str,
    processado_em: datetime,
    revisao: bool,
    arquivo_ausente: bool,
    contrato: Contrato,
    linha: LinhaContrato,
) -> dict:
    """Serializa o registro para os parâmetros de uma linha da tabela.

    ``contrato`` é pydantic (``model_dump_json`` resolve ``Decimal``/``date``/
    enum automaticamente); ``linha`` não é pydantic e usa a serialização
    manual de :func:`_linha_para_dict`.
    """
    return {
        "id": id,
        "arquivo_nome": arquivo_nome,
        "arquivo_hash": arquivo_hash,
        "processado_em": processado_em.isoformat(),
        "revisao": int(revisao),
        "arquivo_ausente": int(arquivo_ausente),
        "contrato_json": contrato.model_dump_json(),
        "linha_json": json.dumps(_linha_para_dict(linha), ensure_ascii=False),
    }


def _from_row(row: sqlite3.Row) -> RegistroContrato:
    """Reidrata um :class:`RegistroContrato` a partir de uma linha da tabela."""
    return RegistroContrato(
        id=row["id"],
        arquivo_nome=row["arquivo_nome"],
        arquivo_hash=row["arquivo_hash"],
        processado_em=datetime.fromisoformat(row["processado_em"]),
        contrato=Contrato.model_validate_json(row["contrato_json"]),
        linha=_dict_para_linha(json.loads(row["linha_json"])),
        revisao=bool(row["revisao"]),
        arquivo_ausente=bool(row["arquivo_ausente"]),
    )


class ContratoRepository:
    """Repositório da tabela ``contratos``.

    Parameters
    ----------
    conn:
        Conexão ``sqlite3`` (ou compatível) injetada. Se ``None``, resolve a
        conexão real de produção via :func:`get_connection` (singleton de
        processo). Em ambos os casos, ``init_schema`` é aplicado — idempotente,
        garante que a tabela exista independentemente de quem forneceu a conexão.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn if conn is not None else get_connection()
        # Garante leitura por nome de coluna independentemente de quem abriu a
        # conexão (produção via get_connection já define; testes que injetam
        # sqlite3.connect(":memory:") cru, não).
        self._conn.row_factory = sqlite3.Row
        init_schema(self._conn)

    def salvar(
        self,
        *,
        arquivo_nome: str,
        arquivo_hash: str,
        contrato: Contrato,
        linha: LinhaContrato,
        revisao: bool,
    ) -> RegistroContrato:
        # O id gerado aqui só "vence" num INSERT novo: em conflito por
        # arquivo_hash, o DO UPDATE SET abaixo não toca a coluna id — o id
        # original sobrevive ao reprocessamento.
        row = _to_row(
            id=str(uuid.uuid4()),
            arquivo_nome=arquivo_nome,
            arquivo_hash=arquivo_hash,
            processado_em=datetime.now(UTC),
            revisao=revisao,
            arquivo_ausente=False,
            contrato=contrato,
            linha=linha,
        )
        try:
            self._conn.execute(
                """
                INSERT INTO contratos
                    (id, arquivo_nome, arquivo_hash, processado_em, revisao,
                     arquivo_ausente, contrato_json, linha_json)
                VALUES
                    (:id, :arquivo_nome, :arquivo_hash, :processado_em, :revisao,
                     :arquivo_ausente, :contrato_json, :linha_json)
                ON CONFLICT(arquivo_hash) DO UPDATE SET
                    arquivo_nome = excluded.arquivo_nome,
                    processado_em = excluded.processado_em,
                    revisao = excluded.revisao,
                    arquivo_ausente = excluded.arquivo_ausente,
                    contrato_json = excluded.contrato_json,
                    linha_json = excluded.linha_json
                """,
                row,
            )
            self._conn.commit()
            cur = self._conn.execute(
                "SELECT * FROM contratos WHERE arquivo_hash = ?", (arquivo_hash,)
            )
            registrado = cur.fetchone()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao salvar contrato {arquivo_nome}: {exc}"
            ) from exc
        return _from_row(registrado)

    def listar(self) -> list[RegistroContrato]:
        # Mais recentes primeiro: faz mais sentido para um painel de histórico
        # (o usuário quer ver o que acabou de processar no topo).
        try:
            cur = self._conn.execute(
                "SELECT * FROM contratos ORDER BY processado_em DESC"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise RepositoryError(f"Falha ao listar contratos: {exc}") from exc
        return [_from_row(r) for r in rows]

    def buscar_por_hash(self, arquivo_hash: str) -> RegistroContrato | None:
        try:
            cur = self._conn.execute(
                "SELECT * FROM contratos WHERE arquivo_hash = ?", (arquivo_hash,)
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao buscar contrato pelo hash {arquivo_hash}: {exc}"
            ) from exc
        return _from_row(row) if row is not None else None

    def excluir(self, id: str) -> bool:
        try:
            cur = self._conn.execute("DELETE FROM contratos WHERE id = ?", (id,))
            self._conn.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(f"Falha ao excluir contrato {id}: {exc}") from exc
        return cur.rowcount > 0

    def excluir_todos(self) -> int:
        try:
            cur = self._conn.execute("DELETE FROM contratos")
            self._conn.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"Falha ao excluir todos os contratos: {exc}"
            ) from exc
        return cur.rowcount
