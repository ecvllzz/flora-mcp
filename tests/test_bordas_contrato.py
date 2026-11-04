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
from flora_mcp.precedents import COMPONENTS, import_package, migrate, normalized_number
from flora_mcp.publication import publish
from flora_mcp.server import create_server
from flora_mcp.store import connection
from flora_mcp.text import NAMES, advanced_query
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


# Descriptions, limits and vocabularies in the schema


def test_every_parameter_of_every_tool_has_a_description():
    missing = [
        f"{tool.name}.{name}"
        for tool in tools().values()
        for name, schema in tool.input_schema["properties"].items()
        if not schema.get("description")
    ]
    assert not missing


def test_closed_values_and_limits_of_optional_parameters_are_also_in_the_text():
    """Some clients do not show the model what is inside the anyOf of an optional parameter."""
    for tool in tools().values():
        for name, schema in tool.input_schema["properties"].items():
            arms = [a for a in schema.get("anyOf", []) if a.get("type") != "null"]
            values = [v for a in arms for v in a.get("enum", []) if not v.startswith("secao:")]
            limits = [a[k] for a in arms for k in ("minimum", "maximum", "maxLength") if k in a]
            for value in [*values, *limits]:
                assert str(value) in schema["description"], (tool.name, name, value)


def test_refusal_says_what_the_parameter_accepts(store):
    ingest(store, [raw_doc()])
    above = call(store, "pesquisar_jurisprudencia", {"limite": 9}).structured_content["mensagem"]
    assert "limite (máximo 8)" in above
    wrong = call(store, "pesquisar_jurisprudencia", {"tribunal": "TJRS"}).structured_content["mensagem"]
    assert "tribunal (aceita 'STJ' ou 'TJSC')" in wrong
    long = call(store, "pesquisar_jurisprudencia", {"relator": "a" * 151}).structured_content["mensagem"]
    assert "relator (até 150 caracteres)" in long


def test_limits_and_date_format_are_in_the_schema():
    schemas = {name: tool.input_schema["properties"] for name, tool in tools().items()}
    for tool in ("pesquisar_jurisprudencia", "pesquisar_precedentes"):
        limite = schemas[tool]["limite"]
        assert (option(limite, "minimum"), option(limite, "maximum")) == (1, 8)
        assert option(schemas[tool]["termos"], "maxLength") == 500
        for name in ("data_inicio", "data_fim"):
            assert schemas[tool][name]["format"] == "date"
    assert option(schemas["pesquisar_jurisprudencia"]["relator"], "maxLength") == 150
    assert (schemas["obter_documento"]["tamanho_bloco"]["minimum"]) == 100
    assert (schemas["obter_documento"]["tamanho_bloco"]["maximum"]) == 32000
    assert (schemas["consultar_cobertura"]["limite"]["minimum"]) == 1
    assert (schemas["consultar_cobertura"]["limite"]["maximum"]) == 50


def test_component_vocabulary_is_closed_and_follows_the_code():
    schema = tools()["obter_documento"].input_schema["properties"]["componente"]
    sections = {"cabecalho", *NAMES.values()}
    assert set(option(schema, "enum")) == {
        "ementa",
        "espelho_original",
        "citacoes",
        *COMPONENTS,
        *{"secao:" + name for name in sections},
    }
    assert schema["default"] is None


@pytest.mark.parametrize(
    "tool,arguments,field",
    [
        ("pesquisar_jurisprudencia", {"limite": 9}, "limite"),
        ("pesquisar_jurisprudencia", {"limite": 0}, "limite"),
        ("pesquisar_jurisprudencia", {"termos": "a" * 501}, "termos"),
        ("pesquisar_jurisprudencia", {"relator": "a" * 151}, "relator"),
        ("pesquisar_precedentes", {"limite": 9}, "limite"),
        ("obter_documento", {"id": "STJ:1", "tamanho_bloco": 99}, "tamanho_bloco"),
        ("obter_documento", {"id": "STJ:1", "tamanho_bloco": 32001}, "tamanho_bloco"),
        ("obter_documento", {"id": "STJ:1", "componente": "secao:inexistente"}, "componente"),
        ("consultar_cobertura", {"limite": 51}, "limite"),
    ],
)
def test_value_beyond_a_schema_limit_is_refused_naming_the_parameter(store, tool, arguments, field):
    ingest(store, [raw_doc()])
    result = call(store, tool, arguments)
    assert_error(result, "parametro_invalido")
    assert field in result.structured_content["mensagem"]


