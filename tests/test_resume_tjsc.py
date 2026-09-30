import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.store import Store, connection

spec = importlib.util.spec_from_file_location("resume_tjsc", Path(__file__).parents[1] / "scripts/resume_tjsc.py")
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)


def empty(_http, _config, chamber, day):
    return json.dumps({"camara": chamber, "data_publicacao": str(day), "total": 0}).encode(), []


@pytest.fixture
def setup(tmp_path):
    config = Config(data_dir=tmp_path / "data", request_delay=0)
    store = Store(config.data_dir)
    store.initialize()
    return config, store


def test_resume_committed_window_after_failure_and_skip_completed(setup, tmp_path):
    config, store = setup
    start = end = date(2026, 1, 1)
    def fail_second(http, config, chamber, day):
        if chamber == 10:
            raise ValueError("source failed")
        return empty(http, config, chamber, day)
    with pytest.raises(ValueError, match="source failed"):
        resume.execute(config, store, start, end, tmp_path / "first.json", tmp_path / "backup1", fetch=fail_second)
    work = resume.plan(store, start, end)
    assert work["concluidas_verificadas"] == 1
    assert [x["camara"] for x in work["pendentes"]] == [10]
    called = []
    def observe(http, config, chamber, day):
        called.append(chamber)
        return empty(http, config, chamber, day)
    result = resume.execute(config, store, start, end, tmp_path / "second.json", tmp_path / "backup2", fetch=observe)
    assert result["status"] == "ok" and called == [10]
    assert resume.plan(store, start, end)["pendentes"] == []
    with connection(store.path) as db:
        assert [r[0] for r in db.execute("SELECT status FROM runs ORDER BY started")] == ["error", "ok"]


def test_corrupt_completed_original_does_not_get_skipped(setup, tmp_path):
    config, store = setup
    day = date(2026, 1, 1)
    resume.execute(config, store, day, day, tmp_path / "run.json", tmp_path / "backup", fetch=empty)
    with connection(store.path) as db:
        raw = db.execute("SELECT raw_path FROM resources LIMIT 1").fetchone()[0]
    (store.directory / raw).write_bytes(b"corrupt")
    with pytest.raises(FloraError, match="tjsc"):
        resume.plan(store, day, day)


def test_completed_run_needs_no_backup_or_fetch(setup, tmp_path):
    config, store = setup
    day = date(2026, 1, 1)
    resume.execute(config, store, day, day, tmp_path / "run.json", tmp_path / "backup", fetch=empty)
    def unexpected(*args):
        pytest.fail("completed windows must not be fetched")
    result = resume.execute(config, store, day, day, tmp_path / "noop.json", tmp_path / "no-backup", fetch=unexpected)
    assert result["status"] == "ok" and result["eventos"] == []
    assert not (tmp_path / "no-backup").exists()


def test_interrupt_retains_pending_day_and_closes_run(setup, tmp_path):
    config, store = setup
    day = date(2026, 1, 1)
    def interrupt(*args):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        resume.execute(config, store, day, day, tmp_path / "run.json", tmp_path / "backup", fetch=interrupt)
    with connection(store.path) as db:
        assert db.execute("SELECT status FROM runs").fetchone()[0] == "interrupted"
    assert len(resume.plan(store, day, day)["pendentes"]) == 2
