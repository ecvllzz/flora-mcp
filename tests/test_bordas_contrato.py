"""Contract flora-mcp-3.5: one test for each edge the blind evaluation proved, over the real MCP client."""

import asyncio
import json
import tomllib
from pathlib import Path

from mcp.client.client import Client

from conftest import ingest, raw_doc
from flora_mcp import __version__
from flora_mcp.publication import publish
from flora_mcp.server import create_server
from test_contrato import stdio

ROOT = Path(__file__).resolve().parents[1]


def tools():
    return {t.name: t for t in asyncio.run(create_server(None).list_tools())}


def call(store, tool, arguments):
    """One call through the real protocol, in process, so that the SDK's error handling runs."""

    async def run():
        async with Client(create_server(store)) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def assert_error(result, code):
    assert result.is_error
    assert result.structured_content["status"] == "erro"
    assert result.structured_content["codigo"] == code
    assert result.structured_content["mensagem"]
    assert json.loads(result.content[0].text) == result.structured_content


def option(schema, key):
    """A key of the non-null arm of an optional parameter, or of the parameter itself."""
    return next(o[key] for o in schema.get("anyOf", [schema]) if key in o)


# Version


def test_handshake_announces_the_version_of_the_package(store):
    ingest(store, [raw_doc()])
    publish(store)

    async def exercise(session):
        return (await session.initialize()).server_info

    info = stdio(store, exercise)
    assert info.version == __version__ and info.name == "Flora-MCP"
    assert create_server(None).version == __version__


def test_package_version_is_the_same_in_pyproject_and_in_the_code():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert next(p["version"] for p in lock["package"] if p["name"] == "flora-mcp") == __version__
