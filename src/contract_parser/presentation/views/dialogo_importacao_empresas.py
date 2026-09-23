"""Diálogo de confirmação de importação de empresas (RF01, Fase 3).

``ctk.CTkToplevel`` modal aberto por ``MainWindow._on_importar`` depois que o
usuário já escolheu o arquivo (o ``filedialog`` continua lá — este módulo só
recebe o ``Path`` já resolvido). Mostra o resultado de ``inspecionar()``
(aba/header/mapa de colunas sugeridos + prévia tabular) e deixa o usuário
corrigir tudo antes de confirmar a importação de fato.

Nesta fase a confirmação chama ``EmpresasController.importar_planilha`` de
forma SÍNCRONA (sem thread/progresso real/cancelamento — isso é uma fase
futura, já suportada pelo controller mas não usada aqui).

Reaproveita os tokens de cor (``_COR_*``) e a formatação de resumo já
estabelecidos em ``main_window.py`` — import direto, sem duplicar valores.
``main_window.py`` importa este módulo só dentro de ``_on_importar`` (import
local), então esta dependência em sentido único não gera import circular.

Funções de nível de módulo (``formatar_tamanho_arquivo``, ``opcoes_colunas``,
``indice_da_opcao``, ``recalcular_mapa_e_total``, ``sugerir_para_aba``) são
puras — sem Tk — de propósito: concentram toda a lógica não-trivial do
diálogo para serem testadas isoladamente (ver ``xp-coach``: design simples e
TDD não abrem mão de testabilidade só porque a tela é gráfica).
"""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from contract_parser.application.empresa_importer import (
    AbaInfo,
    ArquivoImportacaoError,
    MapeamentoColunas,
    PlanilhaInfo,
    detectar_colunas,
    detectar_linha_header,
    inspecionar,
)
from contract_parser.presentation.controllers import ControllerError
from contract_parser.presentation.views.main_window import (
    _COR_PRIMARIA,
    _COR_PRIMARIA_CONTAINER,
    _COR_PRIMARIA_HOVER,
    _COR_SECUNDARIA,
    _COR_SUPERFICIE,
    _COR_SUPERFICIE_ALT,
    _COR_TEXTO_SECUNDARIO,
)

# Nº de linhas de amostra guardadas por aba em ``AbaInfo.amostra`` (ver
# ``empresa_importer._TAMANHO_AMOSTRA``). A prévia/recálculo desta tela opera
# só sobre essa amostra (até 20 linhas) — suficiente para o caso real
# (planilhas de empresas são pequenas); não é esperado que isso seja um
# problema prático, mas é a limitação a documentar.
_UNIDADES_TAMANHO = ("B", "KB", "MB", "GB")


def formatar_tamanho_arquivo(tamanho_bytes: int) -> str:
    """Formata bytes em texto legível (ex. ``"61.2 KB"``), sem lib externa."""
    tamanho = float(tamanho_bytes)
    for unidade in _UNIDADES_TAMANHO[:-1]:
        if tamanho < 1024:
            casas = 0 if unidade == "B" else 1
            return f"{tamanho:.{casas}f} {unidade}"
        tamanho /= 1024
    return f"{tamanho:.1f} {_UNIDADES_TAMANHO[-1]}"


def recalcular_mapa_e_total(
    amostra: list[list[object]], linha_header: int, n_linhas_uteis: int
) -> tuple[MapeamentoColunas | None, int]:
    """Recalcula o mapa de colunas sugerido + total estimado para uma aba.

    Reaproveita ``detectar_colunas`` (pública, opera sobre listas puras) sobre
    a ``amostra`` da aba em vez de reabrir o arquivo — ver nota de módulo
    sobre a limitação de 20 linhas. ``total_estimado`` usa ``n_linhas_uteis``
    (contagem REAL da aba, não limitada à amostra), espelhando a conta de
    ``inspecionar()``. O mapa fica ``None`` quando a linha de header está fora
    da amostra ou quando ``detectar_colunas`` não consegue mapear — quem
    decide, então, é o usuário (seletores manuais).
    """
    total_estimado = max(n_linhas_uteis - linha_header - 1, 0)
    if linha_header < 0 or linha_header >= len(amostra):
        return None, total_estimado
    headers = amostra[linha_header]
    dados = amostra[linha_header + 1 :]
    try:
        mapa = detectar_colunas(headers, dados)
    except ArquivoImportacaoError:
        mapa = None
    return mapa, total_estimado


