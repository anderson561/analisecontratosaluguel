"""Testes unitarios do verificador de ambiente.

Todas as dependencias externas (banco SQLite, binario Tesseract, PATH) sao
injetadas/mockadas. Nenhum teste instala software nem exige servico externo —
o SQLite e embarcado, entao a checagem de banco so precisa de um caminho de
arquivo gravavel (``tmp_path``), sem nenhum servico de pe (ADR-002).
"""
from __future__ import annotations

from types import SimpleNamespace

from contract_parser.infrastructure import environment_check as ec
from contract_parser.infrastructure.database import RepositoryError
from contract_parser.infrastructure.environment_check import CheckResult


# --- Python ------------------------------------------------------------------
def test_check_python_pass_na_versao_minima():
    assert ec.check_python((3, 11)).ok is True


def test_check_python_pass_em_versao_superior():
    assert ec.check_python((3, 13)).ok is True


def test_check_python_fail_abaixo_do_minimo():
    r = ec.check_python((3, 10))
    assert r.ok is False
    assert "3.11" in r.remediacao


# --- Banco de dados (SQLite) --------------------------------------------------
def test_check_banco_dados_pass_com_arquivo_real(tmp_path):
    caminho = str(tmp_path / "envcheck.db")
    r = ec.check_banco_dados(database_path=caminho)
    assert r.ok is True
    assert caminho in r.detalhe


def test_check_banco_dados_usa_settings_quando_sem_argumento(monkeypatch, tmp_path):
    caminho = str(tmp_path / "settings.db")
    # ``settings`` e um dataclass frozen: substitui o objeto inteiro no modulo
    # (nao um atributo) para simular um DATABASE_PATH diferente.
    monkeypatch.setattr(ec, "settings", SimpleNamespace(database_path=caminho))
    r = ec.check_banco_dados()
    assert r.ok is True
    assert caminho in r.detalhe


def test_check_banco_dados_fail_quando_schema_falha_traz_remediacao():
    def abrir_fn_explode(_path: str) -> None:
        raise RepositoryError("falha ao inicializar o schema")

    r = ec.check_banco_dados(database_path="qualquer.db", abrir_fn=abrir_fn_explode)
    assert r.ok is False
    assert "permissao de escrita" in r.remediacao


def test_check_banco_dados_fail_quando_arquivo_nao_pode_ser_criado():
    def abrir_fn_sem_permissao(_path: str) -> None:
        raise OSError("Permission denied")

    r = ec.check_banco_dados(database_path="qualquer.db", abrir_fn=abrir_fn_sem_permissao)
    assert r.ok is False
    assert "DATABASE_PATH" in r.remediacao


# --- Tesseract ---------------------------------------------------------------
def _runner_com_langs(*langs: str):
    saida = "List of available languages:\n" + "\n".join(langs) + "\n"
    return lambda *a, **k: SimpleNamespace(stdout=saida, stderr="", returncode=0)


def test_check_tesseract_pass_via_path_com_idioma_por():
    r = ec.check_tesseract(
        cmd="",
        lang="por",
        which=lambda _: "/usr/bin/tesseract",
        runner=_runner_com_langs("eng", "por", "osd"),
    )
    assert r.ok is True
    assert "por" in r.detalhe


def test_check_tesseract_pass_via_cmd_existente(tmp_path):
    fake_bin = tmp_path / "tesseract.exe"
    fake_bin.write_text("stub")
    r = ec.check_tesseract(
        cmd=str(fake_bin),
        lang="por",
        which=lambda _: None,  # nao deve cair no PATH
        runner=_runner_com_langs("por"),
    )
    assert r.ok is True
    assert str(fake_bin) in r.detalhe


def test_check_tesseract_fail_binario_ausente():
    r = ec.check_tesseract(cmd="", lang="por", which=lambda _: None)
    assert r.ok is False
    assert "PATH" in r.remediacao


def test_check_tesseract_fail_idioma_ausente():
    r = ec.check_tesseract(
        cmd="",
        lang="por",
        which=lambda _: "/usr/bin/tesseract",
        runner=_runner_com_langs("eng", "osd"),
    )
    assert r.ok is False
    assert "tesseract-ocr-por" in r.remediacao


def test_check_tesseract_fail_quando_runner_lanca():
    def runner_explode(*a, **k):
        raise OSError("binario corrompido")

    r = ec.check_tesseract(
        cmd="",
        lang="por",
        which=lambda _: "/usr/bin/tesseract",
        runner=runner_explode,
    )
    assert r.ok is False
    assert "listar idiomas" in r.detalhe


# --- Relatorio e entrypoint --------------------------------------------------
def test_format_report_marca_pass_e_fail_e_acao():
    results = [
        CheckResult("Python", True, "ok"),
        CheckResult("Banco de dados", False, "caiu", "corrija a permissao"),
    ]
    texto = ec.format_report(results)
    assert "[PASS] Python" in texto
    assert "[FAIL] Banco de dados" in texto
    assert "-> Acao: corrija a permissao" in texto
    assert "1/2 checagens OK" in texto


def test_main_retorna_0_quando_tudo_ok(monkeypatch, capsys):
    monkeypatch.setattr(ec, "run_all_checks", lambda: [CheckResult("X", True, "ok")])
    assert ec.main() == 0
    assert "PASS" in capsys.readouterr().out


def test_main_retorna_1_quando_ha_falha(monkeypatch, capsys):
    monkeypatch.setattr(
        ec,
        "run_all_checks",
        lambda: [CheckResult("X", True, "ok"), CheckResult("Y", False, "ruim", "conserte")],
    )
    assert ec.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_run_all_checks_retorna_tres_checagens(monkeypatch):
    monkeypatch.setattr(ec, "check_banco_dados", lambda: CheckResult("Banco de dados", True, "ok"))
    monkeypatch.setattr(ec, "check_tesseract", lambda: CheckResult("Tesseract", True, "ok"))
    results = ec.run_all_checks()
    assert [r.nome for r in results] == ["Python", "Banco de dados", "Tesseract"]
