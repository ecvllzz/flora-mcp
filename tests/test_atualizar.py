"""Comando único de atualização com fontes simuladas: ordem, falha isolada e trava."""

import json
from contextlib import nullcontext
from datetime import date
from pathlib import Path

import httpx
import pytest
from filelock import FileLock, Timeout

from flora_mcp import atualizacao, backups
from flora_mcp.config import Config
from flora_mcp.model import FloraError


@pytest.fixture
def steps(store, monkeypatch):
    """Record the order of the update steps; the backup is real, the sources are simulated."""
    calls = []
    real_backup = backups.create

    def backup(*args, **kwargs):
        calls.append(("backup", args[2]))
        return real_backup(*args, **kwargs)

    def stj(config, store, http):
        calls.append(("stj", config.max_resources))
        return {"fonte": "STJ", "status": "ok"}

    def tjsc(config, store, http, start, end):
        calls.append(("tjsc", str(start), str(end)))
        return {"fonte": "TJSC", "status": "ok"}

    def publish(store):
        calls.append(("publicacao",))
        return {"status": "ok"}

    monkeypatch.setattr(backups, "create", backup)
    monkeypatch.setattr(atualizacao, "sync_stj", stj)
    monkeypatch.setattr(atualizacao, "sync_tjsc", tjsc)
    monkeypatch.setattr(atualizacao, "publish", publish)
    (store.directory / "publicacoes.json").write_text("{}", encoding="utf-8")
    return calls


def run(store, tmp_path, **options):
    config = Config(store.directory, request_delay=0)
    return atualizacao.update(
        config,
        store,
        backup_root=tmp_path / "backups",
        http_client=nullcontext,
        today=date(2026, 9, 30),
        **options,
    )


def test_backup_then_sources_then_publication(store, tmp_path, steps):
    report = run(store, tmp_path, stj_lotes=60, tjsc_dias=30)
    assert steps == [
        ("backup", "antes-atualizacao"),
        ("stj", 60),
        ("tjsc", "2026-09-01", "2026-09-30"),
        ("publicacao",),
    ]
    assert report["status"] == "ok" and report["backup"]["formato"] == "flora-backup-2"
    assert Path(report["backup"]["destino"]).name.endswith("-antes-atualizacao")
    log = json.loads(Path(report["log"]).read_text(encoding="utf-8"))
    assert log["execucoes"] == report["execucoes"] and Path(report["log"]).parent.name == "logs"


def test_failure_of_one_source_does_not_stop_the_other(store, tmp_path, steps, monkeypatch):
    def broken(config, store, http):
        steps.append(("stj", "falhou"))
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(atualizacao, "sync_stj", broken)
    report = run(store, tmp_path)
    assert [s[0] for s in steps] == ["backup", "stj", "tjsc", "publicacao"]
    assert report["status"] == "error"
    assert report["execucoes"][0] == {
        "fonte": "STJ",
        "status": "error",
        "codigo": "erro_fonte",
        "erro": "ConnectError: sem rede",
    }
    assert report["execucoes"][1]["status"] == "ok"


def test_single_source_and_default_window(store, tmp_path, steps):
    run(store, tmp_path, stj=False)
    assert [s[0] for s in steps] == ["backup", "tjsc", "publicacao"]
    assert steps[1] == ("tjsc", "2026-09-24", "2026-09-30")
    steps.clear()
    run(store, tmp_path, tjsc=False)
    assert steps[1] == ("stj", 2) and len(steps) == 3


def test_busy_lock_refuses_before_any_step(store, tmp_path, steps):
    with FileLock(str(store.directory / "collector.lock")), pytest.raises(Timeout):
        run(store, tmp_path)
    assert steps == []
    assert not (tmp_path / "backups").exists() and not (store.directory / "logs").exists()


@pytest.mark.parametrize(
    "options", [{"tjsc_dias": 0}, {"tjsc_dias": 32}, {"stj_lotes": 0}, {"stj": False, "tjsc": False}]
)
def test_invalid_options_are_refused(store, tmp_path, steps, options):
    with pytest.raises(FloraError):
        run(store, tmp_path, **options)
    assert steps == []


def test_window_ends_today_in_sao_paulo(monkeypatch):
    monkeypatch.setattr(atualizacao, "local_date", lambda: date(2026, 3, 1))
    assert atualizacao.tjsc_window(1) == (date(2026, 3, 1), date(2026, 3, 1))
    assert atualizacao.tjsc_window(31)[0] == date(2026, 1, 30)
