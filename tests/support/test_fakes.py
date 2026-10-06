"""Testes dos fakes de ``tests/support`` que têm comportamento próprio."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from contract_parser.domain.contrato import Contrato, Reajuste
from contract_parser.domain.relatorio import LinhaContrato
from tests.support.fakes import FakeContratoRepository


def _linha(proximo_reajuste: str | None) -> LinhaContrato:
    return LinhaContrato(
        locatario_nome="Alpha LTDA",
        locatario_cnpj=None,
        locador_nome="João",
        locadores_adicionais=(),
        valor_aluguel=Decimal("5000.00"),
        irrf=None,
        indice="IPCA",
        indice_fonte=None,
        proximo_reajuste=proximo_reajuste,
        reajuste_automatico=True,
        despesas={},
        prorrogacao_automatica=False,
        prorrogacao_prazo_meses=None,
        vencimento=None,
        carencia_meses=None,
    )


def _salvar(repo: FakeContratoRepository):
    return repo.salvar(
        arquivo_nome="a.pdf",
        arquivo_hash="hash-a",
        contrato=Contrato(reajuste=Reajuste(indice="IPCA", proximo_reajuste="2026-10-10")),
        linha=_linha("2026-10-10"),
        revisao=True,
    )


def test_fake_atualizar_proximo_reajuste_altera_so_o_proximo_reajuste():
    repo = FakeContratoRepository()
    antes = _salvar(repo)

    depois = repo.atualizar_proximo_reajuste(antes.id, date(2027, 3, 1))

    assert depois.contrato.reajuste.proximo_reajuste == "2027-03-01"
    assert depois.linha.proximo_reajuste == "2027-03-01"
    assert depois.contrato.reajuste.indice == "IPCA"
    assert depois.linha.indice == "IPCA"
    assert (depois.id, depois.arquivo_hash, depois.processado_em, depois.revisao) == (
        antes.id,
        antes.arquivo_hash,
        antes.processado_em,
        antes.revisao,
    )
    assert repo.buscar_por_hash("hash-a") == depois
    assert repo.listar() == [depois]


def test_fake_atualizar_proximo_reajuste_id_inexistente_retorna_none():
    repo = FakeContratoRepository()
    antes = _salvar(repo)

    assert repo.atualizar_proximo_reajuste("nao-existe", date(2027, 3, 1)) is None
    assert repo.listar() == [antes]
