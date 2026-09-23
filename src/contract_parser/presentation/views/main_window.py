"""Janela principal da GUI (CustomTkinter) — RF06.

View FINA: monta widgets e delega TODA a lógica ao :class:`AppController` (e seus
sub-controllers). Não implementa regra de negócio nem formatação — apenas
dispara métodos do controller e desenha o resultado. ``customtkinter`` é
importado no topo de propósito: este módulo só é carregado por ``app.main`` (ou
por um smoke test com ``importorskip``), nunca pela suíte headless.

Acessibilidade/UX (skill ux-ui-designer-pro):
- Status do sistema visível (banner de conexão com ícone + texto, não só cor —
  daltonismo).
- Prevenção de erro: ações destrutivas (remover) confirmam; erros do controller
  viram diálogos legíveis, nunca stack traces.
- Hierarquia por abas (Lei de Hick: uma tarefa por aba) + grid consistente.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from contract_parser.infrastructure.audit_log import registrar_evento
from contract_parser.presentation.controllers import (
    AppController,
    ControllerError,
    LinhaPainel,
    ProcessamentoResultado,
)

# Paleta Material Design 3 (light) — cor + ícone/texto (nunca cor isolada).
# Ver ~/.claude/agents/specs/plano-redesign-material-design-light.md (Fase 1)
# para as justificativas de cada token e a verificação de contraste WCAG AA.
_COR_PRIMARIA = "#0B57A4"
_COR_PRIMARIA_HOVER = "#0A4A8C"
_COR_PRIMARIA_CONTAINER = "#D7E3F8"
_COR_SECUNDARIA = "#55606E"
_COR_SUPERFICIE = "#FFFFFF"
_COR_SUPERFICIE_ALT = "#EEF1F6"
_COR_FUNDO = "#F4F6FA"
_COR_TEXTO = "#1B1F27"
_COR_TEXTO_SECUNDARIO = "#49505A"
_COR_BORDA = "#C4CAD3"
_COR_OK = "#1B5E20"          # mantido, já validado
_COR_REVISAO = "#8A5A00"     # mantido, já validado
_COR_ERRO = "#B3261E"        # era #B00020 (token Material 2); token oficial MD3 light
_COR_ERRO_CONTAINER = "#F9DEDC"


class MainWindow(ctk.CTk):
    """Janela raiz com as quatro áreas do RF06 em abas."""

    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self._c = controller

        self.title("AI Contract Parser — Leitor de Contratos de Locação")
        self.geometry("1180x760")
        # Modo claro travado (não "system"): com o Windows em modo escuro, os
        # widgets sem cor customizada escureceriam sozinhos enquanto os tokens
        # novos (_COR_*) continuam claros, resultando numa UI inconsistente.
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=_COR_FUNDO)

        self._construir_banner_status()
        self._configurar_estilo_treeview()

        self._tabs = ctk.CTkTabview(self, fg_color=_COR_SUPERFICIE)
        self._tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._tab_empresas = self._tabs.add("Empresas")
        self._tab_processamento = self._tabs.add("Carregar Contratos")
        self._tab_painel = self._tabs.add("Painel de Contratos")
        self._tab_conformidade = self._tabs.add("Conformidade")

        self._construir_aba_empresas()
        self._construir_aba_processamento()
        self._construir_aba_painel()
        self._construir_aba_conformidade()

        self._atualizar_status()
        self._recarregar_empresas()
        self._recarregar_painel()
        self._recarregar_conformidade()

    # ------------------------------------------------------------------ #
    # Banner de status (conexão com o banco de dados SQLite)
    # ------------------------------------------------------------------ #
    def _construir_banner_status(self) -> None:
        moldura = ctk.CTkFrame(self, fg_color=_COR_SUPERFICIE, corner_radius=8)
        moldura.pack(fill="x", padx=12, pady=8)
        self._banner = ctk.CTkLabel(moldura, text="", anchor="w", height=32)
        self._banner.pack(fill="x", padx=16, pady=12)

    def _atualizar_status(self) -> None:
        status = self._c.status_conexao()
        icone = "✓" if status.ok else "⚠"
        cor = _COR_OK if status.ok else _COR_ERRO
        prefixo = "Banco de dados OK" if status.ok else "Sem conexão com o banco"
        self._banner.configure(text=f"{icone}  {prefixo} — {status.detalhe}", text_color=cor)

    # ------------------------------------------------------------------ #
    # Estilo ttk.Treeview (compartilhado por Painel e Empresas — configurado
    # uma única vez aqui para não duplicar a mesma configuração nas duas
    # abas; ver plano-migracao-treeview-tabelas.md, Fase 2/3)
    # ------------------------------------------------------------------ #
    def _configurar_estilo_treeview(self) -> None:
        # Tema "clam": é o único tema ttk que aceita customizar cores do
        # Treeview de forma consistente entre plataformas (o tema padrão do
        # Tk ignora várias opções de cor dependendo do SO/tema do sistema).
        style = ttk.Style(self)
        style.theme_use("clam")
        fonte_cabecalho = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        style.configure(
            "Treeview",
            background=_COR_SUPERFICIE,
            fieldbackground=_COR_SUPERFICIE,
            foreground=_COR_TEXTO,
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=_COR_SUPERFICIE_ALT,
            foreground=_COR_TEXTO,
            font=fonte_cabecalho,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", _COR_PRIMARIA_CONTAINER)],
            foreground=[("selected", _COR_TEXTO)],
        )

    # ------------------------------------------------------------------ #
    # Aba Empresas
    # ------------------------------------------------------------------ #
    # Colunas de dados do Treeview de Empresas — mesma técnica da Fase 2
    # (_COLS_PAINEL): uma única fonte de verdade para heading e coluna, com
    # larguras medidas via tkinter.font.Font(...).measure() (fonte real do
    # heading, "Segoe UI" 10 bold) sobre o cabeçalho e uma amostra de
    # conteúdo típico. "Razão Social" e "Origem" recebem folga generosa —
    # nomes de empresa e de arquivo de planilha tendem a ser longos.
    _COLS_EMPRESAS: tuple[tuple[str, str, int], ...] = (
        ("cnpj", "CNPJ", 150),
        ("razao_social", "Razão Social", 320),
        ("ativo", "Ativo", 70),
        ("origem", "Origem", 320),
    )

    def _construir_aba_empresas(self) -> None:
        topo = ctk.CTkFrame(self._tab_empresas)
        topo.pack(fill="x", padx=8, pady=8)

        ctk.CTkButton(
            topo,
            text="Importar .xlsx/.csv/.ods…",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=self._on_importar,
        ).pack(side="left", padx=4)
        self._lbl_import = ctk.CTkLabel(topo, text="", anchor="w")
        self._lbl_import.pack(side="left", padx=12)

        form = ctk.CTkFrame(self._tab_empresas)
        form.pack(fill="x", padx=8, pady=4)

        campo_cnpj = ctk.CTkFrame(form, fg_color="transparent")
        campo_cnpj.pack(side="left", padx=4, pady=4)
        ctk.CTkLabel(
            campo_cnpj, text="CNPJ", anchor="w", text_color=_COR_TEXTO_SECUNDARIO
        ).pack(anchor="w")
        self._ent_cnpj = ctk.CTkEntry(campo_cnpj, placeholder_text="CNPJ", width=180)
        self._ent_cnpj.pack(anchor="w")

        campo_razao = ctk.CTkFrame(form, fg_color="transparent")
        campo_razao.pack(side="left", padx=4, pady=4)
        ctk.CTkLabel(
            campo_razao, text="Razão Social", anchor="w", text_color=_COR_TEXTO_SECUNDARIO
        ).pack(anchor="w")
        self._ent_razao = ctk.CTkEntry(campo_razao, placeholder_text="Razão Social", width=320)
        self._ent_razao.pack(anchor="w")

        grupo_edicao = ctk.CTkFrame(form, fg_color="transparent")
        grupo_edicao.pack(side="left", padx=(8, 0), pady=4, anchor="s")
        ctk.CTkButton(
            grupo_edicao,
            text="Adicionar",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=self._on_adicionar,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            grupo_edicao, text="Salvar edição", fg_color=_COR_SECUNDARIA, command=self._on_editar
        ).pack(side="left", padx=4)

        divisor = ctk.CTkFrame(form, width=1, height=1, fg_color=_COR_BORDA)
        divisor.pack(side="left", fill="y", padx=20, pady=6)

        ctk.CTkButton(
            form, text="Remover", fg_color=_COR_ERRO, command=self._on_remover
        ).pack(side="left", padx=4, pady=4, anchor="s")

        container = ctk.CTkFrame(self._tab_empresas, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            container,
            text="Portfólio cadastrado",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        tabela_frame = ctk.CTkFrame(container, fg_color=_COR_SUPERFICIE)
        tabela_frame.pack(fill="both", expand=True)

        colunas = [col_id for col_id, _texto, _largura in self._COLS_EMPRESAS]
        self._tree_empresas = ttk.Treeview(tabela_frame, columns=colunas, show="headings")
        for col_id, texto, largura in self._COLS_EMPRESAS:
            self._tree_empresas.heading(col_id, text=texto)
            self._tree_empresas.column(col_id, width=largura, anchor="w")
        self._tree_empresas.tag_configure("par", background=_COR_SUPERFICIE_ALT)
        self._tree_empresas.tag_configure("impar", background=_COR_SUPERFICIE)

        scrollbar = ttk.Scrollbar(
            tabela_frame, orient="vertical", command=self._tree_empresas.yview
        )
        scrollbar_h = ttk.Scrollbar(
            tabela_frame, orient="horizontal", command=self._tree_empresas.xview
        )
        self._tree_empresas.configure(
            yscrollcommand=scrollbar.set, xscrollcommand=scrollbar_h.set
        )
        tabela_frame.grid_rowconfigure(0, weight=1)
        tabela_frame.grid_columnconfigure(0, weight=1)
        self._tree_empresas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        scrollbar_h.grid(row=1, column=0, sticky="ew")

        self._lbl_empresas_vazio = ctk.CTkLabel(
            container, text="", text_color=_COR_TEXTO_SECUNDARIO, anchor="w"
        )
        # Não empacotado ainda: só aparece quando não há linhas a mostrar
        # (ver _mostrar_estado_vazio_empresas), evitando flicker de
        # criar/destruir o widget a cada recarga (mesmo padrão do Painel).

    def _mostrar_estado_vazio_empresas(
        self, mensagem: str, cor: str = _COR_TEXTO_SECUNDARIO
    ) -> None:
        self._lbl_empresas_vazio.configure(text=mensagem, text_color=cor)
        self._lbl_empresas_vazio.pack(fill="x", pady=(4, 0))

    def _esconder_estado_vazio_empresas(self) -> None:
        self._lbl_empresas_vazio.pack_forget()

    def _recarregar_empresas(self) -> None:
        tree = self._tree_empresas
        tree.delete(*tree.get_children())
        try:
            linhas = self._c.empresas.linhas_empresas()
        except ControllerError as exc:
            self._atualizar_status()
            self._mostrar_estado_vazio_empresas(str(exc), cor=_COR_ERRO)
            return

        if not linhas:
            self._mostrar_estado_vazio_empresas(
                "Nenhuma empresa cadastrada ainda — importe uma planilha "
                "ou cadastre manualmente."
            )
            return

        self._esconder_estado_vazio_empresas()
        for i, linha in enumerate(linhas, start=1):
            tag_zebra = "impar" if i % 2 == 1 else "par"
            tree.insert(
                "",
                "end",
                iid=linha.cnpj,
                values=[linha.cnpj, linha.razao_social, linha.ativo, linha.origem],
                tags=[tag_zebra],
            )

    def _on_importar(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione a planilha de empresas",
            filetypes=[("Planilhas", "*.xlsx *.csv *.ods"), ("Todos", "*.*")],
        )
        if not caminho:
            return
        # Import local (não no topo do módulo): o diálogo importa os tokens de
        # cor deste módulo (``_COR_*``), então um import no topo criaria um
        # ciclo. Como este import só roda dentro do método (depois que a
        # classe MainWindow já está totalmente definida), não há ciclo real.
        from contract_parser.presentation.views.dialogo_importacao_empresas import (
            DialogoImportacaoEmpresas,
        )

        DialogoImportacaoEmpresas(self, Path(caminho))

    def _on_adicionar(self) -> None:
        cnpj = self._ent_cnpj.get().strip()
        razao_social = self._ent_razao.get().strip()
        if not cnpj or not razao_social:
            messagebox.showinfo("Adicionar empresa", "Informe o CNPJ e a Razão Social.")
            return
        try:
            self._c.empresas.adicionar_empresa(cnpj, razao_social)
        except ControllerError as exc:
            messagebox.showerror("Adicionar empresa", str(exc))
            return
        self._limpar_form_empresa()
        self._recarregar_empresas()

    def _on_editar(self) -> None:
        try:
            self._c.empresas.editar_empresa(
                self._ent_cnpj.get(), razao_social=self._ent_razao.get() or None
            )
        except ControllerError as exc:
            messagebox.showerror("Editar empresa", str(exc))
            return
        self._limpar_form_empresa()
        self._recarregar_empresas()

    def _on_remover(self) -> None:
        cnpj = self._ent_cnpj.get().strip()
        if not cnpj:
            messagebox.showinfo("Remover", "Informe o CNPJ no campo para remover.")
            return
        if not messagebox.askyesno("Remover", f"Remover a empresa {cnpj}?"):
            return
        try:
            removeu = self._c.empresas.remover_empresa(cnpj)
        except ControllerError as exc:
            messagebox.showerror("Remover empresa", str(exc))
            return
        if not removeu:
            messagebox.showinfo("Remover", "Nenhuma empresa com esse CNPJ.")
        self._limpar_form_empresa()
        self._recarregar_empresas()

    def _limpar_form_empresa(self) -> None:
        self._ent_cnpj.delete(0, "end")
        self._ent_razao.delete(0, "end")

    # ------------------------------------------------------------------ #
    # Aba Processamento
    # ------------------------------------------------------------------ #
    def _construir_aba_processamento(self) -> None:
        topo = ctk.CTkFrame(self._tab_processamento)
        topo.pack(fill="x", padx=8, pady=8)
        ctk.CTkButton(
            topo,
            text="Selecionar pasta e processar…",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=self._on_processar,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            topo,
            text="Selecionar arquivo(s) e processar…",
            fg_color=_COR_SECUNDARIA,
            command=self._on_processar_arquivos,
        ).pack(side="left", padx=4)
        self._lbl_proc = ctk.CTkLabel(topo, text="Nenhuma pasta processada.", anchor="w")
        self._lbl_proc.pack(side="left", padx=12)

        ctk.CTkLabel(
            self._tab_processamento,
            text="Processe uma pasta inteira ou escolha arquivos avulsos.",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=_COR_TEXTO_SECUNDARIO,
        ).pack(fill="x", padx=12, pady=(0, 4))

        self._barra_progresso = ctk.CTkProgressBar(
            self._tab_processamento, mode="indeterminate"
        )
        # Não empacotada ainda: só aparece durante _processar_e_exibir.

        self._log_proc = ctk.CTkTextbox(self._tab_processamento)
        self._log_proc.pack(fill="both", expand=True, padx=8, pady=8)

    def _on_processar(self) -> None:
        pasta = filedialog.askdirectory(title="Selecione a pasta de contratos")
        if not pasta:
            return
        self._processar_e_exibir(lambda: self._c.processar_pasta(pasta), f"Pasta: {pasta}")

    def _on_processar_arquivos(self) -> None:
        caminhos = filedialog.askopenfilenames(
            title="Selecione o(s) arquivo(s) de contratos",
            filetypes=[("Contratos", "*.pdf *.docx"), ("Todos", "*.*")],
        )
        if not caminhos:
            return
        lista = list(caminhos)
        origem = "Arquivos:\n" + "\n".join(f"  {caminho}" for caminho in lista)
        self._processar_e_exibir(lambda: self._c.processar_arquivos(lista), origem)

    def _processar_e_exibir(
        self, chamada: Callable[[], ProcessamentoResultado], origem: str
    ) -> None:
        self._barra_progresso.pack(fill="x", padx=8, pady=(0, 8))
        self._barra_progresso.start()
        self.update_idletasks()
        try:
            resultado = chamada()
        except ControllerError as exc:
            messagebox.showerror("Carregar Contratos", str(exc))
            self._atualizar_status()
            return
        finally:
            self._barra_progresso.stop()
            self._barra_progresso.pack_forget()
        self._lbl_proc.configure(
            text=(
                f"Arquivos: {resultado.total_arquivos}  ·  Processados: {resultado.processados}"
                f"  ·  Duplicados: {resultado.duplicados}  ·  Erros: {len(resultado.erros)}"
            )
        )
        self._log_proc.delete("1.0", "end")
        self._log_proc.insert("end", f"{origem}\n\n")
        self._log_proc.insert("end", f"Contratos extraídos: {len(resultado.contratos)}\n")
        if resultado.erros:
            self._log_proc.insert("end", "\nErros por arquivo:\n")
            for arquivo, motivo in resultado.erros:
                self._log_proc.insert("end", f"  ⚠ {arquivo}: {motivo}\n")
        self._recarregar_painel()
        self._recarregar_conformidade()

    # ------------------------------------------------------------------ #
    # Aba Painel de Contratos (Relatório 01)
    # ------------------------------------------------------------------ #
    # Colunas de dados do Treeview do Painel — id interno, cabeçalho exibido
    # e largura inicial (px). Uma única fonte de verdade para não desalinhar
    # heading/coluna (era exatamente o bug do layout anterior).
    _COLS_PAINEL: tuple[tuple[str, str, int], ...] = (
        ("locatario", "Locatário", 190),
        ("locador", "Locador", 190),
        ("valor", "Valor", 90),
        ("irrf", "IRRF", 90),
        ("reducao_irrf", "Redução IRRF", 120),
        ("indice", "Índice", 70),
        ("proximo_reajuste", "Próx. Reajuste", 135),
        ("automatico", "Auto?", 60),
        ("vencimento", "Vencimento", 120),
        ("revisao", "Revisão", 90),
    )

    def _construir_aba_painel(self) -> None:
        linha_filtros = ctk.CTkFrame(self._tab_painel)
        linha_filtros.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(linha_filtros, text="Índice:").pack(side="left", padx=(4, 2))
        self._opt_indice = ctk.CTkOptionMenu(linha_filtros, values=["(todos)"])
        self._opt_indice.pack(side="left", padx=4)

        self._chk_auto = ctk.CTkCheckBox(linha_filtros, text="Só reajuste automático")
        self._chk_auto.pack(side="left", padx=8)

        self._ent_busca = ctk.CTkEntry(
            linha_filtros, placeholder_text="Buscar (locatário/locador)…", width=280
        )
        self._ent_busca.pack(side="left", padx=4)

        linha_acoes = ctk.CTkFrame(self._tab_painel)
        linha_acoes.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(
            linha_acoes,
            text="Filtrar",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=self._recarregar_painel,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            linha_acoes, text="Limpar", fg_color=_COR_SECUNDARIA, command=self._limpar_filtros
        ).pack(side="left", padx=4)
        # Empacotados da direita para a esquerda: "Limpar tudo" primeiro fica
        # na borda direita, "Excluir selecionado" fica logo à esquerda dele.
        ctk.CTkButton(
            linha_acoes, text="Limpar tudo", fg_color=_COR_ERRO, command=self._on_limpar_tudo
        ).pack(side="right", padx=(4, 4))
        ctk.CTkButton(
            linha_acoes,
            text="Excluir selecionado",
            fg_color=_COR_ERRO,
            command=self._on_excluir_selecionados,
        ).pack(side="right", padx=(24, 4))

        container = ctk.CTkFrame(self._tab_painel, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            container,
            text="Relatório 01 — Contratos processados",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        tabela_frame = ctk.CTkFrame(container, fg_color=_COR_SUPERFICIE)
        tabela_frame.pack(fill="both", expand=True)

        colunas = [col_id for col_id, _texto, _largura in self._COLS_PAINEL]
        self._tree_painel = ttk.Treeview(tabela_frame, columns=colunas, show="headings")
        for col_id, texto, largura in self._COLS_PAINEL:
            self._tree_painel.heading(col_id, text=texto)
            self._tree_painel.column(col_id, width=largura, anchor="w")
        self._tree_painel.tag_configure("par", background=_COR_SUPERFICIE_ALT)
        self._tree_painel.tag_configure("impar", background=_COR_SUPERFICIE)
        self._tree_painel.tag_configure("revisao", foreground=_COR_REVISAO)

        scrollbar = ttk.Scrollbar(
            tabela_frame, orient="vertical", command=self._tree_painel.yview
        )
        scrollbar_h = ttk.Scrollbar(
            tabela_frame, orient="horizontal", command=self._tree_painel.xview
        )
        self._tree_painel.configure(
            yscrollcommand=scrollbar.set, xscrollcommand=scrollbar_h.set
        )
        tabela_frame.grid_rowconfigure(0, weight=1)
        tabela_frame.grid_columnconfigure(0, weight=1)
        self._tree_painel.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        scrollbar_h.grid(row=1, column=0, sticky="ew")

        self._col_revisao_id = f"#{colunas.index('revisao') + 1}"
        self._mapa_painel_iid_registro: dict[str, str] = {}
        self._mapa_painel_motivo: dict[str, str] = {}
        self._tooltip_painel: tk.Toplevel | None = None
        self._tooltip_painel_chave: tuple[str, str] | None = None
        self._tree_painel.bind("<Motion>", self._on_motion_painel)
        self._tree_painel.bind("<Leave>", self._esconder_tooltip_painel)

        self._lbl_painel_vazio = ctk.CTkLabel(
            container, text="", text_color=_COR_TEXTO_SECUNDARIO, anchor="w"
        )
        # Não empacotado ainda: só aparece quando não há linhas a mostrar
        # (ver _mostrar_estado_vazio_painel), evitando flicker de
        # criar/destruir o widget a cada recarga.

    def _limpar_filtros(self) -> None:
        self._opt_indice.set("(todos)")
        self._chk_auto.deselect()
        self._ent_busca.delete(0, "end")
        self._recarregar_painel()

    def _mostrar_estado_vazio_painel(self, mensagem: str) -> None:
        self._lbl_painel_vazio.configure(text=mensagem)
        self._lbl_painel_vazio.pack(fill="x", pady=(4, 0))

    def _esconder_estado_vazio_painel(self) -> None:
        self._lbl_painel_vazio.pack_forget()

    def _recarregar_painel(self) -> None:
        if not self._c.relatorio.tem_dados():
            registrar_evento("Painel: tem_dados()=False, sem histórico para desenhar")
            self._desenhar_painel([])
            self._mostrar_estado_vazio_painel(
                "Nenhum contrato processado ainda — vá em 'Carregar Contratos' "
                "para começar."
            )
            return
        indices = ["(todos)", *self._c.relatorio.indices_disponiveis()]
        self._opt_indice.configure(values=indices)

        indice = self._opt_indice.get()
        texto_busca = self._ent_busca.get() or None
        auto = True if self._chk_auto.get() else None
        linhas = self._c.relatorio.filtrar(
            indice=None if indice == "(todos)" else indice,
            apenas_automatico=auto,
            texto=texto_busca,
        )
        registrar_evento(
            f"Painel: {len(linhas)} linha(s) apos filtro "
            f"(indice={indice!r}, busca={texto_busca!r}, auto={auto!r})"
        )
        self._desenhar_painel(linhas)
        if not linhas:
            self._mostrar_estado_vazio_painel("Nenhum contrato encontrado com esse filtro.")
        else:
            self._esconder_estado_vazio_painel()

    def _desenhar_painel(self, linhas: list[LinhaPainel]) -> None:
        self._esconder_tooltip_painel()
        tree = self._tree_painel
        tree.delete(*tree.get_children())
        self._mapa_painel_iid_registro.clear()
        self._mapa_painel_motivo.clear()

        for i, linha in enumerate(linhas, start=1):
            # iid = registro_id quando disponível (usado por
            # _on_excluir_selecionados); sintético quando None, para não
            # colidir e ainda assim manter a linha selecionável/exibível.
            iid = linha.registro_id if linha.registro_id is not None else f"_linha{i}"
            if linha.registro_id is not None:
                self._mapa_painel_iid_registro[iid] = linha.registro_id
            if linha.motivo_revisao:
                self._mapa_painel_motivo[iid] = linha.motivo_revisao

            # Zebra striping via tag; "revisao" some depois para sobrepor a
            # cor do texto (foreground) sem mexer no background da zebra.
            tag_zebra = "impar" if i % 2 == 1 else "par"
            tags = [tag_zebra, "revisao"] if linha.revisao else [tag_zebra]

            revisao_txt = "⚠ revisar" if linha.revisao else "ok"
            valores = [
                linha.locatario, linha.locador, linha.valor, linha.irrf, linha.reducao_irrf,
                linha.indice, linha.proximo_reajuste, linha.automatico, linha.vencimento,
                revisao_txt,
            ]
            tree.insert("", "end", iid=iid, values=valores, tags=tags)

    def _on_motion_painel(self, event: tk.Event) -> None:
        tree = self._tree_painel
        row_iid = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        motivo = (
            self._mapa_painel_motivo.get(row_iid)
            if row_iid and col_id == self._col_revisao_id
            else None
        )
        chave = (row_iid, col_id) if motivo else None
        if chave == self._tooltip_painel_chave:
            return
        self._esconder_tooltip_painel()
        self._tooltip_painel_chave = chave
        if not motivo:
            return
        x = tree.winfo_rootx() + event.x + 12
        y = tree.winfo_rooty() + event.y + 16
        self._tooltip_painel = tk.Toplevel(tree)
        self._tooltip_painel.wm_overrideredirect(True)
        self._tooltip_painel.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tooltip_painel,
            text=motivo,
            background="#313033",
            foreground="#FFFFFF",
            relief="solid",
            borderwidth=1,
            justify="left",
            wraplength=360,
            padx=6,
            pady=4,
        ).pack()

    def _esconder_tooltip_painel(self, event: object = None) -> None:
        if self._tooltip_painel is not None:
            self._tooltip_painel.destroy()
            self._tooltip_painel = None
        self._tooltip_painel_chave = None

    def _on_excluir_selecionados(self) -> None:
        selecionados = self._tree_painel.selection()
        if not selecionados:
            messagebox.showinfo("Excluir selecionado", "Selecione um contrato para excluir.")
            return
        registro_ids = [
            self._mapa_painel_iid_registro[iid]
            for iid in selecionados
            if iid in self._mapa_painel_iid_registro
        ]
        if not registro_ids:
            messagebox.showinfo(
                "Excluir selecionado", "Nenhum dos itens selecionados pode ser excluído."
            )
            return
        self._on_excluir_contrato(registro_ids)

    def _on_excluir_contrato(self, registro_id: str | list[str]) -> None:
        ids = [registro_id] if isinstance(registro_id, str) else list(registro_id)
        pergunta = (
            "Excluir este contrato do histórico? Esta ação não pode ser desfeita."
            if len(ids) == 1
            else (
                f"Excluir {len(ids)} contratos selecionados do histórico? "
                "Esta ação não pode ser desfeita."
            )
        )
        if not messagebox.askyesno("Excluir contrato", pergunta):
            return
        try:
            for rid in ids:
                self._c.relatorio.excluir_contrato(rid)
        except ControllerError as exc:
            messagebox.showerror("Excluir contrato", str(exc))
            return
        self._recarregar_painel()

    def _on_limpar_tudo(self) -> None:
        if not messagebox.askyesno(
            "Limpar tudo",
            "Isto vai excluir PERMANENTEMENTE todos os contratos do histórico. "
            "Esta ação não pode ser desfeita. Continuar?",
        ):
            return
        try:
            self._c.relatorio.excluir_todos_contratos()
        except ControllerError as exc:
            messagebox.showerror("Limpar tudo", str(exc))
            return
        self._recarregar_painel()

    # ------------------------------------------------------------------ #
    # Aba Conformidade (Relatório 02)
    # ------------------------------------------------------------------ #
    def _construir_aba_conformidade(self) -> None:
        acoes = ctk.CTkFrame(self._tab_conformidade)
        acoes.pack(fill="x", padx=8, pady=8)
        ctk.CTkButton(
            acoes,
            text="Exportar Excel…",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=lambda: self._on_exportar("excel"),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            acoes,
            text="Exportar PDF…",
            fg_color=_COR_PRIMARIA,
            hover_color=_COR_PRIMARIA_HOVER,
            command=lambda: self._on_exportar("pdf"),
        ).pack(side="left", padx=4)

        self._box_totais = ctk.CTkFrame(self._tab_conformidade)
        self._box_totais.pack(fill="x", padx=8, pady=4)

        self._tabela_pendencias = ctk.CTkScrollableFrame(
            self._tab_conformidade,
            label_text="Pendências — contratos não encontrados",
            fg_color=_COR_SUPERFICIE,
        )
        self._tabela_pendencias.pack(fill="both", expand=True, padx=8, pady=8)

    def _recarregar_conformidade(self) -> None:
        if not self._c.relatorio.tem_dados():
            return
        for w in self._box_totais.winfo_children():
            w.destroy()
        for w in self._tabela_pendencias.winfo_children():
            w.destroy()

        resumo = self._c.relatorio.resumo_conformidade()
        totais = [
            ("Empresas cadastradas", resumo.total_empresas_cadastradas),
            ("Contratos localizados", resumo.total_contratos_localizados),
            ("Empresas com contrato", resumo.total_encontrados),
            ("Pendências", resumo.total_pendencias),
        ]
        for col, (rotulo, valor) in enumerate(totais):
            cel = ctk.CTkFrame(
                self._box_totais,
                fg_color=_COR_SUPERFICIE,
                corner_radius=12,
                border_width=1,
                border_color=_COR_BORDA,
            )
            cel.grid(row=0, column=col, padx=8, pady=6, sticky="w")
            ctk.CTkLabel(cel, text=rotulo, text_color=_COR_TEXTO_SECUNDARIO).pack(
                padx=16, pady=(12, 0)
            )
            ctk.CTkLabel(
                cel, text=str(valor), font=ctk.CTkFont(size=20, weight="bold")
            ).pack(padx=16, pady=(0, 12))

        if resumo.pendencias:
            for i, pendencia in enumerate(resumo.pendencias):
                ctk.CTkLabel(
                    self._tabela_pendencias, text=f"⚠ {pendencia}", text_color=_COR_REVISAO, anchor="w"
                ).grid(row=i, column=0, sticky="w", padx=6, pady=2)
        else:
            ctk.CTkLabel(
                self._tabela_pendencias, text="✓ Nenhuma pendência.", text_color=_COR_OK, anchor="w"
            ).grid(row=0, column=0, sticky="w", padx=6, pady=2)

    def _on_exportar(self, formato: str) -> None:
        ext = ".xlsx" if formato == "excel" else ".pdf"
        destino = filedialog.asksaveasfilename(
            title=f"Exportar relatório ({formato})",
            defaultextension=ext,
            filetypes=[(formato.upper(), f"*{ext}")],
        )
        if not destino:
            return
        try:
            caminho = self._c.relatorio.exportar(formato, destino)
        except (ControllerError, ValueError) as exc:
            messagebox.showerror("Exportar", str(exc))
            return
        messagebox.showinfo("Exportar", f"Relatório salvo em:\n{Path(caminho)}")
