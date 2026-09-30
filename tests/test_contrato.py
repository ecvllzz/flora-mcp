"""Contract flora-mcp-3: the examples of CONTRATO.md and each rule, over the real MCP client."""

import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import ingest, raw_doc
from test_precedents import packet
from flora_mcp import api
from flora_mcp.model import FloraError, canonical
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import publish
from flora_mcp.server import create_server

CONTRATO = Path(__file__).resolve().parents[1] / "CONTRATO.md"
TEXT = (
    "DIREITO CIVIL. FAMÍLIA. ALIMENTOS. PRISÃO CIVIL.\nI. CASO EM EXAME\n1. Habeas corpus contra prisão "
    "civil por dívida de alimentos com pagamento parcial.\nII. QUESTÃO EM DISCUSSÃO\n2. Saber se o "
    "pagamento parcial afasta a prisão."
)


def examples():
    text = CONTRATO.read_text(encoding="utf-8")
    pattern = r"<!-- exemplo: (\S+) -->\n```json\n(.*?)\n```"
    return {m.group(1): json.loads(m.group(2)) for m in re.finditer(pattern, text, re.S)}


def assert_same_shape(example, actual, path="$"):
    """Same keys at every level; lists compared by their first element; scalar values are free."""
    if isinstance(example, dict):
        assert isinstance(actual, dict), path
        assert set(example) == set(actual), (path, set(example) ^ set(actual))
        for key in example:
            assert_same_shape(example[key], actual[key], path + "." + key)
    elif isinstance(example, list):
        assert isinstance(actual, list), path
        if example and actual:
            assert_same_shape(example[0], actual[0], path + "[0]")


@pytest.fixture
def published(store, tmp_path):
    ingest(store, [raw_doc("1", text=TEXT, ministroRelator="MINISTRA EXEMPLO"), raw_doc("2", text="Guarda.")])
    run = store.start_run("STJ")
    store.finish_run(run, "ok", {"eventos": [{"texto": "detalhe fora do resumo"}]})
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    publish(store)
    return store


def stdio(store, exercise):
    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "flora_mcp.cli", "--data-dir", str(store.directory), "serve"],
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await exercise(session)

    return asyncio.run(run())


def test_every_example_in_contrato_md_has_the_shape_of_a_real_response(published):
    async def exercise(session):
        async def ok(tool, arguments):
            result = await session.call_tool(tool, arguments)
            assert not result.is_error, result.content
            return result.structured_content

        answers = {
            "pesquisar_jurisprudencia.triagem": await ok(
                "pesquisar_jurisprudencia", {"termos": "pagamento parcial"}
            ),
            "pesquisar_jurisprudencia.sem_correspondencia": await ok(
                "pesquisar_jurisprudencia", {"termos": "pagou pensão"}
            ),
            "pesquisar_jurisprudencia.fora_da_cobertura": await ok(
                "pesquisar_jurisprudencia",
                {"termos": "alimentos", "data_inicio": "2001-01-01", "data_fim": "2001-12-31"},
            ),
            "pesquisar_jurisprudencia.filtro_restritivo": await ok(
                "pesquisar_jurisprudencia", {"termos": "alimentos", "tribunal": "TJSC"}
            ),
            "pesquisar_precedentes.triagem": await ok("pesquisar_precedentes", {"termos": "sintético"}),
            "pesquisar_precedentes.vazio": await ok("pesquisar_precedentes", {"termos": "tema"}),
            "consultar_cobertura.resumo": await ok("consultar_cobertura", {}),
        }
        first = await ok("obter_documento", {"id": "STJ:1", "tamanho_bloco": 100})
        answers["obter_documento.primeiro_bloco"] = first
        answers["obter_documento.bloco_seguinte"] = await ok(
            "obter_documento", {"id": "STJ:1", "tamanho_bloco": 100, "cursor": first["proximo_cursor"]}
        )
        error = await session.call_tool("obter_documento", {"id": "inexistente"})
        assert error.is_error
        assert json.loads(error.content[0].text) == error.structured_content
        answers["erro"] = error.structured_content
        return answers

    answers = stdio(published, exercise)
    documented = examples()
    assert set(documented) == set(answers)
    for name, example in documented.items():
        assert_same_shape(example, answers[name], name)
    for name, answer in answers.items():
        if name != "erro":
            assert answer["status"] == "ok" and answer["contrato"] == "flora-mcp-3", name
            assert answer["publicacao_id"], name
    assert answers["erro"]["codigo"] == "documento_nao_encontrado"
    assert answers["pesquisar_jurisprudencia.sem_correspondencia"]["termos_sem_ocorrencia"] == [
        "pagou",
        "pensão",
    ]
    assert answers["pesquisar_jurisprudencia.filtro_restritivo"]["total_sem_filtros"] == 1


