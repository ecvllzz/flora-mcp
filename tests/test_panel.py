import hashlib

import pytest
from starlette.testclient import TestClient

from conftest import ingest, raw_doc
from flora_mcp.panel import create_panel_app
from flora_mcp.query import search


def client(store):
    return TestClient(create_panel_app(store), base_url="http://127.0.0.1:8766")


def test_panel_returns_literal_text_and_reference_without_changing_database(store):
    literal = "EMENTA. <script>alert('x')</script>\n  Texto original."
    ingest(store, [raw_doc(text=literal, ministroRelator="MINISTRA EXEMPLO")])
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    with client(store) as browser:
        response = browser.post("/api/search", json={})
        assert response.status_code == 200
        assert response.json() == search(store, limite=5)
        row = response.json()["resultados"][0]
        assert row["ementa"] == literal
        assert row["relator"] == "MINISTRA EXEMPLO"
        assert "MINISTRA EXEMPLO" in row["referencia"]
        assert browser.get("/api/status").json()["documentos"] == 1
        assert browser.get("/api/catalog").json()["cobertura_integral"] is False
        assert browser.get("/").status_code == 200
        assert "script-src 'self'" in browser.get("/").headers["content-security-policy"]
        assert browser.get("/panel.js").status_code == 200
        assert browser.get("/panel.css").status_code == 200
        assert browser.get("/acervo.sqlite").status_code == 404
        assert browser.post("/api/status").status_code == 405
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before


def test_relator_filter_uses_current_version_and_literal_accent_insensitive_name(store):
    ingest(store, [raw_doc("1", ministroRelator="MINISTRA ANTIGA")])
    ingest(
        store,
        [raw_doc("1", ministroRelator="MINISTRA LÚCIA"), raw_doc("2", ministroRelator="MINISTRA MÁRCIA")],
        modified="2026-09-09",
    )
    with client(store) as browser:
        assert browser.post("/api/search", json={"relator": "lucia"}).json()["total_encontrado"] == 1
        assert browser.post("/api/search", json={"relator": "antiga"}).json()["total_encontrado"] == 0
        assert browser.post("/api/search", json={"relator": "%"}).json()["total_encontrado"] == 0
        assert (
            browser.post("/api/search", json={"relator": "lucia", "tribunal": "TJSC"}).json()[
                "total_encontrado"
            ]
            == 0
        )


def test_live_changes_and_cursor_consistency(store):
    ingest(store, [raw_doc(str(i), ministroRelator="MINISTRA EXEMPLO") for i in range(7)])
    with client(store) as browser:
        first = browser.post("/api/search", json={"relator": "exemplo"}).json()
        cursor = first["proximo_cursor"]
        second = browser.post("/api/search", json={"relator": "exemplo", "cursor": cursor}).json()
        ids = [r["id"] for r in first["resultados"] + second["resultados"]]
        assert len(set(ids)) == len(ids) == 7
        assert browser.post("/api/search", json={"relator": "outra", "cursor": cursor}).status_code == 400
        ingest(store, [raw_doc("8")], resource_id="r2")
        assert browser.get("/api/status").json()["documentos"] == 8
        assert (
            browser.post("/api/search", json={"relator": "exemplo", "cursor": cursor}).json()["codigo"]
            == "base_alterada"
        )
        assert browser.post("/api/search", json={}).json()["total_encontrado"] == 8


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example:8766"},
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_other_sites_cannot_query_local_acervo(store, headers):
    with client(store) as browser:
        assert browser.post("/api/search", json={}, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "value", [[], {"limite": "100"}, {"termos": ["a"]}, {"termos": "a" * 8200}, {"data_inicio": "ontem"}]
)
def test_invalid_queries(store, value):
    with client(store) as browser:
        assert browser.post("/api/search", json=value).status_code in {400, 413}
