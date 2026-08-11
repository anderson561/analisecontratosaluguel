"""Testes do log de auditoria leve (infrastructure/audit_log.py).

Suporte ao plano de diagnostico de painel vazio intermitente
(`.agent/specs/plano-log-auditoria-carregamento-historico.md`): registra
eventos de baixo volume (contagem carregada do historico, erros) para
capturar evidencia real na proxima ocorrencia, sem NUNCA derrubar a UI por
falha de IO (mesmo principio de `database.py::check_health`).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from contract_parser.infrastructure import audit_log
from contract_parser.infrastructure.audit_log import registrar_evento


def test_registrar_evento_grava_linha_legivel_no_arquivo(tmp_path):
    destino = tmp_path / "app.log"

    registrar_evento("3 contrato(s) carregado(s) do histórico", log_path=str(destino))

    conteudo = destino.read_text(encoding="utf-8")
    assert "3 contrato(s) carregado(s) do histórico" in conteudo
    # timestamp ISO reconhecivel (comeca com o ano) na mesma linha da mensagem
    linha = conteudo.strip().splitlines()[-1]
    assert linha[:4].isdigit()


def test_registrar_evento_acrescenta_sem_sobrescrever(tmp_path):
    destino = tmp_path / "app.log"

    registrar_evento("primeiro evento", log_path=str(destino))
    registrar_evento("segundo evento", log_path=str(destino))

    linhas = destino.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2
    assert "primeiro evento" in linhas[0]
    assert "segundo evento" in linhas[1]


def test_registrar_evento_cria_diretorio_pai_se_ausente(tmp_path):
    destino = tmp_path / "subdir" / "app.log"
    assert not destino.parent.exists()

    registrar_evento("evento qualquer", log_path=str(destino))

    assert destino.exists()


def test_registrar_evento_usa_settings_log_path_quando_nao_informado(tmp_path):
    destino = tmp_path / "settings.log"
    with patch.object(audit_log, "settings") as fake_settings:
        fake_settings.log_path = str(destino)
        registrar_evento("evento via settings")

    assert destino.exists()
    assert "evento via settings" in destino.read_text(encoding="utf-8")


def test_registrar_evento_nunca_lanca_quando_diretorio_pai_nao_pode_ser_criado(tmp_path):
    # Um arquivo comum no lugar de um componente de diretorio faz o
    # mkdir(parents=True) falhar com OSError (NotADirectoryError/FileExistsError
    # dependendo da plataforma) — exatamente o cenario de "caminho nao gravavel".
    arquivo_no_lugar_de_pasta = tmp_path / "isto_e_um_arquivo"
    arquivo_no_lugar_de_pasta.write_text("nao sou uma pasta")
    caminho_invalido = arquivo_no_lugar_de_pasta / "subpasta" / "app.log"

    registrar_evento("nao deveria lancar", log_path=str(caminho_invalido))  # não lança


def test_registrar_evento_nunca_lanca_com_caminho_vazio():
    registrar_evento("mensagem qualquer", log_path="")  # não lança


def test_registrar_evento_nunca_lanca_quando_open_falha(tmp_path):
    destino = tmp_path / "app.log"
    with patch.object(Path, "open", side_effect=OSError("disco cheio")):
        registrar_evento("mensagem qualquer", log_path=str(destino))  # não lança
