"""Atraso da coleta por fonte e registros inválidos que não derrubam o lote do STJ."""

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone

import httpx
import pytest

from flora_mcp import api
from flora_mcp.config import Config
from flora_mcp.query import search
from flora_mcp.sources import sync_stj
from flora_mcp.store import SCHEMA, Store, collection_delay, connection

from conftest import raw_doc


def add_run(store, source, status, finished):
    with connection(store.path, write=True) as db, db:
        db.execute(
            "INSERT INTO runs(id,source,started,finished,status) VALUES (?,?,?,?,?)",
            (source + status + finished, source, finished, finished, status),
        )


def test_delay_uses_latest_successful_run_per_source(store):
    today = date(2026, 9, 30)
    add_run(store, "STJ", "ok", "2026-07-01T10:00:00+00:00")
    add_run(store, "STJ", "partial", "2026-08-15T23:59:00+00:00")
    add_run(store, "STJ", "error", "2026-09-29T10:00:00+00:00")
    add_run(store, "TJSC", "ok", "2026-09-20T12:00:00+00:00")
    add_run(store, "TJSC-probe", "partial", "2026-09-30T12:00:00+00:00")
    with connection(store.path) as db:
        delay = collection_delay(db, today=today)
        stricter = collection_delay(db, {"STJ": 40, "TJSC": 10}, today=today)
    assert delay["STJ"] == {
        "ultima_coleta_ok": "2026-08-15T23:59:00+00:00",
        "dias_desde_ultima_coleta": 46,
        "limiar_dias": 45,
        "atraso": True,
    }
    assert delay["TJSC"]["dias_desde_ultima_coleta"] == 10 and delay["TJSC"]["atraso"] is True
    assert stricter["TJSC"]["atraso"] is False and stricter["STJ"]["limiar_dias"] == 40
    with connection(store.path) as db:
        assert collection_delay(db, today=date(2026, 9, 29))["STJ"]["atraso"] is False


def test_source_without_run_is_late_and_block_reaches_every_coverage_detail(tmp_path):
    store = Store(tmp_path / "data", atrasos={"STJ": 45, "TJSC": 3})
    store.initialize()
    add_run(store, "TJSC", "ok", datetime.now(timezone.utc).isoformat())
    expected = {
        "STJ": {
            "ultima_coleta_ok": None,
            "dias_desde_ultima_coleta": None,
            "limiar_dias": 45,
            "atraso": True,
        },
        "TJSC": {"dias_desde_ultima_coleta": 0, "limiar_dias": 3, "atraso": False},
    }
    for detail in ("resumo", "completo", "recursos", "execucoes"):
        block = api.coverage(store, detail)["coleta"]
        assert block["STJ"] == expected["STJ"]
        assert {k: block["TJSC"][k] for k in expected["TJSC"]} == expected["TJSC"]
    assert Store(store.directory).coverage()["coleta"]["TJSC"]["limiar_dias"] == 7


def old_database(path):
    """A database created before the rejected-records column existed."""
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db:
        db.executescript(SCHEMA)
        db.commit()


def test_old_database_gains_rejected_column_and_old_snapshot_still_reads(tmp_path):
    store = Store(tmp_path / "data")
    old_database(store.path)
    with connection(store.path) as db:
        assert "rejeitados" not in {r[1] for r in db.execute("PRAGMA table_info(resources)")}
    assert store.view().coverage()["recursos"] == []  # reader of an old snapshot
    store.initialize()
    store.initialize()  # idempotent
    with connection(store.path) as db:
        assert "rejeitados" in {r[1] for r in db.execute("PRAGMA table_info(resources)")}
        assert db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] == 1


def collect(store, batch, force=False):
    config = Config(store.directory, datasets=["espelhos-de-acordaos-terceira-turma"], request_delay=0)
    resource = {"id": "r", "name": "20251130.json", "url": "https://dadosabertos.web.stj.jus.br/r"}

    def route(request):
        if request.url.path.endswith("package_show"):
            return httpx.Response(200, json={"success": True, "result": {"resources": [resource]}})
        return httpx.Response(200, content=json.dumps(batch).encode())

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        return sync_stj(config, store, http, force=force)


def test_invalid_mirrors_are_left_out_and_reported(store):
    batch = [
        raw_doc("1"),
        {**raw_doc("x"), "ementa": None},
        {k: v for k, v in raw_doc("y").items() if k != "id"},
        raw_doc("2", "Guarda. Alimentos."),
    ]
    report = collect(store, batch)
    assert report["status"] == "ok"
    event = report["eventos"][0]
    assert event["registros"] == 2 and event["novos"] == 2
    assert [(r["posicao"], r["id"]) for r in event["rejeitados"]] == [(1, "x"), (2, None)]
    assert all("sem identificador ou ementa" in r["motivo"] for r in event["rejeitados"])
    assert report["rejeitados"] == [
        {"dataset": "espelhos-de-acordaos-terceira-turma", "recurso": "20251130.json", "registros": 2}
    ]
    assert search(store)["total_encontrado"] == 2
    summary = api.coverage(store)
    assert summary["recursos"][0]["rejeitados"] == 2
    assert summary["recursos"][0]["por_status"] == {"ok": 1}
    # The summary keeps the latest run of each source without detail; the history has it.
    assert "detail" not in summary["execucoes_recentes"][0]
    run = api.coverage(store, "execucoes", limite=1)["itens"][0]
    assert run["detail"]["rejeitados"] == report["rejeitados"]
    detail = api.coverage(store, "recursos")["itens"][0]
    assert detail["rejeitados"] == event["rejeitados"]
    with connection(store.path) as db:
        raw_path = db.execute("SELECT raw_path FROM resources").fetchone()[0]
    assert json.loads((store.directory / raw_path).read_bytes()) == batch  # original kept whole


@pytest.mark.parametrize("batch", [[{"ementa": "sem id"}, {"id": "1"}], {"id": "1"}, []])
def test_batch_without_valid_mirror_stays_in_error(store, batch):
    report = collect(store, batch)
    assert report["status"] == "error"
    assert search(store)["total_encontrado"] == 0
    resource = api.coverage(store, "recursos")["itens"][0]
    assert resource["status"] == "error" and "rejeitados" not in resource


def test_valid_batch_clears_previous_rejections(store):
    collect(store, [raw_doc("1"), {"id": "x"}])
    collect(store, [raw_doc("1")], force=True)
    assert "rejeitados" not in api.coverage(store, "recursos")["itens"][0]
    assert "rejeitados" not in api.coverage(store)["recursos"][0]
