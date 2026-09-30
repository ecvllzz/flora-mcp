import sqlite3

from conftest import ingest, raw_doc


def counts(store):
    db = sqlite3.connect(store.path)
    try:
        return (
            db.execute("SELECT count(*) FROM documents").fetchone()[0],
            db.execute("SELECT count(*) FROM search").fetchone()[0],
            db.execute("SELECT count(*) FROM search_map").fetchone()[0],
            db.execute("SELECT count(DISTINCT id) FROM search").fetchone()[0],
        )
    finally:
        db.close()


def test_map_follows_inserts_updates_and_removals(store):
    ingest(store, [raw_doc("1"), raw_doc("2")], resource_id="r1")
    assert counts(store) == (2, 2, 2, 2)
    ingest(store, [raw_doc("1", text="Alimentos alterados."), raw_doc("2")], resource_id="r1")
    assert counts(store) == (2, 2, 2, 2)
    ingest(store, [raw_doc("1", text="Alimentos alterados.")], resource_id="r1")
    assert counts(store) == (1, 1, 1, 1)
    db = sqlite3.connect(store.path)
    rows = db.execute("SELECT s.id FROM search s JOIN search_map m ON m.fts_rowid=s.rowid").fetchall()
    db.close()
    assert rows == [("STJ:1",)]


def test_existing_database_without_map_is_backfilled_once(store):
    ingest(store, [raw_doc("1"), raw_doc("2")], resource_id="r1")
    db = sqlite3.connect(store.path)
    db.execute("DROP TABLE search_map")
    db.execute("DELETE FROM meta WHERE key='search_map'")
    db.commit()
    db.close()
    ingest(store, [raw_doc("1", text="Texto novo."), raw_doc("2")], resource_id="r1")
    assert counts(store) == (2, 2, 2, 2)


def test_update_deletes_by_rowid_without_scanning_fts(store):
    ingest(store, [raw_doc("1")], resource_id="r1")
    db = sqlite3.connect(store.path)
    by_rowid = str(db.execute("EXPLAIN QUERY PLAN DELETE FROM search WHERE rowid=?", (1,)).fetchall())
    by_id = str(db.execute("EXPLAIN QUERY PLAN DELETE FROM search WHERE id=?", ("STJ:1",)).fetchall())
    db.close()
    # "INDEX 0:=" is the FTS5 rowid lookup; a bare "INDEX 0:" is a full scan.
    assert "INDEX 0:=" in by_rowid and "INDEX 0:=" not in by_id
