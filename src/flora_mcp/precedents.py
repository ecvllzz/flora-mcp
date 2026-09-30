"""Qualified precedents: explicit evidence, literal components and auditable admission.

The importer consumes a reviewed source package. It never treats a mention in an
ordinary judgment, an official URL alone or a collector's success as legal status.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .model import FloraError, canonical, digest, folded, now
from .store import Store, connection

SCHEMA_VERSION = 2
COMPONENTS = ("enunciado", "questao_submetida", "tese_firmada", "modulacao", "suspensao")
SPECIES = {
    "STJ": {"tema_repetitivo", "iac", "sumula"},
    "STF": {"tema_repercussao_geral", "sumula_vinculante", "sumula"},
    "TJSC": {"sumula"},
}
LABELS = {"tema_repetitivo": "Tema repetitivo", "iac": "IAC", "sumula": "Súmula",
          "tema_repercussao_geral": "Tema de repercussão geral", "sumula_vinculante": "Súmula vinculante"}
PUBLICATIONS = {"enunciado": "publicação do enunciado", "acordao_merito": "publicação do acórdão de mérito",
                "acordao_embargos": "publicação do acórdão de embargos"}
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
 INSERT INTO precedent_search(precedent_search,rowid,enunciado,questao_submetida,tese_firmada,modulacao,suspensao)
 VALUES('delete',old.rowid,old.enunciado,old.questao_submetida,old.tese_firmada,old.modulacao,old.suspensao);
END;
UPDATE meta SET value=2 WHERE key='schema';
UPDATE meta SET value=value+1 WHERE key='revision';
"""


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


def prepare(record: dict, root: Path, source_cache=None) -> tuple[dict, dict[str, bytes]]:
    """Validate source bytes and structure. Return a policy decision, never a URL-only admission."""
    if not isinstance(record, dict):
        raise FloraError("pacote_invalido", "Registro deve ser um objeto.")
    body = json.loads(canonical(record))
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
    components = body.get("componentes")
    if not isinstance(components, dict) or set(components) - set(COMPONENTS):
        raise FloraError("pacote_invalido", "Componentes inválidos; ementas pertencem aos julgados associados.")
    for name, value in components.items():
        required_text(value, name)
    if species in {"sumula", "sumula_vinculante"} and "tese_firmada" in components:
        raise FloraError("pacote_invalido", "Texto de súmula deve usar enunciado.")
    if species not in {"sumula", "sumula_vinculante"} and "enunciado" in components:
        raise FloraError("pacote_invalido", "Tema usa questão submetida e tese firmada.")
    sources = body.get("fontes")
    if not isinstance(sources, list) or not sources:
        raise FloraError("pacote_invalido", "Fontes oficiais preservadas são obrigatórias.")
    blobs = {}
    for source in sources:
        if not isinstance(source, dict) or not official(source.get("url", ""), tribunal):
            raise FloraError("fonte_invalida", "Fonte deve pertencer ao tribunal do registro e usar HTTPS.")
        sha = source.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise FloraError("pacote_invalido", "Hash de fonte inválido.")
        path = (root / required_text(source.get("arquivo"), "arquivo")).resolve()
        if not path.is_relative_to(root.resolve()):
            raise FloraError("pacote_invalido", "Original fora do pacote.")
        cache = source_cache if source_cache is not None else {}
        key = (path, sha)
        if key not in cache:
            cache[key] = path.read_bytes()
        content = cache[key]
        if digest(content) != sha:
            raise FloraError("arquivo_corrompido", "Original diverge do hash declarado.")
        try:
            collected = datetime.fromisoformat(source["coletado_em"])
            if collected.tzinfo is None:
                raise ValueError()
        except (KeyError, ValueError, TypeError) as exc:
            raise FloraError("pacote_invalido", "Coleta exige data/hora com fuso.") from exc
        blobs[sha] = content
    evidence = body.get("evidencias", {})
    if not isinstance(evidence, dict):
        raise FloraError("pacote_invalido", "Evidências devem ser um objeto.")
    for key, item in evidence.items():
        if not isinstance(item, dict) or item.get("fonte_sha256") not in blobs:
            raise FloraError("pacote_invalido", f"Evidência {key} sem fonte preservada.")
        required_text(item.get("trecho"), f"evidencias.{key}.trecho")
        required_text(item.get("localizador"), f"evidencias.{key}.localizador")
    status = body.get("situacao")
    if status not in STATUSES:
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
    reasons = list(flags)
    if status != "vigente":
        reasons.append("situacao_" + status)
    if body.get("materia") not in {"civil", "processual_civil"}:
        reasons.append("materia_nao_confirmada")
    needed = {"situacao", "publicacao", "materia"} | {"componente:" + x for x in components}
    reasons += ["evidencia_ausente:" + x for x in sorted(needed - set(evidence))]
    if not publication:
        reasons.append("publicacao_ausente")
    main = "enunciado" if species in {"sumula", "sumula_vinculante"} else "tese_firmada"
    publication_type = body.get("tipo_publicacao", "enunciado" if main == "enunciado" else None)
    if publication_type not in PUBLICATIONS:
        reasons.append("tipo_publicacao_nao_informado")
    body["tipo_publicacao"] = publication_type
    if not components.get(main):
        reasons.append(main + "_ausente")
    # A reviewed evidence packet is an explicit input, not inferred from populated metadata.
    review = body.get("conferencia", {})
    if not isinstance(review, dict) or review.get("evidencias_conferidas") is not True:
        reasons.append("conferencia_pendente")
    else:
        required_text(review.get("responsavel"), "conferencia.responsavel")
        required_text(review.get("data"), "conferencia.data")
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
    body["admissao"] = "excluido" if status in EXCLUDED else "pendente" if reasons else "admitido"
    body["motivos_admissao"] = sorted(set(reasons))
    body["referencia"] = (
        f"{tribunal}, {LABELS[species]} n. {number}, {organ}"
        + (f", {PUBLICATIONS.get(publication_type, 'publicação de natureza não identificada')} {publication}" if publication else "")
        + ". Fonte: " + sources[0]["url"]
    )
    body["referencia_completa"] = bool(publication)
    body["referencia_pendencias"] = [] if publication else ["data_publicacao"]
    return body, blobs


