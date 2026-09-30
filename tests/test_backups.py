import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from flora_mcp import api, backups
from flora_mcp.model import FloraError
from flora_mcp.store import Store

from conftest import ingest, raw_doc


def depot(root):
    return sorted(p.name for p in (root / "raw").glob("*/*"))


def test_second_backup_copies_only_new_originals(store, tmp_path):
    root = tmp_path / "backups"
    ingest(store, [raw_doc("1")])
    first = backups.create(store, root, "primeiro")
    assert first["originais"] == first["originais_copiados"] == 1
    ingest(store, [raw_doc("1"), raw_doc("2")], name="20260930.json", resource_id="r2")
    second = backups.create(store, root)
    assert second["originais"] == 2
    assert (second["originais_copiados"], second["originais_ja_no_deposito"]) == (1, 1)
    assert len(depot(root)) == 2
    manifest = backups.read_manifest(Path(second["destino"]))
    assert manifest["schema"] == "flora-backup-2" and manifest["rotulo"] is None
    assert {o["sha256"] for o in manifest["originais"]} == set(depot(root))
    assert not list(root.glob(".*.parcial"))


def test_corrupt_original_in_depot_is_detected(store, tmp_path):
    root = tmp_path / "backups"
    ingest(store, [raw_doc("1")])
    backups.create(store, root)
    (root / "raw").glob("*/*").__next__().write_bytes(b"corrompido")
    with pytest.raises(FloraError, match="depósito") as error:
        backups.create(store, root, "segundo")
    assert error.value.code == "deposito_corrompido"
    assert len([p for p in root.iterdir() if p.name != "raw" and p.is_dir()]) == 1
    assert not list(root.glob(".*.parcial"))


def test_backup_root_inside_data_directory_is_refused(store):
    with pytest.raises(FloraError, match="fora"):
        backups.create(store, store.directory / "backups")
    with pytest.raises(FloraError, match="Rótulo"):
        backups.create(store, store.directory.parent / "b", "../fora")


def fake_backup(root, name, when, shas, schema="flora-backup-2"):
    folder = root / name
    folder.mkdir(parents=True)
    manifest = {
        "schema": schema,
        "data": when.isoformat(),
        "originais": [{"caminho": "raw/x/" + s, "sha256": s} for s in shas],
    }
    (folder / "manifesto.json").write_text(json.dumps(manifest), encoding="utf-8")
    for sha in shas:
        (root / "raw" / sha[:2]).mkdir(parents=True, exist_ok=True)
        (root / "raw" / sha[:2] / sha).write_bytes(b"x")


def test_prune_keeps_recent_and_latest_of_each_month(tmp_path):
    root = tmp_path / "backups"
    start = datetime(2026, 7, 20, 15, tzinfo=timezone.utc)
    names = []
    for day in range(0, 70, 5):  # 14 backups from 20/07 to 22/09
        name = f"b{day:02}"
        fake_backup(root, name, start + timedelta(days=day), [f"{day:02}" + "a" * 62, "f" * 64])
        names.append(name)
    old = root / "antes-migracao-20260929"
    (old / "raw").mkdir(parents=True)
    (old / "acervo.sqlite").write_bytes(b"antigo")
    plan = backups.prune(root, 5)
    kept = {b["nome"]: b["motivos"] for b in plan["manter"]}
    # 5 most recent (b65..b45), plus the latest of July (b10) and August (b40).
    assert set(kept) == {"b65", "b60", "b55", "b50", "b45", "b40", "b10"}
    assert kept["b10"] == ["mes 2026-07"] and kept["b65"] == ["recentes", "mes 2026-09"]
    assert plan["fora_da_poda"] == [{"nome": old.name, "motivo": "formato antigo, fora da poda"}]
    assert plan["aplicado"] is False and plan["deposito"]["orfaos"] == 7
    assert all((root / n).exists() for n in names)
    applied = backups.prune(root, 5, apply=True)
    assert applied["apagar"] == plan["apagar"]
    remaining = {p.name for p in root.iterdir()} - {"backups.lock"}
    assert remaining == set(kept) | {"raw", old.name}
    assert (old / "acervo.sqlite").read_bytes() == b"antigo"
    referenced = {o["sha256"] for n in kept for o in backups.read_manifest(root / n)["originais"]}
    assert set(depot(root)) == referenced
    assert backups.prune(root, 5)["deposito"]["orfaos"] == 0


def test_prune_never_touches_folder_with_other_manifest(tmp_path):
    root = tmp_path / "backups"
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for i in range(3):
        fake_backup(root, f"n{i}", when + timedelta(hours=i), ["a" * 64])
    fake_backup(root, "outro", when, ["b" * 64], schema="flora-backup-1")
    (root / ".20260901-000000-000000.parcial").mkdir()
    result = backups.prune(root, 1, apply=True)
    assert [b["nome"] for b in result["manter"]] == ["n2"]
    assert [b["motivo"] for b in result["fora_da_poda"]] == [
        "backup interrompido, fora da poda",
        "formato antigo, fora da poda",
    ]
    assert (root / "outro").is_dir() and (root / ".20260901-000000-000000.parcial").is_dir()
    # Only new-format manifests hold depot files; other folders carry their own originals.
    assert depot(root) == ["a" * 64]


def test_restore_answers_like_the_original(store, tmp_path):
    root = tmp_path / "backups"
    ingest(store, [raw_doc("1"), raw_doc("2", "Guarda compartilhada. Alimentos.")])
    ingest(
        store, [raw_doc("2", "Guarda compartilhada. Alimentos revistos.")], "20260930.json", resource_id="r2"
    )
    name = Path(backups.create(store, root, "teste")["destino"]).name
    target = tmp_path / "restaurado"
    result = backups.restore(root, name, target)
    assert result["originais"] == 2
    restored = Store(target)
    assert api.search(restored, "alimentos") == api.search(store, "alimentos")
    for component in ("ementa", "espelho_original"):
        assert api.document(restored, "STJ:2", component) == api.document(store, "STJ:2", component)
    with pytest.raises(FloraError, match="já existe"):
        backups.restore(root, name, target)


def test_restore_detects_corrupt_depot_and_leaves_nothing(store, tmp_path):
    root = tmp_path / "backups"
    ingest(store, [raw_doc("1")])
    name = Path(backups.create(store, root)["destino"]).name
    next((root / "raw").glob("*/*")).write_bytes(b"corrompido")
    with pytest.raises(FloraError) as error:
        backups.restore(root, name, tmp_path / "restaurado")
    assert error.value.code == "deposito_corrompido"
    assert not (tmp_path / "restaurado").exists()
    with pytest.raises(FloraError, match="subpasta"):
        backups.restore(root, "../fora", tmp_path / "outro")
