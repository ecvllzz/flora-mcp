import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from conftest import ingest, raw_doc

from flora_mcp import backups, cli
from flora_mcp.api import search
from flora_mcp.coleta_numeros import execute, plan_stj
from flora_mcp.config import Config
from flora_mcp.coverage import tribunal_for
from flora_mcp.model import FloraError, digest
from flora_mcp.numeros import merge, read_list, stj_family, stj_key
from flora_mcp.publication import publish
from flora_mcp.stj_selecao import STJ_SELECAO, collect_selection, mirror_datasets
from flora_mcp.store import connection, coverage_report

BASE = "https://dadosabertos.web.stj.jus.br"
DATASET = "espelhos-de-acordaos-terceira-turma"
OTHER = "espelhos-de-acordaos-quarta-turma"


@pytest.mark.parametrize(
    "value,key",
    [
        ("REsp 2.009.614/SC", "RESP:2009614"),
        ("REsp n. 2.009.614/SC", "RESP:2009614"),
        ("REsp nº 2009614", "RESP:2009614"),
        ("AgInt no AREsp 1.779.343/DF", "ARESP:1779343"),
        ("EDcl no AgInt no AREsp 1779343", "ARESP:1779343"),
        ("Agravo Interno no Agravo em Recurso Especial 1.046.016/RJ", "ARESP:1046016"),
        ("AgInt-AREsp-1046016-RJ", "ARESP:1046016"),
        ("EREsp 1.280.825/RJ", "RESP:1280825"),
        ("EAREsp 12", "ARESP:12"),
        ("RESP:1", "RESP:1"),
        ("AGINT NO ARESP:1779343", "ARESP:1779343"),
        ("REsp 1.234.567/SP, rel. Min. Fulano, j. 01/01/2020", "RESP:1234567"),
        ("201201234567", "REGISTRO:201201234567"),
    ],
)
def test_stj_key_finds_the_process_of_any_acordao(value, key):
    assert stj_key(value)["chave"] == key


@pytest.mark.parametrize("value", ["123", "Súmula 7", "Tema 1.076", "IRDR 17", "sem número", ""])
def test_stj_key_refuses_what_is_not_a_process(value):
    with pytest.raises(FloraError):
        stj_key(value)


def test_merge_routes_by_shape_and_court_and_keeps_every_origin():
    entries, refused = merge(
        [
            ("AgInt no AREsp 1.779.343/DF", None, "biblioteca"),
            ("AREsp 1779343", None, "outra"),
            ("STJ: REsp 5/SP", None, "lista"),
            ("5011469-46.2022.8.24.0000", None, "lista"),
            ("TJSC: 2012.009537-4", None, "lista"),
            ("201201234567", None, "lista"),
            ("123", "STJ", "lista"),
            ("123", None, "lista"),
            ("0000123-45.2020.8.26.0100", None, "lista"),
            ("STF RE 1008166", None, "lista"),
            ("RE 7", "STF", "lista"),
        ]
    )
    assert [(e["tribunal"], e["chave"]) for e in entries] == [
        ("STJ", "ARESP:1779343"),
        ("STJ", "RESP:5"),
        ("TJSC", "50114694620228240000"),
        ("TJSC", "20120095374"),
        ("STJ", "REGISTRO:201201234567"),
    ]
    assert entries[0]["origens"] == ["biblioteca", "outra"]
    assert [r["codigo"] for r in refused] == [
        "numero_invalido",
        "tribunal_ausente",
        "tribunal_fora_da_coleta",
        "tribunal_fora_da_coleta",
        "tribunal_fora_da_coleta",
    ]


def test_list_is_a_plain_file_of_any_origin(tmp_path):
    text = tmp_path / "lista.txt"
    text.write_text("﻿# apontados\n\nREsp 1/SP\nSTJ: AREsp 2\n", encoding="utf-8")
    assert [item[0] for item in read_list(text)] == ["REsp 1/SP", "STJ: AREsp 2"]
    as_list = tmp_path / "lista.json"
    as_list.write_text(json.dumps(["REsp 1/SP", {"numero": "2", "tribunal": "STJ"}]), encoding="utf-8")
    assert read_list(as_list) == [("REsp 1/SP", None, "lista"), ("2", "STJ", "lista")]
    as_object = tmp_path / "objeto.json"
    as_object.write_text(json.dumps({"itens": [{"numero": "REsp 1", "origem": "x"}]}), encoding="utf-8")
    assert read_list(as_object) == [("REsp 1", None, "x")]
    broken = tmp_path / "quebrada.json"
    broken.write_text('{"itens": 1}', encoding="utf-8")
    with pytest.raises(FloraError):
        read_list(broken)


