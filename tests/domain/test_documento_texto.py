"""Testes do modelo de resultado de extração e do hash de conteúdo (domain)."""
from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from contract_parser.domain.documento_texto import DocumentoTexto, calcular_hash


def test_calcular_hash_bate_com_sha256_de_referencia():
    dados = b"conteudo do contrato"
    assert calcular_hash(dados) == hashlib.sha256(dados).hexdigest()


def test_calcular_hash_e_estavel_e_sensivel_ao_conteudo():
    assert calcular_hash(b"abc") == calcular_hash(b"abc")
    assert calcular_hash(b"abc") != calcular_hash(b"abd")


def test_documento_sucesso_quando_sem_erro():
    doc = DocumentoTexto(caminho="a.pdf", hash="h", texto="oi", metodo="nativo", paginas=1)
    assert doc.sucesso is True


def test_documento_falha_quando_erro_preenchido():
    doc = DocumentoTexto(caminho="a.pdf", hash="h", erro="corrompido")
    assert doc.sucesso is False
    assert doc.metodo is None
    assert doc.texto == ""


def test_documento_rejeita_metodo_invalido():
    with pytest.raises(ValidationError):
        DocumentoTexto(caminho="a.pdf", hash="h", metodo="pptx")


def test_documento_rejeita_campo_extra():
    with pytest.raises(ValidationError):
        DocumentoTexto(caminho="a.pdf", hash="h", inexistente=1)
