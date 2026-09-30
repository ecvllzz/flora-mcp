"""Persistent observations, versions, current documents and a transactional search index."""

import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .model import FloraError, canonical, digest, folded, now, number

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('schema',1),('revision',0);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, started TEXT NOT NULL, finished TEXT,
 status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS catalogs (
 dataset TEXT PRIMARY KEY, fetched TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resources (
 id TEXT PRIMARY KEY, dataset TEXT NOT NULL, name TEXT NOT NULL, url TEXT NOT NULL,
 metadata TEXT NOT NULL, expected_fingerprint TEXT NOT NULL, applied_fingerprint TEXT,
 rank TEXT NOT NULL, present INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'pending',
 checked TEXT, sha256 TEXT, raw_path TEXT, count INTEGER, error TEXT, run_id TEXT);
CREATE TABLE IF NOT EXISTS versions (
 document_id TEXT NOT NULL, hash TEXT NOT NULL, first_seen TEXT NOT NULL, raw TEXT NOT NULL,
 PRIMARY KEY(document_id,hash));
CREATE TABLE IF NOT EXISTS observations (
 resource_id TEXT NOT NULL REFERENCES resources(id), document_id TEXT NOT NULL,
 hash TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(resource_id,document_id));
CREATE TABLE IF NOT EXISTS resource_history (
 resource_id TEXT NOT NULL, sha256 TEXT NOT NULL, raw_path TEXT NOT NULL, metadata TEXT NOT NULL,
 fetched TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(resource_id,sha256));
CREATE TABLE IF NOT EXISTS version_origins (
 document_id TEXT NOT NULL, hash TEXT NOT NULL, resource_id TEXT NOT NULL, batch_sha256 TEXT NOT NULL,
 observed TEXT NOT NULL, run_id TEXT NOT NULL,
 PRIMARY KEY(document_id,hash,resource_id,batch_sha256));
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, resource_id TEXT NOT NULL, hash TEXT NOT NULL, body TEXT NOT NULL,
 tribunal TEXT NOT NULL, organ TEXT NOT NULL, class TEXT NOT NULL, process TEXT NOT NULL,
 registration TEXT NOT NULL, judgment TEXT, publication TEXT);
CREATE INDEX IF NOT EXISTS doc_filters ON documents(tribunal,organ,publication);
CREATE INDEX IF NOT EXISTS doc_process ON documents(process);
CREATE INDEX IF NOT EXISTS observations_doc ON observations(document_id);
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
 id UNINDEXED, ementa, tokenize='unicode61 remove_diacritics 2');