def test_rules_the_schema_cannot_state_keep_their_codes(store):
    ingest(store, [raw_doc()])
    assert_error(call(store, "pesquisar_jurisprudencia", {"data_inicio": "2026-02-31"}), "data_invalida")
    too_many = call(store, "pesquisar_jurisprudencia", {"detalhe": "completo", "limite": 6})
    assert_error(too_many, "limite_invalido")


def test_limits_at_the_edge_of_the_schema_are_accepted(store):
    ingest(store, [raw_doc()])
    for tool, arguments in (
        ("pesquisar_jurisprudencia", {"limite": 8}),
        ("obter_documento", {"id": "STJ:1", "tamanho_bloco": 100}),
        ("obter_documento", {"id": "STJ:1", "tamanho_bloco": 32000}),
        ("consultar_cobertura", {"limite": 50, "detalhe": "recursos"}),
    ):
        assert not call(store, tool, arguments).is_error, (tool, arguments)


@pytest.mark.parametrize("numero", [1076, 1.076, 1076.0])
def test_number_sent_as_a_json_number_is_accepted(tema, numero):
    """The client that loses the type of an optional parameter sends it as a number."""
    result = call(tema, "pesquisar_precedentes", {"numero": numero})
    assert not result.is_error
    assert [r["id"] for r in result.structured_content["resultados"]] == ["STJ:tema_repetitivo:1076"]


@pytest.mark.parametrize("numero,code", [(1.1, "filtro_invalido"), (0, "filtro_invalido")])
def test_json_number_that_loses_its_digits_is_refused_not_guessed(tema, numero, code):
    """1.100 arrives as 1.1: the number that came is not the one written, and it does not pass."""
    assert_error(call(tema, "pesquisar_precedentes", {"numero": numero}), code)


@pytest.mark.parametrize("numero", [-5, True])
def test_value_that_is_no_number_of_a_precedent_is_out_of_the_schema(tema, numero):
    assert_error(call(tema, "pesquisar_precedentes", {"numero": numero}), "parametro_invalido")


def test_process_sent_as_a_json_number_is_accepted(store):
    ingest(store, [raw_doc(text="Alimentos.")])
    result = call(store, "pesquisar_jurisprudencia", {"processo": 1234567})
    assert result.structured_content["total_encontrado"] == 1


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


# E and OU in the advanced mode


@pytest.mark.parametrize(
    "value,expected",
    [
        ("guarda OU alimentos", '"guarda" OR "alimentos"'),
        ("guarda ou alimentos", '"guarda" OR "alimentos"'),
        ("guarda OR alimentos", '"guarda" OR "alimentos"'),
        ("guarda or alimentos", '"guarda" OR "alimentos"'),
        ("guarda E alimentos", '"guarda" AND "alimentos"'),
        ("guarda e alimentos", '"guarda" AND "alimentos"'),
        ("guarda AND alimentos", '"guarda" AND "alimentos"'),
        ('(dano OU guarda) E "pensão alimentícia"', '("dano" OR "guarda") AND "pensão alimentícia"'),
        ('guarda "ou" alimentos', '"guarda" AND "ou" AND "alimentos"'),
        ("guarda não alimentos", '"guarda" AND "não" AND "alimentos"'),
        ("ou* E guarda", '"ou"* AND "guarda"'),
    ],
)
def test_portuguese_operators_of_the_advanced_mode(value, expected):
    assert advanced_query(value) == expected


@pytest.mark.parametrize(
    "value",
    ["guarda NOT alimentos", "guarda not alimentos", "guarda NÃO alimentos", "guarda NAO alimentos"]
    + ["guarda NEAR alimentos", "guarda near alimentos", "NEAR/5 guarda", "E guarda", "guarda OU", "OU"],
)
def test_operator_the_grammar_does_not_offer_is_refused(store, value):
    ingest(store, [raw_doc()])
    assert_error(
        call(store, "pesquisar_jurisprudencia", {"termos": value, "modo_busca": "avancado"}),
        "consulta_invalida",
    )


