"""Testes do ``ContratoRepository`` contra ``sqlite3.connect(":memory:")`` real.

Cobre a Fase 1 do plano de persistência
(``.agent/specs/plano-3-features-persistencia-pdf-tooltip.md``): round-trip
fiel de ``RegistroContrato`` (contrato "rico" e "pobre"), upsert por
``arquivo_hash`` (reprocessamento não duplica, mantém o mesmo ``id``),
listagem, exclusão individual e em massa, e conformidade com
``ContratoRepositoryProtocol``.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from contract_parser.domain.contrato import (
    Contrato,
    FlagsJuridicas,
    ModalidadeGarantia,
    OrigemExtracao,
    Parte,
    Reajuste,
    RegistroCampo,
    TipoLocacao,
    TipoParte,
)
from contract_parser.domain.irrf import ResultadoIRRF
from contract_parser.domain.relatorio import LinhaContrato
from contract_parser.domain.repositories import ContratoRepositoryProtocol
from contract_parser.infrastructure.contrato_repository import ContratoRepository
from contract_parser.infrastructure.database import init_schema


def _conexao() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


@pytest.fixture
def repo():
    conn = _conexao()
    try:
        yield ContratoRepository(conn=conn)
    finally:
        conn.close()


def _resultado_irrf() -> ResultadoIRRF:
    return ResultadoIRRF(
        retido=True,
        imposto=Decimal("394.54"),
        base_calculo=Decimal("4392.80"),
        aliquota=Decimal("0.275"),
        deducao=Decimal("908.73"),
        faixa_descricao="acima de 4664.69 — 27.5%",
        tabela_vigencia="2026",
        base_legal="Lei nº 15.191/2025",
        fonte_url="https://exemplo.invalido/tabela",
        observacao="observação de teste",
        imposto_antes_reducao=Decimal("574.29"),
        reducao_aplicada=Decimal("179.75"),
        rendimento_bruto=Decimal("5000.00"),
        desconto_simplificado_aplicado=Decimal("607.20"),
    )


def _contrato_rico() -> Contrato:
    return Contrato(
        locador=Parte(tipo=TipoParte.PF, nome="João da Silva", documento="12345678901"),
        locatario=Parte(
            tipo=TipoParte.PJ, nome="Alpha Comercio LTDA", documento="00000000000159"
        ),
        tipo_locacao=TipoLocacao.COMERCIAL,
        valor_aluguel=Decimal("5000.00"),
        multa_rescisoria_total=Decimal("15000.00"),
        garantias=[ModalidadeGarantia.CAUCAO, ModalidadeGarantia.FIANCA],
        data_inicio_vigencia=date(2024, 10, 10),
        data_fim_vigencia=date(2028, 10, 10),
        prazo_meses=48,
        dia_vencimento_mensal=10,
        reajuste=Reajuste(
            indice="IPCA", periodicidade_meses=12, proximo_reajuste="10/2026", automatico=True
        ),
        flags=FlagsJuridicas(
            violacao_art37_multiplas_garantias=True,
            alertas=["Múltiplas garantias cumuladas (Art. 37)"],
        ),
        memoria_extracao={
            "valor_aluguel": RegistroCampo(
                origem=OrigemExtracao.REGRA, confianca=0.95, necessita_revisao=False
            ),
            "reajuste.indice": RegistroCampo(
                origem=OrigemExtracao.LLM,
                confianca=0.4,
                necessita_revisao=True,
                detalhe="Cláusula ambígua",
            ),
        },
    )


def _contrato_pobre() -> Contrato:
    return Contrato()


def _linha_rica() -> LinhaContrato:
    return LinhaContrato(
        locatario_nome="Alpha Comercio LTDA",
        locatario_cnpj="00000000000159",
        locador_nome="João da Silva",
        valor_aluguel=Decimal("5000.00"),
        irrf=_resultado_irrf(),
        indice="IPCA",
        proximo_reajuste="10/2026",
        reajuste_automatico=True,
        vencimento=date(2028, 10, 10),
    )


def _linha_pobre() -> LinhaContrato:
    return LinhaContrato(
        locatario_nome=None,
        locatario_cnpj=None,
        locador_nome=None,
        valor_aluguel=None,
        irrf=None,
        indice=None,
        proximo_reajuste=None,
        reajuste_automatico=False,
        vencimento=None,
    )


def test_contrato_repository_satisfaz_o_protocol(repo):
    assert isinstance(repo, ContratoRepositoryProtocol)


def test_listar_vazio_antes_de_qualquer_salvar(repo):
    assert repo.listar() == []


def test_salvar_retorna_registro_com_id_nao_vazio_e_campos_corretos(repo):
    registro = repo.salvar(
        arquivo_nome="contrato_alpha.pdf",
        arquivo_hash="hash-alpha",
        contrato=_contrato_rico(),
        linha=_linha_rica(),
        revisao=True,
    )
    assert registro.id
    assert registro.arquivo_nome == "contrato_alpha.pdf"
    assert registro.arquivo_hash == "hash-alpha"
    assert registro.revisao is True
    assert registro.arquivo_ausente is False


def test_roundtrip_fiel_contrato_rico(repo):
    contrato = _contrato_rico()
    linha = _linha_rica()
    salvo = repo.salvar(
        arquivo_nome="contrato_alpha.pdf",
        arquivo_hash="hash-alpha",
        contrato=contrato,
        linha=linha,
        revisao=True,
    )

    obtido_listar = repo.listar()[0]
    obtido_hash = repo.buscar_por_hash("hash-alpha")

    for obtido in (obtido_listar, obtido_hash):
        assert obtido.id == salvo.id
        assert obtido.contrato == contrato
        assert obtido.linha == linha


def test_roundtrip_fiel_contrato_pobre(repo):
    contrato = _contrato_pobre()
    linha = _linha_pobre()
    repo.salvar(
        arquivo_nome="contrato_pobre.pdf",
        arquivo_hash="hash-pobre",
        contrato=contrato,
        linha=linha,
        revisao=False,
    )

    obtido = repo.buscar_por_hash("hash-pobre")

    assert obtido.contrato == contrato
    assert obtido.linha == linha
    assert obtido.linha.irrf is None


def test_buscar_por_hash_ausente_retorna_none(repo):
    assert repo.buscar_por_hash("hash-inexistente") is None


def test_reprocessar_mesmo_hash_atualiza_em_vez_de_duplicar(repo):
    primeiro = repo.salvar(
        arquivo_nome="contrato_alpha.pdf",
        arquivo_hash="hash-alpha",
        contrato=_contrato_rico(),
        linha=_linha_rica(),
        revisao=True,
    )

    contrato_novo = _contrato_pobre()
    linha_nova = _linha_pobre()
    segundo = repo.salvar(
        arquivo_nome="contrato_alpha_v2.pdf",
        arquivo_hash="hash-alpha",
        contrato=contrato_novo,
        linha=linha_nova,
        revisao=False,
    )

    assert segundo.id == primeiro.id
    assert len(repo.listar()) == 1
    obtido = repo.buscar_por_hash("hash-alpha")
    assert obtido.arquivo_nome == "contrato_alpha_v2.pdf"
    assert obtido.revisao is False
    assert obtido.contrato == contrato_novo
    assert obtido.linha == linha_nova


def test_excluir_registro_existente(repo):
    registro = repo.salvar(
        arquivo_nome="contrato_alpha.pdf",
        arquivo_hash="hash-alpha",
        contrato=_contrato_rico(),
        linha=_linha_rica(),
        revisao=True,
    )
    assert repo.excluir(registro.id) is True
    assert repo.listar() == []


def test_excluir_id_inexistente_retorna_false_e_nao_altera_nada(repo):
    repo.salvar(
        arquivo_nome="contrato_alpha.pdf",
        arquivo_hash="hash-alpha",
        contrato=_contrato_rico(),
        linha=_linha_rica(),
        revisao=True,
    )
    assert repo.excluir("id-inexistente") is False
    assert len(repo.listar()) == 1


def test_excluir_todos_remove_tudo_e_retorna_a_contagem(repo):
    repo.salvar(
        arquivo_nome="a.pdf",
        arquivo_hash="hash-a",
        contrato=_contrato_rico(),
        linha=_linha_rica(),
        revisao=True,
    )
    repo.salvar(
        arquivo_nome="b.pdf",
        arquivo_hash="hash-b",
        contrato=_contrato_pobre(),
        linha=_linha_pobre(),
        revisao=False,
    )

    assert repo.excluir_todos() == 2
    assert repo.listar() == []
