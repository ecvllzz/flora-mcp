import json

import pytest

from conftest import ingest, raw_doc
from flora_mcp import api
from flora_mcp.export import export_documents
from flora_mcp.model import FloraError, canonical, digest
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import Reader, publish
from flora_mcp.store import connection


def packet(
    tmp_path,
    *,
    status="vigente",
    number="999999",
    text="Enunciado sintético para teste. " * 30,
    pending=None,
    species="sumula",
):
    raw = "FONTE SINTÉTICA DE TESTE, NÃO É PRECEDENTE REAL. " + status + text
    source = tmp_path / "fonte.txt"
    source.write_text(raw, encoding="utf-8")
    sha = digest(raw.encode())
    component = "enunciado" if species == "sumula" else "tese_firmada"
    evidence = {
        k: {"fonte_sha256": sha, "trecho": raw, "localizador": "fixture integral"}
        for k in ("situacao", "publicacao", "materia", "componente:" + component)
    }
    record = {
        "tribunal": "STJ",
        "especie": species,
        "numero": number,
        "orgao": "Órgão de teste",
        "data_publicacao": "2026-09-01",
        "materia": "civil",
        "situacao": status,
        "tipo_publicacao": "enunciado" if species == "sumula" else "acordao_merito",
        "pendencias": pending or [],
        "componentes": {component: text},
        "fontes": [
            {
                "url": "https://www.stj.jus.br/fixture",
                "sha256": sha,
                "arquivo": "fonte.txt",
                "coletado_em": "2026-09-29T12:00:00-03:00",
            }
        ],
        "evidencias": evidence,
        "conferencia": {
            "evidencias_conferidas": True,
            "responsavel": "teste automatizado",
            "data": "2026-09-29",
        },
    }
    package = tmp_path / "pacote.json"
    package.write_text(canonical({"schema": "flora-precedentes-1", "registros": [record]}), encoding="utf-8")
    return package


def test_migration_preserves_legacy_and_is_idempotent(store, tmp_path):
    ingest(store, [raw_doc()])
    before = api.search(store)
    assert migrate(store)["alterado"] is True
    assert migrate(store)["alterado"] is False
    after = api.search(store)
    assert after["resultados"] == before["resultados"]
    assert after["ementas_completas"] is True
    store.initialize()  # Existing collection commands remain compatible with schema 2.


def test_import_requires_bytes_and_explicit_review(store, tmp_path):
    migrate(store)
    path = packet(tmp_path)
    report = import_package(store, path)
    assert report["registros"][0]["admissao"] == "admitido"
    assert api.search(store, colecao="precedentes", campo="todos")["total_encontrado"] == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    data["registros"][0].pop("conferencia")
    path.write_text(canonical(data), encoding="utf-8")
    assert import_package(store, path, apply=True)["registros"][0]["admissao"] == "pendente"
    assert api.search(store, colecao="precedentes", campo="todos")["total_encontrado"] == 0
    (tmp_path / "fonte.txt").write_text("adulterado", encoding="utf-8")
    with pytest.raises(FloraError, match="hash"):
        import_package(store, path, apply=True)


def test_components_reference_literal_pagination_and_idempotence(store, tmp_path):
    migrate(store)
    path = packet(tmp_path)
    assert import_package(store, path, apply=True)["alterado"]
    assert not import_package(store, path, apply=True)["alterado"]
    result = api.search(store, "enunciado", colecao="precedentes", campo="enunciado", detalhe="triagem")
    item = result["resultados"][0]
    assert item["referencia_completa"]
    assert item["campos_correspondentes"] == ["enunciado"]
    assert len(canonical(result).encode()) <= 8192
    with pytest.raises(FloraError, match="Componentes disponíveis: enunciado"):
        api.document(store, item["id"])
    cursor, blocks = None, []
    while True:
        doc = api.document(store, item["id"], "enunciado", cursor, 100)
        assert doc["metadados"]["referencia"] == item["referencia"]
        blocks.append(doc["texto"])
        cursor = doc["proximo_cursor"]
        if not cursor:
            break
    assert "".join(blocks) == "Enunciado sintético para teste. " * 30


