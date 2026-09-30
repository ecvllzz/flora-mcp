import json

import pytest

from flora_mcp import api
from flora_mcp.model import FloraError, canonical
from flora_mcp.store import connection


def test_default_summary_preserves_diagnostics_and_legacy_detail(store):
    for dataset in ("espelhos-de-acordaos-terceira-turma", "tjsc-9-civil"):
        resources = [{"id": str(i), "name": f"{i:04}.json", "url": "https://example.org/" + str(i)}
                     for i in range(350)]
        store.catalog(dataset, {}, resources)
    run = store.start_run("TJSC")
    detail = {"motivo": "Interrompida pelo operador", "falhas": [{"erro": "Documento sem ementa"}],
              "antes": [{"orgao": "9", "documentos": 10}],
              "depois": [{"orgao": "9", "documentos": 20}],
              "eventos": [{"texto": "x" * 1000}] * 500,
              "janelas": [{"dia": "2026-01-01"}] * 500}
    store.finish_run(run, "interrupted", detail)
    with connection(store.path, write=True) as db, db:
        db.execute("UPDATE resources SET status='error',error='Falha HTTP' WHERE id LIKE '%:0'")
    before = store.coverage()
    result = api.coverage(store)
    assert result["detalhe"] == "resumo"
    assert len(canonical(result)) < 10000
    for key in ("status", "cobertura_integral", "grupos", "catalogos", "inteiros_teores", "tjsc", "limites"):
        assert result[key] == before[key]
    assert sum(r["total"] for r in result["recursos"]) == 700
    for group in result["recursos"]:
        assert group["por_status"] == {"pending": 349, "error": 1}
        assert group["pendentes"] == 350
        assert group["primeiro_lote_pendente"] == "0000.json"
        assert group["ultimo_lote_pendente"] == "0349.json"
        assert group["erros"] == {"Falha HTTP": 1}
    compact = result["execucoes_recentes"][0]
    assert compact["status"] == "interrupted"
    assert compact["detail"] == {k: v for k, v in detail.items() if k not in {"eventos", "janelas"}}
    assert api.coverage(store, "completo") == before
    assert api.coverage(store, "legado") == before
    assert api.coverage(store, "execucoes", limite=1)["itens"][0]["detail"] == detail
    json.dumps(result)  # Counters must remain ordinary JSON objects.


def test_resource_filters_and_cursor_reject_changed_scope(store):
    for dataset in ("tjsc-9-civil", "tjsc-10-civil", "espelhos-de-acordaos-terceira-turma"):
        store.catalog(dataset, {}, [{"id": str(i), "name": f"{i}.json", "url": "https://example.org"}
                                    for i in range(3)])
    first = api.coverage(store, "recursos", limite=2, tribunal="TJSC", dataset="tjsc-9-civil")
    assert first["total"] == 3
    second = api.coverage(store, "recursos", limite=2, tribunal="TJSC", dataset="tjsc-9-civil",
                          cursor=first["proximo_cursor"])
    assert len(second["itens"]) == 1 and second["proximo_cursor"] is None
    assert len({r["name"] for r in first["itens"] + second["itens"]}) == 3
    with pytest.raises(FloraError, match="Cursor de outra"):
        api.coverage(store, "recursos", limite=2, tribunal="STJ", dataset="tjsc-9-civil",
                     cursor=first["proximo_cursor"])
    assert api.coverage(store, "recursos", tribunal="STF")["total"] == 0
    with pytest.raises(FloraError):
        api.coverage(store, tribunal="TJSC")
