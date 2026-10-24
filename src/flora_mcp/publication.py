"""Immutable SQLite generations; a small atomic manifest selects the active one."""

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path, PureWindowsPath

from .model import FloraError, canonical, digest, folded, now
from .citation import citation_metadata
from .precedents import available
from .citations import CITATIONS_DERIVER, extract
from .text import SECTIONS_DERIVER
from .store import ReadView, Store, connection, replace_search_row

COPIES_DERIVER = "copias-texto-1"
# Derivations computed when a generation is read also name the generation, so changing one of them
# changes publicacao_id at the next publication.
DERIVER = f"flora-read-2.3;{SECTIONS_DERIVER};{CITATIONS_DERIVER};{COPIES_DERIVER}"
MANIFEST = "publicacoes.json"


def entry_path(entry) -> Path:
    """Relative path of a generation, whatever the separator of the system that wrote the manifest."""
    return Path(*PureWindowsPath(entry["arquivo"]).parts)


def file_digest(path) -> str:
    """SHA-256 read in chunks: a generation has hundreds of MB and the reader may run on a small host."""
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def precedent_state(dest) -> tuple[list, dict, list]:
    """Withdrawn ids, admission counts and retired versions recorded in the snapshot."""
    if not available(dest):
        return [], {}, []
    withdrawn = [r[0] for r in dest.execute("SELECT id FROM precedents WHERE admission!='admitido'")]
    admission_counts = dict(dest.execute("SELECT admission,count(*) FROM precedents GROUP BY admission"))
    retired_versions = [r[0] + ":" + r[1] for r in dest.execute("SELECT id,hash FROM precedent_retirements")]
    return withdrawn, admission_counts, retired_versions


def verify_originals(store: Store, dest):
    """Every preserved original cited by a resource or an admitted precedent matches its hash."""
    originals = [
        (r[0], r[1]) for r in dest.execute("SELECT raw_path,sha256 FROM resources WHERE raw_path IS NOT NULL")
    ]
    if available(dest):
        for (raw,) in dest.execute("SELECT body FROM precedents WHERE admission='admitido'"):
            originals += [(s["raw_path"], s["sha256"]) for s in json.loads(raw)["fontes"]]
    for relative, expected in set(originals):
        path = (store.directory / relative).resolve()
        if not path.is_relative_to(store.directory.resolve()) or digest(path.read_bytes()) != expected:
            raise FloraError("publicacao_invalida", "Original não confere com o hash registrado.")


def verify_search_index(dest):
    dest.execute("INSERT INTO search(search) VALUES ('integrity-check')")
    if (
        dest.execute("SELECT count(*) FROM documents").fetchone()[0]
        != dest.execute("SELECT count(*) FROM search").fetchone()[0]
    ):
        raise FloraError("publicacao_invalida", "Índice de acórdãos diverge do conteúdo.")


def prune_snapshot(dest):
    # Preserve only originals needed for current citations. Audit remains in the work database.
    dest.execute("DELETE FROM observations")
    dest.execute("DELETE FROM version_origins")
    dest.execute("DELETE FROM resource_history")
    dest.execute(
        "DELETE FROM versions WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.id=document_id AND "
        "d.hash=versions.hash)"
    )


def text_key(ementa: str) -> str | None:
    """Ementa without punctuation, spaces, accents or case; None when nothing is left to compare."""
    letters = re.sub(r"\W+", "", folded(ementa or ""))
    return digest(letters.encode()) if letters else None


def plan_text_copies(rows) -> dict:
    """{kept id: [copies]} over (id, body) rows: the first id of each text stays, the others are copies."""
    first, copies = {}, {}
    for id, body in sorted(rows, key=lambda r: r[0]):
        key = text_key(body.get("ementa"))
        if key is None:
            continue
        if key not in first:
            first[key] = id
            continue
        copies.setdefault(first[key], []).append(
            {
                "id": id,
                "processo": body.get("processo"),
                "orgao": body.get("orgao"),
                "data_julgamento": body.get("data_julgamento"),
            }
        )
    return copies


def with_copies(body: dict, copies: list | None) -> dict:
    return {**body, "copias_texto": copies} if copies else body


def remove_text_copies(dest) -> dict:
    """Acórdãos whose ementa repeats an earlier one leave the generation; the first lists them.

    The work database keeps every acórdão, its original and provenance; only the reader stops
    serving the copy, which competed for the first places of a search with the same text.
    """
    copies = plan_text_copies((r[0], json.loads(r[1])) for r in dest.execute("SELECT id,body FROM documents"))
    for kept, items in copies.items():
        body = json.loads(dest.execute("SELECT body FROM documents WHERE id=?", (kept,)).fetchone()[0])
        dest.execute("UPDATE documents SET body=? WHERE id=?", (canonical(with_copies(body, items)), kept))
        for item in items:
            dest.execute("DELETE FROM documents WHERE id=?", (item["id"],))
            replace_search_row(dest, item["id"], None)
    return {"grupos": len(copies), "copias_retiradas": sum(len(v) for v in copies.values())}


