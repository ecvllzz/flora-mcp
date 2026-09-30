import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import ingest, raw_doc


def test_real_stdio_protocol_lists_and_calls_all_readonly_tools(store):
    original = "Alimentos e proteção.\n" * 500 + "TERMINAÇÃO ORIGINAL"
    ingest(store, [raw_doc(text=original)])

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "flora_mcp.cli", "--data-dir", str(store.directory), "serve"],
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert {t.name for t in tools} == {
                    "pesquisar_jurisprudencia",
                    "pesquisar_precedentes",
                    "obter_documento",
                    "consultar_cobertura",
                }
                assert all(t.annotations.read_only_hint for t in tools)
                result = await session.call_tool(
                    "pesquisar_jurisprudencia", {"termos": "alimentos", "detalhe": "completo"}
                )
                assert not result.is_error
                assert result.structured_content["resultados"][0]["ementa"] == original
                doc = await session.call_tool("obter_documento", {"id": "STJ:1"})
                assert doc.structured_content["texto"] == original
                coverage = await session.call_tool("consultar_cobertura", {})
                assert coverage.structured_content["cobertura_integral"] is False
                error = await session.call_tool("obter_documento", {"id": "missing"})
                assert error.is_error
                assert error.structured_content["codigo"] == "documento_nao_encontrado"

    asyncio.run(exercise())