@pytest.mark.parametrize(
    "status,pending,admission",
    [
        ("cancelado", [], "excluido"),
        ("suspenso", [], "excluido"),
        ("vigente", ["recurso_pendente"], "pendente"),
    ],
)
def test_withdrawal_overrides_snapshot_and_old_hash(store, tmp_path, status, pending, admission):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    publication = publish(store)["publicacao_id"]
    before = api.document(store, "STJ:sumula:999999", "enunciado", tamanho_bloco=100)
    receipt = import_package(store, packet(tmp_path, status=status, pending=pending), apply=True)
    assert receipt["registros"][0]["admissao"] == admission
    assert (
        api.search(store, colecao="precedentes", campo="todos", publicacao_id=publication)["total_encontrado"]
        == 0
    )
    for params in (
        {"publicacao_id": publication},
        {"cursor": before["proximo_cursor"]},
        {"hash_conteudo": before["hash_conteudo"]},
    ):
        with pytest.raises(FloraError, match="retirado"):
            api.document(store, "STJ:sumula:999999", "enunciado", **params)
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM precedent_versions").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM precedent_texts").fetchone()[0] == 0


def test_generations_pagination_integrity_and_retention(store, tmp_path):
    ingest(store, [raw_doc(str(i)) for i in range(5)])
    migrate(store)
    first = publish(store)["publicacao_id"]
    page = api.search(store, limite=2)
    old_reader = Reader(store).resolve()
    with old_reader.read() as opened:
        ingest(store, [raw_doc(str(i)) for i in range(7)])
        publish(store)
        assert opened.execute("SELECT count(*) FROM documents").fetchone()[0] == 5
        assert api.search(store, limite=2, cursor=page["proximo_cursor"])["publicacao_id"] == first
    for i in range(2):
        ingest(store, [raw_doc(str(j), text=str(i)) for j in range(7)])
        publish(store)
    with pytest.raises(FloraError, match="Publicação retirada"):
        api.search(store, publicacao_id=first)
    target = Reader(store).resolve().path
    with target.open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(FloraError, match="inválido"):
        api.search(store)


def test_ordinary_triage_and_summary_are_opt_in(store):
    ingest(store, [raw_doc(str(i), text="Árvore e proteção. " * 3000) for i in range(10)])
    assert len(api.search(store)["resultados"]) == 3
    triage = api.search(store, detalhe="triagem")
    assert 1 <= len(triage["resultados"]) <= 8
    assert len(canonical(triage).encode()) <= 8192
    assert all(item["trecho_parcial"] for item in triage["resultados"])
    assert "recursos" in api.coverage(store)
    assert len(canonical(api.coverage(store, "resumo")).encode()) < 10000


