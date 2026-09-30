"""Human-readable identification from the exact preserved document version."""

import re
from datetime import date


def _text(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _date(value) -> str:
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def citation_metadata(body: dict, raw: dict | None) -> dict:
    """Read through to originals, so existing records need no migration or recollection.

    Names and class descriptions come only from metadata, never ementa inference.
    Completeness concerns identification fields, not legal authority or full text.
    """
    raw = raw if isinstance(raw, dict) else {}
    tribunal = _text(body.get("tribunal"))
    relator = ""
    description = ""
    if tribunal == "STJ":
        relator = _text(raw.get("ministroRelator"))
        description = _text(raw.get("descricaoClasse"))
    elif tribunal == "TJSC":
        fields = raw.get("campos", {})
        fields = fields if isinstance(fields, dict) else {}
        relator = _text(fields.get("RELATOR")) or _text(fields.get("RELATORA"))
        process = _text(fields.get("PROCESSO")) or _text(body.get("processo_original"))
        match = re.search(r"/TJSC\s+\w+\s+-\s+(.+)$", process)
        description = match[1] if match else ""
    class_name = description or _text(body.get("classe"))
    process_number = _text(body.get("numero_processo"))
    organ = _text(body.get("orgao"))
    judgment = _date(body.get("data_julgamento"))
    publication = _date(body.get("data_publicacao"))
    required = {
        "tribunal": tribunal,
        "classe": class_name,
        "numero_processo": process_number,
        "relator": relator,
        "orgao": organ,
        "data_julgamento": judgment,
        "data_publicacao": publication,
    }
    missing = [key for key, value in required.items() if not value]
    unavailable = "[não informado na fonte]"
    publication_label = (
        "publ. " + publication
        if publication
        else (
            "publicação na fonte: " + _text(body.get("publicacao_original"))
            if _text(body.get("publicacao_original"))
            else "publ. " + unavailable
        )
    )
    reference = ", ".join(
        [
            tribunal or "[tribunal não informado na fonte]",
            f"{class_name or '[classe não informada na fonte]'} n. {process_number or unavailable}",
            "rel. " + (relator or unavailable),
            organ or "[órgão não informado na fonte]",
            "j. " + (judgment or unavailable),
            publication_label,
        ]
    )
    return {
        "relator": relator or None,
        "classe_descricao": description or None,
        "referencia": "(" + reference + ")",
        "referencia_completa": not missing,
        "referencia_pendencias": missing,
    }
