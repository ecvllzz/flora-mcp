import asyncio
import json
import os
import sys
from datetime import date

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from starlette.testclient import TestClient

from conftest import ingest, raw_doc
from flora_mcp.http_server import create_http_app
from flora_mcp.query import document, search
from flora_mcp.store import connection
from flora_mcp.tjsc import parse_page
from test_tjsc import page


def stj_doc(**changes):
    return raw_doc(
        ministroRelator="MINISTRA EXEMPLO",
        descricaoClasse="AGRAVO INTERNO NO RECURSO ESPECIAL",
        siglaClasse="AgInt no REsp",
        **changes,
    )


def test_existing_original_is_used_without_changing_bank_or_text(store):
    original = stj_doc()
    ingest(store, [original])
    with connection(store.path) as db:
        before = tuple(db.execute("SELECT body,hash FROM documents").fetchone())
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
    assert "relator" not in json.loads(before[0])
    found = search(store, "alimentos", detalhe="completo")["resultados"][0]
    assert found["relator"] == "MINISTRA EXEMPLO"
    assert found["referencia"] == (
        "(STJ, AGRAVO INTERNO NO RECURSO ESPECIAL n. 1234567, rel. MINISTRA EXEMPLO, "
        "TERCEIRA TURMA, j. 24/08/2026, publ. 01/09/2026)"
    )
    assert found["referencia_completa"] is True
    assert found["referencia_pendencias"] == []
    assert found["ementa"] == original["ementa"]
    assert json.loads(document(store, "STJ:1", "espelho_original")["texto"]) == original
    with connection(store.path) as db:
        assert tuple(db.execute("SELECT body,hash FROM documents").fetchone()) == before
        assert db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0] == revision


@pytest.mark.parametrize("label", ["RELATOR", "RELATORA"])
def test_tjsc_original_labels_and_class_description_are_available(store, label):
    content = page([1], total=1).replace(
        b"</div>",
        f'<span class="resLabel">{label}</span><span class="resValue">PESSOA EXEMPLO</span></div>'.encode(),
    )
    _, rows = parse_page(content, 9, date(2026, 9, 18))
    resource = {"id": "tjsc", "name": "20260918.json", "url": "https://example.test/fixture"}
    store.catalog("fixture", {}, [resource])
    store.ingest(store.resources("fixture")[0], content, rows, "test")
    found = search(store, tribunal="TJSC")["resultados"][0]
    assert found["relator"] == "PESSOA EXEMPLO"
    assert found["classe_descricao"] == "Agravo de Instrumento"
    assert "Agravo de Instrumento n. 5000001-00.2026.8.24.0000" in found["referencia"]
    assert "j. 10/09/2026, publ. 18/09/2026" in found["referencia"]
    assert "D.E." not in found["referencia"]
    assert document(store, found["id"])["metadados"]["referencia"] == found["referencia"]


def test_missing_relator_and_ambiguous_date_are_explicit_never_inferred(store):
    ingest(
        store,
        [
            raw_doc(
                text="Alimentos. Relator citado na ementa: NÃO USAR ESTE NOME.",
                dataPublicacao="DJE 01/09/2026; republicado 02/09/2026",
            )
        ],
    )
    found = search(store)["resultados"][0]
    assert found["relator"] is None
    assert found["referencia_completa"] is False
    assert set(found["referencia_pendencias"]) == {"relator", "data_publicacao"}
    assert "rel. [não informado na fonte]" in found["referencia"]
    assert "NÃO USAR" not in found["referencia"]
    assert "publicação na fonte: DJE 01/09/2026; republicado 02/09/2026" in found["referencia"]


def test_reference_tracks_exact_version_and_does_not_merge_same_process(store):
    first = stj_doc()
    second = {**first, "id": "2", "ministroRelator": "OUTRA PESSOA", "dataDecisao": "20250824"}
    ingest(store, [first, second])
    found = search(store, processo="1234567")["resultados"]
    assert {d["relator"] for d in found} == {"MINISTRA EXEMPLO", "OUTRA PESSOA"}
    changed = {**first, "ministroRelator": "RELATORIA CORRIGIDA"}
    ingest(store, [changed, second], modified="2026-09-10")
    ingest(store, [first], name="20250731.json", resource_id="older")
    assert document(store, "STJ:1")["metadados"]["relator"] == "RELATORIA CORRIGIDA"
    assert {d["id"]: d["relator"] for d in search(store)["resultados"]}["STJ:1"] == "RELATORIA CORRIGIDA"


def test_every_text_block_has_reference_without_inserting_it_into_ementa(store):
    text = "Texto integral preservado.\n" * 30
    ingest(store, [stj_doc(text=text)])
    cursor = None
    blocks = []
    reference = search(store)["resultados"][0]["referencia"]
    while True:
        result = document(store, "STJ:1", tamanho_bloco=100, cursor=cursor)
        assert result["referencia"] == reference
        # Complete metadata only in the first block.
        assert ("metadados" in result) == (cursor is None)
        blocks.append(result["texto"])
        cursor = result["proximo_cursor"]
        if cursor is None:
            break
    assert "".join(blocks) == text


def test_stdio_exposes_reference_and_agent_instructions(store):
    ingest(store, [stj_doc()])

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "flora_mcp.cli", "--data-dir", str(store.directory), "serve"],
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert "referencia_pendencias" in initialized.instructions
                tools = {t.name: t for t in (await session.list_tools()).tools}
                assert "referência" in tools["pesquisar_jurisprudencia"].description
                assert "referencia_pendencias" in tools["obter_documento"].description
                result = await session.call_tool("pesquisar_jurisprudencia", {"termos": "alimentos"})
                found = result.structured_content["resultados"][0]
                assert found["relator"] == "MINISTRA EXEMPLO"
                doc = await session.call_tool("obter_documento", {"id": found["id"]})
                assert doc.structured_content["metadados"]["referencia"] == found["referencia"]

    asyncio.run(exercise())


def test_http_exposes_same_reference_without_changing_transport(store):
    from test_http import KEY, rpc

    ingest(store, [stj_doc()])
    app = create_http_app(store, api_key=KEY, allowed_hosts=["testserver"])
    with TestClient(app) as client:
        found = rpc(
            client,
            "tools/call",
            {
                "name": "pesquisar_jurisprudencia",
                "arguments": {"termos": "alimentos"},
            },
        ).json()["result"]["structuredContent"]["resultados"][0]
        assert found["referencia_completa"] is True
        retrieved = rpc(
            client,
            "tools/call",
            {
                "name": "obter_documento",
                "arguments": {"id": found["id"]},
            },
        ).json()["result"]["structuredContent"]
        assert retrieved["metadados"]["referencia"] == found["referencia"]
