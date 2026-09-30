"""Qualified precedents: explicit evidence, literal components and auditable admission.

The importer consumes a reviewed source package. It never treats a mention in an
ordinary judgment, an official URL alone or a collector's success as legal status.
"""

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .model import FloraError, canonical, digest, folded, now
from .precedent_sources import CLASSES, OUT_OF_SCOPE, structured_url
from .store import Store, connection

SCHEMA_VERSION = 2
COMPONENTS = ("enunciado", "questao_submetida", "tese_firmada", "modulacao", "suspensao")
SPECIES = {
    "STJ": {"tema_repetitivo", "iac", "sumula"},
    "STF": {"tema_repercussao_geral", "sumula_vinculante", "sumula"},
    "TJSC": {"sumula"},
}
LABELS = {
    "tema_repetitivo": "Tema repetitivo",
    "iac": "IAC",
    "sumula": "Súmula",
    "tema_repercussao_geral": "Tema de repercussão geral",
    "sumula_vinculante": "Súmula vinculante",
}
PUBLICATIONS = {
    "enunciado": "publicação do enunciado",
    "acordao_merito": "publicação do acórdão de mérito",
    "acordao_embargos": "publicação do acórdão de embargos",
}
SUMMARIES = {"sumula", "sumula_vinculante"}
MATTERS = {"civil", "processual_civil"}
BATCH_MODE = "fonte_estruturada"
EXCLUDED = {"cancelado", "revogado", "superado", "suspenso"}
STATUSES = EXCLUDED | {"vigente", "pendente", "desconhecido"}
SCHEMA = """
CREATE TABLE precedent_versions (
 id TEXT NOT NULL, hash TEXT NOT NULL, body TEXT NOT NULL, observed TEXT NOT NULL,
 PRIMARY KEY(id,hash));
CREATE TABLE precedents (
 id TEXT PRIMARY KEY, hash TEXT NOT NULL, tribunal TEXT NOT NULL, species TEXT NOT NULL,
 number TEXT NOT NULL, organ TEXT NOT NULL, publication TEXT, admission TEXT NOT NULL,
 reasons TEXT NOT NULL, body TEXT NOT NULL,
 FOREIGN KEY(id,hash) REFERENCES precedent_versions(id,hash));
CREATE INDEX precedent_filters ON precedents(tribunal,species,number,admission);
CREATE TABLE precedent_events (
 sequence INTEGER PRIMARY KEY, id TEXT NOT NULL, hash TEXT NOT NULL, observed TEXT NOT NULL,
 admission TEXT NOT NULL, reasons TEXT NOT NULL);
CREATE TABLE precedent_retirements (
 id TEXT NOT NULL, hash TEXT NOT NULL, retired TEXT NOT NULL, PRIMARY KEY(id,hash));
CREATE TABLE precedent_texts (
 rowid INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE REFERENCES precedents(id),
 enunciado TEXT NOT NULL, questao_submetida TEXT NOT NULL, tese_firmada TEXT NOT NULL,
 modulacao TEXT NOT NULL, suspensao TEXT NOT NULL);
CREATE VIRTUAL TABLE precedent_search USING fts5(
 enunciado,questao_submetida,tese_firmada,modulacao,suspensao,
 content='precedent_texts',content_rowid='rowid',tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER precedent_texts_ai AFTER INSERT ON precedent_texts BEGIN
 INSERT INTO precedent_search(rowid,enunciado,questao_submetida,tese_firmada,modulacao,suspensao)
 VALUES(new.rowid,new.enunciado,new.questao_submetida,new.tese_firmada,new.modulacao,new.suspensao);
END;
CREATE TRIGGER precedent_texts_ad AFTER DELETE ON precedent_texts BEGIN
 INSERT INTO precedent_search(precedent_search,rowid,
  enunciado,questao_submetida,tese_firmada,modulacao,suspensao)
 VALUES('delete',old.rowid,old.enunciado,old.questao_submetida,old.tese_firmada,old.modulacao,old.suspensao);
END;
UPDATE meta SET value=2 WHERE key='schema';
UPDATE meta SET value=value+1 WHERE key='revision';
"""