def derive_document_details(dest):
    """Derived table with relator and class description, read from the stored raw version."""
    dest.execute(
        "CREATE TABLE document_details(id TEXT PRIMARY KEY,relator TEXT NOT NULL,relator_fold TEXT NOT "
        "NULL,classe_descricao TEXT NOT NULL)"
    )
    derived = []
    for body, raw in dest.execute(
        "SELECT d.body,v.raw FROM documents d JOIN versions v ON v.document_id=d.id AND v.hash=d.hash"
    ):
        body = json.loads(body)
        meta = citation_metadata(body, json.loads(raw))
        derived.append(
            (
                body["id"],
                meta.get("relator") or "",
                folded(meta.get("relator") or ""),
                meta.get("classe_descricao") or "",
            )
        )
    dest.executemany("INSERT INTO document_details VALUES (?,?,?,?)", derived)
    dest.execute("CREATE INDEX details_relator ON document_details(relator_fold)")


def derive_document_citations(dest):
    """Citations of every acórdão, extracted from the stored original, resolved against the generation.

    ``resolvido`` names the acórdão or precedent of this generation the key points to, when any;
    the key stays as extracted, and a fragment without key keeps its text, so losses are visible.
    """
    dest.execute(
        "CREATE TABLE document_citations(document_id TEXT NOT NULL,tipo TEXT NOT NULL,chave TEXT NOT NULL,"
        "texto TEXT NOT NULL,origem TEXT NOT NULL,resolvido TEXT)"
    )
    rows = []
    for body, raw in dest.execute(
        "SELECT d.body,v.raw FROM documents d JOIN versions v ON v.document_id=d.id AND v.hash=d.hash"
    ):
        body = json.loads(body)
        for item in extract(body, json.loads(raw)):
            rows.append((body["id"], item["tipo"], item["chave"], item["texto"], item["origem"]))
    dest.executemany("INSERT INTO document_citations VALUES (?,?,?,?,?,NULL)", rows)
    dest.execute("CREATE INDEX citations_key ON document_citations(tipo,chave)")
    dest.execute("CREATE INDEX citations_document ON document_citations(document_id)")
    if available(dest):
        dest.execute(
            "UPDATE document_citations SET resolvido=(SELECT id FROM precedents p WHERE p.id=chave) "
            "WHERE tipo='precedente' AND chave<>''"
        )
    dest.execute(
        "UPDATE document_citations SET resolvido=(SELECT d.id FROM documents d WHERE d.tribunal='TJSC' "
        "AND d.process=substr(chave,6)) WHERE tipo='acordao' AND chave LIKE 'TJSC:%'"
    )
    dest.execute(
        "UPDATE document_citations SET resolvido=(SELECT d.id FROM documents d WHERE d.tribunal='STJ' "
        "AND d.class=substr(chave,5,length(chave)-5-length(substr(chave,instr(substr(chave,5),':')+5))) "
        "AND d.process=substr(chave,instr(substr(chave,5),':')+5) ORDER BY d.judgment DESC LIMIT 1) "
        "WHERE tipo IN ('acordao','similar') AND chave LIKE 'STJ:%'"
    )


def prune_precedents(dest):
    if not available(dest):
        return
    dest.execute("DELETE FROM precedent_events")
    dest.execute("DELETE FROM precedents WHERE admission!='admitido'")
    dest.execute(
        "DELETE FROM precedent_versions WHERE NOT EXISTS (SELECT 1 FROM precedents p WHERE "
        "p.id=precedent_versions.id AND p.hash=precedent_versions.hash)"
    )
    dest.execute("INSERT INTO precedent_search(precedent_search,rank) VALUES ('integrity-check',1)")


def seal_snapshot(dest):
    dest.commit()
    dest.execute("PRAGMA journal_mode=DELETE")
    dest.execute("VACUUM")
    if (
        dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
        or dest.execute("PRAGMA foreign_key_check").fetchone()
    ):
        raise FloraError("publicacao_invalida", "Snapshot não passou na verificação de integridade.")


def install_snapshot(temporary, target, sha: str):
    if target.exists():
        if digest(target.read_bytes()) != sha:
            raise FloraError("publicacao_invalida", "Colisão de publicação.")
        temporary.unlink()
    else:
        temporary.rename(target)


def write_manifest(manifest_path, manifest: dict):
    pending = manifest_path.with_suffix(".tmp")
    pending.write_text(canonical(manifest), encoding="utf-8")
    pending.replace(manifest_path)


def remove_expired(store: Store, directory, history: list, retained: set) -> list:
    """Delete generations beyond retention; an open file is left for a later publication."""
    cleanup = []
    for old in history:
        path = (store.directory / old["arquivo"]).resolve()
        if path.is_relative_to(directory.resolve()) and old["arquivo"] not in retained:
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                cleanup.append(old["id"])
    return cleanup


