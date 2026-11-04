"""A third party serves a publication from the single file a Release carries (M4, RM-D32)."""

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_contrato import published  # noqa: F401  (fixture: acervo com publicação)
from flora_mcp import api
from flora_mcp.http_server import readable
from flora_mcp.leitor import instalar
from flora_mcp.model import FloraError
from flora_mcp.publication import MANIFEST, file_digest
from flora_mcp.store import Store

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "instalar_publicacao.py"


def release_file(published, tmp_path):  # noqa: F811
    """What a Release holds: only the current generation, gzip-compressed."""
    manifest = json.loads((published.directory / MANIFEST).read_text(encoding="utf-8"))
    current = next(x for x in manifest["publicacoes"] if x["id"] == manifest["atual"])
    source = published.directory / current["arquivo"]
    archive = tmp_path / "publicacao.sqlite.gz"
    with source.open("rb") as stream, gzip.open(archive, "wb") as output:
        output.write(stream.read())
    return archive, current, manifest


def test_release_file_alone_serves_search_reading_and_coverage(published, tmp_path):  # noqa: F811
    archive, current, origin = release_file(published, tmp_path)
    destino = tmp_path / "leitor"
    recibo = instalar(archive, destino, sha256=current["sha256"])
    assert recibo["sha256"] == current["sha256"] and recibo["revisao_base"] == current["revisao"]
    manifest = json.loads((destino / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["atual"] == recibo["publicacao_id"] and manifest["retirados"] == origin["retirados"]
    assert manifest["admissao_atual"] == origin["admissao_atual"]
    assert sorted(p.name for p in destino.iterdir()) == ["publicacoes", MANIFEST]
    leitor = Store(destino)
    assert readable(leitor) and not leitor.path.exists()
    busca = api.search(leitor, "alimentos")
    assert busca["total_encontrado"] == 1 and busca["publicacao_id"] == manifest["atual"]
    assert api.document(leitor, busca["resultados"][0]["id"])["referencia"]
    assert api.search_precedents(leitor, "sintético")["total_encontrado"] == 1
    assert api.coverage(leitor)["publicacao_id"] == manifest["atual"]
    # Installing the same file again is idempotent: one generation, same manifest.
    assert instalar(archive, destino)["publicacao_id"] == manifest["atual"]
    assert len(json.loads((destino / MANIFEST).read_text(encoding="utf-8"))["publicacoes"]) == 1


def test_wrong_hash_or_damaged_file_installs_nothing(published, tmp_path):  # noqa: F811
    archive, current, _ = release_file(published, tmp_path)
    destino = tmp_path / "leitor"
    with pytest.raises(FloraError) as info:
        instalar(archive, destino, sha256="0" * 64)
    assert info.value.code == "publicacao_invalida" and not (destino / MANIFEST).exists()
    damaged = tmp_path / "quebrado.sqlite"
    damaged.write_bytes(b"isto nao e um banco")
    with pytest.raises((FloraError, Exception)):
        instalar(damaged, destino)
    assert not (destino / MANIFEST).exists()
    assert file_digest(archive) != current["sha256"]  # the hash checked is the decompressed file's


def test_script_installs_and_the_cli_serves_without_work_database(published, tmp_path):  # noqa: F811
    archive, current, _ = release_file(published, tmp_path)
    destino = tmp_path / "leitor"
    env = {**os.environ, "PYTHONUTF8": "1"}
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--arquivo", str(archive), "--destino", str(destino)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["sha256"] == current["sha256"]
    coverage = subprocess.run(
        [sys.executable, "-m", "flora_mcp.cli", "--data-dir", str(destino), "coverage"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert coverage.returncode == 0, coverage.stderr
    assert json.loads(coverage.stdout)["publicacao_id"].startswith("r")
