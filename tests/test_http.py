import pytest
from starlette.testclient import TestClient

from conftest import ingest, raw_doc
from flora_mcp.http_server import create_http_app


KEY = "fixture-only-not-a-production-key-12345"
HEADERS = {"x-flora-api-key": KEY, "Accept": "application/json, text/event-stream"}


def rpc(client, method, params=None, id=1):
    return client.post(
        "/mcp",
        headers=HEADERS,
        json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}},
    )


def test_http_auth_host_and_readonly_protocol(store):
    original = "Alimentos. Ementa completa de teste."
    ingest(store, [raw_doc(text=original)])
    app = create_http_app(store, api_key=KEY, allowed_hosts=["testserver"])
    with TestClient(app) as client:
        assert client.get("/mcp").status_code == 401
        assert client.post("/mcp", headers={"x-flora-api-key": "wrong"}).status_code == 401
        assert client.get("/acervo.sqlite", headers=HEADERS).status_code == 404
        assert (
            client.post(
                "/mcp",
                headers={**HEADERS, "host": "untrusted.example"},
                json={},
            ).status_code
            == 421
        )
        assert (
            client.post(
                "/mcp",
                headers={**HEADERS, "Origin": "https://untrusted.example"},
                json={},
            ).status_code
            == 403
        )
        initialized = rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "fixture", "version": "1"},
            },
        )
        assert initialized.status_code == 200
        assert initialized.json()["result"]["serverInfo"]["name"] == "Flora-MCP"
        listed = rpc(client, "tools/list").json()["result"]["tools"]
        assert {t["name"] for t in listed} == {
            "pesquisar_jurisprudencia",
            "obter_documento",
            "consultar_cobertura",
        }
        assert all(t["annotations"]["readOnlyHint"] for t in listed)
        found = rpc(
            client,
            "tools/call",
            {
                "name": "pesquisar_jurisprudencia",
                "arguments": {"termos": "alimentos"},
            },
        ).json()["result"]["structuredContent"]
        assert found["resultados"][0]["ementa"] == original
        retrieved = rpc(
            client,
            "tools/call",
            {
                "name": "obter_documento",
                "arguments": {"id": "STJ:1"},
            },
        ).json()["result"]["structuredContent"]
        assert retrieved["texto"] == original
        coverage = rpc(
            client,
            "tools/call",
            {
                "name": "consultar_cobertura",
                "arguments": {},
            },
        ).json()["result"]["structuredContent"]
        assert coverage["cobertura_integral"] is False


@pytest.mark.parametrize("key", ["", "short", "x" * 32 + " ", "á" * 32])
def test_reject_invalid_credentials(store, key):
    with pytest.raises(ValueError):
        create_http_app(store, api_key=key, allowed_hosts=["testserver"])


@pytest.mark.parametrize("hosts", [[], ["*"], ["https://example.com/mcp"]])
def test_require_explicit_hosts(store, hosts):
    with pytest.raises(ValueError):
        create_http_app(store, api_key=KEY, allowed_hosts=hosts)
