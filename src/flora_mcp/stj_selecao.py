"""Selective load of the STJ open data, for a list of pointed numbers.

The catalog has no search: the number is found by reading the files. Every extraction file of the
mirror datasets is read (monthly JSON and the historical ZIP), so a number that appears nowhere can be
registered as not offered. A file that holds a selected acórdão is kept whole, as the original; only
the selected acórdãos enter the documents and the search. Files without a selection leave only their
hash in the receipt.

Each kept file is one resource of the dataset stj-selecao, apart from the datasets of the current
collection: sync_stj treats a catalogued file as loaded, and a partial resource under its own dataset
would stop the whole file from ever coming. The run source is STJ-numero, which does not count as an
update in the delay of the STJ. An acórdão the current collection already holds is not selected again.
"""

import io
import re
import time
import zipfile

import httpx

from .config import Config
from .model import FloraError, digest, normalize_stj, now, number
from .numeros import stj_family
from .sources import STJ_API, download, parse_json
from .store import Store, connection

STJ_SELECAO = "stj-selecao"
RUN_SOURCE = "STJ-numero"
PREFIXO = "espelhos-de-acordaos-"
ARQUIVO = re.compile(r"(\d{8})\.(json|zip)")
# The historical ZIP of the largest panels goes over the limit of a monthly batch.
LIMITE_ZIP = 256 * 1024 * 1024
LIMITE_MEMBRO = 1024 * 1024 * 1024
NO_ID = "sem-id:"
SOURCE_ERRORS = (FloraError, httpx.HTTPError, KeyError, TypeError, ValueError, zipfile.BadZipFile)


def catalog_call(http, action: str, **params) -> dict | list:
    url = STJ_API.replace("package_show", action)
    payload = parse_json(download(http, url, 4 * 1024 * 1024, params=params))
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise FloraError("catalogo_invalido", "Catálogo STJ não confirmou sucesso.")
    return payload["result"]


def mirror_datasets(http) -> list[str]:
    """Every mirror dataset the catalog lists today, so a new panel needs no code."""
    names = [name for name in catalog_call(http, "package_list") if name.startswith(PREFIXO)]
    if not names:
        raise FloraError("catalogo_vazio", "Catálogo STJ sem datasets de espelhos de acórdãos.")
    return sorted(names)


def files_of(package: dict, desde: str | None, ate: str | None) -> list[dict]:
    selected = []
    for resource in package["resources"]:
        match = ARQUIVO.fullmatch(resource.get("name") or "")
        if match and (not desde or match[1] >= desde) and (not ate or match[1] <= ate):
            selected.append(resource)
    return sorted(selected, key=lambda r: r["name"])


def batches(content: bytes, name: str):
    """(member, records) of one file: the file itself, or each JSON inside the ZIP, oldest first."""
    if not name.endswith(".zip"):
        yield None, parse_json(content)
        return
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [info for info in archive.infolist() if info.filename.lower().endswith(".json")]
        if not members:
            raise FloraError("formato_invalido", "ZIP do STJ sem arquivo JSON.")
        for info in sorted(members, key=lambda info: info.filename):
            if info.file_size > LIMITE_MEMBRO:
                raise FloraError("recurso_grande", "Arquivo dentro do ZIP excede o limite de leitura.")
            yield info.filename, parse_json(archive.read(info))


def record_keys(raw) -> set[str]:
    """Keys that find one mirror: its process in its class, and its registration number."""
    if not isinstance(raw, dict):
        return set()
    keys = set()
    digits = number(str(raw.get("numeroProcesso") or "")).lstrip("0")
    family = stj_family(str(raw.get("siglaClasse") or ""))
    if digits and family:
        keys.add(f"{family}:{digits}")
    registration = number(str(raw.get("numeroRegistro") or ""))
    if registration:
        keys.add("REGISTRO:" + registration)
    return keys


def read_file(content: bytes, name: str, wanted: set[str], kept: set[str]) -> dict:
    """Mirrors of one file that the list asks for or that an earlier list selected.

    wanted holds keys and kept source ids. Inside a ZIP the same id may come twice: the later member,
    the newer extraction, stands, as the rank does between files; a difference is reported.
    """
    found, keys_of, total, conflicts = {}, {}, 0, []
    for member, records in batches(content, name):
        if not isinstance(records, list) or not records:
            raise FloraError("formato_invalido", "Arquivo STJ vazio ou sem lista de espelhos.")
        for position, raw in enumerate(records):
            total += 1
            hits = record_keys(raw) & wanted
            source_id = str(raw.get("id") or "") if isinstance(raw, dict) else ""
            if not hits and source_id not in kept:
                continue
            place = {"membro": member, "posicao": position}
            identity = source_id or f"{NO_ID}{member}:{position}"
            if identity in found and found[identity][0] != raw:
                conflicts.append({"id": source_id, **place})
            found[identity] = (raw, place)
            keys_of.setdefault(identity, set()).update(hits)
    return {"registros": total, "achados": found, "chaves": keys_of, "conflitos": conflicts}


