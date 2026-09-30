import asyncio
import json
import os
import subprocess
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import ingest, raw_doc
from flora_mcp.model import FloraError
from flora_mcp.query import search


@pytest.fixture
def ranked_store(store):
    focused = "Guarda compartilhada e alimentos."
    ingest(
        store,
        [
            raw_doc("1", text=focused, dataPublicacao="DJEN DATA:01/08/2026"),
            raw_doc("2", text=focused, dataPublicacao="DJEN DATA:01/08/2026"),
            raw_doc(
                "3",
                text=focused + " Assuntos gerais e diversos." * 150,
                dataPublicacao="DJEN DATA:01/09/2026",
            ),
            raw_doc("4", text=focused, nomeOrgaoJulgador="QUARTA TURMA"),
            raw_doc("5", text="Matéria sem correspondência textual."),
        ],
    )
    return store


def test_relevance_promotes_focused_older_documents_without_changing_date_default(ranked_store):
    options = {"termos": '"guarda compartilhada" alimentos', "orgao": "terceira turma"}
    chronological = search(ranked_store, **options)
    ranked = search(ranked_store, **options, ordenar="relevancia")
    assert chronological["resultados"][0]["id"] == "STJ:3"
    assert [r["id"] for r in ranked["resultados"]] == ["STJ:1", "STJ:2", "STJ:3"]
    assert ranked["total_encontrado"] == chronological["total_encontrado"] == 3
    assert ranked["ementas_completas"] is True
    assert ranked["resultados"][2]["ementa"] == chronological["resultados"][0]["ementa"]
    assert ranked["ordenacao"] == "relevancia"


def test_relevance_pagination_covers_filtered_results_once_and_rejects_changed_query(ranked_store):
    options = dict(termos="guarda alimentos", ordenar="relevancia", orgao="TERCEIRA TURMA", limite=1)
    first = search(ranked_store, **options)
    results = [first["resultados"][0]["id"]]
    cursor = first["proximo_cursor"]
    while cursor:
        page = search(ranked_store, **options, cursor=cursor)
        results.extend(row["id"] for row in page["resultados"])
        cursor = page["proximo_cursor"]
    assert results == ["STJ:1", "STJ:2", "STJ:3"]
    with pytest.raises(FloraError, match="outra consulta"):
        search(ranked_store, **{**options, "ordenar": "mais_recentes"}, cursor=first["proximo_cursor"])
    ingest(ranked_store, [raw_doc("6", text="Guarda e alimentos.")])
    with pytest.raises(FloraError, match="base mudou"):
        search(ranked_store, **options, cursor=first["proximo_cursor"])


def test_relevance_keeps_date_tribunal_and_process_filters_and_explicit_empty_result(ranked_store):
    options = dict(termos="alimentos", ordenar="relevancia")
    page = search(ranked_store, **options, orgao="terceira turma", data_inicio="2026-09-01")
    assert [r["id"] for r in page["resultados"]] == ["STJ:3"]
    assert search(ranked_store, **options, tribunal="TJSC")["total_encontrado"] == 0
    assert search(ranked_store, **options, processo="9999999")["total_encontrado"] == 0
    empty = search(ranked_store, termos="zzinexistente", ordenar="relevancia")
    assert empty["resultados"] == [] and empty["proximo_cursor"] is None
    assert empty["cobertura"]["integral"] is False
    with pytest.raises(FloraError, match="exige termos"):
        search(ranked_store, ordenar="relevancia")


def test_relevance_is_available_through_cli(ranked_store):
    call = subprocess.run(
        [
            sys.executable,
            "-m",
            "flora_mcp.cli",
            "--data-dir",
            str(ranked_store.directory),
            "search",
            "guarda alimentos",
            "--orgao",
            "terceira turma",
            "--ordenar",
            "relevancia",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(call.stdout)
    assert result["ordenacao"] == "relevancia"
    assert result["resultados"][0]["id"] == "STJ:1"


def test_relevance_is_available_through_real_mcp_protocol(ranked_store):
    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "flora_mcp.cli", "--data-dir", str(ranked_store.directory), "serve"],
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "pesquisar_jurisprudencia",
                    {
                        "termos": '"guarda compartilhada" alimentos',
                        "ordenar": "relevancia",
                        "orgao": "terceira turma",
                        "limite": 1,
                    },
                )
                assert not result.is_error
                data = result.structured_content
                assert data["ordenacao"] == "relevancia"
                assert data["resultados"][0]["id"] == "STJ:1"
                assert data["proximo_cursor"] is not None

    asyncio.run(exercise())
