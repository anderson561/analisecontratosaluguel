@echo off
REM Gera o executavel Windows (ContractParser.exe) via PyInstaller.
REM Uso: build.bat  (rodar na raiz do repositorio)
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM Cria o venv de build se ainda nao existir.
if not exist ".venv\Scripts\activate.bat" (
    echo [build] Criando ambiente virtual em .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [build] ERRO: falha ao criar o venv. Verifique se o Python 3.11+ esta no PATH.
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [build] ERRO: falha ao ativar o venv.
    exit /b 1
)

echo [build] Instalando o projeto e dependencias de build (pip install -e .[build]) ...
pip install -e ".[build]"
if errorlevel 1 (
    echo [build] ERRO: falha ao instalar dependencias.
    exit /b 1
)

echo [build] Rodando PyInstaller ...
pyinstaller contract_parser.spec --clean --noconfirm
if errorlevel 1 (
    echo [build] ERRO: PyInstaller falhou. Veja o log acima para detalhes.
    exit /b 1
)

echo.
echo [build] Executavel gerado com sucesso em: dist\ContractParser.exe
echo [build] Lembrete: o Tesseract-OCR NAO e embutido no exe. Instale-o
echo [build] separadamente na maquina de destino e configure TESSERACT_CMD.
exit /b 0