def parse_id(value: str) -> tuple[str, str, str | None, str] | None:
    """Split a qualified precedent identity; None when the text is not one."""
    parts = value.split(":") if isinstance(value, str) else []
    if len(parts) == 3:
        tribunal, species, number = parts
        scope = None
    elif len(parts) == 4:
        tribunal, species, scope, number = parts
    else:
        return None
    if tribunal not in SPECIES or species not in SPECIES[tribunal]:
        return None
    if scope is not None and (tribunal, scope) != ("TJSC", "GCDC"):
        return None
    if tribunal == "TJSC" and scope is None:
        return None
    if not re.fullmatch(r"[1-9][0-9]{0,6}", number):
        return None
    return tribunal, species, scope, number


def available(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name='precedents'").fetchone() is not None


def migrate(store: Store):
    """Explicit administrative migration; caller holds collector lock and backup."""
    with connection(store.path, write=True) as db:
        version = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]
        if version == SCHEMA_VERSION:
            return {"status": "ok", "schema": version, "alterado": False}
        if version != 1:
            raise FloraError("schema_incompativel", "Migração aceita somente schema 1.")
        try:
            db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
        except Exception:
            db.rollback()
            raise
    return {"status": "ok", "schema": SCHEMA_VERSION, "alterado": True}


def official(url: str, tribunal: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    domain = tribunal.lower() + ".jus.br"
    return parsed.scheme == "https" and (host == domain or host.endswith("." + domain))


def required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise FloraError("pacote_invalido", f"Campo textual obrigatório: {field}.")
    return value


def check_identity(body: dict):
    """Identity and organ; sets the canonical id."""
    tribunal, species = body.get("tribunal"), body.get("especie")
    if tribunal not in SPECIES or species not in SPECIES[tribunal]:
        raise FloraError("pacote_invalido", "Tribunal ou espécie fora do contrato.")
    number = required_text(body.get("numero"), "numero")
    if not re.fullmatch(r"[1-9][0-9]{0,6}", number):
        raise FloraError("pacote_invalido", "Número deve ser inteiro positivo, em texto.")
    organ = required_text(body.get("orgao"), "orgao")
    scope = ""
    if tribunal == "TJSC":
        if folded(organ) != "GRUPO DE CAMARAS DE DIREITO CIVIL":
            raise FloraError("pacote_invalido", "Órgão TJSC fora do recorte aprovado.")
        scope = ":GCDC"
    body["id"] = f"{tribunal}:{species}{scope}:{number}"


def check_components(body: dict) -> dict:
    components = body.get("componentes")
    if not isinstance(components, dict) or set(components) - set(COMPONENTS):
        raise FloraError(
            "pacote_invalido", "Componentes inválidos; ementas pertencem aos julgados associados."
        )
    for name, value in components.items():
        required_text(value, name)
    if body["especie"] in SUMMARIES and "tese_firmada" in components:
        raise FloraError("pacote_invalido", "Texto de súmula deve usar enunciado.")
    if body["especie"] not in SUMMARIES and "enunciado" in components:
        raise FloraError("pacote_invalido", "Tema usa questão submetida e tese firmada.")
    return components


def check_sources(body: dict, root: Path, source_cache=None) -> dict[str, bytes]:
    """Official origin, declared hash and preserved bytes of every source."""
    sources = body.get("fontes")
    if not isinstance(sources, list) or not sources:
        raise FloraError("pacote_invalido", "Fontes oficiais preservadas são obrigatórias.")
    cache = source_cache if source_cache is not None else {}
    blobs = {}
    for source in sources:
        if not isinstance(source, dict) or not official(source.get("url", ""), body["tribunal"]):
            raise FloraError("fonte_invalida", "Fonte deve pertencer ao tribunal do registro e usar HTTPS.")
        sha = source.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise FloraError("pacote_invalido", "Hash de fonte inválido.")
        path = (root / required_text(source.get("arquivo"), "arquivo")).resolve()
        if not path.is_relative_to(root.resolve()):
            raise FloraError("pacote_invalido", "Original fora do pacote.")
        key = (path, sha)
        if key not in cache:
            cache[key] = path.read_bytes()
        content = cache[key]
        if digest(content) != sha:
            raise FloraError("arquivo_corrompido", "Original diverge do hash declarado.")
        check_collected(source)
        check_class(source)
        blobs[sha] = content
    return blobs


def check_class(source: dict):
    """A source is a document unless it declares, truthfully, a registered structured origin."""
    declared = source.get("classe", "documento")
    if declared not in CLASSES:
        raise FloraError("pacote_invalido", "Classe de fonte deve ser estruturada ou documento.")
    if declared == "estruturada" and not structured_url(source["url"]):
        raise FloraError("fonte_invalida", "Classe estruturada exige fonte estruturada registrada.")


def check_collected(source: dict):
    try:
        collected = datetime.fromisoformat(source["coletado_em"])
        if collected.tzinfo is None:
            raise ValueError()
    except (KeyError, ValueError, TypeError) as exc:
        raise FloraError("pacote_invalido", "Coleta exige data/hora com fuso.") from exc


def check_evidence(body: dict, blobs: dict[str, bytes]) -> dict:
    evidence = body.get("evidencias", {})
    if not isinstance(evidence, dict):
        raise FloraError("pacote_invalido", "Evidências devem ser um objeto.")
    for key, item in evidence.items():
        if not isinstance(item, dict) or item.get("fonte_sha256") not in blobs:
            raise FloraError("pacote_invalido", f"Evidência {key} sem fonte preservada.")
        required_text(item.get("trecho"), f"evidencias.{key}.trecho")
        required_text(item.get("localizador"), f"evidencias.{key}.localizador")
    return evidence


def check_status(body: dict):
    """Situation, publication date and declared pending flags."""
    if body.get("situacao") not in STATUSES:
        raise FloraError("pacote_invalido", "Situação desconhecida no contrato.")
    publication = body.get("data_publicacao")
    if publication:
        try:
            if date.fromisoformat(publication).isoformat() != publication:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise FloraError("pacote_invalido", "Publicação exige AAAA-MM-DD.") from exc
    flags = body.get("pendencias", [])
    if not isinstance(flags, list) or any(not isinstance(x, str) for x in flags):
        raise FloraError("pacote_invalido", "Pendências devem ser uma lista textual.")


def admission_reasons(body: dict, components: dict, evidence: dict, batch: dict | None = None) -> list[str]:
    """Pending reasons; sets the publication type. Raises only for an incomplete review."""
    status = body["situacao"]
    reasons = list(body.get("pendencias", []))
    if status != "vigente":
        reasons.append("situacao_" + status)
    if body.get("materia") == OUT_OF_SCOPE:
        reasons.append("materia_fora_do_recorte")
    elif body.get("materia") not in MATTERS:
        reasons.append("materia_nao_confirmada")
    needed = {"situacao", "publicacao", "materia"} | {"componente:" + x for x in components}
    reasons += ["evidencia_ausente:" + x for x in sorted(needed - set(evidence))]
    if not body.get("data_publicacao"):
        reasons.append("publicacao_ausente")
    main = "enunciado" if body["especie"] in SUMMARIES else "tese_firmada"
    publication_type = body.get("tipo_publicacao", "enunciado" if main == "enunciado" else None)
    if publication_type not in PUBLICATIONS:
        reasons.append("tipo_publicacao_nao_informado")
    body["tipo_publicacao"] = publication_type
    if not components.get(main):
        reasons.append(main + "_ausente")
    if not reviewed(body, needed, evidence, batch):
        reasons.append("conferencia_pendente")
    return reasons


def from_structured_sources(body: dict, needed: set, evidence: dict) -> bool:
    """Main source and every present required evidence come from structured sources."""
    kinds = {source["sha256"]: source.get("classe", "documento") for source in body["fontes"]}
    return body["fontes"][0].get("classe") == "estruturada" and all(
        kinds[evidence[key]["fonte_sha256"]] == "estruturada" for key in needed & set(evidence)
    )


def reviewed(body: dict, needed: set, evidence: dict, batch: dict | None) -> bool:
    """Individual review of the record, or the approved sample of a structured-source batch.

    A reviewed evidence packet is an explicit input, not inferred from populated metadata.
    """
    review = body.get("conferencia", {})
    if isinstance(review, dict) and review.get("evidencias_conferidas") is True:
        required_text(review.get("responsavel"), "conferencia.responsavel")
        required_text(review.get("data"), "conferencia.data")
        return True
    if batch is None or not from_structured_sources(body, needed, evidence):
        return False
    body["conferencia"] = {
        "modo": BATCH_MODE,
        "responsavel": batch["responsavel"],
        "data": batch["data"],
        "semente": batch["semente"],
        "tamanho": batch["tamanho"],
        "amostrado": body["id"] in batch["ids"],
    }
    return True


def check_links(body: dict, evidence: dict):
    links = body.get("julgados_relacionados", [])
    if not isinstance(links, list):
        raise FloraError("pacote_invalido", "Julgados relacionados devem ser lista.")
    for link in links:
        if not isinstance(link, dict) or link.get("evidencia_vinculo") not in evidence:
            raise FloraError("pacote_invalido", "Vínculo de julgado exige evidência própria.")
        required_text(link.get("id"), "julgado.id")
        required_text(link.get("referencia"), "julgado.referencia")
        if "ementa" in link:
            required_text(link["ementa"], "julgado.ementa")
            if link.get("evidencia_ementa") not in evidence:
                raise FloraError("pacote_invalido", "Ementa vinculada exige evidência própria.")


def brazilian_date(value: str) -> str:
    """AAAA-MM-DD to dd/mm/aaaa, as in judgment references."""
    return date.fromisoformat(value).strftime("%d/%m/%Y")


def set_admission_and_reference(body: dict, reasons: list[str]):
    publication = body.get("data_publicacao")
    kind = PUBLICATIONS.get(body["tipo_publicacao"], "publicação de natureza não identificada")
    body["admissao"] = "excluido" if body["situacao"] in EXCLUDED else "pendente" if reasons else "admitido"
    body["motivos_admissao"] = sorted(set(reasons))
    body["referencia"] = (
        f"{body['tribunal']}, {LABELS[body['especie']]} n. {body['numero']}, {body['orgao']}"
        + (f", {kind} {brazilian_date(publication)}" if publication else "")
        + ". Fonte: "
        + body["fontes"][0]["url"]
    )
    body["referencia_completa"] = bool(publication)
    body["referencia_pendencias"] = [] if publication else ["data_publicacao"]


def prepare(
    record: dict, root: Path, source_cache=None, batch: dict | None = None
) -> tuple[dict, dict[str, bytes]]:
    """Validate source bytes and structure. Return a policy decision, never a URL-only admission.

    Blocks run in a fixed order and the first failure is the one reported. ``batch`` is the
    approved sample of the package, when the package declares a structured-source review.
    """
    if not isinstance(record, dict):
        raise FloraError("pacote_invalido", "Registro deve ser um objeto.")
    body = json.loads(canonical(record))
    check_identity(body)
    components = check_components(body)
    blobs = check_sources(body, root, source_cache)
    evidence = check_evidence(body, blobs)
    check_status(body)
    reasons = admission_reasons(body, components, evidence, batch)
    check_links(body, evidence)
    set_admission_and_reference(body, reasons)
    return body, blobs


def read_package(package_path: Path) -> dict:
    package = json.loads(package_path.read_text(encoding="utf-8-sig"))
    if not isinstance(package, dict) or package.get("schema") != "flora-precedentes-1":
        raise FloraError("pacote_invalido", "Esperado pacote flora-precedentes-1.")
    records = package.get("registros")
    if not isinstance(records, list) or not records:
        raise FloraError("pacote_invalido", "Pacote deve conter registros.")
    return package


def record_id(record) -> str:
    """Canonical identity of a raw record, with the same checks as prepare."""
    if not isinstance(record, dict):
        raise FloraError("pacote_invalido", "Registro deve ser um objeto.")
    body = json.loads(canonical(record))
    check_identity(body)
    return body["id"]


def required_keys(record: dict) -> set:
    """Evidence keys a sample verification must cover for this record."""
    components = record.get("componentes")
    names = components if isinstance(components, dict) else {}
    return {"situacao", "publicacao", "materia"} | {"componente:" + x for x in names}


def minimum_sample(size: int) -> int:
    """max(10, 5% of the batch rounded up), never more than the batch."""
    return min(size, max(10, math.ceil(size * 0.05)))


def draw(ids, seed: int, size: int) -> list[str]:
    """Reproducible draw: ids ordered by the SHA-256 of "seed:id", first ``size``."""
    return sorted(ids, key=lambda value: digest(f"{seed}:{value}".encode()))[:size]


def reject_sample(message: str):
    raise FloraError("amostra_reprovada", "Lote recusado: " + message)


def check_verifications(sample: dict, needed: dict[str, set]):
    checks = sample.get("verificacoes")
    if not isinstance(checks, list) or len(checks) != len(sample["ids"]):
        reject_sample("cada id sorteado exige uma verificação.")
    by_id = {check.get("id"): check for check in checks if isinstance(check, dict)}
    for value in sample["ids"]:
        check = by_id.get(value)
        if check is None:
            reject_sample(f"verificação ausente para {value}.")
        fields = check.get("campos_conferidos")
        if not isinstance(fields, list) or not needed[value] <= set(fields):
            reject_sample(f"verificação de {value} não cobre os campos obrigatórios.")
        if check.get("resultado") != "conforme":
            reject_sample(f"verificação de {value} não está conforme.")


def check_batch_review(package: dict, needed: dict[str, set]) -> dict | None:
    """Approved sample of a structured-source batch; any failure refuses the whole batch."""
    review = package.get("conferencia")
    if review is None:
        return None
    if not isinstance(review, dict) or review.get("modo") != BATCH_MODE:
        raise FloraError("pacote_invalido", "Conferência do lote exige modo fonte_estruturada.")
    sample = review.get("amostra")
    if not isinstance(sample, dict):
        reject_sample("amostra ausente.")
    check_draw(sample, needed)
    check_verifications(sample, needed)
    for field in ("responsavel", "data"):
        if not isinstance(sample.get(field), str) or not sample[field].strip():
            reject_sample(f"{field} da amostra é obrigatório.")
    if sample.get("resultado") != "aprovada":
        reject_sample("resultado da amostra não é aprovada.")
    return {
        "semente": sample["semente"],
        "tamanho": sample["tamanho"],
        "ids": set(sample["ids"]),
        "responsavel": sample["responsavel"],
        "data": sample["data"],
    }


def check_draw(sample: dict, needed: dict[str, set]):
    """Size, membership and reproducibility of the drawn ids."""
    seed, size, ids = sample.get("semente"), sample.get("tamanho"), sample.get("ids")
    if not isinstance(seed, int) or not isinstance(size, int) or not isinstance(ids, list):
        reject_sample("semente, tamanho e ids são obrigatórios.")
    minimum = minimum_sample(len(needed))
    if size < minimum or len(ids) != size:
        reject_sample(f"a amostra deve ter ao menos {minimum} registros sorteados.")
    if any(value not in needed for value in ids):
        reject_sample("id sorteado fora do lote.")
    if ids != draw(needed, seed, size):
        reject_sample("ids não correspondem ao sorteio da semente.")


def keeps_previous_state(old, body: dict) -> bool:
    """An incomplete observation of an admitted precedent is not evidence of withdrawal."""
    return bool(
        old
        and old["admission"] == "admitido"
        and body["admissao"] != "admitido"
        and body["situacao"] in {"vigente", "desconhecido"}
        and not body.get("pendencias")
    )


def retires_previous(old, body: dict) -> bool:
    return bool(
        old
        and old["admission"] == "admitido"
        and (body["admissao"] != "admitido" or json.loads(old["body"])["componentes"] != body["componentes"])
    )


def store_current(db, body: dict, sha: str, raw: str):
    db.execute(
        "INSERT INTO precedents VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "hash=excluded.hash,publication=excluded.publication,admission=excluded.admission,"
        "reasons=excluded.reasons,body=excluded.body,organ=excluded.organ",
        (
            body["id"],
            sha,
            body["tribunal"],
            body["especie"],
            body["numero"],
            folded(body["orgao"]),
            body.get("data_publicacao"),
            body["admissao"],
            canonical(body["motivos_admissao"]),
            raw,
        ),
    )
    db.execute("DELETE FROM precedent_texts WHERE id=?", (body["id"],))
    if body["admissao"] == "admitido":
        db.execute(
            "INSERT INTO precedent_texts(id,enunciado,questao_submetida,tese_firmada,modulacao,"
            "suspensao) "
            "VALUES (?,?,?,?,?,?)",
            (body["id"], *(body["componentes"].get(x, "") for x in COMPONENTS)),
        )


def stored_body(store: Store, body: dict, blobs: dict[str, bytes], *, save: bool) -> tuple[str, str]:
    """Body as recorded, with local paths of the originals; canonical text and its hash."""
    for source in body["fontes"]:
        if save:
            _, path = store.save_raw(blobs[source["sha256"]])
        else:
            path = store.raw_relative(source["sha256"])
        source["raw_path"] = path
        source.pop("arquivo", None)
    raw = canonical(body)
    return raw, digest(raw.encode())


def effect(db, body: dict, sha: str):
    """What recording this version does to the current state, with the previous row."""
    old = db.execute("SELECT hash,admission,body FROM precedents WHERE id=?", (body["id"],)).fetchone()
    if old and old[0] == sha:
        return "sem_alteracao", old
    if (
        body["admissao"] == "admitido"
        and db.execute(
            "SELECT 1 FROM precedent_retirements WHERE id=? AND hash=?", (body["id"], sha)
        ).fetchone()
    ):
        raise FloraError("versao_retirada", "Readmissão exige nova evidência; este conteúdo foi retirado.")
    if keeps_previous_state(old, body):
        return "estado_anterior_conservado", old
    if retires_previous(old, body):
        return "substitui_e_retira_anterior", old
    return ("atualiza" if old else "novo"), old


def apply_record(store: Store, db, body: dict, blobs: dict[str, bytes], entry: dict) -> bool:
    """Record one prepared precedent inside the open transaction; False when nothing changed."""
    raw, sha = stored_body(store, body, blobs, save=True)
    entry["efeito"], old = effect(db, body, sha)
    if entry["efeito"] == "sem_alteracao":
        return False
    db.execute("INSERT OR IGNORE INTO precedent_versions VALUES (?,?,?,?)", (body["id"], sha, raw, now()))
    db.execute(
        "INSERT INTO precedent_events(id,hash,observed,admission,reasons) VALUES (?,?,?,?,?)",
        (body["id"], sha, now(), body["admissao"], canonical(body["motivos_admissao"])),
    )
    if entry["efeito"] == "estado_anterior_conservado":
        # Retain the incomplete observation only in audit.
        entry["estado_anterior_conservado"] = True
        return True
    if entry["efeito"] == "substitui_e_retira_anterior":
        db.execute(
            "INSERT OR IGNORE INTO precedent_retirements VALUES (?,?,?)",
            (body["id"], old["hash"], now()),
        )
    store_current(db, body, sha, raw)
    return True


def simulate_effects(store: Store, prepared: list, entries: list):
    """Read-only preview against the current database, when there is one to compare with."""
    if not store.path.exists():
        return
    with connection(store.path) as db:
        if not available(db):
            return
        for (body, blobs), entry in zip(prepared, entries, strict=True):
            _, sha = stored_body(store, json.loads(canonical(body)), blobs, save=False)
            entry["efeito"], _ = effect(db, body, sha)


def import_package(store: Store, package_path: Path, *, apply: bool = False) -> dict:
    package = read_package(package_path)
    records = package["registros"]
    needed = {record_id(record): required_keys(record) for record in records}
    if len(needed) != len(records):
        raise FloraError("id_duplicado", "Pacote contém identidade duplicada.")
    batch = check_batch_review(package, needed)
    source_cache = {}
    prepared = [prepare(record, package_path.parent, source_cache, batch) for record in records]
    receipt = {
        "status": "ok",
        "aplicado": apply,
        "registros": [
            {"id": body["id"], "admissao": body["admissao"], "motivos": body["motivos_admissao"]}
            for body, _ in prepared
        ],
    }
    if batch is not None:
        receipt["conferencia_lote"] = {k: batch[k] for k in ("semente", "tamanho", "responsavel", "data")}
    if not apply:
        simulate_effects(store, prepared, receipt["registros"])
        return receipt
    with connection(store.path, write=True) as db, db:
        if not available(db):
            raise FloraError("migracao_pendente", "Execute a migração administrativa antes de importar.")
        db.execute("BEGIN IMMEDIATE")
        changed = False
        for (body, blobs), entry in zip(prepared, receipt["registros"], strict=True):
            changed = apply_record(store, db, body, blobs, entry) or changed
        if changed:
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
    receipt["alterado"] = changed
    return receipt
