"""Regressão dos layouts reais descobertos na validação da Fase 4 (RF03).

Fixtures 100% ANONIMIZADAS (dados fictícios) que reproduzem os dois layouts que
faziam o motor devolver ``locador=locatario=tipo_locacao=None``:

- **Quadro parentético** (caso-guia contrato_02 "Bahia Center"): rótulos reais
  ``LOCADOR (A/S/ES):`` / ``LOCATÁRIOS (A/S):`` com o bloco de qualificação numa
  linha SEPARADA (após linha em branco), locador **PF** (CPF) e locatário **PJ**
  (CNPJ) — o caso PF→PJ crítico para o IRRF — e título "RESIDENCIAL" que deve
  prevalecer sobre a menção a "sala comercial" no corpo.
- **Prosa narrativa** (caso contrato_03): partes em redação corrida ("...como
  LOCADORA ... LTDA ... CNPJ ...") sem quadro rotulado, com bloco de assinatura
  ao final (que NÃO pode mascarar a parte real).

Determinístico: motor híbrido SEM LLM.
"""
from __future__ import annotations

from contract_parser.application.contract_extraction_service import ExtratorContrato
from contract_parser.domain.contrato import TipoLocacao, TipoParte
from tests.support import contract_fixtures as cf


def _extrair(nome: str):
    return ExtratorContrato().extrair(cf.carregar_contrato(nome))


# --------------------------------------------------------------------------- #
# Layout PARENTÉTICO (caso-guia contrato_02) — PF→PJ + título residencial
# --------------------------------------------------------------------------- #
def test_parentetico_locador_pf_com_cpf():
    c = _extrair(cf.RESIDENCIAL_ROTULO_PARENTETICO_PF_PJ)
    assert c.locador.tipo == TipoParte.PF
    assert c.locador.nome == "MARCOS ANTONIO PEREIRA LIMA"
    # Pega o CPF do PRÓPRIO locador (não o do cônjuge citado em seguida).
    assert c.locador.documento == "11144477735"
    assert not c.memoria_extracao["locador"].necessita_revisao


def test_parentetico_locatario_pj_com_cnpj():
    c = _extrair(cf.RESIDENCIAL_ROTULO_PARENTETICO_PF_PJ)
    assert c.locatario.tipo == TipoParte.PJ
    assert c.locatario.nome == "ESTUDIO EXEMPLO E SERVIÇOS LTDA"
    assert c.locatario.documento == "11444777000161"


def test_parentetico_tipo_residencial_pelo_titulo_vence_corpo():
    # Título diz RESIDENCIAL; corpo cita "sala comercial" — o título prevalece.
    c = _extrair(cf.RESIDENCIAL_ROTULO_PARENTETICO_PF_PJ)
    assert c.tipo_locacao == TipoLocacao.RESIDENCIAL
    assert c.memoria_extracao["tipo_locacao"].detalhe == "tipo pelo título"


# --------------------------------------------------------------------------- #
# Layout NARRATIVO (caso contrato_03) — partes em prosa + assinatura ao final
# --------------------------------------------------------------------------- #
def test_narrativo_locador_pj_por_cnpj():
    c = _extrair(cf.COMERCIAL_NARRATIVO_PJ_PJ)
    assert c.locador.tipo == TipoParte.PJ
    # Documento da PJ (não o CPF da sócia representante citada logo depois).
    assert c.locador.documento == "22333444000181"


def test_narrativo_locatario_pj_por_cnpj():
    c = _extrair(cf.COMERCIAL_NARRATIVO_PJ_PJ)
    assert c.locatario.tipo == TipoParte.PJ
    assert c.locatario.nome == "BETA CONSTRUTORA LTDA"
    assert c.locatario.documento == "33555666000165"


def test_narrativo_tipo_comercial_pelo_corpo():
    c = _extrair(cf.COMERCIAL_NARRATIVO_PJ_PJ)
    assert c.tipo_locacao == TipoLocacao.COMERCIAL


def test_narrativo_assinatura_nao_mascara_parte_real():
    # O bloco "LOCADORA: ____" ao final não pode sequestrar a extração: a parte
    # real vem da prosa e traz documento (nome-só-de-underscores é descartado).
    c = _extrair(cf.COMERCIAL_NARRATIVO_PJ_PJ)
    assert c.locador.documento is not None
    assert c.locatario.documento is not None
