"""Entrypoint da GUI (RF06) — console-script ``contract-parser-gui``.

Responsável APENAS por compor as dependências reais (repositório SQLite +
serviços) e abrir a janela. Mantém ``customtkinter``/``tkinter`` fora do escopo
de import do módulo: ``main`` importa a view preguiçosamente, então
``import contract_parser.presentation.app`` funciona em ambiente headless/sem a
lib gráfica (só ``main()`` exige display + customtkinter).

Persistência (ADR-002): o :class:`EmpresaRepository` de produção abre o arquivo
SQLite local (``settings.database_path``), criando-o automaticamente se ainda
não existir — não há serviço externo a subir antes de abrir a GUI. Se o
caminho configurado não for gravável, o banner de status avisa o operador em
vez de derrubar o processo (degradação graciosa, §6).
"""
from __future__ import annotations

from collections.abc import Sequence

from contract_parser.presentation.controllers import AppController


def build_controller() -> AppController:
    """Compõe o controller raiz com o repositório e serviços de produção."""
    from contract_parser.infrastructure.empresa_repository import EmpresaRepository

    repository = EmpresaRepository()
    return AppController(repository)


def main(argv: Sequence[str] | None = None) -> int:
    """Abre a janela principal da GUI. Retorna 0 ao encerrar normalmente."""
    from contract_parser.presentation.views.main_window import MainWindow

    controller = build_controller()
    janela = MainWindow(controller)
    janela.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
