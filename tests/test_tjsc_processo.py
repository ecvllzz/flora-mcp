import importlib.util
import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.store import connection
from flora_mcp.tjsc import (
    PROCESSO_DATASET,
    catalog_process,
    catalog_window,
    collect_process,
    parse_process_page,
    portal_number,
    process_key,
)

# Portal answers to searches by process number, read on 13/10/2026 (receipts beside them).
FIXTURES = Path(__file__).parent / "fixtures" / "tjsc"
CNJ_PAGE = (FIXTURES / "processo-cnj-dois-acordaos.html").read_bytes()
SAJ_PAGE = (FIXTURES / "processo-saj-dois-acordaos.html").read_bytes()
EMPTY_PAGE = (FIXTURES / "processo-sem-resultado.html").read_bytes()

spec = importlib.util.spec_from_file_location(
    "coleta_por_numero_tjsc", Path(__file__).parents[1] / "scripts/coleta_por_numero_tjsc.py"
)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


@pytest.mark.parametrize(
    "value,key",
    [
        ("5011469-46.2022.8.24.0000", "50114694620228240000"),
        ("50114694620228240000", "50114694620228240000"),
        ("0000123-45.2020.8.24.0000", "00001234520208240000"),
        ("2012.009537-4 (Balneário Camboriú)", "20120095374"),
        ("0000.20.12.009537-4/TJSC Embargos de Declaração", "20120095374"),
        ("20120095374", "20120095374"),
    ],
)
def test_process_key_reads_cnj_and_saj_numbers(value, key):
    assert process_key(value) == key


def test_unrecognized_number_is_refused_and_portal_number_is_masked():
    with pytest.raises(FloraError) as info:
        process_key("34")
    assert info.value.code == "numero_invalido"
    assert portal_number("50114694620228240000") == "5011469-46.2022.8.24.0000"
    assert portal_number("20120095374") == "2012.009537-4"


def test_real_pages_bring_every_acordao_of_the_process_from_any_organ():
    total, rows = parse_process_page(CNJ_PAGE, "50114694620228240000")
    assert total == len(rows) == 2
    assert {body["orgao"] for body, _ in rows} == {"Grupo de Câmaras de Direito Civil"}
    assert {body["numero_processo"] for body, _ in rows} == {"5011469-46.2022.8.24.0000"}
    total, rows = parse_process_page(SAJ_PAGE, "20120095374")
    assert total == len(rows) == 2
    assert {body["numero_processo"] for body, _ in rows} == {"2012.009537-4"}
    assert parse_process_page(EMPTY_PAGE, "20080608666") == (0, [])


def test_document_of_another_process_fails_the_page():
    with pytest.raises(FloraError) as info:
        parse_process_page(CNJ_PAGE, "50114694620228240001")
    assert info.value.code == "filtro_nao_respeitado"


def test_search_sends_the_number_without_organ_filter_and_rechecks_the_first_page(store):
    sent = []

    def route(req):
        sent.append(parse_qs(req.content.decode()))
        return httpx.Response(200, content=CNJ_PAGE)

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        content, rows = collect_process(
            http, Config(store.directory, request_delay=0), "50114694620228240000"
        )
    envelope = json.loads(content)
    assert (envelope["consulta"], envelope["numero_processo"], envelope["total"]) == (
        "processo",
        "5011469-46.2022.8.24.0000",
        2,
    )
    assert len(sent) == 2 and all("selOrgao[]" not in values for values in sent)
    assert {values["txtProcesso"][0] for values in sent} == {"5011469-46.2022.8.24.0000"}
    assert len(rows) == 2


def ingest(store, resource_id, rows):
    with connection(store.path) as db:
        saved = dict(db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone())
    run = store.start_run("teste")
    return store.ingest(saved, b'{"teste": true}' + resource_id.encode(), rows, run)


def test_window_keeps_the_current_version_and_the_search_adds_the_rest(store):
    _, rows = parse_process_page(CNJ_PAGE, "50114694620228240000")
    window = catalog_window(store, "1ª Câmara Especial de Enfrentamento de Acervos", date(2026, 1, 5))
    ingest(store, window, rows[:1])
    process = catalog_process(store, "50114694620228240000")
    counts = ingest(store, process, rows)
    assert (counts["novos"], counts["inalterados"]) == (1, 1)
    with connection(store.path) as db:
        current = dict(db.execute("SELECT id,resource_id FROM documents").fetchall())
    assert current[rows[0][0]["id"]] == window
    assert current[rows[1][0]["id"]] == process


def fake_collect(results):
    def collect(_config, _store, _http, entry, _run):
        if results.get(entry["chave"]) == "falha":
            raise FloraError("acesso_bloqueado", "bloqueio simulado")
        return {**entry, "registros": results.get(entry["chave"], 0), "orgaos": [], "documentos": []}

    return collect


def test_receipt_lists_refused_and_not_offered_and_resumes_after_failure(store, tmp_path):
    config = Config(store.directory, request_delay=0)
    insumos = tmp_path / "insumos.json"
    insumos.write_text(
        json.dumps(
            {
                "schema": "flora-r1-insumos-1",
                "biblioteca_fora_do_acervo": [
                    {"id": "TJSC-AI-1", "tribunal": "TJSC", "numero": "5011469-46.2022.8.24.0000"},
                    {"id": "TJSC-Sumula-34", "tribunal": "TJSC", "numero": "34"},
                    {"id": "STJ-REsp-1", "tribunal": "STJ", "numero": "1/SP"},
                ],
                "mais_citados_ausentes": [
                    {"chave": "TJSC:50114694620228240000", "citado_por": 70},
                    {"chave": "TJSC:20120095374", "citado_por": 3},
                    {"chave": "STJ:RESP:1", "citado_por": 9},
                ],
            }
        ),
        encoding="utf-8",
    )
    entries, refused = script.entries_from(insumos, [])
    assert [(e["chave"], len(e["origens"])) for e in entries] == [
        ("50114694620228240000", 2),
        ("20120095374", 1),
    ]
    assert [r["numero_informado"] for r in refused] == ["34"]
    with pytest.raises(FloraError):
        script.execute(
            config,
            store,
            entries,
            refused,
            tmp_path / "r1.json",
            tmp_path / "bk",
            collect=fake_collect({"50114694620228240000": 2, "20120095374": "falha"}),
        )
    first = json.loads((tmp_path / "r1.json").read_text(encoding="utf-8"))
    assert (first["status"], first["em_andamento"]["chave"]) == ("error", "20120095374")
    assert first["recusados"] == refused
    with connection(store.path) as db:
        assert db.execute("SELECT source FROM runs").fetchone()[0] == "TJSC-processo"
    # The fake collector does not write; the plan sees the finished search through its resource.
    catalog_process(store, "50114694620228240000")
    ingest(store, f"{PROCESSO_DATASET}:50114694620228240000", [])
    assert [e["chave"] for e in script.plan(store, entries)["pendentes"]] == ["20120095374"]
    second = script.execute(
        config, store, entries, refused, tmp_path / "r2.json", tmp_path / "bk", collect=fake_collect({})
    )
    assert second["status"] == "ok"
    assert second["nao_oferecidos"] == [{"numero": "2012.009537-4", "origens": ["citado:3"]}]