def import_package(store: Store, package_path: Path, *, apply: bool = False) -> dict:
    package = json.loads(package_path.read_text(encoding="utf-8-sig"))
    if not isinstance(package, dict) or package.get("schema") != "flora-precedentes-1":
        raise FloraError("pacote_invalido", "Esperado pacote flora-precedentes-1.")
    records = package.get("registros")
    if not isinstance(records, list) or not records:
        raise FloraError("pacote_invalido", "Pacote deve conter registros.")
    source_cache = {}
    prepared = [prepare(record, package_path.parent, source_cache) for record in records]
    if len({body["id"] for body, _ in prepared}) != len(prepared):
        raise FloraError("id_duplicado", "Pacote contém identidade duplicada.")
    receipt = {"status": "ok", "aplicado": apply, "registros": [
        {"id": body["id"], "admissao": body["admissao"], "motivos": body["motivos_admissao"]}
        for body, _ in prepared]}
    if not apply:
        return receipt
    with connection(store.path, write=True) as db, db:
        if not available(db):
            raise FloraError("migracao_pendente", "Execute a migração administrativa antes de importar.")
        db.execute("BEGIN IMMEDIATE")
        changed = False
        for body, blobs in prepared:
            for source in body["fontes"]:
                _, path = store.save_raw(blobs[source["sha256"]])
                source["raw_path"] = path
                source.pop("arquivo", None)
            raw = canonical(body)
            sha = digest(raw.encode())
            old = db.execute("SELECT hash,admission,body FROM precedents WHERE id=?", (body["id"],)).fetchone()
            if old and old[0] == sha:
                continue
            if body["admissao"] == "admitido" and db.execute("SELECT 1 FROM precedent_retirements WHERE id=? AND hash=?", (body["id"], sha)).fetchone():
                raise FloraError("versao_retirada", "Readmissão exige nova evidência; este conteúdo foi retirado.")
            changed = True
            db.execute("INSERT OR IGNORE INTO precedent_versions VALUES (?,?,?,?)", (body["id"], sha, raw, now()))
            db.execute("INSERT INTO precedent_events(id,hash,observed,admission,reasons) VALUES (?,?,?,?,?)",
                       (body["id"], sha, now(), body["admissao"], canonical(body["motivos_admissao"])))
            if (old and old["admission"] == "admitido" and body["admissao"] != "admitido"
                    and body["situacao"] in {"vigente", "desconhecido"} and not body.get("pendencias")):
                # An incomplete observation is not evidence of withdrawal. Retain it only in audit.
                next(x for x in receipt["registros"] if x["id"] == body["id"])["estado_anterior_conservado"] = True
                continue
            if old and old["admission"] == "admitido" and (
                    body["admissao"] != "admitido" or json.loads(old["body"])["componentes"] != body["componentes"]):
                db.execute("INSERT OR IGNORE INTO precedent_retirements VALUES (?,?,?)", (body["id"], old["hash"], now()))
            db.execute("INSERT INTO precedents VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "hash=excluded.hash,publication=excluded.publication,admission=excluded.admission,"
                       "reasons=excluded.reasons,body=excluded.body,organ=excluded.organ",
                       (body["id"], sha, body["tribunal"], body["especie"], body["numero"],
                        folded(body["orgao"]), body.get("data_publicacao"), body["admissao"],
                        canonical(body["motivos_admissao"]), raw))
            db.execute("DELETE FROM precedent_texts WHERE id=?", (body["id"],))
            if body["admissao"] == "admitido":
                db.execute("INSERT INTO precedent_texts(id,enunciado,questao_submetida,tese_firmada,modulacao,suspensao) "
                           "VALUES (?,?,?,?,?,?)", (body["id"], *(body["componentes"].get(x, "") for x in COMPONENTS)))
        if changed:
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
    receipt["alterado"] = changed
    return receipt