def normalized(found: dict) -> tuple[list[tuple[dict, dict]], dict[str, dict]]:
    """Valid mirrors for the ingest and, by identity, the ones the model refuses."""
    rows, rejected = [], {}
    for identity, (raw, place) in found.items():
        try:
            rows.append((normalize_stj(raw), raw))
        except FloraError as exc:
            source_id = raw.get("id") if isinstance(raw, dict) else None
            rejected[identity] = {**place, "id": source_id or None, "motivo": str(exc)}
    return rows, rejected


def resource_for(store: Store, dataset: str, package: dict, file: dict) -> dict:
    """Catalog the kept file; the dataset of origin stays in the resource metadata."""
    entry = {
        "id": f"{dataset}/{file['name']}",
        "name": file["name"],
        "url": file["url"],
        "last_modified": file.get("last_modified"),
        "dataset_origem": dataset,
        "recurso_origem": file.get("id"),
        "tipo": "selecao_por_numero",
    }
    summary = {
        "fonte": STJ_API,
        "tipo": "selecao_por_numero",
        "license_id": package.get("license_id"),
        "metadata_modified": package.get("metadata_modified"),
    }
    store.catalog(STJ_SELECAO, summary, [entry], complete_listing=False)
    with connection(store.path) as db:
        row = db.execute("SELECT * FROM resources WHERE id=?", (f"{STJ_SELECAO}:{entry['id']}",)).fetchone()
    return dict(row)


def earlier_selection(store: Store) -> dict[str, set[str]]:
    """Source ids selected before, by resource id: a new list adds to them and removes nothing."""
    selection = {}
    with connection(store.path) as db:
        for resource_id, document_id in db.execute(
            """SELECT o.resource_id,o.document_id FROM observations o JOIN resources r ON r.id=o.resource_id
            WHERE r.dataset=?""",
            (STJ_SELECAO,),
        ):
            selection.setdefault(resource_id, set()).add(document_id.removeprefix("STJ:"))
    return selection


def held_elsewhere(store: Store, source_ids: set[str]) -> set[str]:
    """Which of these acórdãos the current collection already holds."""
    held = set()
    with connection(store.path) as db:
        for source_id in source_ids:
            row = db.execute(
                """SELECT 1 FROM observations o JOIN resources r ON r.id=o.resource_id
                WHERE o.document_id=? AND r.dataset<>? LIMIT 1""",
                ("STJ:" + source_id, STJ_SELECAO),
            ).fetchone()
            if row:
                held.add(source_id)
    return held


def document_note(raw: dict, dataset: str, file: dict, sha: str, place: dict, *, held: bool) -> dict:
    return {
        "id": "STJ:" + str(raw.get("id")),
        "classe": raw.get("siglaClasse"),
        "numero_processo": raw.get("numeroProcesso"),
        "numero_registro": raw.get("numeroRegistro"),
        "orgao": raw.get("nomeOrgaoJulgador"),
        "data_julgamento": raw.get("dataDecisao"),
        "dataset_origem": dataset,
        "arquivo": file["name"],
        "membro": place["membro"],
        "sha256_arquivo": sha,
        "na_coleta_corrente": held,
    }


def load_selection(store, source, content, sha, rows, rejected, earlier, run, report) -> None:
    """Keep the file as the original and load its selection, when the selection or the file changed."""
    dataset, package, file = source
    resource_id = f"{STJ_SELECAO}:{dataset}/{file['name']}"
    ids = {body["id_origem"] for body, _ in rows}
    with connection(store.path) as db:
        saved = db.execute("SELECT sha256 FROM resources WHERE id=?", (resource_id,)).fetchone()
    if not rows or (saved and saved[0] == sha and ids <= earlier.get(resource_id, set())):
        return
    resource = resource_for(store, dataset, package, file)
    try:
        counts = store.ingest(resource, content, rows, run, rejected=list(rejected.values()) or None)
    except Exception as exc:
        store.failure(resource["id"], run, str(exc))
        raise
    report["arquivos_guardados"].append(
        {
            "dataset_origem": dataset,
            "arquivo": file["name"],
            "sha256": sha,
            "bytes": len(content),
            "selecionados": len(rows),
            **counts,
        }
    )


def apply_result(store, source, content, result, sha, index, earlier, run, report) -> None:
    """Credit each found mirror to the numbers that asked for it, then load the new ones."""
    dataset, _, file = source
    found = result["achados"]
    held = held_elsewhere(store, {identity for identity in found if not identity.startswith(NO_ID)})
    rows, rejected = normalized({i: value for i, value in found.items() if i not in held})
    for identity, (raw, place) in found.items():
        for key in result["chaves"].get(identity, ()):
            if identity in rejected:
                index[key]["rejeitados"].append(
                    {"dataset_origem": dataset, "arquivo": file["name"], **rejected[identity]}
                )
            else:
                note = document_note(raw, dataset, file, sha, place, held=identity in held)
                index[key]["documentos"].append(note)
    load_selection(store, source, content, sha, rows, rejected, earlier, run, report)


