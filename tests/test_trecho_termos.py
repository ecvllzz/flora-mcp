"""Triage window with several terms (FTS5 snippet) and the list of query terms present in the ementa."""

from conftest import ingest, raw_doc
from flora_mcp import api, query
from flora_mcp.model import canonical
from flora_mcp.text import plain, present_terms, query_terms, snippet_window

TEXT = (
    "DIREITO CIVIL. FAMÍLIA. ALIMENTOS. PRISÃO CIVIL.\nI. CASO EM EXAME\n1. Habeas corpus contra prisão "
    "civil por dívida de alimentos com pagamento parcial.\nII. QUESTÃO EM DISCUSSÃO\n2. Saber se o "
    "pagamento parcial afasta a prisão.\nIII. RAZÕES DE DECIDIR\n3. A guarda compartilhada e a convivência "
    "não entram aqui; só o débito alimentar e a prisão civil do devedor."
)


def test_window_is_the_literal_run_with_most_distinct_terms(store):
    ingest(store, [raw_doc("1", text=TEXT)])
    item = api.search(store, "prisão guarda convivência pagamento")["resultados"][0]
    window = item["trecho_correspondente"]
    assert TEXT[window["offset"] : window["offset"] + len(window["texto"])] == window["texto"]
    assert window["parcial"] is True
    # The run from "pagamento parcial" to "convivência" carries the four terms; the first occurrence
    # of "prisão", in the cabecalho, carried one.
    shown = plain(window["texto"])
    assert all(plain(t) in shown for t in ("pagamento", "prisão", "guarda", "convivência"))
    assert window["offset"] == TEXT.index("pagamento parcial afasta")
    assert item["termos_presentes"] == ["prisão", "guarda", "convivência", "pagamento"]


def test_present_terms_follow_the_effective_query_and_its_order(store):
    ingest(store, [raw_doc("1", text=TEXT), raw_doc("2", text="Guarda unilateral. Nada de pensão.")])
    page = api.search(store, "o juiz pode fixar a guarda e a pensão?")
    assert page["consulta_efetiva"] == '"juiz" OR "fixar" OR "guarda" OR "pensão?"'
    by_id = {r["id"]: r for r in page["resultados"]}
    assert by_id["STJ:2"]["termos_presentes"] == ["guarda", "pensão?"]
    assert by_id["STJ:1"]["termos_presentes"] == ["guarda"]
    # Phrases and prefixes: the term is listed as the query shows it.
    advanced = api.search(store, '"guarda compartilhada" OU alimen* OU pensão', modo_busca="avancado")
    found = {r["id"]: r["termos_presentes"] for r in advanced["resultados"]}
    assert found["STJ:1"] == ["guarda compartilhada", "alimen*"]
    assert found["STJ:2"] == ["pensão"]
    # By date, every term is present (AND), and the broadened query lists the terms kept.
    dated = api.search(store, "guarda pensão", ordenar="mais_recentes")
    assert dated["resultados"][0]["termos_presentes"] == ["guarda", "pensão"]


def test_single_term_and_no_terms(store):
    ingest(store, [raw_doc("1", text=TEXT)])
    one = api.search(store, "alimentos")["resultados"][0]
    assert one["termos_presentes"] == ["alimentos"] and "alimentos" in one["trecho_correspondente"]["texto"]
    none = api.search(store)["resultados"][0]
    assert "trecho_correspondente" not in none and "termos_presentes" not in none


def test_helpers():
    assert query_terms('"guarda" OR "pensão?"') == [("guarda", False), ("pensão?", False)]
    assert query_terms('"guarda compartilhada" AND "alimen"* OR ("x" OR "x")') == [
        ("guarda compartilhada", False),
        ("alimen", True),
        ("x", False),
    ]
    assert plain("Pensão? alimentícia,") == "PENSAO ALIMENTICIA"
    marked = "A \x01GUARDA\x02, \x01compartilhada\x02 e \x01ALIMENTOS\x02."
    assert present_terms([("guarda", False), ("aliment", True), ("pensão", False)], marked) == [
        "guarda",
        "aliment*",
    ]
    assert present_terms([("guarda compartilhada", False)], "x \x01guarda, compartilhada\x02") == [
        "guarda compartilhada"
    ]
    assert snippet_window("abc def", "") == {"texto": "abc def", "offset": 0, "parcial": False}
    assert snippet_window("um dois três", "\x01dois\x02 três") == {
        "texto": "dois três",
        "offset": 3,
        "parcial": True,
    }


def test_page_budget_still_holds_with_the_window_and_the_term_list(store):
    long_reference = {"ministroRelator": "MINISTRA " + "NOME " * 60}
    ingest(
        store,
        [
            raw_doc(str(i), text="Alimentos guarda pensão convivência. " + "Texto " * 400, **long_reference)
            for i in range(12)
        ],
    )
    seen, cursor = [], None
    while True:
        page = api.search(store, "alimentos guarda pensão convivência", cursor=cursor)
        assert len(canonical(page).encode()) <= 8192
        seen += [r["id"] for r in page["resultados"]]
        cursor = page["proximo_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 12
    assert query.SNIPPET_TOKENS == 16
