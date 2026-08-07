"""Fakes de teste: repositório in-memory usado pelos testes de application.

- ``FakeEmpresaRepository``: implementa ``EmpresaRepositoryProtocol`` em memória.
  Usado nos testes de application (service/importer) e no cenário CA-01, sem
  qualquer dependência de banco real (nem SQLite, nem o extinto MongoDB).

Nota (ADR-002): desde a migração MongoDB -> SQLite, ``EmpresaRepository`` (a
implementação de infraestrutura) é testado contra ``sqlite3.connect(":memory:")``
real (ver ``tests/infrastructure/test_empresa_repository.py``) — não precisa
mais de um fake de baixo nível equivalente ao antigo ``pymongo.Collection``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from contract_parser.domain.cnpj import normalizar_cnpj
from contract_parser.domain.contrato import Contrato
from contract_parser.domain.documento_texto import DocumentoTexto
from contract_parser.domain.empresa import Empresa
from contract_parser.domain.extracao import ResultadoOcr
from contract_parser.domain.interpretador import (
    PedidoInterpretacao,
    ResultadoInterpretacao,
)
from contract_parser.domain.irrf import TabelaIRRF, tabela_irrf_2026
from contract_parser.domain.registro_contrato import RegistroContrato
from contract_parser.domain.relatorio import LinhaContrato
from contract_parser.infrastructure.database import RepositoryError


class FakeEmpresaRepository:
    """Repositório in-memory que satisfaz ``EmpresaRepositoryProtocol``."""

    def __init__(self) -> None:
        self._store: dict[str, Empresa] = {}

    def add(self, empresa: Empresa) -> Empresa:
        if empresa.cnpj in self._store:
            raise ValueError(f"CNPJ {empresa.cnpj} já existe.")
        self._store[empresa.cnpj] = empresa
        return empresa

    def get_by_cnpj(self, cnpj: str) -> Empresa | None:
        return self._store.get(normalizar_cnpj(cnpj))

    def list_all(self) -> list[Empresa]:
        return list(self._store.values())

    def update(self, empresa: Empresa) -> Empresa:
        self._store[empresa.cnpj] = empresa
        return empresa

    def remove(self, cnpj: str) -> bool:
        return self._store.pop(normalizar_cnpj(cnpj), None) is not None

    def upsert_many(self, empresas: list[Empresa]) -> int:
        for e in empresas:
            self._store[e.cnpj] = e
        return len(empresas)


class FakeExtractor:
    """Extrator fake que satisfaz ``ExtratorTexto`` (sem tocar bibliotecas).

    - ``extensao``: extensão que este backend aceita (ex.: ``.pdf``).
    - ``resultado``: :class:`DocumentoTexto` a devolver (se dado); caso contrário
      um resultado sintético é montado por caminho.
    - ``chamadas``: registra os caminhos passados a ``extrair`` (verificação de
      roteamento por extensão).
    """

    def __init__(
        self,
        extensao: str,
        *,
        resultado: DocumentoTexto | None = None,
        texto: str = "conteudo fake",
        metodo: str = "nativo",
    ) -> None:
        self.extensao = extensao.lower()
        self._resultado = resultado
        self._texto = texto
        self._metodo = metodo
        self.chamadas: list[Path] = []

    def aceita(self, caminho: Path) -> bool:
        return caminho.suffix.lower() == self.extensao

    def extrair(self, caminho: Path) -> DocumentoTexto:
        self.chamadas.append(caminho)
        if self._resultado is not None:
            return self._resultado
        return DocumentoTexto(
            caminho=str(caminho),
            hash=f"hash-{caminho.name}",
            texto=self._texto,
            metodo=self._metodo,  # type: ignore[arg-type]
        )


class FakeOcr:
    """Motor de OCR fake (implementa ``OcrEngine``) sem exigir Tesseract.

    Devolve ``resultado`` fixo e registra em ``chamadas`` os bytes recebidos —
    permite verificar que a rota nativo→OCR foi de fato acionada.
    """

    def __init__(self, resultado: ResultadoOcr | None = None) -> None:
        self._resultado = resultado or ResultadoOcr(
            texto="texto reconhecido por ocr", paginas=1, baixa_confianca=True
        )
        self.chamadas: list[bytes] = []

    def reconhecer(self, dados: bytes) -> ResultadoOcr:
        self.chamadas.append(dados)
        return self._resultado


class FakeInterpretadorLLM:
    """Interpretador de cláusula FAKE (satisfaz ``InterpretadorClausula``).

    Substitui o LLM nos testes do orquestrador híbrido: NÃO faz IO nem importa
    SDK. Registra em ``pedidos`` todos os :class:`PedidoInterpretacao` recebidos
    — o que permite provar QUANDO o orquestrador recorre (ou não) ao LLM — e
    devolve uma ``resposta`` pré-programada. Se ``erro`` for dado, ``interpretar``
    o levanta (simula o stub de produção sem provedor / falha do backend).
    """

    def __init__(
        self,
        *,
        resposta: ResultadoInterpretacao | None = None,
        erro: Exception | None = None,
    ) -> None:
        self._resposta = resposta
        self._erro = erro
        self.pedidos: list[PedidoInterpretacao] = []

    def interpretar(self, pedido: PedidoInterpretacao) -> ResultadoInterpretacao:
        self.pedidos.append(pedido)
        if self._erro is not None:
            raise self._erro
        if self._resposta is None:
            return ResultadoInterpretacao(valor=None, confianca=0.0, justificativa="sem resposta")
        return self._resposta


class FakeAtualizadorTabelaRFB:
    """Revalidador FAKE (satisfaz ``AtualizadorTabelaRFB``) — sem rede.

    Substitui o stub de produção (``StubAtualizadorTabelaRFB``) nos testes: NÃO
    faz IO. Devolve uma ``tabela`` pré-programada (default: a factory oficial
    2026) e conta as chamadas em ``chamadas`` — permite provar que a aplicação
    aciona o revalidador. Se ``erro`` for dado, ``buscar_tabela_vigente`` o
    levanta (simula falha de rede / stub sem integração).
    """

    def __init__(
        self,
        *,
        tabela: TabelaIRRF | None = None,
        erro: Exception | None = None,
    ) -> None:
        self._tabela = tabela if tabela is not None else tabela_irrf_2026()
        self._erro = erro
        self.chamadas = 0

    def buscar_tabela_vigente(self) -> TabelaIRRF:
        self.chamadas += 1
        if self._erro is not None:
            raise self._erro
        return self._tabela


class FakeContratoRepository:
    """Repositório in-memory que satisfaz ``ContratoRepositoryProtocol``.

    Reproduz o upsert por ``arquivo_hash`` da implementação SQLite real (mesmo
    ``id`` sobrevive a um reprocessamento). ``arquivos_com_erro`` permite
    simular falha de persistência de um item específico (``RepositoryError``),
    sem afetar os demais — usado para testar a degradação graciosa do
    ``RelatorioController`` (Fase 2 do plano de persistência).
    """

    def __init__(self) -> None:
        self._store: dict[str, RegistroContrato] = {}
        self._id_por_hash: dict[str, str] = {}
        self.chamadas_salvar: list[str] = []
        self.arquivos_com_erro: set[str] = set()

    def salvar(
        self,
        *,
        arquivo_nome: str,
        arquivo_hash: str,
        contrato: Contrato,
        linha: LinhaContrato,
        revisao: bool,
    ) -> RegistroContrato:
        if arquivo_nome in self.arquivos_com_erro:
            raise RepositoryError(f"falha simulada ao salvar {arquivo_nome}")
        self.chamadas_salvar.append(arquivo_nome)
        id_ = self._id_por_hash.get(arquivo_hash, str(uuid.uuid4()))
        registro = RegistroContrato(
            id=id_,
            arquivo_nome=arquivo_nome,
            arquivo_hash=arquivo_hash,
            processado_em=datetime.now(UTC),
            contrato=contrato,
            linha=linha,
            revisao=revisao,
        )
        self._store[id_] = registro
        self._id_por_hash[arquivo_hash] = id_
        return registro

    def listar(self) -> list[RegistroContrato]:
        return list(self._store.values())

    def buscar_por_hash(self, arquivo_hash: str) -> RegistroContrato | None:
        id_ = self._id_por_hash.get(arquivo_hash)
        return self._store.get(id_) if id_ is not None else None

    def excluir(self, id: str) -> bool:
        registro = self._store.pop(id, None)
        if registro is None:
            return False
        self._id_por_hash.pop(registro.arquivo_hash, None)
        return True

    def excluir_todos(self) -> int:
        total = len(self._store)
        self._store.clear()
        self._id_por_hash.clear()
        return total
