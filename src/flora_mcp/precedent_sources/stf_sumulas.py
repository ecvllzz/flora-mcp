"""STF summaries and binding summaries, from the official summary index and summary pages.

The index (sumariosumulas.asp?base=30 or base=26) gives the number and the status marker of
each summary; the page of a summary (same address with &sumula=<id>) gives the statement and
the publication date of the statement. Pages do not print a branch of law, so the matter stays
unconfirmed.
"""

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .common import Original, Result, iso_date

CLASSE = "estruturada"
BASES = {"30": "sumula", "26": "sumula_vinculante"}
# Marker in parentheses after the label in the index. No marker: listed as current.
MARCADORES = {"cancelada": "cancelado", "revogada": "revogado", "superada": "superado"}
# The summary pages name no organ; summaries are of the Court itself.
ORGAO = "Supremo Tribunal Federal"
ROTULO = re.compile(r"Súmula(?P<vinculante> Vinculante)? (?P<numero>\d+)(?: \((?P<marcador>[^()]+)\))?")
PUBLICACAO = re.compile(
    r"Data de publicação do enunciado:\s*(?P<rotulo>DJE|DJe|DJ)\s+de\s+"
    r"(?P<dia>\d{1,2})-(?P<mes>\d{1,2})-(?P<ano>\d{4})"
)


def address(url: str) -> tuple[str, str | None] | None:
    query = parse_qs(urlparse(url).query)
    base = query.get("base", [None])[0]
    if base not in BASES:
        return None
    return base, query.get("sumula", [None])[0]


def role(url: str) -> str | None:
    found = address(url)
    if found is None:
        return None
    return "pagina" if found[1] else "indice"


def index_entries(original: Original) -> dict[tuple[str, str], tuple[str, str, str | None]]:
    """(base, page id) -> (number, literal label, marker) for each summary of the index."""
    base = address(original.url)[0]
    entries = {}
    for anchor in BeautifulSoup(original.text(), "html.parser").find_all("a", href=True):
        label = anchor.get_text(" ", strip=True)
        match = ROTULO.fullmatch(label)
        target = address(urljoin(original.url, anchor["href"]))
        if match and target and target[0] == base and target[1]:
            entries[target] = (match["numero"], label, match["marcador"])
    return entries


def page_parts(original: Original) -> tuple[re.Match | None, str, list[re.Match]]:
    """Title of the summary, statement below it and publication labels of the page."""
    page = BeautifulSoup(original.text(), "html.parser")
    title = page.select_one("div.titulo")
    heading = ROTULO.fullmatch(title.get_text(" ", strip=True)) if title else None
    body = title.find_next_sibling("div", class_="parCOM") if title else None
    text = body.get_text().strip() if body else ""
    return heading, text, list(PUBLICACAO.finditer(page.get_text()))


def record(page: Original, index: Original, entry: tuple, species: str) -> dict | str:
    number, label, marker = entry
    heading, text, publications = page_parts(page)
    if (
        heading is None
        or heading["numero"] != number
        or bool(heading["vinculante"]) != (species == "sumula_vinculante")
    ):
        return "titulo_diverge_do_indice"
    page_id = address(page.url)[1]
    status = MARCADORES.get(marker, "desconhecido") if marker else "vigente"
    evidence = {"situacao": index.evidence(label, f"{index.arquivo}, âncora do índice para sumula={page_id}")}
    found = publications[0] if len(publications) == 1 else None
    published = iso_date(found["dia"], found["mes"], found["ano"]) if found else None
    if published:
        evidence["publicacao"] = page.evidence(
            found.group(0), f"{page.arquivo}, rótulo 'Data de publicação do enunciado'"
        )
    if text:
        evidence["componente:enunciado"] = page.evidence(
            text, f"{page.arquivo}, div.parCOM após div.titulo '{heading.group(0)}'"
        )
    return {
        "tribunal": "STF",
        "especie": species,
        "numero": number,
        "orgao": ORGAO,
        "materia": None,
        "data_publicacao": published,
        "tipo_publicacao": "enunciado",
        "situacao": status,
        "pendencias": [] if len(publications) < 2 else ["publicacao_ambigua"],
        "componentes": {"enunciado": text} if text else {},
        "fontes": [page.source(), index.source()],
        "evidencias": evidence,
        "julgados_relacionados": [],
    }


def adapt(originals: list[Original]) -> Result:
    indexes = {address(o.url)[0]: o for o in originals if role(o.url) == "indice"}
    entries = {}
    for index in indexes.values():
        entries.update(index_entries(index))
    result, seen = Result(), set()
    for page in sorted((o for o in originals if role(o.url) == "pagina"), key=lambda o: o.arquivo):
        key = address(page.url)
        entry = entries.get(key)
        species = BASES[key[0]]
        if entry is None:
            result.ignore(page.arquivo, "fora_do_indice")
            continue
        if (species, entry[0]) in seen:
            result.ignore(page.arquivo, "identidade_repetida")
            continue
        body = record(page, indexes[key[0]], entry, species)
        if isinstance(body, str):
            result.ignore(page.arquivo, body)
            continue
        seen.add((species, entry[0]))
        result.registros.append(body)
    return result
