import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.store import Store, connection
from flora_mcp.tjsc_orgaos import ESPECIAIS, identity

spec = importlib.util.spec_from_file_location(
    "resume_tjsc", Path(__file__).parents[1] / "scripts/resume_tjsc.py"
)
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)


def empty(_http, _config, organ, day):
    envelope = {"fonte": "TJSC", **identity(organ), "data_publicacao": str(day), "total": 0}
    return json.dumps(envelope).encode(), []


def legacy(_http, _config, organ, day):
    """Envelope of a window collected before organs were named: chamber number only."""
    number = identity(organ)["camara"]
    return json.dumps({"camara": number, "data_publicacao": str(day), "total": 0}).encode(), []


@pytest.fixture
def setup(tmp_path):
    config = Config(data_dir=tmp_path / "data", request_delay=0)
    store = Store(config.data_dir)
    store.initialize()
    return config, store


def test_resume_committed_window_after_failure_and_skip_completed(setup, tmp_path):
    config, store = setup
    start = end = date(2026, 1, 1)

    def fail_second(http, config, organ, day):
        if organ == "10ª Câmara de Direito Civil":
            raise ValueError("source failed")
        return empty(http, config, organ, day)

    with pytest.raises(ValueError, match="source failed"):
        resume.execute(
            config, store, start, end, tmp_path / "first.json", tmp_path / "backup1", fetch=fail_second
        )
    work = resume.plan(store, start, end)
    assert work["concluidas_verificadas"] == 1
    assert [x["camara"] for x in work["pendentes"]] == [10]
    called = []

    def observe(http, config, organ, day):
        called.append(organ)
        return empty(http, config, organ, day)

    result = resume.execute(
        config, store, start, end, tmp_path / "second.json", tmp_path / "backup2", fetch=observe
    )
    assert result["status"] == "ok" and called == ["10ª Câmara de Direito Civil"]
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

    result = resume.execute(
        config, store, day, day, tmp_path / "noop.json", tmp_path / "no-backup", fetch=unexpected
    )
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


def test_windows_from_before_named_organs_still_verify(setup, tmp_path):
    """tjsc-N-civil datasets and envelopes with only the chamber number need no migration."""
    config, store = setup
    day = date(2026, 1, 1)
    resume.execute(config, store, day, day, tmp_path / "old.json", tmp_path / "b1", fetch=legacy)
    with connection(store.path) as db:
        datasets = [r[0] for r in db.execute("SELECT dataset FROM resources ORDER BY dataset")]
        metadata = json.loads(db.execute("SELECT metadata FROM resources LIMIT 1").fetchone()[0])
    assert datasets == ["tjsc-10-civil", "tjsc-9-civil"]
    assert "chamber" in metadata and "orgao" not in metadata
    work = resume.plan(store, day, day, (9, "10ª Câmara de Direito Civil"))
    assert (work["concluidas_verificadas"], work["pendentes"]) == (2, [])
    assert work["orgaos"] == ["9ª Câmara de Direito Civil", "10ª Câmara de Direito Civil"]


def test_named_organ_gets_its_own_dataset_and_is_verified_by_name(setup, tmp_path):
    config, store = setup
    day = date(2026, 1, 1)
    special = ESPECIAIS[0]
    called = []

    def observe(http, config, organ, day):
        called.append(organ)
        return empty(http, config, organ, day)

    report = resume.execute(
        config, store, day, day, tmp_path / "run.json", tmp_path / "b", fetch=observe, organs=(9, special)
    )
    assert called == ["9ª Câmara de Direito Civil", special]
    assert report["eventos"][1]["orgao"] == special and "camara" not in report["eventos"][1]
    with connection(store.path) as db:
        rows = {r[0]: json.loads(r[1]) for r in db.execute("SELECT dataset,metadata FROM resources")}
    dataset = "tjsc-1a-camara-especial-de-enfrentamento-de-acervos"
    assert rows[dataset]["orgao"] == special and "chamber" not in rows[dataset]
    assert resume.plan(store, day, day, (special,))["concluidas_verificadas"] == 1


def test_window_of_another_organ_is_inconsistent(setup, tmp_path):
    config, store = setup
    day = date(2026, 1, 1)

    def wrong(http, config, organ, day):
        return empty(http, config, ESPECIAIS[1], day)

    resume.execute(config, store, day, day, tmp_path / "run.json", tmp_path / "b", fetch=wrong, organs=(9,))
    with pytest.raises(FloraError, match="tjsc-9-civil"):
        resume.plan(store, day, day, (9,))


@pytest.mark.parametrize(
    "camaras,orgaos,expected",
    [
        (None, [], ("9ª Câmara de Direito Civil", "10ª Câmara de Direito Civil")),
        ("1,2", [], ("1ª Câmara de Direito Civil", "2ª Câmara de Direito Civil")),
        (None, list(ESPECIAIS[:2]), ESPECIAIS[:2]),
        ("9", ["9ª Câmara de Direito Civil", ESPECIAIS[2]], ("9ª Câmara de Direito Civil", ESPECIAIS[2])),
    ],
)
def test_organs_by_number_and_by_name(camaras, orgaos, expected):
    assert resume.selected_organs(camaras, orgaos) == expected


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["--camaras", "11"], "1 a 10"),
        (["--orgaos", "1ª Câmara de Enfrentamento de Acervos"], "fora da lista"),
        (["--orgaos", "Câmara Especial de Enfrentamento"], "fora da lista"),
    ],
)
def test_command_line_refuses_unknown_organs(monkeypatch, capsys, tmp_path, arguments, message):
    argv = ["resume_tjsc.py", "--data-dir", str(tmp_path), "--inicio", "2026-01-01", "--fim", "2026-01-01"]
    monkeypatch.setattr("sys.argv", argv + arguments)
    with pytest.raises(SystemExit):
        resume.main()
    assert message in capsys.readouterr().err
    assert not (tmp_path / "acervo.sqlite").exists()


def test_command_line_plans_named_organs_without_writing(monkeypatch, capsys, setup):
    config, _ = setup
    argv = ["resume_tjsc.py", "--data-dir", str(config.data_dir), "--inicio", "2026-01-01"]
    argv += ["--fim", "2026-01-02", "--camaras", "10", "--orgaos", ESPECIAIS[2]]
    monkeypatch.setattr("sys.argv", argv)
    resume.main()
    printed = json.loads(capsys.readouterr().out)
    assert printed["orgaos"] == ["10ª Câmara de Direito Civil", ESPECIAIS[2]]
    assert printed["pendentes"] == 4
