"""Testes unitarios do verificador de ambiente.

Todas as dependencias externas (Mongo, binario Tesseract, PATH) sao injetadas/mockadas.
Nenhum teste instala software nem exige servico real.
"""
from __future__ import annotations

from types import SimpleNamespace

from contract_parser.infrastructure import environment_check as ec
from contract_parser.infrastructure.database import HealthResult
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


# --- MongoDB -----------------------------------------------------------------
def test_check_mongo_pass_quando_health_ok():
    r = ec.check_mongo(health_fn=lambda: HealthResult(ok=True, detalhe="pong"))
    assert r.ok is True
    assert r.detalhe == "pong"


def test_check_mongo_fail_quando_health_falha_traz_remediacao():
    r = ec.check_mongo(health_fn=lambda: HealthResult(ok=False, detalhe="sem servidor"))
    assert r.ok is False
    assert "MongoDB Community" in r.remediacao


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
        CheckResult("MongoDB", False, "caiu", "suba o servico"),
    ]
    texto = ec.format_report(results)
    assert "[PASS] Python" in texto
    assert "[FAIL] MongoDB" in texto
    assert "-> Acao: suba o servico" in texto
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
    monkeypatch.setattr(ec, "check_mongo", lambda: CheckResult("MongoDB", True, "ok"))
    monkeypatch.setattr(ec, "check_tesseract", lambda: CheckResult("Tesseract", True, "ok"))
    results = ec.run_all_checks()
    assert [r.nome for r in results] == ["Python", "MongoDB", "Tesseract"]
