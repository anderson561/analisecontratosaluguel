"""Orquestrador híbrido de extração de contrato (camada application) — RF03/D1.

Coordena o motor determinístico (``domain.regras_extracao``) e, **apenas** para
campos que as regras não resolvem com confiança, o interpretador de cláusulas
ambíguas (``domain.interpretador`` — LLM atrás de interface). Monta o
:class:`~contract_parser.domain.contrato.Contrato` com a memória de extração
(proveniência/confiança/revisão por campo) e as flags jurídicas.

Sem IO de rede: o interpretador é injetado (fake nos testes; stub em produção).
Segue o padrão de ``document_ingestor`` — resultado estruturado, nada de exceção
por campo ausente (campos não encontrados viram "revisão", não erro).
"""
from __future__ import annotations

from typing import Any

from contract_parser.domain import regras_extracao as regras
from contract_parser.domain.contrato import (
    Contrato,
    OrigemExtracao,
    Reajuste,
    RegistroCampo,
    TipoLocacao,
)
from contract_parser.domain.interpretador import (
    InterpretadorClausula,
    PedidoInterpretacao,
)
from contract_parser.domain.regras_extracao import LIMIAR_REVISAO, ResultadoCampo
from contract_parser.domain.regras_juridicas import avaliar_flags


class ExtratorContrato:
    """Caso de uso: extrair um :class:`Contrato` a partir do texto do documento.

    ``interpretador`` (opcional) resolve cláusulas ambíguas quando as regras
    falham. Se ``None`` (ou se ele falhar), o campo ambíguo é apenas marcado para
    revisão — a extração nunca quebra por falta de LLM.
    """

    def __init__(self, interpretador: InterpretadorClausula | None = None) -> None:
        self._interpretador = interpretador

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def extrair(self, texto: str) -> Contrato:
        texto = texto or ""
        memoria: dict[str, RegistroCampo] = {}

        locador = self._registrar(memoria, "locador", regras.extrair_locador(texto))
        locatario = self._registrar(memoria, "locatario", regras.extrair_locatario(texto))

        valor_aluguel = self._registrar(
            memoria, "valor_aluguel", regras.extrair_valor_aluguel(texto)
        )
        multa = self._registrar(
            memoria,
            "multa_rescisoria_total",
            regras.extrair_multa_rescisoria(texto, valor_aluguel),
        )

        garantias = self._registrar(memoria, "garantias", regras.extrair_garantias(texto))

        data_inicio = self._registrar(
            memoria, "data_inicio_vigencia", regras.extrair_data_inicio(texto)
        )
        data_fim = self._registrar(memoria, "data_fim_vigencia", regras.extrair_data_fim(texto))
        prazo = self._registrar(memoria, "prazo_meses", regras.extrair_prazo_meses(texto))
        dia_venc = self._registrar(
            memoria, "dia_vencimento_mensal", regras.extrair_dia_vencimento(texto)
        )

        reajuste = self._montar_reajuste(memoria, texto)

        # Campo AMBÍGUO: regra primeiro; só recorre ao interpretador (LLM) se a
        # regra não resolver com confiança suficiente.
        tipo_locacao = self._resolver_tipo_locacao(memoria, texto)

        flags = avaliar_flags(garantias=garantias, reajuste=reajuste, texto=texto)
        memoria["flags_juridicas"] = RegistroCampo(
            origem=OrigemExtracao.REGRA,
            confianca=regras.CONF_ALTA,
            necessita_revisao=False,
            detalhe=f"{len(flags.alertas)} alerta(s)",
        )

        return Contrato(
            locador=locador or regras.Parte(),
            locatario=locatario or regras.Parte(),
            tipo_locacao=tipo_locacao,
            valor_aluguel=valor_aluguel,
            multa_rescisoria_total=multa,
            garantias=garantias or [],
            data_inicio_vigencia=data_inicio,
            data_fim_vigencia=data_fim,
            prazo_meses=prazo,
            dia_vencimento_mensal=dia_venc,
            reajuste=reajuste,
            flags=flags,
            memoria_extracao=memoria,
        )

    # ------------------------------------------------------------------ #
    # Auxiliares
    # ------------------------------------------------------------------ #
    @staticmethod
    def _registrar(
        memoria: dict[str, RegistroCampo], campo: str, resultado: ResultadoCampo
    ) -> Any:
        """Grava a proveniência do campo e devolve o valor (ou ``None``)."""
        necessita_revisao = (
            resultado.origem == OrigemExtracao.NAO_ENCONTRADO
            or resultado.confianca < LIMIAR_REVISAO
        )
        memoria[campo] = RegistroCampo(
            origem=resultado.origem,
            confianca=resultado.confianca,
            necessita_revisao=necessita_revisao,
            detalhe=resultado.detalhe,
        )
        return resultado.valor

    def _montar_reajuste(self, memoria: dict[str, RegistroCampo], texto: str) -> Reajuste:
        indice = self._registrar(memoria, "reajuste_indice", regras.extrair_indice_reajuste(texto))
        periodicidade = self._registrar(
            memoria, "reajuste_periodicidade", regras.extrair_periodicidade_meses(texto)
        )
        proximo = self._registrar(
            memoria, "reajuste_proximo", regras.extrair_proximo_reajuste(texto)
        )
        automatico = self._registrar(
            memoria, "reajuste_automatico", regras.extrair_reajuste_automatico(texto)
        )
        return Reajuste(
            indice=indice,
            periodicidade_meses=periodicidade,
            proximo_reajuste=proximo,
            automatico=bool(automatico),
        )

    def _resolver_tipo_locacao(
        self, memoria: dict[str, RegistroCampo], texto: str
    ) -> TipoLocacao | None:
        resultado = regras.extrair_tipo_locacao(texto)
        if resultado.resolvido:
            self._registrar(memoria, "tipo_locacao", resultado)
            return resultado.valor

        # Regra não resolveu → tenta o interpretador (LLM) se disponível.
        resultado_llm = self._interpretar_tipo_locacao(texto, memoria)
        self._registrar(memoria, "tipo_locacao", resultado_llm)
        return resultado_llm.valor

    def _interpretar_tipo_locacao(
        self, texto: str, memoria: dict[str, RegistroCampo]
    ) -> ResultadoCampo[TipoLocacao]:
        """Fallback ambíguo: consulta o interpretador; degrada para revisão."""
        if self._interpretador is None:
            return ResultadoCampo.nao_encontrado("ambíguo e sem interpretador de LLM")

        pedido = PedidoInterpretacao(
            campo="tipo_locacao",
            texto=self._recorte_objeto(texto),
            contexto={"garantias_detectadas": memoria.get("garantias") is not None},
        )
        try:
            resposta = self._interpretador.interpretar(pedido)
        except NotImplementedError:
            # Stub de produção sem provedor (LGPD): não quebra, marca revisão.
            return ResultadoCampo.nao_encontrado("interpretador de LLM não configurado")

        valor = self._coagir_tipo_locacao(resposta.valor)
        if valor is None:
            return ResultadoCampo.nao_encontrado("interpretador não determinou o tipo")
        return ResultadoCampo(valor, resposta.confianca, OrigemExtracao.LLM, resposta.justificativa)

    @staticmethod
    def _coagir_tipo_locacao(valor: Any) -> TipoLocacao | None:
        if isinstance(valor, TipoLocacao):
            return valor
        if isinstance(valor, str):
            try:
                return TipoLocacao(valor.strip().lower())
            except ValueError:
                return None
        return None

    @staticmethod
    def _recorte_objeto(texto: str, largura: int = 400) -> str:
        """Recorte mínimo enviado ao interpretador (minimização LGPD).

        Prioriza a vizinhança de termos de objeto/finalidade; senão, o início.
        """
        alvo = ("destina", "finalidade", "objeto", "imóvel", "imovel")
        baixo = texto.lower()
        for termo in alvo:
            pos = baixo.find(termo)
            if pos != -1:
                inicio = max(0, pos - largura // 4)
                return texto[inicio : inicio + largura]
        return texto[:largura]
