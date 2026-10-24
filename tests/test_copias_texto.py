"""Text copies: an ementa that repeats an earlier one leaves the generation, and the first names it."""

import pytest
from conftest import ingest, raw_doc

from flora_mcp import api
from flora_mcp.model import FloraError
from flora_mcp.publication import plan_text_copies, publish, text_key
from flora_mcp.store import connection


@pytest.fixture
def copies(store):
    ingest(
        store,
        [
            raw_doc("1", text="Guarda compartilhada. Recurso provido.", numeroProcesso="1111111"),
            raw_doc("2", text="GUARDA COMPARTILHADA - recurso provido", numeroProcesso="2222222"),
            raw_doc("3", text="Partilha de bens. Recurso desprovido.", numeroProcesso="3333333"),
            raw_doc("4", text="Guarda  compartilhada.\nRecurso provido.", numeroProcesso="4444444"),
        ],
    )
    return store


def test_text_key_ignores_case_accents_spaces_and_punctuation():
    assert text_key("Guarda compartilhada. Recurso provido.") == text_key(
        "GUARDA COMPARTILHADA - recurso provido"
    )
    assert text_key("Pensão") == text_key("pensao")
    assert text_key("Guarda.") != text_key("Guarda provida.")
    assert text_key(" .- ") is None and text_key("") is None


def test_first_id_stays_and_lists_its_copies():
    rows = [
        ("STJ:4", {"ementa": "A b.", "processo": "REsp 4"}),
        ("STJ:1", {"ementa": "a B", "processo": "REsp 1"}),
        ("STJ:3", {"ementa": "Outra."}),
        ("STJ:2", {"ementa": "...", "processo": "REsp 2"}),
    ]
    plan = plan_text_copies(rows)
    assert list(plan) == ["STJ:1"]
    assert [c["id"] for c in plan["STJ:1"]] == ["STJ:4"]
    assert plan["STJ:1"][0]["processo"] == "REsp 4"


def test_publication_leaves_copies_out_and_keeps_them_in_the_work_database(copies):
    result = publish(copies)
    assert result["copias_texto"] == {"grupos": 1, "copias_retiradas": 2}
    page = api.search(copies, "compartilhada")
    assert page["total_encontrado"] == 1 and page["resultados"][0]["id"] == "STJ:1"
    first = api.document(copies, "STJ:1")
    assert [(c["id"], c["processo"]) for c in first["metadados"]["copias_texto"]] == [
        ("STJ:2", "REsp 2222222"),
        ("STJ:4", "REsp 4444444"),
    ]
    assert "copias_texto" not in api.document(copies, "STJ:3")["metadados"]
    with pytest.raises(FloraError) as error:
        api.document(copies, "STJ:2")
    assert error.value.code == "documento_nao_encontrado"
    assert api.search(copies, processo="2222222")["total_encontrado"] == 0
    with connection(copies.path) as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM search").fetchone()[0] == 4


def test_generation_without_copies_is_unchanged_apart_from_the_deriver(store):
    ingest(store, [raw_doc("1", text="Alimentos."), raw_doc("2", text="Guarda.")])
    result = publish(store)
    assert result["copias_texto"] == {"grupos": 0, "copias_retiradas": 0}
    assert api.search(store, "", ordenar="mais_recentes")["total_encontrado"] == 2
