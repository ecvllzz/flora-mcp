"""The search reaches the document from the FTS rowid, not from the UNINDEXED id column.

Proof of order: the legacy plan (documents JOIN search ON search.id=d.id) and the current one
return the same ids in the same order, page after page, over a sample of queries, including the
ties that only the date and the id break, in the three states of the database: with the index
on search_map, without it (temporary copy) and without search_map at all (legacy join).
"""

import sqlite3

import pytest

from conftest import ingest, raw_doc
from flora_mcp import api, query
from flora_mcp.publication import publish
from flora_mcp.store import ROWID_INDEX, connection

VOCABULARY = ["guarda", "alimentos", "compartilhada", "convivência", "menor", "pensão"]
QUERIES = [
    {"termos": "guarda compartilhada alimentos"},
    {"termos": "guarda de alimentos", "ordenar": "mais_recentes"},
    {"termos": "guarda alimentos", "ordenar": "mais_antigos", "tipo_data": "julgamento"},
    {"termos": '"guarda compartilhada"'},
    {"termos": "pensão"},
    {"termos": "guarda OR pensão", "modo_busca": "avancado"},
    {"termos": "guarda convivência menor", "orgao": "quarta turma"},
    {"termos": "alimentos guarda", "data_inicio": "2026-08-10", "data_fim": "2026-08-20"},
    {"termos": "guarda compartilhada", "processo": "1234567"},
    {"termos": "", "orgao": "terceira turma"},
    {"termos": "alimentos", "limite": 3},
]


def documents():
    """40 acórdãos: repeated texts (BM25 ties) over several dates, some without a publication date."""
    docs = []
    for i in range(1, 41):
        words = [VOCABULARY[(i + k) % len(VOCABULARY)] for k in range(1 + i % 4)]
        text = "Verbete. " + " ".join(words) + "."
        if i % 7 == 0:
            text += " Texto longo sobre outros assuntos." * 20
        day = 1 + (i * 5) % 28
        # Two dates in the source leave the publication date null, as in the real spelling.
        published = "DJEN DATA:01/09/2026 DATA:02/09/2026" if i % 9 == 0 else f"DJEN DATA:{day:02d}/08/2026"
        docs.append(
            raw_doc(
                str(i),
                text=text,
                dataDecisao=f"202608{1 + (i * 3) % 28:02d}",
                dataPublicacao=published,
                nomeOrgaoJulgador="QUARTA TURMA" if i % 3 == 0 else "TERCEIRA TURMA",
                numeroProcesso="1234567" if i % 5 == 0 else str(7000000 + i),
            )
        )
    return docs


@pytest.fixture
def sample(store):
    ingest(store, documents())
    return store


def legacy_ids(view, options):
    """Every id, in order, by the plan before this reform, over the same validated parameters."""
    plan = query.JudgmentSearch(
        view,
        options.get("termos", ""),
        detalhe="triagem",
        limite=options.get("limite"),
        ordenar=options.get("ordenar"),
        modo_busca=options.get("modo_busca", "simples"),
        tipo_data=options.get("tipo_data", "publicacao"),
    )
    plan.restrict(
        *query.judgment_filters(
            view,
            processo=options.get("processo"),
            tribunal=None,
            orgao=options.get("orgao"),
            classe=None,
            relator=None,
        )
    )
    plan.restrict(
        *query.date_filters("d." + plan.column, options.get("data_inicio"), options.get("data_fim"))
    )
    ranked = plan.ordenar == "relevancia"
    source = "documents d JOIN search ON search.id=d.id" if ranked else "documents d"
    direction = "ASC" if plan.ordenar == "mais_antigos" else "DESC"
    order = f"d.{plan.column} IS NULL,d.{plan.column} {direction},d.id"
    if ranked:
        order = "bm25(search)," + order

    def rows(db, terms):
        filters, params = list(plan.filters), list(plan.params)
        if terms:
            match = "search MATCH ?" if ranked else "d.id IN (SELECT id FROM search WHERE search MATCH ?)"
            filters.insert(0, match)
            params.insert(0, terms)
        where = " AND ".join(filters) or "1=1"
        return [r[0] for r in db.execute(f"SELECT d.id FROM {source} WHERE {where} ORDER BY {order}", params)]

    with view.read() as db:
        found = rows(db, plan.query)
        broadened = query.broadening(plan.termos) if not found and plan.modo_busca == "simples" else None
        if broadened and not plan.any_term:
            found = rows(db, query.any_term_query(broadened[0]))  # The ampliação of the date order.
    return found


def paged_ids(store, options):
    """Every id the tool returns, following the cursor to the end."""
    found, cursor = [], None
    while True:
        page = api.search(store, cursor=cursor, **options)
        found += [r["id"] for r in page["resultados"]]
        if page["resultados"] and options.get("termos"):
            assert all("trecho_correspondente" in r for r in page["resultados"])
        cursor = page["proximo_cursor"]
        if not cursor:
            return found, page["total_encontrado"]


def drop_index(store):
    with connection(store.path, write=True) as db, db:
        db.execute(f"DROP INDEX {ROWID_INDEX}")