def mirror(id, process, class_name="REsp", registration=None, **changes):
    return raw_doc(
        id=id,
        numeroProcesso=str(process),
        siglaClasse=class_name,
        numeroRegistro=registration or f"2020{int(process):08d}",
        text=f"Ementa do espelho {id} sobre tema{id}.",
        **changes,
    )


def zipped(members: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, records in members.items():
            archive.writestr(name, json.dumps(records))
    return buffer.getvalue()


class Source:
    """The catalog and the files of the open data, through a mock transport."""

    def __init__(self, files: dict[str, dict[str, bytes]]):
        self.files = files
        self.broken = set()
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path.endswith("package_list"):
            return httpx.Response(200, json={"success": True, "result": [*self.files, "pautas-futuras"]})
        if path.endswith("package_show"):
            dataset = request.url.params["id"]
            resources = [
                {
                    "id": f"id-{name}",
                    "name": name,
                    "url": f"{BASE}/{dataset}/{name}",
                    "last_modified": "2026-01-01",
                }
                for name in self.files[dataset]
            ]
            resources.append({"id": "d", "name": "dicionario.csv", "url": f"{BASE}/d.csv"})
            package = {"resources": resources, "license_id": "cc-by", "metadata_modified": "2026-10-29"}
            return httpx.Response(200, json={"success": True, "result": package})
        _, dataset, name = path.split("/")
        if name in self.broken:
            return httpx.Response(404)
        return httpx.Response(200, content=self.files[dataset][name])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


MONTHLY = [
    mirror("10", 100),
    mirror("11", 100, "AgInt no REsp"),
    mirror("12", 100, "AREsp", registration="202100000012"),
    mirror("13", 200),
]
HISTORY = {
    "20101231.json": [mirror("20", 300, "AgRg no AREsp"), mirror("21", 301, "REsp")],
    "20220508.json": [mirror("22", 301, "EDcl no REsp")],
}


@pytest.fixture
def source():
    return Source(
        {
            DATASET: {
                "20220508.zip": zipped(HISTORY),
                "20230131.json": json.dumps(MONTHLY).encode(),
            },
            OTHER: {"20230131.json": json.dumps([mirror("30", 400, "EREsp")]).encode()},
        }
    )


def entries_of(*values):
    entries, refused = merge([(value, "STJ", "teste") for value in values])
    assert not refused
    return entries


def collect(store, source, *values, scope=None):
    with source.client() as http:
        return collect_selection(
            Config(store.directory, request_delay=0), store, http, entries_of(*values), scope
        )


def current_ids(store):
    with connection(store.path) as db:
        return {r[0] for r in db.execute("SELECT id FROM documents")}


def indexed_ids(store):
    with connection(store.path) as db:
        return {r[0] for r in db.execute("SELECT id FROM search")}


def test_mirror_datasets_come_from_the_catalog(source):
    with source.client() as http:
        assert mirror_datasets(http) == [OTHER, DATASET]


def test_selection_loads_the_process_and_keeps_the_whole_file(store, source):
    report = collect(store, source, "AgInt no REsp 100/SP", "REsp 999", "AgRg no AREsp 300")
    assert report["status"] == "ok"
    assert report["varredura_completa"] is True
    # The AREsp with the same number is another process; the AgInt is the same one.
    expected = {"STJ:10", "STJ:11", "STJ:20"}
    assert current_ids(store) == expected
    assert indexed_ids(store) == expected
    assert [e["numero"] for e in report["nao_oferecidos"]] == ["REsp 999"]
    assert [e["chave"] for e in report["selecionados"]] == ["RESP:100", "ARESP:300"]
    monthly = source.files[DATASET]["20230131.json"]
    history = source.files[DATASET]["20220508.zip"]
    assert {f["sha256"] for f in report["arquivos_guardados"]} == {digest(monthly), digest(history)}
    assert {d["sha256_arquivo"] for e in report["selecionados"] for d in e["documentos"]} == {
        digest(monthly),
        digest(history),
    }
    # Every file read leaves its hash, including the one with nothing selected.
    assert len(report["arquivos_varridos"]) == 3
    assert sum(f["registros"] for f in report["arquivos_varridos"]) == 8
    with connection(store.path) as db:
        rows = db.execute("SELECT name,raw_path,sha256,count,dataset FROM resources ORDER BY name").fetchall()
    assert [(r["name"], r["count"], r["dataset"]) for r in rows] == [
        ("20220508.zip", 1, STJ_SELECAO),
        ("20230131.json", 2, STJ_SELECAO),
    ]
    assert rows[0]["raw_path"].endswith(".zip")
    assert (store.directory / rows[0]["raw_path"]).read_bytes() == history
    assert (store.directory / rows[1]["raw_path"]).read_bytes() == monthly


def test_selection_is_found_by_registration_and_embargos_by_the_appeal(store, source):
    report = collect(store, source, "202100000012", "REsp 400")
    assert current_ids(store) == {"STJ:12", "STJ:30"}
    assert not report["nao_oferecidos"]


def test_second_list_adds_to_the_file_and_the_same_list_changes_nothing(store, source):
    collect(store, source, "REsp 100")
    assert current_ids(store) == {"STJ:10", "STJ:11"}
    report = collect(store, source, "REsp 200")
    assert current_ids(store) == {"STJ:10", "STJ:11", "STJ:13"}
    assert report["arquivos_guardados"][0]["novos"] == 1
    assert report["arquivos_guardados"][0]["removidos"] == 0
    with connection(store.path) as db:
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
    again = collect(store, source, "REsp 200")
    assert again["arquivos_guardados"] == []
    assert [e["chave"] for e in again["selecionados"]] == ["RESP:200"]
    with connection(store.path) as db:
        assert db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0] == revision