def test_closed_vocabularies_are_enums_and_defaults_are_the_contract():
    tools = {t.name: t.input_schema["properties"] for t in asyncio.run(create_server(None).list_tools())}
    assert set(tools) == {
        "pesquisar_jurisprudencia",
        "pesquisar_precedentes",
        "obter_documento",
        "consultar_cobertura",
    }

    def enum(schema):
        options = schema.get("anyOf", [schema])
        return next(o["enum"] for o in options if "enum" in o)

    judgments, precedents = tools["pesquisar_jurisprudencia"], tools["pesquisar_precedentes"]
    assert not {"colecao", "especie", "numero", "campo"} & set(judgments)
    assert enum(judgments["tribunal"]) == ["STJ", "TJSC"]
    assert enum(judgments["tipo_data"]) == ["publicacao", "julgamento"]
    assert enum(judgments["modo_busca"]) == ["simples", "avancado"]
    for schema in (judgments, precedents):
        assert set(enum(schema["ordenar"])) == {"relevancia", "mais_recentes", "mais_antigos"}
        assert schema["ordenar"]["default"] is None
        assert enum(schema["detalhe"]) == ["triagem", "completo"]
        assert schema["detalhe"]["default"] == "triagem"
    assert enum(precedents["tribunal"]) == ["STJ", "STF", "TJSC"]
    assert set(enum(precedents["especie"])) == {
        "tema_repetitivo",
        "iac",
        "sumula",
        "tema_repercussao_geral",
        "sumula_vinculante",
    }
    assert precedents["campo"]["default"] == "todos" and "todos" in enum(precedents["campo"])
    assert enum(tools["consultar_cobertura"]["detalhe"]) == ["resumo", "completo", "recursos", "execucoes"]


def test_value_outside_the_schema_is_a_structured_tool_error(store):
    ingest(store, [raw_doc()])

    async def exercise(session):
        wrong = await session.call_tool("pesquisar_jurisprudencia", {"termos": "x", "ordenar": "relevance"})
        legacy = await session.call_tool("consultar_cobertura", {"detalhe": "legado"})
        refused = await session.call_tool("pesquisar_jurisprudencia", {"data_inicio": "ontem"})
        return wrong, legacy, refused

    for result, code in zip(
        stdio(store, exercise), ["parametro_invalido"] * 2 + ["data_invalida"], strict=True
    ):
        assert result.is_error
        assert result.structured_content["status"] == "erro"
        assert result.structured_content["codigo"] == code
        assert json.loads(result.content[0].text) == result.structured_content


def test_triage_item_has_header_and_matched_window_with_unicode_offsets(store):
    prefix = "Ação é órfã. " * 20
    ingest(store, [raw_doc("1", text=prefix + "\n1. COMPENSATÓRIOS devidos. " + "Fim. " * 100)])
    item = api.search(store, "compensatorios")["resultados"][0]
    full = api.search(store, "compensatorios", detalhe="completo")["resultados"][0]["ementa"]
    window = item["trecho_correspondente"]
    assert window["offset"] == full.index("COMPENSATÓRIOS") - 60
    assert full[window["offset"] : window["offset"] + len(window["texto"])] == window["texto"]
    assert len(window["texto"]) == 240 and window["parcial"] is True
    assert item["cabecalho"] == prefix.strip() and item["cabecalho_parcial"] is False
    assert not {"trecho", "offset", "trecho_parcial", "campos_correspondentes", "ementa"} & set(item)
    assert "trecho_correspondente" not in api.search(store)["resultados"][0]


@pytest.mark.parametrize(
    "text,expected,partial",
    [
        ("VERBETE. TEMA.\nI. CASO EM EXAME\nFatos.", "VERBETE. TEMA.", False),
        ("VERBETE sem título.\n\nCorpo da ementa.", "VERBETE sem título.", False),
        (
            "VERBETE LONGO DO STJ, QUE\n CONTINUA NA LINHA.\n 1. Corpo.",
            "VERBETE LONGO DO STJ, QUE\n CONTINUA NA LINHA.",
            False,
        ),
        ("VERBETE.\nI - Corpo em inciso.", "VERBETE.", False),
        ("I. CASO EM EXAME\nFatos.\nMais.", "I. CASO EM EXAME", False),
        ("X" * 500, "X" * 300, True),
    ],
)
def test_header_stops_at_first_heading_or_line_break_and_at_300_characters(store, text, expected, partial):
    ingest(store, [raw_doc(text=text)])
    item = api.search(store)["resultados"][0]
    assert (item["cabecalho"], item["cabecalho_parcial"]) == (expected, partial)


