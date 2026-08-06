# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o executável Windows do AI Contract Parser (GUI).

Gerado/mantido manualmente (não é saída automática de `pyi-makespec`).

Ponto de entrada: usamos diretamente
``src/contract_parser/presentation/app.py`` como script de análise — o
próprio módulo já expõe ``if __name__ == "__main__": raise SystemExit(main())``,
então não é necessário um launcher adicional; isso evita duplicar a lógica
do console-script ``contract-parser-gui`` (registrado em pyproject.toml,
que também aponta para ``contract_parser.presentation.app:main``).

Tesseract-OCR É EMBUTIDO no `.exe` (binário `tesseract.exe` + todas as DLLs
de runtime + o pacote de idioma `tessdata/por.traineddata`), para que a
máquina que apenas EXECUTA o `.exe` pronto não precise mais instalar o
Tesseract manualmente — só a máquina que RECOMPILA precisa tê-lo instalado
localmente (ver `TesseractOcr` em
`src/contract_parser/infrastructure/text_extractors.py`, que resolve o
caminho embutido automaticamente em runtime quando `TESSERACT_CMD` não foi
configurado pelo usuário). Por padrão, embutimos SOMENTE o pacote de idioma
português (`por.traineddata`) — o escopo está fechado a esse idioma; outros
idiomas exigiriam um pedido/alteração separada. O diretório de origem do
Tesseract na máquina de build pode ser configurado via a variável de
ambiente `TESSERACT_BUILD_DIR` (default: `C:\\Program Files\\Tesseract-OCR`,
instalação padrão do instalador UB-Mannheim).
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# customtkinter exige seus arquivos de tema/assets (JSON) embutidos
# explicitamente — não são detectados pela análise estática de imports.
customtkinter_datas = collect_data_files("customtkinter")

# --------------------------------------------------------------------------- #
# Tesseract-OCR embutido — resolução do diretório de origem (máquina de build)
# --------------------------------------------------------------------------- #
tesseract_dir = Path(os.environ.get("TESSERACT_BUILD_DIR", r"C:\Program Files\Tesseract-OCR"))

if not tesseract_dir.is_dir():
    raise SystemExit(
        f"Tesseract não encontrado em {tesseract_dir} — instale o Tesseract OCR "
        "(UB-Mannheim) nesta máquina antes de compilar, ou defina TESSERACT_BUILD_DIR."
    )

tesseract_exe = tesseract_dir / "tesseract.exe"
if not tesseract_exe.is_file():
    raise SystemExit(
        f"tesseract.exe não encontrado em {tesseract_dir} — instale o Tesseract OCR "
        "(UB-Mannheim) nesta máquina antes de compilar, ou defina TESSERACT_BUILD_DIR."
    )

tessdata_por = tesseract_dir / "tessdata" / "por.traineddata"
if not tessdata_por.is_file():
    raise SystemExit(
        f"Pacote de idioma português não encontrado em {tessdata_por} — reinstale o "
        "Tesseract OCR (UB-Mannheim) incluindo o pacote de idioma 'Portuguese', ou "
        "defina TESSERACT_BUILD_DIR apontando para uma instalação que o tenha."
    )

# Todas as DLLs de runtime do Tesseract (libtesseract, libleptonica, libpng,
# libjpeg, libtiff, libwebp etc.) + o próprio binário — destino: subpasta
# `tesseract/` dentro do bundle. NÃO incluímos os `.exe` auxiliares de
# treinamento (ambiguous_words.exe, cntraining.exe, ...) — não são usados em
# runtime.
tesseract_binaries = [(str(tesseract_exe), "tesseract")]
tesseract_binaries += [
    (str(dll), "tesseract") for dll in sorted(tesseract_dir.glob("*.dll"))
]

# Pacote de idioma português — único embutido por padrão.
tesseract_datas = [(str(tessdata_por), "tesseract/tessdata")]

a = Analysis(
    ["src/contract_parser/presentation/app.py"],
    pathex=["src"],
    binaries=tesseract_binaries,
    datas=customtkinter_datas + tesseract_datas,
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
