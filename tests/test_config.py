"""Testes do calculo do caminho padrao do banco SQLite (config.py).

Cobre o bug de raiz: o caminho do banco nao pode depender do diretorio de
trabalho (CWD) do processo no momento em que ele inicia, e sim da localizacao
real do executavel (`.exe` empacotado) ou da raiz do repo (modo dev). Ver
`.agent/specs/plano-persistencia-caminho-banco.md`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from contract_parser import config
from contract_parser.config import Settings, _caminho_banco_padrao, _caminho_log_padrao

_RAIZ_REPO = Path(config.__file__).resolve().parent.parent.parent


def test_caminho_banco_padrao_modo_dev_aponta_para_raiz_do_repo(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)

    resultado = _caminho_banco_padrao()

    assert resultado == str(_RAIZ_REPO / "data" / "contract_parser.db")


def test_caminho_banco_padrao_modo_frozen_ancora_no_executavel_independente_do_cwd(
    monkeypatch, tmp_path
):
    exe_fake = r"C:\Alguma\Pasta\ContractParser.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe_fake)
    monkeypatch.chdir(tmp_path)

    resultado = _caminho_banco_padrao()

    esperado = str(Path(exe_fake).resolve().parent / "data" / "contract_parser.db")
    assert resultado == esperado


def test_caminho_banco_padrao_modo_frozen_nao_muda_com_cwd_diferente(
    monkeypatch, tmp_path
):
    exe_fake = r"C:\Outra\Pasta\ContractParser.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe_fake)

    monkeypatch.chdir(tmp_path)
    resultado_cwd_a = _caminho_banco_padrao()

    outro_cwd = tmp_path / "subpasta"
    outro_cwd.mkdir()
    monkeypatch.chdir(outro_cwd)
    resultado_cwd_b = _caminho_banco_padrao()

    assert resultado_cwd_a == resultado_cwd_b


def test_settings_database_path_usa_variavel_ambiente_quando_definida_modo_dev(
    monkeypatch,
):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("DATABASE_PATH", "/caminho/explicito/banco.db")

    settings = Settings()

    assert settings.database_path == "/caminho/explicito/banco.db"


def test_settings_database_path_usa_variavel_ambiente_quando_definida_modo_frozen(
    monkeypatch,
):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Qualquer\App.exe")
    monkeypatch.setenv("DATABASE_PATH", "/caminho/explicito/banco.db")

    settings = Settings()

    assert settings.database_path == "/caminho/explicito/banco.db"


def test_settings_database_path_usa_padrao_calculado_quando_env_ausente(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)

    settings = Settings()

    assert settings.database_path == str(_RAIZ_REPO / "data" / "contract_parser.db")


# --------------------------------------------------------------------------- #
# log_path (log de auditoria — mesmo padrao de ancoragem de database_path)
# --------------------------------------------------------------------------- #
def test_caminho_log_padrao_modo_dev_aponta_para_raiz_do_repo(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)

    resultado = _caminho_log_padrao()

    assert resultado == str(_RAIZ_REPO / "data" / "app.log")


def test_caminho_log_padrao_modo_frozen_ancora_no_executavel_independente_do_cwd(
    monkeypatch, tmp_path
):
    exe_fake = r"C:\Alguma\Pasta\ContractParser.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe_fake)
    monkeypatch.chdir(tmp_path)

    resultado = _caminho_log_padrao()

    esperado = str(Path(exe_fake).resolve().parent / "data" / "app.log")
    assert resultado == esperado


def test_settings_log_path_usa_variavel_ambiente_quando_definida(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LOG_PATH", "/caminho/explicito/auditoria.log")

    settings = Settings()

    assert settings.log_path == "/caminho/explicito/auditoria.log"


def test_settings_log_path_usa_padrao_calculado_quando_env_ausente(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("LOG_PATH", raising=False)

    settings = Settings()

    assert settings.log_path == str(_RAIZ_REPO / "data" / "app.log")
