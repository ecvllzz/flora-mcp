import gzip
import hashlib
import json
import runpy
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1] / "deploy" / "render"
prepare = runpy.run_path(str(ROOT / "prepare_data.py"))["prepare"]
build_app = runpy.run_path(str(ROOT / "serve.py"))["build_app"]


def test_snapshot_rebuilt_and_hash_required(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    payload = b"snapshot fixture" * 100
    archive = gzip.compress(payload)
    manifest = {
        "atual": "r1",
        "publicacoes": [
            {
                "id": "r1",
                "arquivo": "publicacoes/r1.sqlite",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    (source / "publicacoes.json").write_text(json.dumps(manifest))
    (source / "publicacao.sqlite.gz.part000").write_bytes(archive[:10])
    (source / "publicacao.sqlite.gz.part001").write_bytes(archive[10:])
    prepare(source, tmp_path / "restored")
    assert (tmp_path / "restored/publicacoes/r1.sqlite").read_bytes() == payload
    manifest["publicacoes"][0]["sha256"] = "0" * 64
    (source / "publicacoes.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="SHA-256"):
        prepare(source, tmp_path / "invalid")
    assert not (tmp_path / "invalid/publicacoes.json").exists()


def test_render_health_does_not_bypass_mcp_auth(store, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "testserver")
    monkeypatch.setenv("FLORA_MCP_DATA_DIR", str(store.directory))
    monkeypatch.setenv("FLORA_MCP_API_KEY", "a" * 40)
    with TestClient(build_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.post("/mcp", json={}).status_code == 401
        result = client.post(
            "/mcp",
            headers={"x-flora-api-key": "a" * 40, "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert result.status_code == 200
        assert {t["name"] for t in result.json()["result"]["tools"]} == {
            "pesquisar_jurisprudencia",
            "pesquisar_precedentes",
            "obter_documento",
            "consultar_cobertura",
        }
