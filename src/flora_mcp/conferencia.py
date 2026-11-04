"""Batch check of references against the loaded collection: by number, never by the text of a brief.

Each reference is one short string with a number: a CNJ number, with or without punctuation; a
class and number of the STJ ("AgInt no AREsp 1.779.343/DF"); a SAJ number of the TJSC
("AC 2006.011052-9"); a theme, summary, IRDR or IAC ("Tema 1.076", "Súmula 7 do STJ", "IRDR 17").
Whatever else the citation says (relator, organ, dates) is compared with the stored record and
reported as "confere" or "diverge", never corrected.

The answer says what the collection proves and nothing more:

- ``numero_invalido``: the CNJ check digit fails; refuted without the collection.
- ``localizado``: the record is loaded; its fields come with the comparison. A process with more
  than one acórdão lists them all and asks for a check, unless the citation singles one out.
- ``nao_localizado``: not loaded. The collection is partial, so this never means nonexistent.
- ``inexistente_na_fonte``: a theme number absent from the official catalog of the STJ, when the
  generation carries that catalog (``theme_catalog``); the catalog date is given.
- ``nao_reconhecida``: no number the tool knows how to check.
"""

import json
import re

from .citations import (
    CNJ_NUMBER,
    SAJ_NUMBER,
    STJ_CITATION,
    precedent_filter_key,
    short_classes,
    split_court,
    stj_class,
)
from .catalogo import catalog_entries, has_catalog
from .citation import citation_metadata
from .model import FloraError, folded
from .precedents import LABELS, available

LIMIT, LENGTH = 50, 200
STATES = ("numero_invalido", "localizado", "nao_localizado", "inexistente_na_fonte", "nao_reconhecida")
# CNJ segments J.TR of the courts the collection has, to the tribunal stored.
CNJ_COURTS = {"824": "TJSC"}
DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
RELATOR = re.compile(
    r"(?i)\brel(?:\.|ator[a]?)?\s*:?\s*(?:min(?:\.|istr[oa])?|des(?:\.|embargador[a]?)?|ju[ií]z[a]?)?"
    r"\s*(?:conv(?:ocad[oa])?\.?)?\s*(?P<nome>[^,;()]+?)\s*(?=[,;()]|\bj\.|$)"
)
ORGAO = re.compile(
    r"(?i)\b(?P<orgao>(?:[\wªº°]+\s+)?(?:c[âa]mara|turma|se[çc][ãa]o|grupo de c[âa]maras"
    r"|[óo]rg[ãa]o especial|corte especial|plen[áa]rio|tribunal pleno)[^,;()]*)"
)
AVISOS = [
    "nao_localizado não é inexistente: a base é parcial e só prova o que carregou; veja consultar_cobertura.",
    "confere e diverge comparam o texto da referência com o registro carregado; divergência pede "
    "conferência na fonte, não corrige a citação.",
    "localizado não afirma vigência nem autoridade; leia o documento com obter_documento antes de citar.",
]


def cnj_valid(digits: str) -> bool:
    """Check digit of a 20-digit CNJ number (Resolução CNJ 65/2008): 98 minus the rest modulo 97."""
    return 98 - int(digits[:7] + digits[9:] + "00") % 97 == int(digits[7:9])


def stated(reference: str) -> dict:
    """What the citation states, beyond the number: dates, relator and organ, when written."""
    found = {}
    dates = []
    for day, month, year in DATE.findall(reference):
        dates.append(f"{year}-{int(month):02d}-{int(day):02d}")
    if dates:
        found["datas"] = dates
    relator = RELATOR.search(reference)
    if relator and relator.group("nome").strip():
        found["relator"] = relator.group("nome").strip()
    organ = ORGAO.search(reference)
    if organ:
        found["orgao"] = organ.group("orgao").strip()
    return found


