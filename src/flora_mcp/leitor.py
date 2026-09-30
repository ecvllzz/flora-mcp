"""Reader copy: the current published generation and its manifest, without work database or collector.

Collection and publication stay where the collector runs; a reader host (the HTTP adapter for the
Studio, for instance) only receives what reading needs. The generation file goes first, verified by
SHA-256, and the manifest last, by atomic replacement, so a reader never sees a manifest pointing to
a missing or partial file.
"""

import json
import os
import shutil
from pathlib import Path

from .model import FloraError
from .publication import MANIFEST, entry_path, file_digest, write_manifest


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
