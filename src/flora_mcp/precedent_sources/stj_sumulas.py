"""STJ summaries, from the SCON listing pages (div.gridSumula, one block per summary).

The statement is the verbete text before the single reference in parentheses
"(ORGAO, julgado em DATA, DJe DATA)"; a block without exactly one such reference at its end is
left out, never cut by guess.
"""

import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .common import Original, Result, branch_matter, iso_date, section_flag

CLASSE = "estruturada"
# Marker span.clsINDE next to the number. No marker: the listing presents the summary as current.
MARCADORES = {"CANCELADA": "cancelado", "REVOGADA": "revogado", "SUPERADA": "superado"}
# Branch printed before " - " in span.ramoSumula.
RAMOS = {
    "DIREITO CIVIL": "civil",
    "DIREITO DO CONSUMIDOR": "civil",
    "DIREITO EMPRESARIAL": "civil",
    "DIREITO PROCESSUAL CIVIL": "processual_civil",
}
DATA = r"\d{1,2}/\d{1,2}/\d{4}"
# Labels of the official gazette; REP marks a republication and never gives the publication date.
ROTULOS = r"REPDJe|REPDJ|DJEN|DJe|DJ"
PUBLICACAO = re.compile(
    r"(?P<rotulo>" + ROTULOS + r")\s+(?:de\s+)?(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{4})"
)
# Old entries print the gazette page after the date: "DJ 10/04/2006, p. 126".
PUBLICACOES = r"(?:" + ROTULOS + r")\s+(?:de\s+)?" + DATA + r"(?:,?\s*p\.\s*\d+)?"
REFERENCIA = re.compile(
    r"\(\s*(?:SÚMULA\s+\d+\s*,\s*)?(?P<orgao>[^,()]+?)\s*,\s*julgad[oa]\s+em\s+" + DATA + r"\s*,\s*"
    r"(?P<publicacoes>" + PUBLICACOES + r"(?:\s*,\s*" + PUBLICACOES + r")*)\s*\)"
)


def role(url: str) -> str | None:
    """Only the paged listing (i=<first>&l=<count>); a single-summary page is not read."""
    query = parse_qs(urlparse(url).query)
    return "listagem" if "/SCON/sumstj/toc.jsp" in url and "i" in query and "l" in query else None


def statement(block) -> tuple[str, re.Match] | None:
    """Statement and reference of a verbete, or None when they are not delimited."""
    verbete = block.select_one("div.blocoVerbete")
    if verbete is None:
        return None
    for tag in verbete.select("span.ramoSumula, span.clsCOM"):
        tag.extract()
    text = verbete.get_text()
    matches = list(REFERENCIA.finditer(text))
    if len(matches) != 1 or text[matches[0].end() :].strip():
        return None
    return text[: matches[0].start()].strip(), matches[0]


def situation(original: Original, block, where: str) -> tuple[str, dict]:
    marker = block.select_one("span.clsINDE")
    if marker is None:
        heading = block.select_one("div.blocoNumSumula").get_text(" ", strip=True)
        return "vigente", original.evidence(heading, f"{where}, div.blocoNumSumula sem span.clsINDE")
    text = marker.get_text(strip=True)
    return MARCADORES.get(text, "desconhecido"), original.evidence(text, f"{where}, span.clsINDE")


def record(original: Original, block, number: str) -> dict | None:
    where = f"{original.arquivo}, div.gridSumula com span.numeroSumula {number}"
    branch = block.select_one("span.ramoSumula")
    branch_text = branch.get_text(strip=True) if branch else ""
    delimited = statement(block)
    if delimited is None:
        return None
    text, reference = delimited
    status, status_evidence = situation(original, block, where)
    evidence = {"situacao": status_evidence}
    first = [p for p in PUBLICACAO.finditer(reference["publicacoes"]) if not p["rotulo"].startswith("REP")]
    published = iso_date(first[0]["dia"], first[0]["mes"], first[0]["ano"]) if len(first) == 1 else None
    if published:
        evidence["publicacao"] = original.evidence(
            reference.group(0),
            f"{where}, div.blocoVerbete, referência entre parênteses após o enunciado, "
            f"rótulo {first[0]['rotulo']}",
        )
    if branch_text:
        evidence["materia"] = original.evidence(branch_text, f"{where}, span.ramoSumula")
    if text:
        evidence["componente:enunciado"] = original.evidence(
            text, f"{where}, div.blocoVerbete, do ramo à referência entre parênteses"
        )
    # The name may wrap across source lines; only its whitespace is normalized.
    organ = " ".join(reference["orgao"].split())
    flags = ["publicacao_ambigua"] if len(first) > 1 else []
    return {
        "tribunal": "STJ",
        "especie": "sumula",
        "numero": number,
        "orgao": organ,
        "materia": branch_matter([branch_text.split(" - ")[0].strip()] if branch_text else [], RAMOS),
        "data_publicacao": published,
        "tipo_publicacao": "enunciado",
        "situacao": status,
        "pendencias": flags + [f for f in (section_flag(organ),) if f],
        "componentes": {"enunciado": text} if text else {},
        "fontes": [original.source()],
        "evidencias": evidence,
        "julgados_relacionados": [],
    }


def adapt(originals: list[Original]) -> Result:
    result, seen = Result(), set()
    for original in sorted(originals, key=lambda o: o.url):
        page = BeautifulSoup(original.text(), "html.parser")
        for block in page.select("div.gridSumula"):
            number_tag = block.select_one("span.numeroSumula")
            number = number_tag.get_text(strip=True) if number_tag else ""
            reference = f"{original.arquivo}, Súmula {number or '?'}"
            if not re.fullmatch(r"[1-9][0-9]{0,6}", number):
                result.ignore(reference, "numero_invalido")
            elif number in seen:
                result.ignore(reference, "identidade_repetida")
            elif (body := record(original, block, number)) is None:
                result.ignore(reference, "verbete_fora_do_padrao")
            else:
                seen.add(number)
                result.registros.append(body)
    return result