def compare(said: dict, record: dict) -> dict:
    """confere, diverge or nao_informado for each field the citation could state."""
    result = {}
    if "datas" in said:
        stored = {record.get("data_julgamento"), record.get("data_publicacao")} - {None}
        result["data"] = "confere" if stored & set(said["datas"]) else "diverge"
    else:
        result["data"] = "nao_informado"
    for field in ("relator", "orgao"):
        if field not in said:
            result[field] = "nao_informado"
        elif not record.get(field):
            result[field] = "nao_informado_na_fonte"
        else:
            a, b = folded(said[field]), folded(record[field])
            result[field] = "confere" if a in b or b in a else "diverge"
    return result


def recognize(reference: str) -> tuple[str, str] | tuple[None, None]:
    """(tipo, chave) of the number the reference carries: CNJ, STJ, SAJ or precedent."""
    court, rest = split_court(reference)
    cnj = CNJ_NUMBER.search(reference)
    if cnj:
        return "acordao_cnj", "".join(cnj.groups())
    stj = STJ_CITATION.search(short_classes(rest))
    if stj and court in {None, "STJ"}:
        return (
            "acordao_stj",
            f"STJ:{stj_class(stj.group('classe'))}:{int(stj.group('numero').replace('.', ''))}",
        )
    saj = SAJ_NUMBER.search(rest)
    if saj and court in {None, "TJSC"}:
        return "acordao_saj", "TJSC:" + "".join(saj.groups())
    try:
        return "precedente", precedent_filter_key(reference)
    except ValueError:
        pass
    if stj:
        return (
            "acordao_outro_tribunal",
            f"{court}:{stj_class(stj.group('classe'))}:{int(stj.group('numero').replace('.', ''))}",
        )
    return None, None


def judgment_rows(db, where: str, params) -> list[dict]:
    rows = db.execute(
        "SELECT d.id,d.body,(SELECT v.raw FROM versions v WHERE v.document_id=d.id AND v.hash=d.hash) AS raw "
        f"FROM documents d WHERE {where} ORDER BY d.judgment DESC,d.id",
        params,
    ).fetchall()
    found = []
    for row in rows:
        body = json.loads(row["body"])
        meta = citation_metadata(body, json.loads(row["raw"]) if row["raw"] else None)
        found.append(
            {
                "id": row["id"],
                "classe": body.get("classe"),
                "processo": body.get("processo"),
                "orgao": body.get("orgao"),
                "relator": meta["relator"],
                "data_julgamento": body.get("data_julgamento"),
                "data_publicacao": body.get("data_publicacao"),
                "referencia": meta["referencia"],
                "referencia_pendencias": meta["referencia_pendencias"],
                "hash_conteudo": body.get("hash_conteudo"),
            }
        )
    return found


def located(reference: str, records: list[dict]) -> dict:
    """The records found, each compared with what the citation says; several ask for a check.

    When the citation singles out one of several acórdãos (every field it states fits only that
    one), ``acordao_correspondente`` names it and the divergences of the others are not flagged.
    """
    said = stated(reference)
    for record in records:
        record["campos"] = compare(said, record)
    matching = [r for r in records if "diverge" not in r["campos"].values()]
    singled = [r for r in matching if any(v == "confere" for v in r["campos"].values())]
    chosen = singled[0] if len(records) > 1 and len(singled) == 1 else None
    scope = [chosen] if chosen else records
    check = sorted({k for r in scope for k, v in r["campos"].items() if v == "diverge"})
    if len(records) > 1:
        check.append("processo_com_varios_acordaos")
    item = {"estado": "localizado", "acordaos": records, "conferir": check}
    if chosen:
        item["acordao_correspondente"] = chosen["id"]
    return item


def not_located(reason: str) -> dict:
    return {"estado": "nao_localizado", "motivo": reason}