"""


@contextmanager
def connection(path: Path, *, write: bool = False, immutable: bool = False):
    if not write and not path.exists():
        raise FloraError("base_nao_inicializada", "Execute flora-mcp init e sync-stj antes de pesquisar.")
    path = Path(path).resolve()
    uri = path.as_uri() + "?mode=ro" + ("&immutable=1" if immutable else "")
    db = sqlite3.connect(path if write else uri, uri=not write, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class ReadView:
    """What a reader sees: the work database or one immutable published generation."""

    path: Path
    immutable: bool = False
    publication: str | None = None
    withdrawn: frozenset[str] = field(default_factory=frozenset)
    retired_versions: frozenset[str] = field(default_factory=frozenset)
    admission_counts: dict | None = None

    def read(self):
        return connection(self.path, immutable=self.immutable)

    def coverage(self) -> dict:
        return coverage_report(self)


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "acervo.sqlite"
        self.reader = None  # publication.Reader, created by api on first read

    def read(self):
        return connection(self.path)

    def view(self) -> "ReadView":
        return ReadView(self.path)

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with connection(self.path, write=True) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            if db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] not in {1, 2}:
                raise FloraError("schema_incompativel", "Versão de banco não suportada.")
            db.commit()

    def start_run(self, source: str) -> str:
        run_id = str(uuid4())
        with connection(self.path, write=True) as db, db:
            # Called with the exclusive collector lock held: old running rows were interrupted.
            db.execute("UPDATE runs SET status='interrupted',finished=? WHERE status='running'", (now(),))
            db.execute(
                "INSERT INTO runs(id,source,started,status) VALUES (?,?,?,'running')", (run_id, source, now())
            )
        return run_id

    def finish_run(self, run_id: str, status: str, detail: dict):
        with connection(self.path, write=True) as db, db:
            db.execute(
                "UPDATE runs SET status=?,finished=?,detail=? WHERE id=?",
                (status, now(), canonical(detail), run_id),
            )

    def catalog(self, dataset: str, package: dict, selected: list[dict], *, complete_listing: bool = True):
        with connection(self.path, write=True) as db, db:
            db.execute("INSERT OR REPLACE INTO catalogs VALUES (?,?,?)", (dataset, now(), canonical(package)))
            if complete_listing:
                db.execute("UPDATE resources SET present=0 WHERE dataset=?", (dataset,))
            for r in selected:
                # Metadata fingerprint is separate from the downloaded byte hash.
                metadata = canonical(r)
                fingerprint = digest(metadata.encode())
                rank = r["name"][:8] + ":" + str(r.get("last_modified") or "")
                db.execute(
                    """INSERT INTO resources(id,dataset,name,url,metadata,expected_fingerprint,rank)
                    VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,url=excluded.url,metadata=excluded.metadata,
                    expected_fingerprint=excluded.expected_fingerprint,rank=excluded.rank,present=1""",
                    (dataset + ":" + r["id"], dataset, r["name"], r["url"], metadata, fingerprint, rank),
                )

    def resources(self, dataset: str) -> list[dict]:
        with connection(self.path) as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM resources WHERE dataset=? AND present=1 ORDER BY name DESC,id", (dataset,)
                )
            ]

    def failure(self, resource_id: str, run_id: str, message: str):
        with connection(self.path, write=True) as db, db:
            db.execute(
                "UPDATE resources SET status='error',error=?,run_id=? WHERE id=?",
                (message, run_id, resource_id),
            )

    def save_raw(self, content: bytes) -> tuple[str, str]:
        sha = digest(content)
        path = self.directory / "raw" / sha[:2] / (sha + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if digest(path.read_bytes()) != sha:
                raise FloraError("arquivo_corrompido", "Arquivo original local não confere com seu hash.")
        else:
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
        return sha, str(path.relative_to(self.directory))

    def ingest(
        self,
        resource: dict,
        content: bytes,
        rows: list[tuple[dict, dict]],
        run_id: str,
        *,
        observed_at: str | None = None,
    ) -> dict:
        observed_at = observed_at or now()
        sha, raw_path = self.save_raw(content)
        seen = set()
        for body, _raw in rows:
            if body["id"] in seen:
                raise FloraError("id_duplicado", "Identificador duplicado dentro do mesmo recurso.")
            seen.add(body["id"])
        counts = dict(novos=0, alterados=0, inalterados=0, removidos=0)
        with connection(self.path, write=True) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO resource_history VALUES (?,?,?,?,?,?)",
                (resource["id"], sha, raw_path, resource["metadata"], observed_at, run_id),
            )
            affected = {
                r[0]
                for r in db.execute(
                    "SELECT document_id FROM observations WHERE resource_id=?", (resource["id"],)
                )
            } | seen
            db.execute("DELETE FROM observations WHERE resource_id=?", (resource["id"],))
            for body, raw in rows:
                raw_json = canonical(raw)
                version = digest(raw_json.encode())
                body = {
                    **body,
                    "hash_conteudo": version,
                    "url_lote": resource["url"],
                    "recurso": resource["name"],
                    "dataset": resource["dataset"],
                }
                db.execute(
                    "INSERT OR IGNORE INTO versions VALUES (?,?,?,?)", (body["id"], version, now(), raw_json)
                )
                db.execute(
                    "INSERT OR IGNORE INTO version_origins VALUES (?,?,?,?,?,?)",
                    (body["id"], version, resource["id"], sha, observed_at, run_id),
                )
                db.execute(
                    "INSERT INTO observations VALUES (?,?,?,?)",
                    (resource["id"], body["id"], version, canonical(body)),
                )
            for doc_id in affected:
                old = db.execute("SELECT hash,body FROM documents WHERE id=?", (doc_id,)).fetchone()
                winner = db.execute(
                    """SELECT o.* FROM observations o JOIN resources r ON r.id=o.resource_id
                    WHERE document_id=? ORDER BY r.rank DESC,r.id DESC LIMIT 1""",
                    (doc_id,),
                ).fetchone()
                if not winner:
                    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
                    db.execute("DELETE FROM search WHERE id=?", (doc_id,))
                    counts["removidos"] += 1
                    continue
                body = json.loads(winner["body"])
                counts[
                    "inalterados"
                    if old and old["hash"] == winner["hash"]
                    else "alterados"
                    if old
                    else "novos"
                ] += 1
                if old and old["body"] == winner["body"]:
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        doc_id,
                        winner["resource_id"],
                        winner["hash"],
                        winner["body"],
                        body["tribunal"],
                        folded(body["orgao"]),
                        folded(body["classe"]),
                        number(body["numero_processo"]),
                        number(body["numero_registro"]),
                        body["data_julgamento"],
                        body["data_publicacao"],
                    ),
                )
                db.execute("DELETE FROM search WHERE id=?", (doc_id,))
                db.execute("INSERT INTO search VALUES (?,?)", (doc_id, body["ementa"]))
            db.execute(
                """UPDATE resources SET status='ok',checked=?,sha256=?,raw_path=?,count=?,
                applied_fingerprint=expected_fingerprint,error=NULL,run_id=? WHERE id=?""",
                (observed_at, sha, raw_path, len(rows), run_id, resource["id"]),
            )
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
        return counts

    def coverage(self) -> dict:
        return coverage_report(self)

    def backup(self, target: Path):
        if target.exists():
            raise FloraError("destino_existente", "O destino do backup já existe.")
        target.mkdir(parents=True)
        import shutil

        with connection(self.path) as source, closing(sqlite3.connect(target / "acervo.sqlite")) as dest:
            source.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise FloraError("backup_invalido", "Falha na integridade do backup.")
            paths = [
                r[0]
                for r in dest.execute("SELECT DISTINCT raw_path FROM resources WHERE raw_path IS NOT NULL")
            ]
            if dest.execute("SELECT 1 FROM sqlite_master WHERE name='precedent_versions'").fetchone():
                for (body,) in dest.execute("SELECT body FROM precedent_versions"):
                    paths.extend(s["raw_path"] for s in json.loads(body)["fontes"])
        # Caller holds writer lock; retain all originals, including superseded versions.
        if (self.directory / "raw").exists():
            shutil.copytree(self.directory / "raw", target / "raw")
        for relative in set(paths):
            p = target / relative
            if digest(p.read_bytes()) != p.stem:
                raise FloraError("backup_invalido", "Original no backup não confere com seu hash.")
        return {"status": "ok", "destino": str(target), "originais_atuais_verificados": len(paths)}


def coverage_report(reader) -> dict:
    with reader.read() as db:
        groups = [
            dict(r)
            for r in db.execute("""SELECT tribunal,json_extract(body,'$.orgao') AS orgao,
            count(*) AS documentos,min(judgment) AS julgamento_min,max(judgment) AS julgamento_max,
            min(publication) AS publicacao_min,max(publication) AS publicacao_max,
            sum(publication IS NULL) AS publicacao_nao_normalizada
            FROM documents GROUP BY tribunal,organ ORDER BY tribunal,organ""")
        ]
        resources = [
            dict(r)
            for r in db.execute("""SELECT dataset,name,url,status,present,checked,
            count,sha256,error,(applied_fingerprint IS NOT expected_fingerprint) AS pendente
            FROM resources ORDER BY dataset,name DESC""")
        ]
        runs = [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY started DESC LIMIT 10")]
        for r in runs:
            r["detail"] = json.loads(r["detail"])
        catalogs = [
            dict(r)
            for r in db.execute("""SELECT dataset,fetched,
            json_extract(body,'$.metadata_modified') AS atualizado_na_fonte,
            json_extract(body,'$.license_id') AS licenca FROM catalogs""")
        ]
    return {
        "status": "ok",
        "cobertura_integral": False,
        "grupos": groups,
        "catalogos": catalogs,
        "recursos": resources,
        "execucoes_recentes": runs,
        "inteiros_teores": 0,
        "tjsc": ("Coleta experimental por dia de publicação; somente janelas registradas estão carregadas."),
        "limites": [
            "Carga de recursos JSON selecionados; histórico ZIP não incorporado.",
            "Datas extremas observadas não comprovam cobertura contínua do período.",
            "Ementas e espelhos não equivalem ao inteiro teor.",
            "Versão corrente prioriza o recurso com data de extração mais recente; "
            "isso não é certificação de revisão jurídica pela fonte.",
        ],
    }