def test_empty_page_reasons_follow_the_contract_order(store):
    ingest(store, [raw_doc("1", text="Alimentos gravídicos."), raw_doc("2", text="Guarda.")])
    outside = api.search(store, "alimentos", data_inicio="2020-01-01", data_fim="2020-12-31")
    assert outside["motivo"] == "fora_da_cobertura"
    assert outside["intervalos_carregados"][0]["inicio"] == "2026-09-01"
    # The interval compared is the one of the requested kind of date.
    by_judgment = api.search(store, "alimentos", data_inicio="2026-08-25", tipo_data="julgamento")
    assert by_judgment["motivo"] == "fora_da_cobertura"  # judged 2026-08-24
    assert (
        api.search(store, "alimentos", data_inicio="2026-08-25")["total_encontrado"] == 1
    )  # published 09-01
    inside = api.search(store, "guarda alimentos", data_inicio="2026-08-25")
    # Filtered, but the same terms find nothing without filters either.
    assert inside["motivo"] == "sem_correspondencia" and "total_sem_filtros" not in inside
    process = api.search(store, "alimentos", processo="999")
    assert (process["motivo"], process["total_sem_filtros"]) == ("filtro_restritivo", 1)
    none = api.search(store, "alimentos inexistente", orgao="terceira turma")
    assert none["motivo"] == "sem_correspondencia"
    assert none["termos"] == [
        {"termo": "alimentos", "documentos": 1},
        {"termo": "inexistente", "documentos": 0},
    ]
    assert none["termos_sem_ocorrencia"] == ["inexistente"]
    advanced = api.search(store, "zz OR yy", modo_busca="avancado")
    assert advanced["motivo"] == "sem_correspondencia" and "termos" not in advanced
    assert "motivo" not in api.search(store, "alimentos")


def test_empty_precedent_page_keeps_absence_and_gets_a_reason(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    stf = api.search_precedents(store, "sintético", tribunal="STF")
    assert (stf["motivo"], stf["total_sem_filtros"]) == ("filtro_restritivo", 1)
    assert stf["ausencia"]
    old = api.search_precedents(store, data_fim="2000-01-01")
    assert old["motivo"] == "fora_da_cobertura"
    field = api.search_precedents(store, "sintético", campo="tese_firmada")
    assert field["termos"] == [{"termo": "sintético", "documentos": 0}]


def test_automatic_order_and_coverage_block(store):
    ingest(store, [raw_doc("1", text="Alimentos."), raw_doc("2", text="Alimentos e guarda.")])
    run = store.start_run("STJ")
    store.finish_run(run, "ok", {})
    assert api.search(store, "alimentos")["ordenacao"] == "relevancia"
    assert api.search(store)["ordenacao"] == "mais_recentes"
    assert api.search(store, "alimentos", ordenar="mais_antigos")["ordenacao"] == "mais_antigos"
    assert api.search_precedents(store)["ordenacao"] == "mais_recentes"
    block = api.search(store, "alimentos")["cobertura"]
    assert set(block) == {"integral", "fontes_em_atraso", "aviso"}
    assert block["integral"] is False and block["fontes_em_atraso"] == ["TJSC"]


def test_single_cursor_encoding_pins_publication_and_rejects_other_contracts(published):
    page = api.search(published, limite=1)
    decoded = json.loads(base64.urlsafe_b64decode(page["proximo_cursor"]))
    assert decoded["contrato"] == "flora-mcp-3"
    assert decoded["publicacao"] == page["publicacao_id"]
    assert "continua" not in decoded  # no cursor inside a cursor
    legacy = base64.urlsafe_b64encode(
        canonical({"publicacao": page["publicacao_id"], "continua": "x"}).encode()
    ).decode()
    for cursor in (
        legacy,
        base64.urlsafe_b64encode(canonical({**decoded, "contrato": "flora-mcp-2"}).encode()),
    ):
        with pytest.raises(FloraError) as info:
            api.search(published, limite=1, cursor=cursor if isinstance(cursor, str) else cursor.decode())
        assert info.value.code == "cursor_invalido"
    with pytest.raises(FloraError) as info:
        api.search(published, limite=1, cursor=page["proximo_cursor"], publicacao_id="outra")
    assert info.value.code == "cursor_invalido"
    second = api.search(published, limite=1, cursor=page["proximo_cursor"])
    assert second["resultados"][0]["id"] != page["resultados"][0]["id"]


def test_precedent_metadata_only_in_the_first_block(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    first = api.document(store, "STJ:sumula:999999", "enunciado", tamanho_bloco=100)
    assert {"metadados", "evidencia_componente", "evidencia_situacao", "julgados_relacionados"} <= set(first)
    second = api.document(store, "STJ:sumula:999999", "enunciado", first["proximo_cursor"], 100)
    assert not {"metadados", "evidencia_componente", "julgados_relacionados"} & set(second)
    assert second["referencia"] == first["metadados"]["referencia"]


def test_triage_budget_trims_items_and_cursor_continues_after_the_last_one(store):
    long_reference = {"ministroRelator": "MINISTRA " + "NOME " * 60}
    ingest(store, [raw_doc(str(i), text="Alimentos. " + "Texto " * 400, **long_reference) for i in range(12)])
    seen, cursor = [], None
    while True:
        page = api.search(store, "alimentos", cursor=cursor)
        assert len(canonical(page).encode()) <= 8192
        seen += [r["id"] for r in page["resultados"]]
        cursor = page["proximo_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 12
