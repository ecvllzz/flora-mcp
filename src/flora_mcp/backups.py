"""Backups sharing one store of originals addressed by SHA-256; each backup keeps database and manifest.

Layout of the backup root::

    raw/ab/abcdef...          one copy of each original, named by its hash
    20261001-093000-000000-rotulo/
        acervo.sqlite         consistent copy made with the SQLite backup API
        manifesto.json        schema flora-backup-2: database hash and the originals it references
"""

import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from .model import FloraError, local_date, now
from .store import Store, connection

SCHEMA = "flora-backup-2"
MANIFEST = "manifesto.json"
DEPOT = "raw"
DATABASE = "acervo.sqlite"
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
HASH = re.compile(r"[0-9a-f]{64}")


def default_root(data_dir: Path) -> Path:
    return data_dir.parent / (data_dir.name + "-backups")


def file_digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def inside(base: Path, relative: str) -> Path:
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise FloraError("caminho_invalido", "Caminho de original fora do acervo: " + relative)
    return path


def referenced_originals(db) -> set[str]:
    """Originals the database cites: current and superseded batches, and precedent sources."""
    paths = {r[0] for r in db.execute("SELECT raw_path FROM resources WHERE raw_path IS NOT NULL")}
    paths |= {r[0] for r in db.execute("SELECT raw_path FROM resource_history")}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='precedent_versions'").fetchone():
        for (body,) in db.execute("SELECT body FROM precedent_versions"):
            paths.update(s["raw_path"] for s in json.loads(body)["fontes"])
    return paths


def depot_path(root: Path, sha: str) -> Path:
    return root / DEPOT / sha[:2] / sha


def deposit(root: Path, source: Path, sha: str) -> bool:
    """Copy one original into the depot when absent; True when copied. Both cases check the hash."""
    target = depot_path(root, sha)
    if target.exists():
        if file_digest(target) != sha:
            raise FloraError("deposito_corrompido", "Original no depósito não confere com seu hash: " + sha)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(sha + ".tmp")
    shutil.copyfile(source, temporary)
    if file_digest(temporary) != sha:
        temporary.unlink()
        raise FloraError("backup_invalido", "Cópia do original não confere com seu hash: " + sha)
    temporary.replace(target)
    return True


def copy_database(store: Store, target: Path) -> tuple[int, set[str]]:
    with connection(store.path) as source, closing(sqlite3.connect(target)) as dest:
        source.backup(dest)
        if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FloraError("backup_invalido", "Falha na integridade do backup.")
        revision = dest.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        return revision, referenced_originals(dest)


def lock(root: Path) -> FileLock:
    return FileLock(str(root / "backups.lock"), timeout=0)


