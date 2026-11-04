"""Contract flora-mcp-3.5: one test for each edge the blind evaluation proved, over the real MCP client."""

import asyncio
import json
import tomllib
from pathlib import Path

import pytest
from mcp.client.client import Client

from conftest import ingest, raw_doc
from flora_mcp import __version__, api
from flora_mcp.model import FloraError, canonical
from flora_mcp.precedents import import_package, migrate, normalized_number
from flora_mcp.publication import publish
from flora_mcp.server import create_server
from flora_mcp.store import connection
from test_contrato import stdio
from test_precedents import packet

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


# numero


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1076", "1076"),
        ("1.076", "1076"),
        (" 1.076 ", "1076"),
        ("Tema 1.076", "1076"),
        ("Tema 1076/STJ", "1076"),
        ("Súmula n. 7 do STJ", "7"),
        ("007", "7"),
        ("1.234.567", "1234567"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_number_is_normalized_to_the_stored_form(value, expected):
    assert normalized_number(value) == expected


@pytest.mark.parametrize("value", ["abc", "Tema", "0", "1.07", "1,076", "5/2020", "Temas 1 e 2", "12345678"])
def test_number_that_is_not_one_number_is_refused(value):
    with pytest.raises(FloraError) as info:
        normalized_number(value)
    assert info.value.code == "filtro_invalido"


@pytest.fixture
def tema(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path, number="1076", species="tema_repetitivo"), apply=True)
    return store


@pytest.mark.parametrize("numero", ["1076", "1.076", "Tema 1.076"])
def test_written_number_finds_the_theme_through_the_tool(tema, numero):
    result = call(tema, "pesquisar_precedentes", {"numero": numero})
    assert not result.is_error
    assert [r["id"] for r in result.structured_content["resultados"]] == ["STJ:tema_repetitivo:1076"]


def test_cursor_is_the_same_query_for_every_way_of_writing_the_number(store, tmp_path):
    migrate(store)
    for number in ("1076", "1077"):
        import_package(store, packet(tmp_path, number=number, species="tema_repetitivo"), apply=True)
    plain = api.search_precedents(store, numero="1076")
    dotted = api.search_precedents(store, numero="1.076")
    assert plain["resultados"] == dotted["resultados"]
    refused = call(store, "pesquisar_precedentes", {"numero": "tema mil e setenta e seis"})
    assert_error(refused, "filtro_invalido")


# Default component


def test_precedent_read_without_component_answers_with_its_default_and_names_it(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    import_package(store, packet(tmp_path, number="1076", species="tema_repetitivo"), apply=True)
    sumula = call(store, "obter_documento", {"id": "STJ:sumula:999999"})
    assert not sumula.is_error
    assert sumula.structured_content["componente"] == "enunciado"
    tema_lido = call(store, "obter_documento", {"id": "STJ:tema_repetitivo:1076"})
    assert not tema_lido.is_error
    assert tema_lido.structured_content["componente"] == "tese_firmada"


def test_default_component_of_a_precedent_prefers_what_it_says(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path, number="1076", species="tema_repetitivo"), apply=True)
    with connection(store.path, write=True) as db, db:
        row = db.execute("SELECT body FROM precedents WHERE id='STJ:tema_repetitivo:1076'").fetchone()
        body = json.loads(row["body"])
        body["componentes"] = {"questao_submetida": "Questão.", "tese_firmada": "Tese."}
        db.execute("UPDATE precedents SET body=? WHERE id='STJ:tema_repetitivo:1076'", (canonical(body),))
    assert api.document(store, "STJ:tema_repetitivo:1076")["componente"] == "tese_firmada"
    assert api.document(store, "STJ:tema_repetitivo:1076", "questao_submetida")["texto"] == "Questão."


def test_ementa_of_a_precedent_is_its_default_not_a_failure(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    result = call(store, "obter_documento", {"id": "STJ:sumula:999999", "componente": "ementa"})
    assert not result.is_error
    assert result.structured_content["componente"] == "enunciado"


def test_block_cursor_continues_a_precedent_read_with_the_default(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    first = api.document(store, "STJ:sumula:999999", tamanho_bloco=100)
    second = api.document(store, "STJ:sumula:999999", None, first["proximo_cursor"], 100)
    assert second["offset"] == 100 and second["componente"] == "enunciado"
    explicit = api.document(store, "STJ:sumula:999999", "enunciado", first["proximo_cursor"], 100)
    assert explicit["texto"] == second["texto"]


def test_precedent_keeps_refusing_a_component_it_does_not_have(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    result = call(store, "obter_documento", {"id": "STJ:sumula:999999", "componente": "tese_firmada"})
    assert_error(result, "componente_indisponivel")
    assert "enunciado" in result.structured_content["mensagem"]


def test_judgment_default_stays_the_ementa(store):
    ingest(store, [raw_doc(text="Alimentos.")])
    result = call(store, "obter_documento", {"id": "STJ:1"})
    assert result.structured_content["componente"] == "ementa"
    assert result.structured_content["texto"] == "Alimentos."


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
