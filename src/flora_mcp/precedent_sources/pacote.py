"""Package building from originals already collected, and the sample skeleton for the audit.

Nothing here writes to the collection: the package is a file for import-precedents, which is
still the only command that records precedents, and simulates by default.
"""

import json
from collections import Counter
from pathlib import Path

from ..model import FloraError, digest
from ..precedents import BATCH_MODE, draw, minimum_sample, read_package, record_id, required_keys
from . import adapter
from .common import Original


def receipts(folder: Path):
    """Collected originals of a folder: each <name>.recibo.json next to the bytes it describes."""
    for path in sorted(folder.glob("*.recibo.json")):
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
        if receipt.get("status") != "obtido" or not receipt.get("sha256"):
            continue
        name = Path(str(receipt.get("arquivo", "")).replace("\\", "/")).name
        original = folder / name if name else None
        if original is None or not original.is_file():
            continue
        yield receipt, original


def load_originals(folder: Path, name: str) -> list[Original]:
    """Originals of one source, checked against their receipts; the same bytes count once."""
    module = adapter(name)
    chosen: dict[str, tuple[dict, Path]] = {}
    for receipt, path in receipts(folder):
        url = receipt.get("url_final") or receipt.get("url_solicitada") or ""
        if module.role(url) is None:
            continue
        content = path.read_bytes()
        if digest(content) != receipt["sha256"]:
            raise FloraError("arquivo_corrompido", f"Original diverge do recibo: {path.name}.")
        previous = chosen.get(receipt["sha256"])
        # Same bytes collected twice: keep the latest observation.
        if previous is None or receipt["obtido_em"] > previous[0]["obtido_em"]:
            chosen[receipt["sha256"]] = (receipt, path)
    urls = Counter(r.get("url_final") or r["url_solicitada"] for r, _ in chosen.values())
    if any(count > 1 for count in urls.values()):
        raise FloraError("originais_ambiguos", "O mesmo endereço tem originais diferentes na pasta.")
    return [
        Original(
            arquivo="originais/" + path.name,
            content=path.read_bytes(),
            url=receipt.get("url_final") or receipt["url_solicitada"],
            coletado_em=receipt["obtido_em"],
            sha256=receipt["sha256"],
            content_type=receipt.get("content_type"),
        )
        for receipt, path in sorted(chosen.values(), key=lambda item: item[1].name)
    ]


def copy_original(original: Original, root: Path):
    target = root / original.arquivo
    if target.exists():
        if digest(target.read_bytes()) != original.sha256:
            raise FloraError("destino_invalido", f"Já existe outro arquivo em {original.arquivo}.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(original.content)
    temporary.replace(target)


def write_json(path: Path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_package(name: str, folder: Path, output: Path) -> dict:
    """flora-precedentes-1 package from the originals of one structured source, without network."""
    originals = load_originals(folder, name)
    if not originals:
        raise FloraError("originais_ausentes", "Nenhum original desta fonte na pasta, com recibo.")
    result = adapter(name).adapt(originals)
    if not result.registros:
        raise FloraError("pacote_vazio", "O adaptador não produziu registros.")
    used = {s["sha256"] for body in result.registros for s in body["fontes"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    for original in originals:
        if original.sha256 in used:
            copy_original(original, output.parent)
    write_json(
        output,
        {
            "schema": "flora-precedentes-1",
            "origem": {
                "fonte": name,
                "classe": "estruturada",
                "originais": [
                    {"arquivo": o.arquivo, "url": o.url, "sha256": o.sha256, "coletado_em": o.coletado_em}
                    for o in originals
                    if o.sha256 in used
                ],
                "ignorados": result.ignorados,
            },
            "registros": result.registros,
        },
    )
    return {
        "status": "ok",
        "pacote": str(output),
        "registros": len(result.registros),
        "ignorados": dict(Counter(item["motivo"].split(":")[0] for item in result.ignorados)),
    }


def sample_skeleton(package_path: Path, seed: int) -> dict:
    """Draw the sample of a package and write the skeleton of its batch review for a person."""
    package = read_package(package_path)
    review = package.get("conferencia")
    if isinstance(review, dict) and (review.get("amostra") or {}).get("resultado") is not None:
        raise FloraError("amostra_existente", "O pacote já tem amostra com resultado; nada foi alterado.")
    needed = {record_id(record): required_keys(record) for record in package["registros"]}
    if len(needed) != len(package["registros"]):
        raise FloraError("id_duplicado", "Pacote contém identidade duplicada.")
    size = minimum_sample(len(needed))
    ids = draw(needed, seed, size)
    package["conferencia"] = {
        "modo": BATCH_MODE,
        "amostra": {
            "tamanho": size,
            "semente": seed,
            "ids": ids,
            "verificacoes": [
                {
                    "id": value,
                    "campos_a_conferir": sorted(needed[value]),
                    "campos_conferidos": [],
                    "resultado": None,
                }
                for value in ids
            ],
            "responsavel": None,
            "data": None,
            "resultado": None,
        },
    }
    write_json(package_path, package)
    return {"status": "ok", "pacote": str(package_path), "semente": seed, "tamanho": size, "ids": ids}