def drop_map(store):
    with connection(store.path, write=True) as db, db:
        db.execute(f"DROP INDEX {ROWID_INDEX}")
        db.execute("DROP TABLE search_map")
        db.execute("DELETE FROM meta WHERE key='search_map'")


@pytest.mark.parametrize("state", ["indexado", "sem_indice", "sem_mapa"])
def test_same_ids_in_the_same_order_as_the_legacy_plan_in_every_state(sample, state):
    if state == "sem_indice":
        drop_index(sample)
    elif state == "sem_mapa":
        drop_map(sample)
    view = sample.view()
    with view.read() as db:
        expected_map = {"indexado": "search_map", "sem_indice": "temp.search_rowids", "sem_mapa": None}[state]
        assert query.rowid_map(db) == expected_map
    for options in QUERIES:
        expected = legacy_ids(view, options)
        found, total = paged_ids(sample, options)
        assert found == expected, options
        assert total == len(expected), options
    # The sample exercises the tie-breakers: same BM25 score, dates and null dates, id order.
    ranked = legacy_ids(view, QUERIES[0])
    assert len(ranked) > 8


def test_ties_are_broken_by_date_then_id_and_null_dates_go_last(store):
    """Five identical ementas, one BM25 score: the date decides, then the id, and a null date goes last."""
    same = "Pensão alimentícia."
    ingest(
        store,
        [
            raw_doc("9", text=same, dataPublicacao="DJEN DATA:10/08/2026"),
            raw_doc("10", text=same, dataPublicacao="DJEN DATA:10/08/2026"),
            raw_doc("2", text=same, dataPublicacao="DJEN DATA:20/08/2026"),
            raw_doc("3", text=same, dataPublicacao="DJEN DATA:01/09/2026 DATA:02/09/2026"),
            raw_doc("4", text=same, dataPublicacao="DJEN DATA:05/08/2026"),
            raw_doc("5", text=same + " E guarda, num texto maior.", dataPublicacao="DJEN DATA:30/08/2026"),
        ],
    )
    expected = ["STJ:2", "STJ:10", "STJ:9", "STJ:4", "STJ:3", "STJ:5"]
    assert paged_ids(store, {"termos": "pensão", "limite": 2})[0] == expected
    assert legacy_ids(store.view(), {"termos": "pensão", "limite": 2}) == expected
    oldest = {"termos": "pensão", "ordenar": "mais_antigos", "limite": 4}
    by_date = ["STJ:4", "STJ:10", "STJ:9", "STJ:2", "STJ:5", "STJ:3"]
    assert paged_ids(store, oldest)[0] == legacy_ids(store.view(), oldest) == by_date


def test_ingest_and_publication_carry_the_rowid_index(sample):
    with connection(sample.path) as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (ROWID_INDEX,)).fetchone()
    drop_index(sample)
    publish(sample)
    view = api._view(sample, None, None)
    with view.read() as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (ROWID_INDEX,)).fetchone()
        assert query.rowid_map(db) == "search_map"
    assert paged_ids(sample, QUERIES[0])[0] == legacy_ids(view, QUERIES[0])


def test_ranked_plan_reads_the_index_by_rowid_and_not_the_id_column(sample):
    with connection(sample.path) as db:
        plan = query.JudgmentSearch(
            sample.view(),
            "guarda alimentos",
            detalhe="triagem",
            limite=None,
            ordenar=None,
            modo_busca="simples",
            tipo_data="publicacao",
        )
        plan.prepare(db)
        source, where, params, order = plan.plan()
        explain = f"EXPLAIN QUERY PLAN SELECT d.id FROM {source} WHERE {where} ORDER BY {order}"
        steps = str([tuple(r) for r in db.execute(explain, params)])
    assert "search.id" not in source and "m.fts_rowid=search.rowid" in source
    assert "SEARCH m USING" in steps and "SCAN m" not in steps


def test_cursor_is_the_same_whatever_the_plan(sample):
    first = api.search(sample, "guarda alimentos", limite=2)
    drop_index(sample)
    second = api.search(sample, "guarda alimentos", limite=2, cursor=first["proximo_cursor"])
    assert second["resultados"][0]["id"] not in {r["id"] for r in first["resultados"]}


def test_a_read_only_generation_without_the_index_still_answers(sample, monkeypatch):
    # A generation published before the index existed: publish() would add it, so it is held back.
    monkeypatch.setattr("flora_mcp.publication.ensure_search_map", lambda db: None)
    drop_index(sample)
    publish(sample)
    view = api._view(sample, None, None)
    with view.read() as db:
        db.execute("BEGIN")
        assert query.rowid_map(db) == "temp.search_rowids"
        documents = db.execute("SELECT count(*) FROM documents").fetchone()[0]
        assert db.execute("SELECT count(*) FROM temp.search_rowids").fetchone()[0] == documents
    with pytest.raises(sqlite3.OperationalError):
        with view.read() as db:
            db.execute("CREATE INDEX x ON search_map(fts_rowid)")
    assert paged_ids(sample, QUERIES[0])[0] == legacy_ids(view, QUERIES[0])
