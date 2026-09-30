import json

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.query import search
from flora_mcp.sources import sync_stj, validate_tjsc_page

from conftest import raw_doc


def test_catalog_discovery_resume_and_failed_resource_is_not_complete(store):
    config = Config(store.directory, datasets=["fixture"], max_resources=1, request_delay=0)
    resources = [
        {
            "id": str(i),
            "name": f"20260{i}31.json",
            "url": f"https://dadosabertos.web.stj.jus.br/{i}",
            "last_modified": "2026-09-08",
        }
        for i in (7, 8)
    ]
    fail = True

    def route(req):
        if req.url.path.endswith("package_show"):
            return httpx.Response(200, json={"success": True, "result": {"resources": resources}})
        if req.url.path == "/8" and fail:
            return httpx.Response(200, text="<html>WAF</html>")
        return httpx.Response(200, content=json.dumps([raw_doc(req.url.path)]).encode())

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        assert sync_stj(config, store, http)["status"] == "error"
        assert search(store)["total_encontrado"] == 0
        fail = False
        assert sync_stj(config, store, http)["status"] == "partial"
        assert sync_stj(config, store, http)["status"] == "ok"
        assert search(store)["total_encontrado"] == 2
        assert sync_stj(config, store, http)["eventos"] == []


def test_tjsc_waf_http200_is_not_empty_search():
    with pytest.raises(FloraError, match="verificação"):
        validate_tjsc_page(b"<html>Please enable JavaScript. Your support ID is 1</html>", 9)


def test_tjsc_latin1_and_organ_filter():
    html = """<meta charset="iso-8859-1"><input id="hdnTotalResultado" value="1">
    <div class="resultadoItem" id="resultado123">
    <span class="resLabel">ÓRGÃO JULGADOR</span><span class="resValue">9ª Câmara de Direito Civil</span>
    <span class="resLabel">EMENTA</span><span class="resValue">Proteção à criança.</span></div>"""
    assert validate_tjsc_page(html.encode("latin1"), 9)["documentos_na_pagina"] == 1
    with pytest.raises(FloraError, match="outro órgão"):
        validate_tjsc_page(html.encode("latin1"), 10)