def test_advanced_or_in_portuguese_finds_either_term_through_the_tool(store):
    ingest(
        store, [raw_doc("1", text="Guarda."), raw_doc("2", text="Alimentos."), raw_doc("3", text="Outro.")]
    )
    either = {"termos": "guarda OU alimentos", "modo_busca": "avancado"}
    result = call(store, "pesquisar_jurisprudencia", either)
    assert result.structured_content["total_encontrado"] == 2
    assert result.structured_content["consulta_efetiva"] == '"guarda" OR "alimentos"'
    both = call(store, "pesquisar_jurisprudencia", {"termos": "guarda E alimentos", "modo_busca": "avancado"})
    assert both.structured_content["total_encontrado"] == 0


def test_operators_also_hold_in_the_advanced_search_of_precedents(tema):
    found = api.search_precedents(tema, "sintético OU inexistente", modo_busca="avancado")
    assert found["consulta_efetiva"] == '"sintético" OR "inexistente"' and found["total_encontrado"] == 1


def test_simple_mode_keeps_operators_as_plain_words(store):
    ingest(store, [raw_doc("1", text="Guarda ou alimentos.")])
    assert '"ou"' not in api.search(store, "guarda ou alimentos")["consulta_efetiva"]  # a stopword
    assert " AND " in api.search(store, "guarda ou alimentos", ordenar="mais_recentes")["consulta_efetiva"]


# Unexpected error


def test_unexpected_error_is_typed_structured_and_hides_the_cause(store, caplog):
    ingest(store, [raw_doc()])
    with connection(store.path, write=True) as db, db:
        db.execute("DELETE FROM versions WHERE document_id='STJ:1'")  # TypeError when reading the raw
    result = call(store, "obter_documento", {"id": "STJ:1"})
    assert_error(result, "erro_interno")
    assert "obter_documento" in result.structured_content["mensagem"]
    assert "NoneType" not in result.content[0].text and "Traceback" not in result.content[0].text
    assert any(r.levelname == "ERROR" and r.exc_info for r in caplog.records)  # The cause is in the log.


@pytest.mark.parametrize(
    "tool,arguments,target",
    [
        ("pesquisar_jurisprudencia", {"termos": "x"}, "search"),
        ("pesquisar_precedentes", {"termos": "x"}, "search_precedents"),
        ("obter_documento", {"id": "STJ:1"}, "document"),
        ("consultar_cobertura", {}, "coverage"),
    ],
)
def test_every_tool_answers_an_unexpected_error_the_same_way(store, monkeypatch, tool, arguments, target):
    def fail(*_args, **_kwargs):
        raise RuntimeError("segredo interno")

    monkeypatch.setattr("flora_mcp.server." + target, fail)
    result = call(store, tool, arguments)
    assert_error(result, "erro_interno")
    assert "segredo" not in result.content[0].text


def test_expected_error_keeps_its_own_code(store):
    ingest(store, [raw_doc()])
    assert_error(call(store, "obter_documento", {"id": "inexistente"}), "documento_nao_encontrado")


# Triage item


def test_triage_item_brings_dates_and_class_as_fields(store):
    ingest(store, [raw_doc(text="Alimentos.")])
    item = call(store, "pesquisar_jurisprudencia", {"termos": "alimentos"}).structured_content["resultados"][
        0
    ]
    assert item["classe"] == "REsp"
    assert item["data_julgamento"] == "2026-08-24"
    assert item["data_publicacao"] == "2026-09-01"


def test_triage_item_with_a_date_the_source_does_not_give_says_it_is_null(store):
    ingest(store, [raw_doc(text="Alimentos.", dataPublicacao="DJEN sem data")])
    item = api.search(store, "alimentos")["resultados"][0]
    assert item["data_publicacao"] is None and item["data_julgamento"] == "2026-08-24"


def test_new_fields_count_in_the_triage_budget(store):
    ingest(store, [raw_doc(str(i), text="Alimentos. " + "Texto " * 400) for i in range(12)])
    seen, cursor = [], None
    while True:
        page = api.search(store, "alimentos", cursor=cursor)
        assert len(canonical(page).encode()) <= 8192
        seen += [r["id"] for r in page["resultados"]]
        cursor = page["proximo_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 12


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
