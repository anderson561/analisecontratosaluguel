"""Testes do orquestrador híbrido de extração (application, RF03/D1).

Provam o contrato do motor híbrido "regras → LLM":

- as regras determinísticas resolvem os campos objetivos;
- o interpretador (LLM, atrás de interface) é consultado **apenas** quando a
  regra não resolve com confiança suficiente (campo ambíguo);
- campos ausentes/ambíguos NUNCA quebram a extração — são marcados para revisão
  na memória de extração (§6).

O LLM é sempre um FAKE injetado (``tests.support.fakes.FakeInterpretadorLLM``);
nenhuma chamada de rede/SDK ocorre. O teste de LLM "real" fica marcado como
``integration`` e é pulado (provedor adiado por LGPD, ADR-001).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from contract_parser.application.contract_extraction_service import ExtratorContrato
from contract_parser.domain.contrato import OrigemExtracao, TipoLocacao
from contract_parser.domain.interpretador import (
    InterpretadorClausula,
    PedidoInterpretacao,
    ResultadoInterpretacao,
)
from tests.support import contract_fixtures as cf
from tests.support.fakes import FakeInterpretadorLLM

# Texto mínimo com tipo de locação AMBÍGUO (nem residencial nem comercial
# explícitos) — força o caminho de fallback para o interpretador.
TEXTO_AMBIGUO = (
    "LOCADOR: Fulano de Tal, CPF 123.456.789-09.\n\n"
    "O imóvel objeto deste contrato será destinado conforme cláusula própria.\n"
    "O aluguel mensal é de R$ 2.000,00."
)
TEXTO_RESIDENCIAL = (
    "LOCADOR: Fulano de Tal, CPF 123.456.789-09.\n\n"
    "O imóvel destina-se a fins residenciais, para moradia.\n"
    "O aluguel mensal é de R$ 2.000,00."
)


def _pedido() -> PedidoInterpretacao:
    return PedidoInterpretacao(campo="tipo_locacao", texto="trecho", contexto={})


# --------------------------------------------------------------------------- #
# Fronteira regra × LLM
# --------------------------------------------------------------------------- #
def test_llm_acionado_apenas_quando_regra_nao_resolve():
    fake = FakeInterpretadorLLM(
        resposta=ResultadoInterpretacao(TipoLocacao.RESIDENCIAL, 0.85, "inferido")
    )
    contrato = ExtratorContrato(interpretador=fake).extrair(TEXTO_AMBIGUO)

    assert contrato.tipo_locacao == TipoLocacao.RESIDENCIAL
    assert contrato.memoria_extracao["tipo_locacao"].origem == OrigemExtracao.LLM
    # Provou-se que o LLM FOI consultado (uma vez) para o campo ambíguo.
    assert len(fake.pedidos) == 1
    assert fake.pedidos[0].campo == "tipo_locacao"


def test_llm_nao_acionado_quando_regra_resolve():
    fake = FakeInterpretadorLLM(
        resposta=ResultadoInterpretacao(TipoLocacao.COMERCIAL, 0.99)
    )
    contrato = ExtratorContrato(interpretador=fake).extrair(TEXTO_RESIDENCIAL)

    # A regra resolveu (residencial) e o LLM NÃO foi chamado.
    assert contrato.tipo_locacao == TipoLocacao.RESIDENCIAL
    assert contrato.memoria_extracao["tipo_locacao"].origem == OrigemExtracao.REGRA
    assert fake.pedidos == []


def test_llm_coage_string_para_enum():
    fake = FakeInterpretadorLLM(resposta=ResultadoInterpretacao("comercial", 0.8))
    contrato = ExtratorContrato(interpretador=fake).extrair(TEXTO_AMBIGUO)
    assert contrato.tipo_locacao == TipoLocacao.COMERCIAL


def test_llm_valor_invalido_cai_para_revisao():
    fake = FakeInterpretadorLLM(resposta=ResultadoInterpretacao("banana", 0.9))
    contrato = ExtratorContrato(interpretador=fake).extrair(TEXTO_AMBIGUO)

    assert contrato.tipo_locacao is None
    assert contrato.memoria_extracao["tipo_locacao"].necessita_revisao
    assert len(fake.pedidos) == 1  # o LLM foi consultado, mas não determinou


# --------------------------------------------------------------------------- #
# Degradação graciosa: sem LLM e com LLM que falha (§6 — nunca quebra)
# --------------------------------------------------------------------------- #
def test_ambiguo_sem_interpretador_marca_revisao_sem_quebrar():
    contrato = ExtratorContrato(interpretador=None).extrair(TEXTO_AMBIGUO)

    assert contrato.tipo_locacao is None
    reg = contrato.memoria_extracao["tipo_locacao"]
    assert reg.origem == OrigemExtracao.NAO_ENCONTRADO
    assert reg.necessita_revisao


def test_stub_llm_nao_configurado_degrada_para_revisao():
    from contract_parser.infrastructure.llm_interpreter import StubInterpretadorLLM

    contrato = ExtratorContrato(interpretador=StubInterpretadorLLM()).extrair(TEXTO_AMBIGUO)

    # O stub de produção levanta; o orquestrador captura e marca revisão.
    assert contrato.tipo_locacao is None
    assert contrato.memoria_extracao["tipo_locacao"].necessita_revisao


def test_extrair_texto_vazio_nao_quebra():
    contrato = ExtratorContrato().extrair("")
    assert contrato.tipo_locacao is None
    assert contrato.necessita_revisao  # tudo em aberto -> revisão


# --------------------------------------------------------------------------- #
# Memória de extração e proveniência sobre uma fixture completa
# --------------------------------------------------------------------------- #
def test_fixture_completa_monta_contrato_e_marca_campos_ausentes():
    texto = cf.carregar_contrato(cf.RESIDENCIAL_PJ_PF_REAJUSTE_VEDADO)
    contrato = ExtratorContrato().extrair(texto)

    # Campos determinísticos resolvidos.
    assert contrato.valor_aluguel == Decimal("1800.00")
    assert contrato.prazo_meses == 24
    # Flags jurídicas do Art. 18 disparadas.
    assert contrato.flags.indice_vedado_art18
    assert contrato.flags.periodicidade_inferior_12m_art18
    # Campo genuinamente ausente (sem cláusula de multa) -> revisão, sem exceção.
    assert contrato.multa_rescisoria_total is None
    assert "multa_rescisoria_total" in contrato.campos_para_revisao
    assert contrato.necessita_revisao


def test_toda_extracao_registra_proveniencia_por_campo():
    contrato = ExtratorContrato().extrair(cf.carregar_contrato(cf.RESIDENCIAL_PF_PJ))
    # Cada campo lógico tem um registro de memória com confiança válida [0,1].
    assert contrato.memoria_extracao
    for reg in contrato.memoria_extracao.values():
        assert 0.0 <= reg.confianca <= 1.0
        assert isinstance(reg.origem, OrigemExtracao)


# --------------------------------------------------------------------------- #
# Contrato do interpretador (Protocol) e caminho de LLM real (integração)
# --------------------------------------------------------------------------- #
def test_fake_satisfaz_protocol_interpretador():
    assert isinstance(FakeInterpretadorLLM(), InterpretadorClausula)


def test_stub_llm_recusa_operar_sem_provedor():
    from contract_parser.infrastructure.llm_interpreter import (
        InterpretadorLLMNaoConfigurado,
        StubInterpretadorLLM,
    )

    with pytest.raises(InterpretadorLLMNaoConfigurado):
        StubInterpretadorLLM().interpretar(_pedido())


@pytest.mark.integration
def test_interpretador_llm_real_indisponivel_por_lgpd():
    # Nenhum provedor de LLM foi definido (decisão adiada por LGPD, ADR-001):
    # não há chamada real a validar nesta fase.
    pytest.skip("Provedor de LLM não configurado (LGPD/ADR-001) — sem chamada real.")
