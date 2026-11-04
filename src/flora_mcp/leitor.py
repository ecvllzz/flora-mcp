"""Reader copy: the current published generation and its manifest, without work database or collector.

Collection and publication stay where the collector runs; a reader host (the HTTP adapter for the
Studio, for instance) only receives what reading needs. The generation file goes first, verified by
SHA-256, and the manifest last, by atomic replacement, so a reader never sees a manifest pointing to
a missing or partial file.
"""

import gzip
import json
import os
import shutil
from pathlib import Path

from .model import FloraError, now
from .publication import MANIFEST, entry_path, file_digest, precedent_state, write_manifest
from .store import connection


def _copy_verified(source: Path, target: Path, sha256: str) -> bool:
    if target.is_file() and file_digest(target) == sha256:
        return False
    partial = target.with_name(target.name + ".parcial")
    shutil.copyfile(source, partial)
    if file_digest(partial) != sha256:
        partial.unlink()
        raise FloraError("publicacao_invalida", "Cópia da publicação não confere com o hash do manifesto.")
    os.replace(partial, target)
    return True


def sincronizar(origem: Path, destino: Path, manter: int = 2) -> dict:
    """Bring destino to the current generation of origem, keeping up to `manter` generations there."""
    if manter < 1:
        raise ValueError("manter deve ser ao menos 1.")
    manifest = json.loads((origem / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema") != "flora-publicacoes-1":
        raise FloraError("publicacao_invalida", "Manifesto de origem desconhecido.")
    atual = next(x for x in manifest["publicacoes"] if x["id"] == manifest["atual"])
    (destino / "publicacoes").mkdir(parents=True, exist_ok=True)
    copiado = _copy_verified(origem / entry_path(atual), destino / entry_path(atual), atual["sha256"])
    anteriores = [
        x for x in manifest["publicacoes"] if x["id"] != atual["id"] and (destino / entry_path(x)).is_file()
    ]
    anteriores.sort(key=lambda x: x.get("revisao", 0), reverse=True)
    mantidas = [atual, *anteriores[: manter - 1]]
    novo = dict(manifest, publicacoes=[dict(x, arquivo=entry_path(x).as_posix()) for x in mantidas])
    write_manifest(destino / MANIFEST, novo)
    guardar = {(destino / entry_path(x)).resolve() for x in mantidas}
    removidas, adiadas = [], []
    for arquivo in sorted((destino / "publicacoes").glob("*.sqlite")):
        if arquivo.resolve() in guardar:
            continue
        try:
            arquivo.unlink()
            removidas.append(arquivo.name)
        except OSError:
            adiadas.append(arquivo.name)  # still open by a reader; the next run removes it
    return {
        "status": "ok",
        "atual": atual["id"],
        "copiado": copiado,
        "mantidas": [x["id"] for x in mantidas],
        "removidas": removidas,
        "remocao_adiada": adiadas,
    }


INSTALADA = "instalada"  # marca, no id, uma geração montada de um arquivo de publicação avulso


def instalar(arquivo: Path, destino: Path, sha256: str | None = None) -> dict:
    """Make destino a reader folder for one published generation given as a file (.sqlite or .sqlite.gz).

    The file is decompressed if needed, verified against sha256 when given, read for its revision and
    schema, and placed under destino/publicacoes; the manifest is written last, as the current
    generation, with the withdrawn precedents recorded in the file itself. The original deriver is not
    in the file, so the id carries the mark "instalada" instead of the deriver digest.
    """
    if not arquivo.is_file():
        raise FloraError("arquivo_ausente", f"Arquivo de publicação não encontrado: {arquivo}.")
    (destino / "publicacoes").mkdir(parents=True, exist_ok=True)
    partial = destino / "publicacoes" / "instalando.sqlite"
    opener = gzip.open if arquivo.name.endswith(".gz") else open
    with opener(arquivo, "rb") as stream, partial.open("wb") as output:
        shutil.copyfileobj(stream, output, 1024 * 1024)
    sha = file_digest(partial)
    if sha256 and sha != sha256.lower():
        partial.unlink()
        raise FloraError(
            "publicacao_invalida", "SHA-256 do arquivo descomprimido não confere com o esperado."
        )
    with connection(partial) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FloraError(
                "publicacao_invalida", "Arquivo de publicação não passou na verificação de integridade."
            )
        meta = dict(db.execute("SELECT key,value FROM meta WHERE key IN ('schema','revision')"))
        if meta.get("schema") not in {1, 2}:
            raise FloraError("publicacao_invalida", "Arquivo de publicação com schema desconhecido.")
        withdrawn, admission_counts, retired = precedent_state(db)
    identity = f"r{meta['revision']}-s{meta['schema']}-{INSTALADA}-{sha[:12]}"
    target = destino / "publicacoes" / f"{identity}.sqlite"
    if target.is_file() and file_digest(target) == sha:
        partial.unlink()
    else:
        os.replace(partial, target)
    manifest_path = destino / MANIFEST
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    entry = {
        "id": identity,
        "arquivo": f"publicacoes/{identity}.sqlite",
        "sha256": sha,
        "schema": meta["schema"],
        "revisao": meta["revision"],
        "derivador": INSTALADA,
    }
    history = [entry] + [x for x in previous.get("publicacoes", []) if x["id"] != identity]
    write_manifest(
        manifest_path,
        {
            "schema": "flora-publicacoes-1",
            "atual": identity,
            "publicado_em": now(),
            "publicacoes": history[:3],
            "retirados": sorted(withdrawn),
            "versoes_retiradas": sorted(retired),
            "admissao_atual": admission_counts,
        },
    )
    return {"status": "ok", "publicacao_id": identity, "sha256": sha, "revisao_base": meta["revision"]}
