"""Simple mode: ranked by relevance, any term without stopwords; ordered by date, every term first and any
term only when every term finds nothing."""

import pytest

from conftest import ingest, raw_doc
from test_precedents import packet
from flora_mcp import api
from flora_mcp.model import FloraError
from flora_mcp.precedents import import_package, migrate
from flora_mcp.query import RANKED_STOPWORDS, broadening, content_terms

RECENT = {"ordenar": "mais_recentes"}


@pytest.fixture
def family(store):
    ingest(
        store,
        [
            raw_doc("1", text="Alimentos gravídicos."),
            raw_doc("2", text="Guarda unilateral.", nomeOrgaoJulgador="QUARTA TURMA"),
            raw_doc("3", text="Guarda compartilhada e alimentos."),
            raw_doc("4", text="Partilha de bens."),
        ],
    )
    return store


def test_ranked_query_is_any_term_and_ranks_more_terms_first(family):
    page = api.search(family, "guarda alimentos")
    assert page["consulta_efetiva"] == '"guarda" OR "alimentos"'
    assert page["total_encontrado"] == 3 and page["ordenacao"] == "relevancia"
    assert page["resultados"][0]["id"] == "STJ:3"  # both terms rank first
    assert page["termos_descartados"] == [] and "ampliacao" not in page


def test_ranked_query_drops_stopwords_negation_and_possessives(family):
    page = api.search(family, "o juiz não pode fixar sua guarda e alimentos?")
    assert page["consulta_efetiva"] == '"juiz" OR "fixar" OR "guarda" OR "alimentos?"'
    assert page["termos_descartados"] == ["o", "não", "pode", "sua", "e"]
    assert page["total_encontrado"] == 3 and page["resultados"][0]["id"] == "STJ:3"
    assert "ampliacao" not in page and "motivo" not in page
    assert page["resultados"][0]["trecho_correspondente"]["texto"]


def test_every_term_with_results_is_not_broadened_by_date(family):
    page = api.search(family, "guarda alimentos", **RECENT)
    assert page["total_encontrado"] == 1 and "ampliacao" not in page
    assert page["consulta_efetiva"] == '"guarda" AND "alimentos"' and "termos_descartados" not in page


def test_empty_conjunction_by_date_is_broadened_without_stopwords(family):
    page = api.search(family, "o juiz pode fixar guarda e alimentos?", ordenar="mais_antigos")
    assert page["consulta_efetiva"] == '"juiz" OR "fixar" OR "guarda" OR "alimentos?"'
    assert page["total_encontrado"] == 3 and page["ordenacao"] == "mais_antigos"
    assert page["ampliacao"] == {
        "de": "todos_os_termos",
        "para": "qualquer_termo",
        "motivo": "nenhum documento contém todos os termos",
        "termos": [
            {"termo": "juiz", "documentos": 0},
            {"termo": "fixar", "documentos": 0},
            {"termo": "guarda", "documentos": 2},
            {"termo": "alimentos?", "documentos": 2},
        ],
        "termos_descartados": ["o", "pode", "e"],
    }
    assert "motivo" not in page and "termos_descartados" not in page


def test_stopwords_compare_after_folding_case_and_accents_and_phrases_stay_whole():
    assert broadening('Até "de cujus" QUAL é herança') == (["de cujus", "herança"], ["Até", "QUAL", "é"])
    assert broadening('"de" alimentos') == (["de", "alimentos"], [])
    assert broadening("alimentos") is None
    assert broadening('"guarda compartilhada"') is None
    assert broadening("de que o") is None
    # The ranked query also drops the negation; the broadening keeps it.
    assert content_terms("não cabe guarda", RANKED_STOPWORDS) == (["guarda"], ["não", "cabe"])
    assert broadening("não cabe guarda") == (["não", "guarda"], ["cabe"])


def test_quoted_phrase_is_kept_whole(family):
    page = api.search(family, '"guarda compartilhada" de inexistente')
    assert page["consulta_efetiva"] == '"guarda compartilhada" OR "inexistente"'
    assert [r["id"] for r in page["resultados"]] == ["STJ:3"]
    assert page["termos_descartados"] == ["de"]
    dated = api.search(family, '"guarda compartilhada" de inexistente', **RECENT)
    assert dated["consulta_efetiva"] == '"guarda compartilhada" OR "inexistente"'
    assert dated["ampliacao"]["termos_descartados"] == ["de"]


def test_advanced_mode_single_term_and_only_stopwords_keep_the_query(family):
    advanced = api.search(family, "guarda AND inexistente", modo_busca="avancado")
    assert advanced["total_encontrado"] == 0 and "ampliacao" not in advanced
    assert "termos_descartados" not in advanced
    single = api.search(family, "inexistente")
    assert single["total_encontrado"] == 0 and "ampliacao" not in single
    assert single["consulta_efetiva"] == '"inexistente"' and "termos_descartados" not in single
    only_stopwords = api.search(family, "de que")
    assert only_stopwords["total_encontrado"] == 0 and "ampliacao" not in only_stopwords
    assert only_stopwords["consulta_efetiva"] == '"de" AND "que"'


