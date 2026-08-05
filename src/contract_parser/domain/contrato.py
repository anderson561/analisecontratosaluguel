"""Modelo de domínio ``Contrato`` e vocabulário associado (pydantic v2, sem IO).

Núcleo do RF03 (ver requisitos §3). É um DTO puro de domínio: não faz IO, não
importa infraestrutura nem SDK de LLM. Carrega, além dos valores extraídos:

- **Memória de extração** (``memoria_extracao``): para CADA campo, registra qual
  extrator o produziu (regra determinística × LLM × não encontrado), a confiança
  associada e se ``necessita_revisao``. É a rastreabilidade exigida pela fase
  (mentalidade de experimento: cada valor tem proveniência auditável).
- **Flags jurídicas** (``FlagsJuridicas``): alertas de conformidade (Art. 37 do
  Art. 18 e cláusulas abusivas) calculados de forma determinística.

Os tipos monetários usam :class:`~decimal.Decimal` (rigor financeiro: nunca
``float`` para dinheiro).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TipoParte(str, Enum):
    """Natureza jurídica de uma parte — define a retenção de IRRF (§3)."""

    PF = "PF"
    PJ = "PJ"


class TipoLocacao(str, Enum):
    """Residencial × comercial (comercial habilita ação renovatória, Art. 51)."""

    RESIDENCIAL = "residencial"
    COMERCIAL = "comercial"


class ModalidadeGarantia(str, Enum):
    """Modalidades de garantia locatícia do Art. 37 da Lei 8.245/91."""

    CAUCAO = "caucao"
    FIANCA = "fianca"
    SEGURO_FIANCA = "seguro_fianca"
    CESSAO_FIDUCIARIA = "cessao_fiduciaria"


class OrigemExtracao(str, Enum):
    """De onde veio o valor de um campo (memória de extração, D1 híbrido)."""

    REGRA = "regra"  # extrator determinístico (regex/heurística)
    LLM = "llm"  # interpretador de cláusula ambígua (atrás de interface)
    NAO_ENCONTRADO = "nao_encontrado"  # nenhum extrator resolveu → revisão


class Parte(BaseModel):
    """Locador ou Locatário: tipo PF/PJ, nome e documento (só dígitos)."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoParte | None = None
    nome: str | None = None
    documento: str | None = None  # normalizado: apenas dígitos (11 CPF / 14 CNPJ)


class Reajuste(BaseModel):
    """Cláusula de reajuste: índice, periodicidade, próximo e flag automático."""

    model_config = ConfigDict(extra="forbid")

    indice: str | None = None  # IPCA / IGP-M / INPC / ... (ou texto vedado bruto)
    periodicidade_meses: int | None = None
    proximo_reajuste: str | None = None  # ISO (aaaa-mm-dd) ou "mm/aaaa"
    automatico: bool = False


class FlagsJuridicas(BaseModel):
    """Alertas de conformidade calculados deterministicamente (§3, §6).

    ``alertas`` acompanha descrições legíveis para o relatório/GUI.
    """

    model_config = ConfigDict(extra="forbid")

    violacao_art37_multiplas_garantias: bool = False
    indice_vedado_art18: bool = False
    periodicidade_inferior_12m_art18: bool = False
    renuncia_benfeitorias_necessarias: bool = False
    cumulacao_multas_bis_in_idem: bool = False
    alertas: list[str] = Field(default_factory=list)

    @property
    def houve_alerta(self) -> bool:
        return bool(self.alertas)


class RegistroCampo(BaseModel):
    """Proveniência de um único campo (memória de extração)."""

    model_config = ConfigDict(extra="forbid")

    origem: OrigemExtracao
    confianca: float = Field(ge=0.0, le=1.0)
    necessita_revisao: bool = False
    detalhe: str | None = None


class Contrato(BaseModel):
    """Contrato de locação extraído (RF03), com proveniência por campo.

    Todos os campos de conteúdo são opcionais: um contrato de layout inédito
    pode não render todos os valores — os ausentes ficam ``None`` e marcados
    para revisão em ``memoria_extracao`` (nunca quebram a extração, §6).
    """

    model_config = ConfigDict(extra="forbid")

    # Partes
    locador: Parte = Field(default_factory=Parte)
    locatario: Parte = Field(default_factory=Parte)

    # Objeto
    tipo_locacao: TipoLocacao | None = None

    # Financeiro (Decimal — rigor monetário)
    valor_aluguel: Decimal | None = None
    multa_rescisoria_total: Decimal | None = None

    # Garantia
    garantias: list[ModalidadeGarantia] = Field(default_factory=list)

    # Vigência
    data_inicio_vigencia: date | None = None
    data_fim_vigencia: date | None = None
    prazo_meses: int | None = None
    dia_vencimento_mensal: int | None = None

    # Reajuste
    reajuste: Reajuste = Field(default_factory=Reajuste)

    # Risco jurídico
    flags: FlagsJuridicas = Field(default_factory=FlagsJuridicas)

    # Memória de extração: campo lógico -> proveniência/confiança/revisão
    memoria_extracao: dict[str, RegistroCampo] = Field(default_factory=dict)

    @property
    def campos_para_revisao(self) -> list[str]:
        """Campos marcados para conferência manual (ordem determinística)."""
        return sorted(
            campo for campo, reg in self.memoria_extracao.items() if reg.necessita_revisao
        )

    @property
    def necessita_revisao(self) -> bool:
        """``True`` se qualquer campo exige conferência manual."""
        return any(reg.necessita_revisao for reg in self.memoria_extracao.values())