def sugerir_para_aba(aba: AbaInfo) -> tuple[int, MapeamentoColunas | None, int]:
    """Sugere header + mapa + total para UMA aba específica (a que o usuário
    escolheu no seletor), espelhando o que ``inspecionar()`` faz para a aba
    que ela mesma escolhe (maior ``n_linhas_uteis``). Usa só a ``amostra`` já
    trazida em ``AbaInfo`` (``detectar_linha_header``/``detectar_colunas``,
    ambas públicas e sem IO) — não reabre o arquivo.
    """
    linha_header = detectar_linha_header(aba.amostra) if aba.amostra else 0
    mapa, total = recalcular_mapa_e_total(aba.amostra, linha_header, aba.n_linhas_uteis)
    return linha_header, mapa, total


def opcoes_colunas(amostra: list[list[object]], linha_header: int) -> list[str]:
    """Rótulos ``"idx — texto do header"`` para os seletores de mapeamento.

    Usa a linha de header atual (se estiver dentro da amostra) como fonte dos
    rótulos; cai para ``"idx — Coluna idx"`` quando o header está fora da
    amostra ou a célula correspondente está vazia.
    """
    n_cols = max((len(linha) for linha in amostra), default=0)
    headers = amostra[linha_header] if 0 <= linha_header < len(amostra) else []
    rotulos = []
    for i in range(n_cols):
        bruto = headers[i] if i < len(headers) else None
        texto = str(bruto).strip() if bruto not in (None, "") else ""
        rotulos.append(f"{i} — {texto}" if texto else f"{i} — Coluna {i}")
    return rotulos


def indice_da_opcao(rotulo: str) -> int:
    """Extrai o índice numérico de um rótulo produzido por ``opcoes_colunas``."""
    return int(rotulo.split(" — ", 1)[0])


