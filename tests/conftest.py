import json

import pytest

from flora_mcp.model import normalize_stj
from flora_mcp.store import Store


def raw_doc(id="1", text="Alimentos. Proteção à criança.", **changes):
    return {
        "id": id,
        "numeroProcesso": "1234567",
        "numeroRegistro": "202500012345",
        "siglaClasse": "REsp",
        "nomeOrgaoJulgador": "TERCEIRA TURMA",
        "dataDecisao": "20260824",
        "dataPublicacao": "DJEN DATA:01/09/2026",
        "ementa": text,
        "notas": "",
        **changes,
    }


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "data")
    value.initialize()
    return value


def ingest(store, docs, name="20260831.json", modified="2026-09-08", resource_id="r1"):
    dataset = "fixture"
    resource = {
        "id": resource_id,
        "name": name,
        "last_modified": modified,
        "url": "https://dadosabertos.web.stj.jus.br/fixture/" + name,
    }
    store.catalog(dataset, {"license_id": "cc-by", "resources": [resource]}, [resource])
    saved = next(r for r in store.resources(dataset) if r["id"] == dataset + ":" + resource_id)
    return store.ingest(saved, json.dumps(docs).encode(), [(normalize_stj(d), d) for d in docs], "test")
