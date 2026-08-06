# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o executável Windows do AI Contract Parser (GUI).

Gerado/mantido manualmente (não é saída automática de `pyi-makespec`).

Ponto de entrada: usamos diretamente
``src/contract_parser/presentation/app.py`` como script de análise — o
próprio módulo já expõe ``if __name__ == "__main__": raise SystemExit(main())``,
então não é necessário um launcher adicional; isso evita duplicar a lógica
do console-script ``contract-parser-gui`` (registrado em pyproject.toml,
que também aponta para ``contract_parser.presentation.app:main``).

Tesseract-OCR NÃO é embutido: continua como dependência externa do host,
configurada via `TESSERACT_CMD` (ver `.env.example`). O usuário final precisa
instalá-lo separadamente.
"""

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# customtkinter exige seus arquivos de tema/assets (JSON) embutidos
# explicitamente — não são detectados pela análise estática de imports.
customtkinter_datas = collect_data_files("customtkinter")

a = Analysis(
    ["src/contract_parser/presentation/app.py"],
    pathex=["src"],
    binaries=[],
    datas=customtkinter_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ContractParser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # aplicação GUI (CustomTkinter) — sem janela de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
