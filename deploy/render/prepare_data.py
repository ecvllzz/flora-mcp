"""Restore and verify a deployment snapshot; never mutate the source collection."""

import gzip
import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import urlopen


def download_snapshot(source: Path, archive: Path):
    release = json.loads((source / "release.json").read_text(encoding="utf-8"))
    if not release["url"].startswith("https://github.com/ecvllzz/flora-mcp/releases/download/"):
        raise ValueError("Origem da publicacao invalida")
    with urlopen(release["url"], timeout=120) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output, 1024 * 1024)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != release["sha256"]:
        archive.unlink()
        raise ValueError("SHA-256 do arquivo comprimido diverge")


def prepare(source: Path, destination: Path):
    manifest = json.loads((source / "publicacoes.json").read_text(encoding="utf-8"))
    current = next(p for p in manifest["publicacoes"] if p["id"] == manifest["atual"])
    relative = Path(current["arquivo"])
    if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "publicacoes":
        raise ValueError("Caminho de publicacao invalido")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "snapshot.gz"
    download_snapshot(source, archive)
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(archive, "rb") as stream, target.open("wb") as output:
        shutil.copyfileobj(stream, output, 1024 * 1024)
    with target.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != current["sha256"]:
        target.unlink()
        raise ValueError("SHA-256 da publicacao diverge do manifesto")
    shutil.copyfile(source / "publicacoes.json", destination / "publicacoes.json")
    archive.unlink()
    print(f"Publicacao verificada: {current['id']}")


if __name__ == "__main__":
    prepare(Path(__file__).parent / "data", Path("/app/acervo"))