def test_empty_answers_are_over_the_query_run(family):
    page = api.search(family, "zzz yyy de")
    assert page["consulta_efetiva"] == '"zzz" OR "yyy"' and "ampliacao" not in page
    assert page["motivo"] == "sem_correspondencia"
    assert page["termos_sem_ocorrencia"] == ["zzz", "yyy"]
    dated = api.search(family, "zzz yyy de", **RECENT)
    assert "ampliacao" not in dated and dated["consulta_efetiva"] == '"zzz" AND "yyy" AND "de"'
    assert dated["motivo"] == "sem_correspondencia"
    filtered = api.search(family, "alimentos inexistente", tribunal="TJSC", **RECENT)
    assert "ampliacao" not in filtered and filtered["motivo"] == "sem_correspondencia"
    assert filtered["termos"] == [
        {"termo": "alimentos", "documentos": 2},
        {"termo": "inexistente", "documentos": 0},
    ]
    ranked = api.search(family, "alimentos inexistente", tribunal="TJSC")
    assert (ranked["motivo"], ranked["total_sem_filtros"]) == ("filtro_restritivo", 2)


def test_any_term_keeps_the_filters(family):
    page = api.search(family, "guarda gravídicos", orgao="terceira turma")
    # STJ:2 has "guarda" but sits in the fourth panel.
    assert {r["id"] for r in page["resultados"]} == {"STJ:1", "STJ:3"}
    assert page["total_encontrado"] == 2 and "ampliacao" not in page
    older = api.search(family, "guarda gravídicos", orgao="terceira turma", ordenar="mais_antigos")
    assert older["ordenacao"] == "mais_antigos" and older["total_encontrado"] == 2 and older["ampliacao"]
    none = api.search(family, "guarda gravídicos", data_inicio="2027-01-01")
    assert none["total_encontrado"] == 0 and "ampliacao" not in none
    assert none["motivo"] == "fora_da_cobertura"


@pytest.mark.parametrize("ordem", [{}, RECENT])
def test_cursor_pages_the_query_run_once_and_only_it(store, ordem):
    ingest(
        store, [raw_doc(str(i), text=("Guarda. " if i % 2 else "Alimentos. ") * (i + 1)) for i in range(7)]
    )
    options = dict(termos="guarda de alimentos", limite=2, **ordem)
    first = api.search(store, **options)
    assert first["total_encontrado"] == 7 and ("ampliacao" in first) == bool(ordem)
    seen, cursor = [r["id"] for r in first["resultados"]], first["proximo_cursor"]
    while cursor:
        page = api.search(store, **options, cursor=cursor)
        assert page.get("ampliacao") == first.get("ampliacao")
        assert page["consulta_efetiva"] == first["consulta_efetiva"]
        seen += [r["id"] for r in page["resultados"]]
        cursor = page["proximo_cursor"]
    assert len(seen) == len(set(seen)) == 7
    with pytest.raises(FloraError, match="outra consulta"):
        api.search(store, termos="guarda", limite=2, cursor=first["proximo_cursor"])


@pytest.fixture
def precedents(store, tmp_path):
    migrate(store)
    for number in ("1", "2", "3"):
        import_package(store, packet(tmp_path, number=number), apply=True)
    return store


def test_precedents_broaden_only_an_empty_simple_conjunction(precedents):
    found = api.search_precedents(precedents, "sintético para")
    assert found["total_encontrado"] == 3 and "ampliacao" not in found
    page = api.search_precedents(precedents, "enunciado sintético inexistente", campo="enunciado")
    assert page["consulta_efetiva"] == 'enunciado : ("enunciado" OR "sintético" OR "inexistente")'
    assert page["total_encontrado"] == 3 and "ausencia" not in page and "motivo" not in page
    assert page["ampliacao"]["termos"] == [
        {"termo": "enunciado", "documentos": 3},
        {"termo": "sintético", "documentos": 3},
        {"termo": "inexistente", "documentos": 0},
    ]
    assert page["ampliacao"]["termos_descartados"] == []
    advanced = api.search_precedents(precedents, "sintético AND inexistente", modo_busca="avancado")
    assert advanced["total_encontrado"] == 0 and "ampliacao" not in advanced
    single = api.search_precedents(precedents, "inexistente")
    assert "ampliacao" not in single and single["ausencia"]


def test_precedents_keep_filters_reason_and_cursor_when_broadened(precedents):
    stf = api.search_precedents(precedents, "sintético inexistente", tribunal="STF")
    assert "ampliacao" not in stf and stf["motivo"] == "sem_correspondencia"
    assert stf["consulta_efetiva"] == '"sintético" AND "inexistente"'
    one = api.search_precedents(precedents, "sintético inexistente", numero="2")
    assert [r["id"] for r in one["resultados"]] == ["STJ:sumula:2"] and one["ampliacao"]
    options = dict(termos="o sintético inexistente", limite=1)
    first = api.search_precedents(precedents, **options)
    assert first["ampliacao"]["termos_descartados"] == ["o"]
    seen, cursor = [r["id"] for r in first["resultados"]], first["proximo_cursor"]
    while cursor:
        page = api.search_precedents(precedents, **options, cursor=cursor)
        assert page["ampliacao"] == first["ampliacao"]
        seen += [r["id"] for r in page["resultados"]]
        cursor = page["proximo_cursor"]
    assert sorted(seen) == ["STJ:sumula:1", "STJ:sumula:2", "STJ:sumula:3"]