def test_export_identity_literal_conflict_and_withdrawal(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    publish(store)
    target = tmp_path / "export"
    report = export_documents(store, target)
    assert report["documentos"] == 1
    assert export_documents(store, target)["alterado"] is False
    catalog = json.loads((target / "catalogo.json").read_text(encoding="utf-8"))
    path = target / catalog["registros"][0]["arquivo"]
    original = path.read_bytes()
    assert "Enunciado sintético para teste. " * 30 in original.decode()
    path.write_text("edição humana", encoding="utf-8")
    with pytest.raises(FloraError, match="alterado"):
        export_documents(store, target)
    path.write_bytes(original)
    import_package(store, packet(tmp_path, status="revogado"), apply=True)
    publish(store)
    assert export_documents(store, target)["retirados"] == ["STJ:sumula:999999"]
    assert not path.exists()


def test_panel_and_api_share_published_precedents(store, tmp_path):
    from starlette.testclient import TestClient
    from flora_mcp.panel import create_panel_app

    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    publish(store)
    values = {"colecao": "precedentes", "campo": "todos"}
    with TestClient(create_panel_app(store), base_url="http://127.0.0.1:8766") as browser:
        assert browser.post("/api/search", json=values).json() == api.search(store, **values, limite=5)
        assert browser.get("/api/catalog").json()["precedentes"][0]["documentos"] == 1


def test_search_components_and_cursor_filters(store, tmp_path):
    migrate(store)
    import_package(store, packet(tmp_path, species="tema_repetitivo", text="Tese sintética"), apply=True)
    assert api.search(store, "sintética", colecao="precedentes", campo="enunciado")["total_encontrado"] == 0
    result = api.search(
        store,
        "sintética",
        colecao="precedentes",
        campo="tese_firmada",
        ordenar="relevancia",
        detalhe="triagem",
    )
    assert result["resultados"][0]["campos_correspondentes"] == ["tese_firmada"]
    assert result["resultados"][0]["trecho"] == "Tese sintética"


def test_incomplete_observation_preserves_last_state_and_readmission_does_not_revive_retired_version(
    store, tmp_path
):
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    old = publish(store)["publicacao_id"]
    path = packet(tmp_path, status="desconhecido")
    assert import_package(store, path, apply=True)["registros"][0]["estado_anterior_conservado"]
    assert api.search(store, colecao="precedentes", campo="todos")["total_encontrado"] == 1
    import_package(store, packet(tmp_path, status="cancelado"), apply=True)
    import_package(store, packet(tmp_path, text="Nova versão admitida com fonte revista"), apply=True)
    publish(store)
    assert api.search(store, colecao="precedentes", campo="todos")["total_encontrado"] == 1
    assert api.search(store, colecao="precedentes", campo="todos", publicacao_id=old)["total_encontrado"] == 0
    with pytest.raises(FloraError, match="Versão retirada"):
        api.document(store, "STJ:sumula:999999", "enunciado", publicacao_id=old)


def test_opt_in_grammar_preserves_filters_and_phrases(store):
    ingest(
        store,
        [
            raw_doc("1", text="Dano moral e alimentos", ministroRelator="LÚCIA"),
            raw_doc("2", text="Danos materiais e alimentos", ministroRelator="OUTRA"),
            raw_doc("3", text="Danos morais e guarda", ministroRelator="LÚCIA"),
        ],
    )
    expression = 'alimentos AND ("dano moral" OR materiais)'
    assert api.search(store, expression)["total_encontrado"] == 0
    assert api.search(store, expression, modo_busca="avancado")["total_encontrado"] == 2
    publish(store)
    assert api.search(store, expression, modo_busca="avancado", relator="lucia")["total_encontrado"] == 1
    assert api.search(store, "dan* AND guarda", modo_busca="avancado")["total_encontrado"] == 1
    for bad in ("AND teste", "(dano OR )", "*", "(dano", "dano)", "dano AND", "a***"):
        with pytest.raises(FloraError):
            api.search(store, bad, modo_busca="avancado")


def test_literal_sections_have_original_unicode_offsets_and_no_qualified_thesis(store):
    text = "Árvore.\nI. CASO EM EXAME\nFatos.\nII. QUESTÃO EM DISCUSSÃO\nQuestão.\nIV. DISPOSITIVO E TESE\nConclusão.\nTese de julgamento: texto local."
    ingest(store, [raw_doc(text=text)])
    full = api.document(store, "STJ:1")
    assert full["texto"] == text
    for section in full["metadados"]["secoes_ementa"]:
        part = api.document(store, "STJ:1", "secao:" + section["nome"])
        assert part["texto"] == text[section["inicio"] : section["fim"]]
    assert api.search(store, colecao="precedentes", campo="todos")["total_encontrado"] == 0


def test_qualified_contract_over_real_stdio(store, tmp_path):
    import asyncio
    import os
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    publish(store)

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "flora_mcp.cli", "--data-dir", str(store.directory), "serve"],
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                found = await session.call_tool(
                    "pesquisar_jurisprudencia",
                    {"colecao": "precedentes", "campo": "todos", "detalhe": "triagem"},
                )
                result = found.structured_content
                assert len(canonical(result).encode()) <= 8192
                item = result["resultados"][0]
                doc = await session.call_tool(
                    "obter_documento",
                    {
                        "id": item["id"],
                        "componente": "enunciado",
                        "hash_conteudo": item["hash_conteudo"],
                        "publicacao_id": result["publicacao_id"],
                    },
                )
                assert doc.structured_content["texto"] == "Enunciado sintético para teste. " * 30
                summary = await session.call_tool("consultar_cobertura", {"detalhe": "resumo"})
                assert summary.structured_content["precedentes"][0]["documentos"] == 1

    asyncio.run(exercise())
