"""List of process numbers to collect, from any origin: one reader, one key per process.

The list is a plain file and asks nothing of the vault. Text, one number per line (blank lines and
lines starting with # are skipped, "STJ:" or "TJSC:" may open a line), or JSON: a list, or an object
with "itens", of strings or of objects with "numero" and, optionally, "tribunal" and "origem".

A number of the TJSC is the key the portal search takes (see tjsc.process_key). A number of the STJ
is a process of a class: the mirrors have no CNJ number, and the sequence restarts in each class, so
REsp 123 and AREsp 123 are different processes and a bare 123 identifies neither. Any acórdão of the
process answers for it (AgInt no AREsp 123 and AREsp 123 are one key); so does the STJ registration
number (12 digits), which needs no class. What cannot be read is refused, with the reason, and never
sent to a source: a wrong number would come back as "not offered".
"""

import json
import re
from pathlib import Path

from .citations import short_classes, stj_class
from .model import FloraError, number
from .tjsc import CNJ, SAJ_CITED, SAJ_PORTAL, portal_number, process_key

TRIBUNAIS = ("STJ", "TJSC")
ORIGEM_PADRAO = "lista"
OPENING = re.compile(
    r"^\s*(?P<court>STJ|STF|TST|TSE|TJ[A-Z]{2}|TRF\d)\b(?:[\s:\-,]+|$)(?P<rest>.*)$", re.I | re.S
)
STJ_NUMBER = re.compile(
    r"^(?P<classe>[^\W\d_][^\d]*?)[\s:\-]*(?:n[.º°o]+\s*)?"
    r"(?P<numero>\d{1,3}(?:\.\d{3})+|\d{1,9})(?![\d.]*\d)"
)
REGISTRATION = re.compile(r"^\d{12}$")
# The class of the embargos keeps the number of the appeal they attack.
FAMILY = {"ERESP": "RESP", "EARESP": "ARESP"}
# Precedents have their own catalogs; here they would come back as "not offered".
NOT_A_PROCESS = {"TEMA", "SUMULA", "IRDR", "IAC"}


def stj_family(class_name: str) -> str:
    """Class of the process an acórdão belongs to: the last one named (AGINT NO ARESP is ARESP)."""
    words = stj_class(class_name).split()
    last = words[-1] if words else ""
    return FAMILY.get(last, last)


def stj_key(value: str) -> dict:
    """Key and display number of one STJ process, as written in a list."""
    text = str(value).strip()
    if REGISTRATION.fullmatch(number(text)) and not re.search(r"[^\W\d_]", text):
        registration = number(text)
        return {"chave": "REGISTRO:" + registration, "numero": "registro " + registration}
    match = STJ_NUMBER.match(short_classes(text))
    if not match:
        raise FloraError(
            "numero_invalido", f"Número do STJ precisa de classe e número, ou do registro: {value}."
        )
    family, digits = stj_family(match["classe"]), number(match["numero"]).lstrip("0")
    if not digits or family in NOT_A_PROCESS:
        raise FloraError("numero_invalido", f"Não é número de processo do STJ: {value}.")
    return {"chave": f"{family}:{digits}", "numero": f"{' '.join(match['classe'].split())} {digits}"}


def infer_court(text: str) -> str:
    """Court of a number given without one, from its shape; anything doubtful is refused."""
    cnj = CNJ.search(text)
    if cnj:
        if cnj[0].endswith(".8.24.0000") or ".8.24." in cnj[0]:
            return "TJSC"
        raise FloraError("tribunal_fora_da_coleta", f"Número CNJ de outro tribunal: {text}.")
    if SAJ_PORTAL.search(text) or SAJ_CITED.search(text):
        return "TJSC"
    digits = number(text)
    if not re.search(r"[^\W\d_]", text):
        if len(digits) == 12:
            return "STJ"
        if len(digits) in (11, 20):
            return "TJSC"
        raise FloraError("tribunal_ausente", f"Informe o tribunal do número: {text}.")
    return "STJ"


def read_item(value: str, court: str | None) -> tuple[str, str]:
    """Court and number of one item; the court written in the line wins over the given one."""
    text = str(value).strip()
    opening = OPENING.match(text)
    if opening:
        court, text = opening["court"], opening["rest"].strip()
    court = court.upper() if court else infer_court(text)
    if court not in TRIBUNAIS:
        raise FloraError("tribunal_fora_da_coleta", f"Coleta por número só cobre STJ e TJSC: {value}.")
    return court, text


def entry_for(value: str, court: str | None) -> dict:
    court, text = read_item(value, court)
    if court == "TJSC":
        key = process_key(text)
        return {"tribunal": "TJSC", "chave": key, "numero": portal_number(key)}
    return {"tribunal": "STJ", **stj_key(text)}


def merge(asked: list[tuple], default_court: str | None = None) -> tuple[list[dict], list[dict]]:
    """Numbers to collect, one per process with every origin that asked for it, and the refused.

    asked holds (number, court or None, origin).
    """
    merged, refused = {}, []
    for value, court, origin in asked:
        try:
            entry = entry_for(value, court or default_court)
        except FloraError as exc:
            refused.append(
                {"numero_informado": str(value), "origem": origin, "codigo": exc.code, "motivo": str(exc)}
            )
            continue
        saved = merged.setdefault((entry["tribunal"], entry["chave"]), {**entry, "origens": []})
        if origin not in saved["origens"]:
            saved["origens"].append(origin)
    return list(merged.values()), refused


def _json_items(data) -> list:
    items = data.get("itens") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise FloraError("lista_invalida", 'JSON da lista deve ser uma lista ou um objeto com "itens".')
    return items


def _item(item) -> tuple:
    if isinstance(item, str):
        return item, None, ORIGEM_PADRAO
    if isinstance(item, dict) and item.get("numero"):
        return str(item["numero"]), item.get("tribunal"), str(item.get("origem") or ORIGEM_PADRAO)
    raise FloraError("lista_invalida", 'Item da lista sem "numero".')


def read_list(path: Path) -> list[tuple]:
    """Items of one list file, as (number, court or None, origin)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    if text.lstrip()[:1] in ("[", "{"):
        try:
            return [_item(item) for item in _json_items(json.loads(text))]
        except ValueError as exc:
            raise FloraError("lista_invalida", "Lista JSON inválida.") from exc
    lines = (line.strip() for line in text.splitlines())
    return [(line, None, ORIGEM_PADRAO) for line in lines if line and not line.startswith("#")]
