import json
import sqlite3

import pytest

from flora_mcp.model import FloraError, digest
from flora_mcp.query import document, search
from flora_mcp.store import Store, connection

from conftest import ingest, raw_doc


def test_idempotence_versions_and_nonindexed_updates(store):
    assert ingest(store, [raw_doc()])["novos"] == 1
    assert ingest(store, [raw_doc()])["inalterados"] == 1
    assert ingest(store, [raw_doc(notas="correção em campo não pesquisado")])["alterados"] == 1
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM search").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM version_origins").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM resource_history").fetchone()[0] == 2


def test_same_process_different_decisions_and_search_filters(store):
    ingest(
        store,
        [
            raw_doc("1"),
            raw_doc("2", dataDecisao="20250901"),
            raw_doc("3", numeroProcesso="12345678", nomeOrgaoJulgador="QUARTA TURMA"),
        ],
    )
    assert search(store, processo="1.234.567")["total_encontrado"] == 2
    assert search(store, processo="2025/0001234-5")["total_encontrado"] == 3
    assert search(store, termos='"protecao a crianca"', orgao="terceira turma")["total_encontrado"] == 2
    assert search(store, data_inicio="2026-01-01", tipo_data="julgamento")["total_encontrado"] == 2
    assert search(store, tribunal="TJSC")["total_encontrado"] == 0
    with pytest.raises(FloraError, match="inteiro teor"):
        search(store, campo="inteiro_teor")


def test_older_resource_cannot_replace_newer_text(store):
    ingest(store, [raw_doc(text="Versão nova")])
    ingest(store, [raw_doc(text="Versão antiga")], name="20250731.json", resource_id="old")
    assert document(store, "STJ:1")["texto"] == "Versão nova"
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 2


def test_full_unicode_text_and_explicit_lossless_blocks(store):
    text = "Direito à proteção.\n" * 3000 + "FIM AUTÊNTICO"
    ingest(store, [raw_doc(text=text)])
    assert search(store, "protecao")["resultados"][0]["ementa"] == text
    pieces, cursor = [], None
    while True:
        result = document(store, "STJ:1", cursor=cursor, tamanho_bloco=3000)
        assert result["offset"] == sum(map(len, pieces))
        pieces.append(result["texto"])
        cursor = result["proximo_cursor"]
        if cursor is None:
            break
    assert "".join(pieces) == text
    assert result["sha256_texto_completo"] == digest(text.encode())


def test_pagination_does_not_silently_skip_after_update(store):
    ingest(store, [raw_doc(str(i)) for i in range(4)])
    first = search(store, limite=2)
    second = search(store, limite=2, cursor=first["proximo_cursor"])
    assert {r["id"] for r in first["resultados"]}.isdisjoint(r["id"] for r in second["resultados"])
    ingest(store, [raw_doc(str(i)) for i in range(5)])
    with pytest.raises(FloraError, match="base mudou"):
        search(store, limite=2, cursor=first["proximo_cursor"])


def test_document_cursor_rejects_updated_version(store):
    ingest(store, [raw_doc(text="A" * 1000)])
    cursor = document(store, "STJ:1", tamanho_bloco=100)["proximo_cursor"]
    ingest(store, [raw_doc(text="B" * 1000)])
    with pytest.raises(FloraError, match="atualizado"):
        document(store, "STJ:1", cursor=cursor)


def test_failed_index_write_rolls_back_documents_versions_and_checkpoint(store):
    ingest(store, [raw_doc()])
    with connection(store.path, write=True) as db, db:
        db.execute("""CREATE TRIGGER simulate_failure BEFORE INSERT ON documents
            BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="simulated"):
        ingest(store, [raw_doc(text="changed")], modified="2026-09-09")
    assert document(store, "STJ:1")["texto"] == raw_doc()["ementa"]
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 1
        row = db.execute("SELECT * FROM resources").fetchone()
        assert row["expected_fingerprint"] != row["applied_fingerprint"]
    with connection(store.path, write=True) as db, db:
        db.execute("DROP TRIGGER simulate_failure")
    assert ingest(store, [raw_doc(text="changed")], modified="2026-09-09")["alterados"] == 1


def test_removed_row_in_changed_resource_is_removed_from_search_but_version_retained(store):
    ingest(store, [raw_doc("1"), raw_doc("2")])
    assert ingest(store, [raw_doc("1")])["removidos"] == 1
    assert search(store)["total_encontrado"] == 1
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 2


def test_backup_can_be_opened_independently_with_sources(store, tmp_path):
    ingest(store, [raw_doc()])
    target = tmp_path / "restored"
    store.backup(target)
    restored = Store(target)
    assert search(restored, "alimentos")["total_encontrado"] == 1
    result = document(restored, "STJ:1", "espelho_original")
    assert json.loads(result["texto"])["id"] == "1"
    assert (target / result["fonte"]["raw_path"]).exists()


def test_query_connection_is_readonly(store):
    with connection(store.path) as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("DELETE FROM documents")


def test_collector_lock_rejects_second_writer(store):
    from filelock import FileLock, Timeout

    lock_path = str(store.directory / "collector.lock")
    with FileLock(lock_path), pytest.raises(Timeout), FileLock(lock_path, timeout=0):
        pass


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data_inicio": "ontem"},
        {"data_inicio": "2026-02-30"},
        {"limite": 0},
        {"processo": "REsp"},
        {"termos": '"incompleta'},
        {"cursor": "not-a-cursor"},
    ],
)
def test_invalid_queries_are_explicit_errors(store, kwargs):
    with pytest.raises(FloraError):
        search(store, **kwargs)
