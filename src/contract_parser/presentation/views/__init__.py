"""Views CustomTkinter (camada presentation).

Estes módulos importam ``customtkinter``/``tkinter`` NO TOPO e só são carregados
quando a GUI de fato roda (``app.main`` faz o import preguiçoso). A suíte de
testes NÃO importa este pacote (exceto um smoke test guardado por
``pytest.importorskip``) — a lógica testável vive em ``presentation.controllers``.
"""
