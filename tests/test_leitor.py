import json

from test_contrato import published  # noqa: F401  (fixture: acervo com publicação)
from flora_mcp import api
from flora_mcp.http_server import readable
from flora_mcp.leitor import sincronizar
from flora_mcp.publication import MANIFEST
from flora_mcp.store import Store


def test_reader_copy_serves_the_four_tools_without_work_database(published, tmp_path):  # noqa: F811
    destino = tmp_path / "leitor"
    first = sincronizar(published.directory, destino)
    manifest = json.loads((destino / MANIFEST).read_text(encoding="utf-8"))
    assert first["copiado"] and first["mantidas"] == [manifest["atual"]]
    assert sorted(p.name for p in destino.iterdir()) == ["publicacoes", MANIFEST]
    leitor = Store(destino)
    assert not leitor.path.exists() and readable(leitor)
    busca = api.search(leitor)
    assert busca["resultados"] and busca["publicacao_id"] == manifest["atual"]
    documento = api.document(leitor, busca["resultados"][0]["id"], componente="ementa")
    assert documento["referencia"]
    assert api.search_precedents(leitor)["publicacao_id"] == manifest["atual"]
    assert api.coverage(leitor)["publicacao_id"] == manifest["atual"]
    assert not leitor.path.exists()
    assert sincronizar(published.directory, destino)["copiado"] is False


def test_reader_resolves_manifest_written_with_backslashes(published, tmp_path):  # noqa: F811
    destino = tmp_path / "leitor"
    sincronizar(published.directory, destino)
    path = destino / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for entry in manifest["publicacoes"]:
        entry["arquivo"] = entry["arquivo"].replace("/", "\\")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert api.search(Store(destino))["publicacao_id"] == manifest["atual"]


def test_readable_needs_database_or_manifest(tmp_path):
    assert not readable(Store(tmp_path))
