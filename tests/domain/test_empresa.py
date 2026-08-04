"""Testes unitários do modelo de domínio ``Empresa`` (pydantic v2)."""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from contract_parser.domain.empresa import Empresa


def test_empresa_normaliza_cnpj_e_defaults():
    emp = Empresa(cnpj="11.222.333/0001-81", razao_social="  Alpha LTDA  ")

    assert emp.cnpj == "11222333000181"
    assert emp.razao_social == "Alpha LTDA"  # strip
    assert emp.aliases == []
    assert emp.nomes_fantasia == []
    assert emp.ativo is True
    assert emp.origem_import is None
    assert isinstance(emp.created_at, datetime)


def test_empresa_cnpj_invalido_vira_validation_error():
    with pytest.raises(ValidationError):
        Empresa(cnpj="123", razao_social="X")


def test_empresa_razao_vazia_rejeitada():
    with pytest.raises(ValidationError):
        Empresa(cnpj="11222333000181", razao_social="   ")


def test_empresa_listas_removem_vazios_e_duplicatas():
    emp = Empresa(
        cnpj="11222333000181",
        razao_social="Alpha",
        aliases=["A", "A", "  ", "B"],
        nomes_fantasia=["Fantasia", ""],
    )
    assert emp.aliases == ["A", "B"]
    assert emp.nomes_fantasia == ["Fantasia"]


def test_empresa_extra_field_proibido():
    with pytest.raises(ValidationError):
        Empresa(cnpj="11222333000181", razao_social="Alpha", inesperado="x")


def test_to_document_usa_cnpj_como_id_e_roundtrip():
    emp = Empresa(cnpj="11222333000181", razao_social="Alpha", origem_import="arq.xlsx")
    doc = emp.to_document()

    assert doc["_id"] == "11222333000181"
    assert doc["cnpj"] == "11222333000181"

    reidratado = Empresa.from_document(doc)
    assert reidratado.cnpj == emp.cnpj
    assert reidratado.razao_social == emp.razao_social
    assert reidratado.origem_import == "arq.xlsx"