class DialogoImportacaoEmpresas(ctk.CTkToplevel):
    """Tela de confirmação: aba/header/mapa de colunas + prévia, antes de importar."""

    def __init__(self, master: ctk.CTk, caminho: Path) -> None:
        super().__init__(master)
        self._master_janela = master
        self._caminho = Path(caminho)

        self.title("Confirmar importação de empresas")
        self.geometry("780x640")
        self.configure(fg_color=_COR_SUPERFICIE)

        self._info: PlanilhaInfo = inspecionar(self._caminho)
        self._aba_atual = self._info.aba_sugerida
        self._linha_header_atual = self._info.linha_header_sugerida
        self._mapa_atual = self._info.mapa_sugerido

        self._construir_widgets()
        self._atualizar_tudo()

        # Modal: foco travado nesta janela até fechar (Cancelar/Confirmar).
        self.transient(master)
        self.grab_set()
        self.focus_set()

    # ------------------------------------------------------------------ #
    # Construção dos widgets (estático — o conteúdo é preenchido por
    # ``_atualizar_tudo``/helpers, chamados na criação e a cada mudança de
    # aba/header/mapa).
    # ------------------------------------------------------------------ #
    def _construir_widgets(self) -> None:
        info = self._info

        frame_arquivo = ctk.CTkFrame(self, fg_color="transparent")
        frame_arquivo.pack(fill="x", padx=16, pady=(16, 8))
        tamanho = formatar_tamanho_arquivo(self._caminho.stat().st_size)
        ctk.CTkLabel(
            frame_arquivo,
            text=f"Arquivo: {self._caminho.name}  ·  {tamanho}",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(fill="x")

        frame_opcoes = ctk.CTkFrame(self, fg_color="transparent")
        frame_opcoes.pack(fill="x", padx=16, pady=4)

        # Seletor de aba: só faz sentido com mais de 1 aba (ODS multi-aba).
        self._combo_aba: ttk.Combobox | None = None
        if len(info.abas) > 1:
            campo_aba = ctk.CTkFrame(frame_opcoes, fg_color="transparent")
            campo_aba.pack(side="left", padx=(0, 16))
            ctk.CTkLabel(
                campo_aba, text="Aba:", text_color=_COR_TEXTO_SECUNDARIO, anchor="w"
            ).pack(anchor="w")
            self._combo_aba = ttk.Combobox(
                campo_aba, values=[a.nome for a in info.abas], state="readonly", width=22
            )
            self._combo_aba.set(info.abas[self._aba_atual].nome)
            self._combo_aba.bind("<<ComboboxSelected>>", self._on_aba_change)
            self._combo_aba.pack(anchor="w")

        campo_header = ctk.CTkFrame(frame_opcoes, fg_color="transparent")
        campo_header.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(
            campo_header, text="Linha de header:", text_color=_COR_TEXTO_SECUNDARIO, anchor="w"
        ).pack(anchor="w")
        self._ent_header = ctk.CTkEntry(campo_header, width=80)
        self._ent_header.pack(anchor="w")
        self._ent_header.bind("<Return>", self._on_header_change)
        self._ent_header.bind("<FocusOut>", self._on_header_change)

        self._lbl_total = ctk.CTkLabel(
            frame_opcoes, text="", text_color=_COR_TEXTO_SECUNDARIO, anchor="w"
        )
        self._lbl_total.pack(side="left", anchor="s")

        ctk.CTkLabel(
            self, text="Prévia das primeiras linhas", font=ctk.CTkFont(weight="bold"), anchor="w"
        ).pack(fill="x", padx=16, pady=(8, 4))

        frame_tabela = ctk.CTkFrame(self, fg_color=_COR_SUPERFICIE)
        frame_tabela.pack(fill="both", expand=True, padx=16, pady=4)
        self._tree_preview = ttk.Treeview(frame_tabela, show="headings")
        self._tree_preview.tag_configure("header", background=_COR_PRIMARIA_CONTAINER)
        self._tree_preview.tag_configure("par", background=_COR_SUPERFICIE_ALT)
        self._tree_preview.tag_configure("impar", background=_COR_SUPERFICIE)
        scrollbar = ttk.Scrollbar(
            frame_tabela, orient="vertical", command=self._tree_preview.yview
        )
        self._tree_preview.configure(yscrollcommand=scrollbar.set)
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)
        self._tree_preview.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        frame_mapa = ctk.CTkFrame(self, fg_color="transparent")
        frame_mapa.pack(fill="x", padx=16, pady=8)

        campo_cnpj = ctk.CTkFrame(frame_mapa, fg_color="transparent")
        campo_cnpj.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(
            campo_cnpj, text="Coluna de CNPJ:", text_color=_COR_TEXTO_SECUNDARIO, anchor="w"
        ).pack(anchor="w")
        self._combo_cnpj = ttk.Combobox(campo_cnpj, state="readonly", width=26)
        self._combo_cnpj.bind("<<ComboboxSelected>>", self._on_mapa_change)
        self._combo_cnpj.pack(anchor="w")

        campo_razao = ctk.CTkFrame(frame_mapa, fg_color="transparent")
        campo_razao.pack(side="left")
        ctk.CTkLabel(
            campo_razao,
            text="Coluna de Razão Social:",
            text_color=_COR_TEXTO_SECUNDARIO,
            anchor="w",
        ).pack(anchor="w")
        self._combo_razao = ttk.Combobox(campo_razao, state="readonly", width=26)
        self._combo_razao.bind("<<ComboboxSelected>>", self._on_mapa_change)
        self._combo_razao.pack(anchor="w")

        frame_botoes = ctk.CTkFrame(self, fg_color="transparent")
        frame_botoes.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(
            frame_botoes, text="Cancelar", fg_color=_COR_SECUNDARIA, command=self.destroy
        ).pack(side="right", padx=(8, 0))
        self._btn_confirmar = ctk.CTkButton(
            frame_botoes,
            text="Confirmar importação",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=self._on_confirmar,
        )
        self._btn_confirmar.pack(side="right")

    # ------------------------------------------------------------------ #
    # Estado → tela (recalcula e redesenha tudo a partir de
    # self._aba_atual/self._linha_header_atual/self._mapa_atual)
    # ------------------------------------------------------------------ #
    def _aba_info_atual(self) -> AbaInfo:
        return self._info.abas[self._aba_atual]

    def _atualizar_tudo(self) -> None:
        aba = self._aba_info_atual()
        amostra = aba.amostra

        self._ent_header.delete(0, "end")
        self._ent_header.insert(0, str(self._linha_header_atual + 1))

        mapa, total = recalcular_mapa_e_total(amostra, self._linha_header_atual, aba.n_linhas_uteis)
        self._mapa_atual = mapa
        self._lbl_total.configure(text=f"Total estimado: {total} linha(s)")

        self._preencher_preview(amostra)
        self._preencher_combos_mapa(amostra)
        self._atualizar_estado_confirmar()

    def _preencher_preview(self, amostra: list[list[object]]) -> None:
        tree = self._tree_preview
        tree.delete(*tree.get_children())
        n_cols = max((len(linha) for linha in amostra), default=1)
        colunas = [f"col{i}" for i in range(n_cols)]
        tree.configure(columns=colunas)
        for i, col_id in enumerate(colunas):
            tree.heading(col_id, text=str(i))
            tree.column(col_id, width=110, anchor="w")

        for i, linha in enumerate(amostra):
            valores = [
                "" if (v := (linha[c] if c < len(linha) else None)) is None else v
                for c in range(n_cols)
            ]
            if i == self._linha_header_atual:
                tags = ["header"]
            else:
                tags = ["impar" if i % 2 == 0 else "par"]
            tree.insert("", "end", values=valores, tags=tags)

    def _preencher_combos_mapa(self, amostra: list[list[object]]) -> None:
        opcoes = opcoes_colunas(amostra, self._linha_header_atual)
        self._combo_cnpj.configure(values=opcoes)
        self._combo_razao.configure(values=opcoes)

        mapa = self._mapa_atual
        if mapa is not None and mapa.idx_cnpj < len(opcoes):
            self._combo_cnpj.set(opcoes[mapa.idx_cnpj])
        else:
            self._combo_cnpj.set("")
        if mapa is not None and mapa.idx_razao < len(opcoes):
            self._combo_razao.set(opcoes[mapa.idx_razao])
        else:
            self._combo_razao.set("")

    def _atualizar_estado_confirmar(self) -> None:
        self._btn_confirmar.configure(state="normal" if self._mapa_atual is not None else "disabled")

    # ------------------------------------------------------------------ #
    # Handlers de interação
    # ------------------------------------------------------------------ #
    def _on_aba_change(self, event: object = None) -> None:
        assert self._combo_aba is not None
        nome_escolhido = self._combo_aba.get()
        for aba in self._info.abas:
            if aba.nome == nome_escolhido:
                self._aba_atual = aba.indice
                break
        self._linha_header_atual, self._mapa_atual, _total = sugerir_para_aba(
            self._aba_info_atual()
        )
        self._atualizar_tudo()

    def _on_header_change(self, event: object = None) -> None:
        texto = self._ent_header.get().strip()
        try:
            linha_1based = int(texto)
        except ValueError:
            linha_1based = self._linha_header_atual + 1
        self._linha_header_atual = max(linha_1based - 1, 0)
        self._atualizar_tudo()

    def _on_mapa_change(self, event: object = None) -> None:
        cnpj_txt = self._combo_cnpj.get()
        razao_txt = self._combo_razao.get()
        if not cnpj_txt or not razao_txt:
            self._mapa_atual = None
        else:
            self._mapa_atual = MapeamentoColunas(
                idx_cnpj=indice_da_opcao(cnpj_txt), idx_razao=indice_da_opcao(razao_txt)
            )
        self._atualizar_estado_confirmar()

    def _on_confirmar(self) -> None:
        if self._mapa_atual is None:
            return
        try:
            resumo = self._master_janela._c.empresas.importar_planilha(
                self._caminho,
                aba=self._aba_atual,
                linha_header=self._linha_header_atual,
                mapa=self._mapa_atual,
            )
        except ControllerError as exc:
            messagebox.showerror("Importação", str(exc))
            self._master_janela._atualizar_status()
            return
        self._master_janela._lbl_import.configure(
            text=(
                f"Importados: {resumo.importados}  ·  Duplicados: {resumo.duplicados}"
                f"  ·  Erros: {resumo.total_erros}"
            )
        )
        self._master_janela._recarregar_empresas()
        self.destroy()
