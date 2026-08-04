"""Testes do serviço CRUD ``EmpresaService`` com repositório fake in-memory."""
from __future__ import annotations

import pytest

from contract_parser.application.empresa_service import EmpresaService
from tests.support.fakes import FakeEmpresaRepository


@pytest.fixture
def service() -> EmpresaService:
    return EmpresaService(FakeEmpresaRepository())


def test_adicionar_e_listar(service):
    service.adicionar("11.222.333/0001-81", "Alpha LTDA")
    empresas = service.listar()

    assert len(empresas) == 1
    assert empresas[0].cnpj == "11222333000181"
    assert empresas[0].origem_import == "manual"


def test_obter_por_cnpj_com_mascara(service):
    service.adicionar("11222333000181", "Alpha LTDA")
    assert service.obter("11.222.333/0001-81").razao_social == "Alpha LTDA"
    assert service.obter("45566778000109") is None


def test_editar_altera_campos_e_preserva_created_at(service):
    criada = service.adicionar("11222333000181", "Alpha LTDA")
    editada = service.editar(
        "11.222.333/0001-81",
        razao_social="Alpha Nova LTDA",
        aliases=["ANL"],
        ativo=False,
    )

    assert editada.razao_social == "Alpha Nova LTDA"
    assert editada.aliases == ["ANL"]
    assert editada.ativo is False
    assert editada.created_at == criada.created_at


def test_editar_cnpj_inexistente_levanta_keyerror(service):
    with pytest.raises(KeyError):
        service.editar("11222333000181", razao_social="X")


def test_remover(service):
    service.adicionar("11222333000181", "Alpha LTDA")
    assert service.remover("11.222.333/0001-81") is True
    assert service.remover("11222333000181") is False
    assert service.listar() == []
