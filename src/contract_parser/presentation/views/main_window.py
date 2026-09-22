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
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox

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


class _Tooltip:
    """Tooltip simples de hover (bind Enter/Leave + Toplevel sem decoração).

    Não depende de nenhuma lib externa — primeira implementação do tipo neste
    projeto (ver .agent/specs/plano-3-features-persistencia-pdf-tooltip.md,
    Fase 5). Só liga o hover quando há texto (evita bind inútil em células
    sem motivo de revisão) e destrói a janela ao sair, para não deixar a
    tooltip "grudada" na tela quando o mouse sai do widget.
    """

    def __init__(self, widget: ctk.CTkBaseClass, texto: str) -> None:
        self._widget = widget
        self._texto = texto
        self._janela: tk.Toplevel | None = None
        if texto:
            widget.bind("<Enter>", self._mostrar)
            widget.bind("<Leave>", self._esconder)

    def _mostrar(self, event: object = None) -> None:
        if self._janela is not None:
            return
        x = self._widget.winfo_rootx() + 12
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._janela = tk.Toplevel(self._widget)
        self._janela.wm_overrideredirect(True)
        self._janela.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._janela,
            text=self._texto,
            background="#313033",
            foreground="#FFFFFF",
            relief="solid",
            borderwidth=1,
            justify="left",
            wraplength=360,
            padx=6,
            pady=4,
        ).pack()

    def _esconder(self, event: object = None) -> None:
        if self._janela is not None:
            self._janela.destroy()
            self._janela = None


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
    # Aba Empresas
    # ------------------------------------------------------------------ #
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

        divisor = ctk.CTkFrame(form, width=1, fg_color=_COR_BORDA)
        divisor.pack(side="left", fill="y", padx=20, pady=6)

        ctk.CTkButton(
            form, text="Remover", fg_color=_COR_ERRO, command=self._on_remover
        ).pack(side="left", padx=4, pady=4, anchor="s")

        self._tabela_empresas = ctk.CTkScrollableFrame(
            self._tab_empresas, label_text="Portfólio cadastrado", fg_color=_COR_SUPERFICIE
        )
        self._tabela_empresas.pack(fill="both", expand=True, padx=8, pady=8)

    def _recarregar_empresas(self) -> None:
        for w in self._tabela_empresas.winfo_children():
            w.destroy()
        try:
            linhas = self._c.empresas.linhas_empresas()
        except ControllerError as exc:
            self._atualizar_status()
            ctk.CTkLabel(
                self._tabela_empresas, text=str(exc), text_color=_COR_ERRO, wraplength=900
            ).grid(row=0, column=0, sticky="w", padx=6, pady=6)
            return

        if not linhas:
            ctk.CTkLabel(
                self._tabela_empresas,
                text=(
                    "Nenhuma empresa cadastrada ainda — importe uma planilha "
                    "ou cadastre manualmente."
                ),
                text_color=_COR_TEXTO_SECUNDARIO,
            ).grid(row=0, column=0, sticky="w", padx=6, pady=6)
            return

        cabecalhos = ["CNPJ", "Razão Social", "Ativo", "Origem"]
        for col, texto in enumerate(cabecalhos):
            ctk.CTkLabel(
                self._tabela_empresas, text=texto, font=ctk.CTkFont(weight="bold")
            ).grid(row=0, column=col, sticky="w", padx=6, pady=4)
        for i, linha in enumerate(linhas, start=1):
            for col, valor in enumerate(
                [linha.cnpj, linha.razao_social, linha.ativo, linha.origem]
            ):
                ctk.CTkLabel(self._tabela_empresas, text=valor, anchor="w").grid(
                    row=i, column=col, sticky="w", padx=6, pady=2
                )

    def _on_importar(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione a planilha de empresas",
            filetypes=[("Planilhas", "*.xlsx *.csv *.ods"), ("Todos", "*.*")],
        )
        if not caminho:
            return
        try:
            resumo = self._c.empresas.importar_planilha(caminho)
        except ControllerError as exc:
            messagebox.showerror("Importação", str(exc))
            self._atualizar_status()
            return
        self._lbl_import.configure(
            text=(
                f"Importados: {resumo.importados}  ·  Duplicados: {resumo.duplicados}"
                f"  ·  Erros: {resumo.total_erros}"
            )
        )
        self._recarregar_empresas()

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
        ctk.CTkButton(
            linha_acoes, text="Limpar tudo", fg_color=_COR_ERRO, command=self._on_limpar_tudo
        ).pack(side="right", padx=(24, 4))

        self._tabela_painel = ctk.CTkScrollableFrame(
            self._tab_painel,
            label_text="Relatório 01 — Contratos processados",
            fg_color=_COR_SUPERFICIE,
        )
        self._tabela_painel.pack(fill="both", expand=True, padx=8, pady=8)

    def _limpar_filtros(self) -> None:
        self._opt_indice.set("(todos)")
        self._chk_auto.deselect()
        self._ent_busca.delete(0, "end")
        self._recarregar_painel()

    def _recarregar_painel(self) -> None:
        if not self._c.relatorio.tem_dados():
            registrar_evento("Painel: tem_dados()=False, sem histórico para desenhar")
            for w in self._tabela_painel.winfo_children():
                w.destroy()
            ctk.CTkLabel(
                self._tabela_painel,
                text=(
                    "Nenhum contrato processado ainda — vá em 'Carregar Contratos' "
                    "para começar."
                ),
                text_color=_COR_TEXTO_SECUNDARIO,
            ).grid(row=0, column=0, sticky="w", padx=6, pady=6)
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

    def _desenhar_painel(self, linhas: list[LinhaPainel]) -> None:
        for w in self._tabela_painel.winfo_children():
            w.destroy()
        cabecalhos = [
            "Locatário", "Locador", "Valor", "IRRF", "Redução IRRF", "Índice",
            "Próx. Reajuste", "Auto?", "Vencimento", "Revisão", "Ações",
        ]
        # Sem grid_columnconfigure(weight=...): as colunas do cabeçalho devem
        # manter a largura NATURAL do texto. Com weight=1 em todas (tentativa
        # anterior da Fase 3) o Tkinter comprime colunas proporcionalmente
        # quando a soma das larguras naturais excede a área visível do
        # CTkScrollableFrame (sem scroll horizontal) — cabeçalhos e células
        # ficavam cortados/sobrepostos. Ver plano de correção do bug.
        for col, texto in enumerate(cabecalhos):
            ctk.CTkLabel(
                self._tabela_painel, text=texto, font=ctk.CTkFont(weight="bold")
            ).grid(row=0, column=col, sticky="w", padx=6, pady=4)

        if not linhas:
            ctk.CTkLabel(
                self._tabela_painel,
                text="Nenhum contrato encontrado com esse filtro.",
                text_color=_COR_TEXTO_SECUNDARIO,
            ).grid(row=1, column=0, columnspan=len(cabecalhos), sticky="w", padx=6, pady=6)
            return

        # Larguras aproximadas por coluna (px) usadas só dentro do frame de
        # cada linha (pack, ver abaixo). Não pretendem alinhar pixel-a-pixel
        # com o cabeçalho (grid manual) — este layout nunca foi
        # pixel-perfect no projeto; o que importa é não haver sobreposição.
        larguras_col = [190, 190, 90, 90, 100, 70, 110, 60, 100, 90]

        col_revisao = cabecalhos.index("Revisão")
        for i, linha in enumerate(linhas, start=1):
            # Zebra striping: linhas ímpares (1, 3, ...) em _COR_SUPERFICIE,
            # pares em _COR_SUPERFICIE_ALT — legibilidade em tabelas longas.
            # Implementado como um CTkFrame por linha (não weight nas
            # colunas do grid principal) para não comprimir a largura
            # natural das colunas do cabeçalho — ver nota acima.
            cor_linha = _COR_SUPERFICIE if i % 2 == 1 else _COR_SUPERFICIE_ALT
            # Destaque de revisão: ícone + texto + cor (nunca cor isolada).
            revisao_txt = "⚠ revisar" if linha.revisao else "ok"
            cor = _COR_REVISAO if linha.revisao else None
            celulas = [
                linha.locatario, linha.locador, linha.valor, linha.irrf, linha.reducao_irrf,
                linha.indice, linha.proximo_reajuste, linha.automatico, linha.vencimento,
                revisao_txt,
            ]
            linha_frame = ctk.CTkFrame(
                self._tabela_painel, fg_color=cor_linha, corner_radius=0
            )
            linha_frame.grid(
                row=i, column=0, columnspan=len(cabecalhos), sticky="ew", padx=0, pady=1
            )
            for col, valor in enumerate(celulas):
                label = ctk.CTkLabel(
                    linha_frame,
                    text=valor,
                    anchor="w",
                    text_color=cor,
                    fg_color="transparent",
                    width=larguras_col[col],
                )
                label.pack(side="left", padx=6, pady=4)
                if col == col_revisao:
                    # Tooltip explica o motivo específico da linha (§Fase 5) —
                    # só liga o hover quando há motivo (texto vazio = sem-op).
                    _Tooltip(label, linha.motivo_revisao)
            if linha.registro_id is not None:
                ctk.CTkButton(
                    linha_frame,
                    text="Excluir",
                    fg_color=_COR_ERRO,
                    width=70,
                    command=lambda rid=linha.registro_id: self._on_excluir_contrato(rid),
                ).pack(side="left", padx=6, pady=2)

    def _on_excluir_contrato(self, registro_id: str) -> None:
        if not messagebox.askyesno(
            "Excluir contrato",
            "Excluir este contrato do histórico? Esta ação não pode ser desfeita.",
        ):
            return
        try:
            self._c.relatorio.excluir_contrato(registro_id)
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