def test_absence_needs_a_complete_reading(store, source):
    narrowed = collect(store, source, "REsp 999", scope={"desde": "20230101"})
    assert narrowed["varredura_completa"] is False
    assert "nao_oferecidos" not in narrowed
    assert [e["numero"] for e in narrowed["nao_localizados_no_recorte"]] == ["REsp 999"]
    assert len(narrowed["arquivos_varridos"]) == 2
    source.broken.add("20220508.zip")
    failed = collect(store, source, "REsp 999", "REsp 100")
    assert failed["status"] == "error"
    assert failed["falhas"][0]["arquivo"] == "20220508.zip"
    assert "nao_oferecidos" not in failed
    assert [e["numero"] for e in failed["nao_localizados_no_recorte"]] == ["REsp 999"]
    # What the other files held still loaded.
    assert current_ids(store) == {"STJ:10", "STJ:11"}


def test_offered_but_defective_is_not_absent(store):
    broken = [mirror("40", 500, nomeOrgaoJulgador=""), mirror("41", 501)]
    source = Source({DATASET: {"20230131.json": json.dumps(broken).encode()}})
    report = collect(store, source, "REsp 500", "REsp 501")
    assert current_ids(store) == {"STJ:41"}
    assert [e["numero"] for e in report["nao_oferecidos"]] == []
    assert [e["chave"] for e in report["oferecidos_com_defeito"]] == ["RESP:500"]
    with connection(store.path) as db:
        rejected = json.loads(db.execute("SELECT rejeitados FROM resources").fetchone()[0])
    assert rejected[0]["id"] == "40"


def test_acordao_of_the_current_collection_stays_where_it_is(store, source):
    ingest(store, [mirror("10", 100)], resource_id="corrente")
    with connection(store.path) as db:
        before = db.execute("SELECT resource_id,body FROM documents WHERE id='STJ:10'").fetchone()
    report = collect(store, source, "REsp 100")
    notes = {d["id"]: d["na_coleta_corrente"] for d in report["selecionados"][0]["documentos"]}
    assert notes == {"STJ:10": True, "STJ:11": False}
    with connection(store.path) as db:
        after = db.execute("SELECT resource_id,body FROM documents WHERE id='STJ:10'").fetchone()
    assert tuple(after) == tuple(before)
    assert current_ids(store) == {"STJ:10", "STJ:11"}


def test_later_member_of_the_zip_stands_and_the_conflict_is_reported(store):
    old, new = mirror("50", 600), {**mirror("50", 600), "ementa": "Ementa corrigida."}
    content = zipped({"20101231.json": [old], "20220508.json": [new]})
    source = Source({DATASET: {"20220508.zip": content}})
    report = collect(store, source, "REsp 600")
    assert report["arquivos_varridos"][0]["conflitos"] == [
        {"id": "50", "membro": "20220508.json", "posicao": 0}
    ]
    with connection(store.path) as db:
        body = json.loads(db.execute("SELECT body FROM documents").fetchone()[0])
    assert body["ementa"] == "Ementa corrigida."


def test_selection_does_not_count_as_update_and_shows_as_stj(store, source):
    collect(store, source, "REsp 100")
    coverage = coverage_report(store)
    assert coverage["coleta"]["STJ"]["ultima_coleta_ok"] is None
    assert tribunal_for(STJ_SELECAO) == "STJ"
    with connection(store.path) as db:
        detail = json.loads(db.execute("SELECT detail FROM runs").fetchone()[0])
    assert "arquivos_varridos" not in detail
    assert detail["arquivos_lidos"] == 3


