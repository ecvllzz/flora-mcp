"""Immutable SQLite generations; a small atomic manifest selects the active one."""

import json
import sqlite3
from contextlib import closing

from .model import FloraError, canonical, digest, folded, now
from .citation import citation_metadata
from .precedents import available
from .text import SECTIONS_DERIVER
from .store import ReadView, Store, connection

# Derivations computed when a generation is read also name the generation, so changing one of them
# changes publicacao_id at the next publication.
DERIVER = f"flora-read-2.3;{SECTIONS_DERIVER}"
MANIFEST = "publicacoes.json"


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
        prune_snapshot(dest)
        derive_document_details(dest)
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
            target = (self.store.directory / entry["arquivo"]).resolve()
            if (
                not target.is_relative_to((self.store.directory / "publicacoes").resolve())
                or not target.is_file()
            ):
                raise ValueError()
            stat = target.stat()
            signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, entry["sha256"])
            if self.verified.get(target) != signature:
                if digest(target.read_bytes()) != entry["sha256"]:
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
