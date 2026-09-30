import sqlite3

import pytest

from conftest import ingest, raw_doc
from flora_mcp import api, config, precedent_query, query
from flora_mcp.model import FloraError
from flora_mcp.precedents import parse_id
from flora_mcp.publication import Reader
from flora_mcp.store import ReadView, connection


@pytest.mark.parametrize(
    "value,expected",
    [
        ("STJ:tema_repetitivo:1085", ("STJ", "tema_repetitivo", None, "1085")),
        ("STF:sumula_vinculante:25", ("STF", "sumula_vinculante", None, "25")),
        ("TJSC:sumula:GCDC:67", ("TJSC", "sumula", "GCDC", "67")),
        ("STJ:1461494", None),
        ("TJSC:321780325060937409680905905071", None),
        ("TJSC:sumula:67", None),
        ("STJ:sumula:GCDC:1", None),
        ("STJ:tema_repercussao_geral:1", None),
        ("STF:sumula:0", None),
        ("X:sumula:1", None),
        ("", None),
    ],
)
def test_parse_id(value, expected):
    assert parse_id(value) == expected


def test_reader_without_manifest_returns_work_database_view(store):
    ingest(store, [raw_doc()])
    view = Reader(store).resolve()
    assert isinstance(view, ReadView)
    assert view.publication is None and view.path == store.path and not view.immutable
    assert view.withdrawn == frozenset() and view.coverage()["grupos"]


def test_api_keeps_one_declared_reader_per_store(store):
    ingest(store, [raw_doc()])
    api.search(store, "alimentos")
    first = store.reader
    api.search(store, "alimentos")
    assert first is not None and store.reader is first


@pytest.mark.parametrize(
    "message,code",
    [
        ('fts5: syntax error near "AND"', "consulta_invalida"),
        ("no such column: xyz", "consulta_invalida"),
        ("database is locked", "base_indisponivel"),
        ("disk I/O error", "base_indisponivel"),
        ("unable to open database file", "base_indisponivel"),
    ],
)
def test_database_errors_are_not_reported_as_bad_queries(message, code):
    assert query.database_error(sqlite3.OperationalError(message)).code == code


class _Failing:
    def __init__(self, db, message):
        self.db, self.message = db, message

    def execute(self, sql, *args):
        if "MATCH" in sql or "precedent" in sql and "count(" in sql:
            raise sqlite3.OperationalError(self.message)
        return self.db.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.db, name)


@pytest.mark.parametrize("colecao", ["acordaos", "precedentes"])
def test_locked_database_surfaces_as_unavailable(store, monkeypatch, colecao):
    ingest(store, [raw_doc()])
    view = store.view()
    real = view.read

    from contextlib import contextmanager

    @contextmanager
    def failing():
        with real() as db:
            yield _Failing(db, "database is locked")

    monkeypatch.setattr(ReadView, "read", lambda self: failing())
    with pytest.raises(FloraError) as info:
        if colecao == "acordaos":
            query.search(view, "alimentos")
        else:
            db_view = view
            monkeypatch.setattr(precedent_query, "available", lambda db: True)
            precedent_query.search(db_view, termos="alimentos")
    assert info.value.code == "base_indisponivel"


def test_connection_accepts_relative_path(store, monkeypatch):
    ingest(store, [raw_doc()])
    monkeypatch.chdir(store.directory)
    with connection(store.path.relative_to(store.directory)) as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 1


def test_config_file_from_environment(monkeypatch, tmp_path):
    other = tmp_path / "outro.toml"
    target = tmp_path / "acervo"
    other.write_text("[flora]\ndata_dir = '" + str(target) + "'\n", encoding="utf-8")
    monkeypatch.setattr(config, "LOCAL_CONFIG", tmp_path / "absent.toml")
    monkeypatch.delenv("FLORA_MCP_DATA_DIR", raising=False)
    monkeypatch.setenv("FLORA_MCP_CONFIG", str(other))
    assert config.load_config().data_dir == target
    monkeypatch.delenv("FLORA_MCP_CONFIG")
    with pytest.raises(ValueError, match="não configurada"):
        config.load_config()