def scan_file(http, config: Config, store, source, index, earlier, run, report) -> None:
    dataset, _, file = source
    is_zip = file["name"].endswith(".zip")
    limit = max(config.max_download_bytes, LIMITE_ZIP) if is_zip else config.max_download_bytes
    content = download(http, file["url"], limit)
    sha = digest(content)
    kept = earlier.get(f"{STJ_SELECAO}:{dataset}/{file['name']}", set())
    result = read_file(content, file["name"], set(index), kept)
    entry = {"dataset": dataset, "arquivo": file["name"], "sha256": sha, "bytes": len(content)}
    entry.update(registros=result["registros"], achados=len(result["achados"]))
    if result["conflitos"]:
        entry["conflitos"] = result["conflitos"]
    report["arquivos_varridos"].append(entry)
    if result["achados"]:
        apply_result(store, source, content, result, sha, index, earlier, run, report)


def scan_dataset(http, config, store, dataset, scope, index, earlier, run, report) -> None:
    try:
        package = catalog_call(http, "package_show", id=dataset)
        files = files_of(package, scope.get("desde"), scope.get("ate"))
        if not files:
            raise FloraError("catalogo_vazio", "Dataset sem arquivo de extração no recorte.")
    except SOURCE_ERRORS as exc:
        failure = {"dataset": dataset, "codigo": getattr(exc, "code", "erro_catalogo"), "erro": str(exc)}
        report["falhas"].append(failure)
        return
    for file in files:
        time.sleep(config.request_delay)
        try:
            scan_file(http, config, store, (dataset, package, file), index, earlier, run, report)
        except SOURCE_ERRORS as exc:
            report["falhas"].append(
                {
                    "dataset": dataset,
                    "arquivo": file.get("name"),
                    "codigo": getattr(exc, "code", "erro_fonte"),
                    "erro": str(exc),
                }
            )


def conclude(entries: list[dict], index: dict, report: dict, narrowed: bool) -> None:
    """Selected and absent numbers. Only a complete reading of the source proves an absence."""
    found, refused, absent = [], [], []
    for entry in entries:
        results = index[entry["chave"]]
        if results["documentos"]:
            found.append({**entry, **results})
        elif results["rejeitados"]:
            refused.append({**entry, "rejeitados": results["rejeitados"]})
        else:
            absent.append({"numero": entry["numero"], "chave": entry["chave"], "origens": entry["origens"]})
    complete = not narrowed and not report["falhas"]
    report.update(selecionados=found, oferecidos_com_defeito=refused, varredura_completa=complete)
    report["nao_oferecidos" if complete else "nao_localizados_no_recorte"] = absent


def run_summary(report: dict) -> dict:
    """What stays in the database: the receipt without the hash of every file read."""
    return {
        **{k: v for k, v in report.items() if k != "arquivos_varridos"},
        "arquivos_lidos": len(report["arquivos_varridos"]),
    }


def collect_selection(
    config: Config, store: Store, http, entries: list[dict], scope: dict | None = None
) -> dict:
    """Read the source and load what the entries point at. The caller holds the collector lock."""
    scope = scope or {}
    narrowed = bool(scope.get("datasets") or scope.get("desde") or scope.get("ate"))
    index = {entry["chave"]: {"documentos": [], "rejeitados": []} for entry in entries}
    run = store.start_run(RUN_SOURCE)
    report = {
        "execucao": run,
        "fonte": "STJ",
        "inicio": now(),
        "recorte": {k: scope.get(k) for k in ("datasets", "desde", "ate")},
        "numeros": len(entries),
        "arquivos_varridos": [],
        "arquivos_guardados": [],
        "falhas": [],
        "status": "running",
    }
    try:
        earlier = earlier_selection(store)
        try:
            datasets = scope.get("datasets") or mirror_datasets(http)
        except SOURCE_ERRORS as exc:
            report["falhas"].append({"codigo": getattr(exc, "code", "erro_catalogo"), "erro": str(exc)})
            datasets = []
        for dataset in datasets:
            scan_dataset(http, config, store, dataset, scope, index, earlier, run, report)
        conclude(entries, index, report, narrowed)
        report.update(status="error" if report["falhas"] else "ok", fim=now())
        store.finish_run(run, report["status"], run_summary(report))
        return report
    except BaseException as exc:
        conclude(entries, index, report, True)
        report.update(status="interrupted", erro=f"{type(exc).__name__}: {exc}", fim=now())
        store.finish_run(run, "interrupted", run_summary(report))
        raise
