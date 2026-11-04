"""Official situation catalog of the STJ themes and IAC, from the preserved temas.csv.

The precedent collection serves only what was admitted; a theme the source cancelled, revised or
has not judged yet is left out, and until now the reader could not tell "cancelado segundo a
fonte" from "não carregado". The catalog lists every theme of the latest temas.csv preserved as
an original of a precedent (admitted or not), with the situation as the source writes it. It
admits nothing and serves no thesis: only the number, the situation and where the row came from.
"""

import io
import json
import re

from .model import digest
from .precedent_sources import structured_url
from .precedent_sources.stj_temas import SITUACOES, TIPOS

CATALOG_DERIVER = "catalogo-temas-1"
TABLE = "theme_catalog"
NOTA = "Não servido nesta base: só precedentes admitidos são servidos, e a tese não é fornecida."
SCHEMA = (
    f"CREATE TABLE {TABLE}(id TEXT PRIMARY KEY,especie TEXT NOT NULL,numero TEXT NOT NULL,"
    "situacao_fonte TEXT NOT NULL,situacao TEXT NOT NULL,fonte_url TEXT NOT NULL,fonte_sha256 TEXT NOT NULL,"
    "coletado_em TEXT NOT NULL,linha INTEGER NOT NULL)"
)


def latest_theme_source(dest) -> dict | None:
    """The most recently collected temas.csv among the sources of the precedents in the generation."""
    latest = None
    if not dest.execute("SELECT 1 FROM sqlite_master WHERE name='precedent_versions'").fetchone():
        return None
    for (body,) in dest.execute("SELECT body FROM precedent_versions"):
        for source in json.loads(body).get("fontes", []):
            if structured_url(source.get("url", "")) != "stj_temas" or not source["url"].endswith(
                "temas.csv"
            ):
                continue
            if latest is None or source["coletado_em"] > latest["coletado_em"]:
                latest = source
    return latest


def catalog_rows(content: bytes, source: dict) -> list[tuple]:
    """One row per theme or IAC of the CSV; a theme repeated with another situation keeps both, joined."""
    import csv

    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    found = {}
    for index, row in enumerate(reader):
        kind = row.get("tipoPrecedente", "").strip()
        number = row.get("numeroPrecedente", "").strip()
        if kind not in TIPOS or not re.fullmatch(r"[1-9][0-9]{0,6}", number):
            continue
        id = f"STJ:{TIPOS[kind]}:{number}"
        stated = row.get("situacao", "").strip()
        if id in found:
            if stated not in found[id][3].split(" | "):
                found[id][3] += " | " + stated
                found[id][4] = "desconhecido"
            continue
        status = SITUACOES.get(stated, ("desconhecido", None))[0]
        found[id] = [
            id,
            TIPOS[kind],
            number,
            stated,
            status,
            source["url"],
            source["sha256"],
            source["coletado_em"],
            index + 2,
        ]
    return [tuple(v) for v in found.values()]


def derive_theme_catalog(store, dest) -> dict:
    """Create and fill theme_catalog from the preserved original; empty when no temas.csv was preserved."""
    dest.execute(SCHEMA)
    source = latest_theme_source(dest)
    if source is None:
        return {"temas": 0, "fonte": None}
    path = (store.directory / source["raw_path"]).resolve()
    content = path.read_bytes()
    if digest(content) != source["sha256"]:
        raise ValueError("Original de temas.csv não confere com o hash registrado.")
    rows = catalog_rows(content, source)
    dest.executemany(f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?)", rows)
    situations = dict(dest.execute(f"SELECT situacao_fonte,count(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC"))
    return {
        "temas": len(rows),
        "fonte": {"url": source["url"], "sha256": source["sha256"], "coletado_em": source["coletado_em"]},
        "por_situacao": situations,
    }


def has_catalog(db) -> bool:
    """A generation carries the catalog when the table exists and has rows: an empty one proves nothing."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
        return False
    return bool(db.execute(f"SELECT 1 FROM {TABLE} LIMIT 1").fetchone())


def catalog_entries(db, ids) -> dict:
    """{id: row} for the ids the catalog has; empty without a catalog."""
    ids = [i for i in ids if isinstance(i, str) and i.startswith("STJ:")]
    if not ids or not has_catalog(db):
        return {}
    marks = ",".join("?" * len(ids))
    return {r["id"]: dict(r) for r in db.execute(f"SELECT * FROM {TABLE} WHERE id IN ({marks})", ids)}


def catalog_lookup(db, tribunal, especie, params) -> list[dict]:
    """Rows of the catalog that a search by number could mean, for the empty page.

    ``params`` are the exact filters of the search plan; the number is the value that follows the
    species or the organ, so it is read from the plan's own values, never guessed from the text.
    """
    if tribunal not in {None, "STJ"} or not has_catalog(db):
        return []
    numbers = [p for p in params if isinstance(p, str) and re.fullmatch(r"[1-9][0-9]{0,6}", p)]
    species = [especie] if especie else list(TIPOS.values())
    ids = [f"STJ:{s}:{n}" for n in numbers for s in species if s in TIPOS.values()]
    return [
        {
            "id": e["id"],
            "numero": e["numero"],
            "situacao_fonte": e["situacao_fonte"],
            "situacao": e["situacao"],
            "fonte": e["fonte_url"],
            "coletado_em": e["coletado_em"],
            "nota": NOTA,
        }
        for e in catalog_entries(db, ids).values()
    ]