def check_judgment(db, tipo: str, key: str, reference: str) -> dict:
    if tipo == "acordao_cnj":
        if not cnj_valid(key):
            return {"estado": "numero_invalido", "motivo": "dígito verificador do número CNJ não confere"}
        court = CNJ_COURTS.get(key[13:16])
        if court is None:
            if key[13:16] == "300":
                return not_located("o espelho do STJ não traz o número CNJ; informe classe e número do STJ")
            return not_located("tribunal não coletado")
        records = judgment_rows(db, "d.tribunal=? AND d.process=?", (court, key))
    elif tipo == "acordao_stj":
        _, klass, number = key.split(":", 2)
        records = judgment_rows(db, "d.tribunal='STJ' AND d.class=? AND d.process=?", (klass, number))
    elif tipo == "acordao_saj":
        records = judgment_rows(db, "d.tribunal='TJSC' AND d.process=?", (key[5:],))
    else:
        return not_located("tribunal não coletado")
    if not records:
        return not_located("não carregado nesta base")
    return located(reference, records)


def check_precedent(db, view, key: str) -> dict:
    row = (
        db.execute("SELECT body,admission,hash FROM precedents WHERE id=?", (key,)).fetchone()
        if available(db)
        else None
    )
    served = (
        row is not None
        and row["admission"] == "admitido"
        and key not in view.withdrawn
        and key + ":" + row["hash"] not in view.retired_versions
    )
    catalog = catalog_entries(db, [key]).get(key)
    if served:
        body = json.loads(row["body"])
        item = {
            "estado": "localizado",
            "precedente": {
                "id": key,
                "referencia": body.get("referencia"),
                "orgao": body.get("orgao"),
                "situacao": body.get("situacao"),
                "materia": body.get("materia"),
                "data_publicacao": body.get("data_publicacao"),
                "componentes_disponiveis": list(body.get("componentes", {})),
            },
        }
        if catalog:
            item["precedente"]["situacao_fonte"] = catalog["situacao_fonte"]
        return item
    if catalog:
        return {
            "estado": "nao_localizado",
            "motivo": "não servido nesta base",
            "situacao_fonte": catalog["situacao_fonte"],
            "catalogo": {"fonte": catalog["fonte_url"], "coletado_em": catalog["coletado_em"]},
        }
    if key.startswith("STJ:tema_repetitivo:") and has_catalog(db):
        date = db.execute("SELECT max(coletado_em) FROM theme_catalog").fetchone()[0]
        return {
            "estado": "inexistente_na_fonte",
            "motivo": "número ausente do catálogo oficial de temas do STJ (temas.csv dos dados abertos)",
            "catalogo": {"coletado_em": date},
        }
    return not_located("não admitido nesta base; a coleção de precedentes é parcial")


def check(view, referencias) -> dict:
    if not isinstance(referencias, list) or not 1 <= len(referencias) <= LIMIT:
        raise FloraError("parametro_invalido", f"referencias: lista de 1 a {LIMIT} referências.")
    for value in referencias:
        if not isinstance(value, str) or not value.strip() or len(value) > LENGTH:
            raise FloraError(
                "parametro_invalido",
                f"Cada referência é um texto de até {LENGTH} caracteres com o número citado; "
                "texto de peça não é aceito.",
            )
    items = []
    with view.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        for value in referencias:
            reference = " ".join(value.split())
            tipo, key = recognize(reference)
            item = {"referencia": reference, "tipo": tipo, "chave": key}
            if tipo is None:
                item.update(
                    estado="nao_reconhecida", motivo="nenhum número CNJ, do STJ, do SAJ ou de precedente"
                )
            elif tipo == "precedente":
                item.update(check_precedent(db, view, key))
            else:
                item.update(check_judgment(db, tipo, key, reference))
            items.append(item)
    summary = {state: sum(i["estado"] == state for i in items) for state in STATES}
    return {
        "status": "ok",
        "referencias": items,
        "resumo": summary,
        "revisao_base": revision,
        "avisos": AVISOS,
    }


__all__ = ["check", "cnj_valid", "recognize", "stated", "compare", "LABELS"]