def publish(store: Store):
    """Caller holds collector lock. Never replace an open SQLite file."""
    directory = store.directory / "publicacoes"
    directory.mkdir(exist_ok=True)
    manifest_path = store.directory / MANIFEST
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    temporary = directory / "preparando.sqlite"
    if temporary.exists():
        temporary.unlink()
    with connection(store.path) as source, closing(sqlite3.connect(temporary)) as dest:
        source.backup(dest)
        schema = dest.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]
        revision = dest.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        if schema not in {1, 2}:
            raise FloraError("schema_incompativel", "Publicação exige schema suportado.")
        withdrawn, admission_counts, retired_versions = precedent_state(dest)
        verify_originals(store, dest)
        verify_search_index(dest)
        copies = remove_text_copies(dest)
        verify_search_index(dest)
        prune_snapshot(dest)
        derive_document_details(dest)
        derive_document_citations(dest)
        prune_precedents(dest)
        seal_snapshot(dest)
    sha = digest(temporary.read_bytes())
    identity = f"r{revision}-s{schema}-{digest(DERIVER.encode())[:10]}-{sha[:12]}"
    target = directory / (identity + ".sqlite")
    install_snapshot(temporary, target, sha)
    entry = {
        "id": identity,
        "arquivo": str(target.relative_to(store.directory)),
        "sha256": sha,
        "schema": schema,
        "revisao": revision,
        "derivador": DERIVER,
    }
    history = [entry] + [x for x in (previous or {}).get("publicacoes", []) if x["id"] != identity]
    manifest = {
        "schema": "flora-publicacoes-1",
        "atual": identity,
        "publicado_em": now(),
        "publicacoes": history[:3],
        "retirados": sorted(withdrawn),
        "versoes_retiradas": sorted(retired_versions),
    }
    manifest["admissao_atual"] = admission_counts
    write_manifest(manifest_path, manifest)
    retained = {x["arquivo"] for x in manifest["publicacoes"]}
    cleanup = remove_expired(store, directory, history[3:], retained)
    return {
        "status": "ok",
        "publicacao_id": identity,
        "sha256": sha,
        "revisao_base": revision,
        "copias_texto": copies,
        "limpeza_adiada_arquivo_aberto": cleanup,
    }


class Reader:
    def __init__(self, store: Store):
        self.store = store
        self.verified = {}

    def _local_withdrawals(self, withdrawn: set, retired: set) -> dict | None:
        with connection(self.store.path) as db:
            if not available(db):
                return None
            withdrawn.update(
                r[0] for r in db.execute("SELECT id FROM precedents WHERE admission!='admitido'")
            )
            retired.update(r[0] + ":" + r[1] for r in db.execute("SELECT id,hash FROM precedent_retirements"))
            return dict(db.execute("SELECT admission,count(*) FROM precedents GROUP BY admission"))

    def resolve(self, publication=None) -> ReadView:
        path = self.store.directory / MANIFEST
        if not path.exists():
            if publication:
                raise FloraError("publicacao_expirada", "Publicação solicitada indisponível.")
            # Before explicit activation, the legacy work database remains the reader.
            return self.store.view()
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest["schema"] != "flora-publicacoes-1":
                raise ValueError()
            identity = publication or manifest["atual"]
            entry = next((x for x in manifest["publicacoes"] if x["id"] == identity), None)
            if entry is None:
                raise FloraError("publicacao_expirada", "Publicação retirada; reinicie a consulta.")
            target = (self.store.directory / entry_path(entry)).resolve()
            if (
                not target.is_relative_to((self.store.directory / "publicacoes").resolve())
                or not target.is_file()
            ):
                raise ValueError()
            stat = target.stat()
            signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, entry["sha256"])
            if self.verified.get(target) != signature:
                if file_digest(target) != entry["sha256"]:
                    raise ValueError()
                with connection(target) as db:
                    actual = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]
                    if actual != entry["schema"] or actual not in {1, 2}:
                        raise ValueError()
                self.verified[target] = signature
            withdrawn = set(manifest.get("retirados", []))
            retired = set(manifest.get("versoes_retiradas", []))
            admission_counts = manifest.get("admissao_atual", {})
            # Local withdrawals apply immediately, even before the next publication.
            if self.store.path.exists():
                local = self._local_withdrawals(withdrawn, retired)
                if local is not None:
                    admission_counts = local
            return ReadView(
                path=target,
                immutable=True,
                publication=identity,
                withdrawn=frozenset(withdrawn),
                retired_versions=frozenset(retired),
                admission_counts=admission_counts,
                atrasos=self.store.atrasos,
            )
        except (OSError, KeyError, ValueError, TypeError, sqlite3.Error) as exc:
            raise FloraError(
                "publicacao_invalida", "Manifesto ou snapshot inválido; leitura interrompida."
            ) from exc