def test_publication_serves_only_the_selection_and_backup_restores_the_zip(store, source, tmp_path):
    collect(store, source, "AgRg no AREsp 300")
    assert publish(store)["status"] == "ok"
    found = search(store, "tema20")
    assert [item["id"] for item in found["resultados"]] == ["STJ:20"]
    assert search(store, "tema21")["resultados"] == []
    root = tmp_path / "bk"
    saved = backups.create(store, root, "teste")
    restored = backups.restore(root, Path(saved["destino"]).name, tmp_path / "volta")
    assert restored["originais"] == 1
    kept = next((tmp_path / "volta" / "raw").rglob("*.zip"))
    assert kept.read_bytes() == source.files[DATASET]["20220508.zip"]


def fake_tjsc(results):
    def collect_one(config, store, http, entry, run):
        return {**entry, "registros": results.get(entry["chave"], 0), "orgaos": [], "documentos": []}

    return collect_one


def test_execute_takes_one_list_of_both_courts_with_one_backup_and_receipt(store, source, tmp_path):
    entries, refused = merge(
        [
            ("REsp 100", None, "lista"),
            ("REsp 999", None, "lista"),
            ("5011469-46.2022.8.24.0000", None, "lista"),
            ("123", None, "lista"),
        ]
    )
    report = execute(
        Config(store.directory, request_delay=0),
        store,
        entries,
        refused,
        tmp_path / "recibo.json",
        tmp_path / "bk",
        collect=fake_tjsc({}),
        http_factory=source.client,
    )
    saved = json.loads((tmp_path / "recibo.json").read_text(encoding="utf-8"))
    assert saved["status"] == "ok"
    assert saved["backup"]["status"] == "ok"
    assert [e["numero"] for e in saved["nao_oferecidos"]] == ["5011469-46.2022.8.24.0000"]
    assert saved["stj"]["status"] == "ok"
    assert [e["numero"] for e in saved["stj"]["nao_oferecidos"]] == ["REsp 999"]
    assert [r["numero_informado"] for r in saved["recusados"]] == ["123"]
    assert report["stj"]["selecionados"][0]["chave"] == "RESP:100"
    assert {g["documentos"] for g in saved["depois"]} == {2}
    with connection(store.path) as db:
        assert {r[0] for r in db.execute("SELECT source FROM runs")} == {"STJ-numero", "TJSC-processo"}
    assert len(list((tmp_path / "bk").glob("*-antes-coleta-por-numero"))) == 1
    with pytest.raises(ValueError):
        execute(Config(store.directory), store, entries, refused, tmp_path / "recibo.json", tmp_path / "bk")


def test_plan_reports_what_the_collection_holds(store, source):
    collect(store, source, "REsp 100")
    plan = plan_stj(store, entries_of("EDcl no REsp 100", "REsp 999"))
    assert [item["acordaos_ja_no_acervo"] for item in plan["itens"]] == [2, 0]


def run_cli(capsys, *args):
    cli.main(list(args))
    return json.loads(capsys.readouterr().out)


def test_command_plans_without_network_or_writing_and_asks_only_for_a_list(
    store, tmp_path, capsys, monkeypatch
):
    def no_network(*args, **kwargs):
        raise AssertionError("o plano não usa a rede")

    monkeypatch.setattr("flora_mcp.sources.client", no_network)
    monkeypatch.setattr("flora_mcp.coleta_numeros.client", no_network)
    monkeypatch.delenv("FLORA_MCP_CONFIG", raising=False)
    listing = tmp_path / "qualquer-origem.txt"
    listing.write_text("REsp 100\n5011469-46.2022.8.24.0000\nSúmula 7\n", encoding="utf-8")
    result = run_cli(capsys, "--data-dir", str(store.directory), "coletar-numeros", "--lista", str(listing))
    assert result["status"] == "plano"
    assert result["stj"]["numeros"] == 1
    assert result["tjsc"]["pendentes"] == 1
    assert [r["numero_informado"] for r in result["recusados"]] == ["Súmula 7"]
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


@pytest.mark.parametrize(
    "args,code",
    [
        ([], "lista_vazia"),
        (["--numero", "REsp 1", "--apply"], "recibo_obrigatorio"),
        (["--numero", "REsp 1", "--stj-desde", "2023"], "recorte_invalido"),
    ],
)
def test_command_refuses_incomplete_requests(store, capsys, args, code):
    with pytest.raises(SystemExit):
        cli.main(["--data-dir", str(store.directory), "coletar-numeros", *args])
    assert json.loads(capsys.readouterr().err)["codigo"] == code


def test_family_of_a_nested_class():
    assert stj_family("EDcl no AgRg nos EREsp") == "RESP"
    assert stj_family("AgRg no RE no AgRg no AgRg nos EDcl no REsp") == "RESP"
    assert stj_family("") == ""