def create(store: Store, root: Path, label: str | None = None) -> dict:
    """New backup under root. The caller holds the collector lock of the data directory."""
    if label is not None and not LABEL.fullmatch(label):
        raise FloraError("rotulo_invalido", "Rótulo aceita letras, dígitos, hífen e sublinhado.")
    root = Path(root).resolve()
    if root == store.directory.resolve() or root.is_relative_to(store.directory.resolve()):
        raise FloraError("destino_invalido", "Backups devem ficar fora do diretório do acervo.")
    name = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ("-" + label if label else "")
    root.mkdir(parents=True, exist_ok=True)
    with lock(root):
        work = root / ("." + name + ".parcial")
        work.mkdir()
        try:
            revision, paths = copy_database(store, work / DATABASE)
            originals, copied, copied_bytes = [], 0, 0
            for relative in sorted(paths):
                source = inside(store.directory, relative)
                if not source.is_file():
                    raise FloraError("original_ausente", "Original citado pelo banco não existe: " + relative)
                sha = file_digest(source)
                if HASH.fullmatch(source.stem) and source.stem != sha:
                    raise FloraError("original_corrompido", "Original não confere com seu hash: " + relative)
                if deposit(root, source, sha):
                    copied += 1
                    copied_bytes += source.stat().st_size
                originals.append({"caminho": relative, "sha256": sha})
            manifest = {
                "schema": SCHEMA,
                "data": now(),
                "rotulo": label,
                "revisao": revision,
                "banco": {"arquivo": DATABASE, "sha256": file_digest(work / DATABASE)},
                "originais": originals,
            }
            (work / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
            work.rename(root / name)
        except BaseException:
            shutil.rmtree(work, ignore_errors=True)
            raise
    return {
        "status": "ok",
        "formato": SCHEMA,
        "destino": str(root / name),
        "revisao": revision,
        "originais": len(originals),
        "originais_copiados": copied,
        "originais_ja_no_deposito": len(originals) - copied,
        "bytes_copiados": copied_bytes,
    }


def read_manifest(folder: Path) -> dict | None:
    """Manifest of a new-format backup; None for anything else, which is never pruned."""
    try:
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        return None
    return manifest


def inventory(root: Path) -> tuple[list[dict], list[dict]]:
    """New-format backups, most recent first, and folders outside the pruning."""
    current, other = [], []
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        if not child.is_dir() or child.name == DEPOT:
            continue
        if child.name.startswith("."):
            if child.name.endswith(".parcial"):
                other.append({"nome": child.name, "motivo": "backup interrompido, fora da poda"})
            continue
        manifest = read_manifest(child)
        if manifest is None:
            other.append({"nome": child.name, "motivo": "formato antigo, fora da poda"})
        else:
            current.append({"nome": child.name, "data": manifest["data"], "manifesto": manifest})
    current.sort(key=lambda b: (b["data"], b["nome"]), reverse=True)
    return current, other


def retention(backups: list[dict], keep: int) -> dict[str, list[str]]:
    """Reasons to keep each retained backup: the most recent N and the latest of each calendar month."""
    reasons = {b["nome"]: ["recentes"] for b in backups[:keep]}
    months = {}
    for backup in backups:
        months.setdefault(local_date(backup["data"]).strftime("%Y-%m"), backup["nome"])
    for month, name in months.items():
        reasons.setdefault(name, []).append("mes " + month)
    return reasons


def depot_files(root: Path) -> list[Path]:
    depot = root / DEPOT
    return sorted(p for p in depot.glob("*/*") if p.is_file()) if depot.is_dir() else []


def prune(root: Path, keep: int = 5, *, apply: bool = False) -> dict:
    if keep < 1:
        raise FloraError("limite_invalido", "Manter ao menos um backup.")
    root = Path(root).resolve()
    if not root.is_dir():
        raise FloraError("raiz_inexistente", "Pasta de backups não encontrada.")
    with lock(root):
        backups, other = inventory(root)
        reasons = retention(backups, keep)
        kept = [b for b in backups if b["nome"] in reasons]
        removed = [b for b in backups if b["nome"] not in reasons]
        referenced = {o["sha256"] for b in kept for o in b["manifesto"]["originais"]}
        orphans = [p for p in depot_files(root) if p.name not in referenced]
        if apply:
            for backup in removed:
                shutil.rmtree(root / backup["nome"])
            for path in orphans:
                path.unlink()
                if not any(path.parent.iterdir()):
                    path.parent.rmdir()
    return {
        "status": "ok",
        "aplicado": apply,
        "raiz": str(root),
        "manter": [{"nome": b["nome"], "data": b["data"], "motivos": reasons[b["nome"]]} for b in kept],
        "apagar": [{"nome": b["nome"], "data": b["data"]} for b in removed],
        "fora_da_poda": other,
        "deposito": {
            "referenciados_pelos_mantidos": len(referenced),
            "orfaos": len(orphans),
            "bytes_orfaos": sum(p.stat().st_size for p in orphans) if not apply else None,
        },
    }


def restore(root: Path, name: str, destination: Path) -> dict:
    """Assemble a usable data directory (database and cited originals) in a new folder."""
    root = Path(root).resolve()
    if Path(name).name != name or name in {DEPOT, ""} or name.startswith("."):
        raise FloraError("backup_invalido", "Informe o nome de uma subpasta da raiz de backups.")
    manifest = read_manifest(root / name)
    if manifest is None:
        raise FloraError("backup_invalido", "Backup sem manifesto " + SCHEMA + ".")
    destination = Path(destination).resolve()
    if destination.exists():
        raise FloraError("destino_existente", "O destino da restauração já existe.")
    destination.mkdir(parents=True)
    try:
        database = destination / DATABASE
        shutil.copyfile(root / name / manifest["banco"]["arquivo"], database)
        if file_digest(database) != manifest["banco"]["sha256"]:
            raise FloraError("backup_invalido", "Banco do backup não confere com o manifesto.")
        for original in manifest["originais"]:
            target = inside(destination, original["caminho"])
            source = depot_path(root, original["sha256"])
            if not source.is_file():
                raise FloraError("original_ausente", "Original ausente do depósito: " + original["sha256"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if file_digest(target) != original["sha256"]:
                raise FloraError("deposito_corrompido", "Original não confere com seu hash: " + target.name)
        with closing(sqlite3.connect(database)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise FloraError("backup_invalido", "Falha na integridade do banco restaurado.")
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "status": "ok",
        "backup": name,
        "destino": str(destination),
        "revisao": manifest["revisao"],
        "originais": len(manifest["originais"]),
    }
