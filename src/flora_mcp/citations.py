"""Citations as data: precedents, acórdãos and statutory provisions cited by each acórdão.

The source is the stored original: the two closing lines of the CNJ-model ementa of the TJSC
("Dispositivos relevantes citados" and "Jurisprudência relevante citada") and the fields
``jurisprudenciaCitada``, ``referenciasLegislativas``, ``tema`` and ``acordaosSimilares`` of the STJ
mirror. Every citation keeps the literal fragment it came from; the key is a normalization, not a
verification, and an unparsed fragment is kept with an empty key so the loss is visible.

Keys (``chave``) by type (``tipo``):

- ``precedente``: the precedent identity of the collection (``STJ:tema_repetitivo:908``,
  ``STJ:sumula:7``, ``STF:sumula_vinculante:10``, ``TJSC:irdr:17``).
- ``acordao``: ``TJSC:<20 digits>`` for CNJ numbers of any state court (``TJSP:...``), and
  ``STJ:<CLASSE>:<número>`` for the STJ (``STJ:AGINT NO ARESP:1779343``), the class as the
  acervo stores it.
- ``dispositivo``: ``<DIPLOMA>:<artigo>`` (``CPC:85``, ``CC:1634``, ``LEI 8.560/1992:2``).
- ``similar``: ``STJ:<CLASSE>:<número>`` of the acórdãos the STJ itself lists as similar.
"""

import re

from .model import folded
from .text import sections

CITATIONS_DERIVER = "citacoes-1"
TYPES = ("precedente", "acordao", "dispositivo", "similar")

# Statutes by the names the TJSC writes and by the STJ aliases, to one key each.
DIPLOMAS = {
    "CPC": "CPC",
    "CPC/2015": "CPC",
    "CPC/15": "CPC",
    "NCPC": "CPC",
    "CODIGO DE PROCESSO CIVIL": "CPC",
    "CPC/1973": "CPC/1973",
    "CPC/73": "CPC/1973",
    "CC": "CC",
    "CC/2002": "CC",
    "CC/02": "CC",
    "CODIGO CIVIL": "CC",
    "CC/1916": "CC/1916",
    "CC/16": "CC/1916",
    "CF": "CF",
    "CF/1988": "CF",
    "CF/88": "CF",
    "CRFB": "CF",
    "CRFB/1988": "CF",
    "CRFB/88": "CF",
    "CONSTITUICAO FEDERAL": "CF",
    "CONSTITUICAO DA REPUBLICA": "CF",
    "ECA": "ECA",
    "ESTATUTO DA CRIANCA E DO ADOLESCENTE": "ECA",
    "CDC": "CDC",
    "CODIGO DE DEFESA DO CONSUMIDOR": "CDC",
    "CLT": "CLT",
    "CTN": "CTN",
    "CP": "CP",
    "CPP": "CPP",
    "LINDB": "LINDB",
    "RISTJ": "RISTJ",
}
# STJ numeric references of the codes above.
STJ_CODES = {
    ("LEI", "13105", "2015"): "CPC",
    ("LEI", "5869", "1973"): "CPC/1973",
    ("LEI", "10406", "2002"): "CC",
    ("LEI", "3071", "1916"): "CC/1916",
    ("LEI", "8069", "1990"): "ECA",
    ("LEI", "8078", "1990"): "CDC",
    ("LEI", "5172", "1966"): "CTN",
    ("DEL", "5452", "1943"): "CLT",
    ("DEL", "2848", "1940"): "CP",
    ("DEL", "3689", "1941"): "CPP",
    ("DEL", "4657", "1942"): "LINDB",
}
STJ_KINDS = {"LEI": "LEI", "LCP": "LC", "DEL": "DL", "DEC": "DECRETO", "MPR": "MP", "RES": "RESOLUCAO"}

DIPLOMA_ANCHOR = re.compile(
    r"(?i)(?<![\w/])(?P<diploma>"
    r"C[óo]digo (?:Civil|de Processo Civil|de Defesa do Consumidor)|"
    r"Constitui[çc][ãa]o (?:Federal|da Rep[úu]blica)|Estatuto da Crian[çc]a e do Adolescente|"
    r"Lei(?: Complementar)?(?: n[.º°o]*)?\s*[\d.]+/\d{2,4}|Decreto(?:-Lei)?(?: n[.º°o]*)?\s*[\d.]+/\d{2,4}|"
    r"(?:CPC|CC|CF|CRFB|ECA|CDC|CLT|CTN|CPP|CP|LINDB|RISTJ|NCPC)(?:/\d{2,4})?"
    r")(?![\w/])"
)
ARTICLE = re.compile(r"^(\d{1,4}(?:\.\d{3})*)(?:\s*[ºo°])?(?:-([A-Z]))?$")
COMPLEMENT = re.compile(r"(?i)^(?:§|§§|par[áa]grafo|inciso|inc\.|al[íi]nea|caput|[IVXLC]+\b|[a-z]\))")

PRECEDENT = re.compile(
    r"(?i)\b(?:(?P<tema>Tema(?:s)?(?: de)?(?: Repercuss[ãa]o Geral| Repetitivo| RG| STJ| STF)?\s*n?[.º°o]*\s*"
    r"(?P<tema_n>\d{1,3}(?:\.\d{3})?|\d{1,5}))|"
    r"(?P<sumula>S[úu]mula(?P<vinc> Vinculante)?\s*n?[.º°o]*\s*(?P<sumula_n>\d{1,3}(?:\.\d{3})?|\d{1,4}))|"
    r"(?P<irdr>IRDR\s*n?[.º°o]*\s*(?P<irdr_n>\d{1,4}))|(?P<iac>IAC\s*n?[.º°o]*\s*(?P<iac_n>\d{1,4})))"
)
CNJ_NUMBER = re.compile(r"\b(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\b")
STJ_CLASSES = (
    "AgInt|AgRg|EDcl|EREsp|EAREsp|AREsp|REsp|RMS|RHC|HC|CC|RE|ARE|ADI|ADPF|ADC|Rcl|MS|Pet|AR|"
    "EmbDiv|AgInt|SLS|SS|CR|HD|MI|RO"
)
STJ_CITATION = re.compile(
    rf"\b(?P<classe>(?:(?:{STJ_CLASSES})(?:\s+n[oa]s?\s+)?)+)\s*(?:n[.º°o]*)?\s*(?P<numero>\d{{1,3}}(?:\.\d{{3}})+|\d{{1,8}})"
    r"(?:\s*/\s*(?P<uf>[A-Z]{2}))?"
)
LONG_CLASSES = (
    ("agravo interno", "AgInt"),
    ("agravo regimental", "AgRg"),
    ("embargos de declaração", "EDcl"),
    ("embargos de declaracao", "EDcl"),
    ("embargos de divergência em agravo em recurso especial", "EAREsp"),
    ("embargos de divergência em recurso especial", "EREsp"),
    ("embargos de divergencia em recurso especial", "EREsp"),
    ("agravo em recurso especial", "AREsp"),
    ("recurso especial", "REsp"),
    ("recurso em mandado de segurança", "RMS"),
    ("recurso ordinário em habeas corpus", "RHC"),
    ("habeas corpus", "HC"),
    ("conflito de competência", "CC"),
    ("conflito de competencia", "CC"),
    ("reclamação", "Rcl"),
    ("recurso extraordinário", "RE"),
    ("agravo em recurso extraordinário", "ARE"),
)
SAJ_NUMBER = re.compile(r"\b(\d{4})\.(\d{6})-(\d)\b")
MARKED = re.compile(r"<<(?P<classe>[^>\d]+?)\s*(?P<numero>\d+)>>(?:-(?P<uf>[A-Z]{2}))?")
MARKED_THEME = re.compile(r"(?i)TEMA\(?s?\)?\s*(?P<n>\d{1,3}(?:\.\d{3})?|\d{1,5})")
COURT_LINE = re.compile(r"^\s*(?P<court>[A-Z]{2,6})\s+-\s+", re.M)
TRIBUNAL_PREFIX = re.compile(r"(?i)^\s*(?:e\s+)?(?P<court>STF|STJ|TJ-?[A-Z]{2}|TRF-?\d|TST|TSE)\b[\s,.:-]*")
STJ_LAW = re.compile(r"LEG:(?P<scope>\w+)\s+(?P<kind>\w+):(?P<number>[\w*]+)\s+ANO:(?P<year>[\w*]+)")
STJ_ARTICLE = re.compile(r"\bART:(?P<n>\d+)(?P<suffix>[A-Z])?")
STJ_SUMMARY = re.compile(r"\bSUM:(?P<n>\d+)")
STJ_ALIAS = re.compile(r"(?m)^\*{5}\s+(?P<alias>\S+)")
SIMILAR = re.compile(r"^\s*(?P<classe>[A-Za-z][A-Za-z ]*?)\s+(?P<numero>\d+)\s+(?P<uf>[A-Z]{2})\b")


def court_name(value: str) -> str:
    return value.upper().replace("-", "")


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def short_classes(text: str) -> str:
    """Class names written in full, as the TJSC sometimes cites the STJ, to their siglas."""
    for long, short in LONG_CLASSES:
        text = re.sub(r"(?i)\b" + long + r"\b", short, text)
    return text


def stj_class(value: str) -> str:
    """Class as the acervo stores it: upper, accents and extra spaces removed."""
    return " ".join(folded(value).replace("-", " ").split())


def diploma_key(name: str) -> str:
    """One key per statute, from the names the TJSC writes."""
    clean = " ".join(folded(name).split())
    if clean in DIPLOMAS:
        return DIPLOMAS[clean]
    law = re.match(
        r"(?i)^(LEI(?: COMPLEMENTAR)?|DECRETO(?:-LEI)?)\s*(?:N[.º°O]*)?\s*([\d.]+)/(\d{2,4})$", clean
    )
    if law:
        kind = {"LEI": "LEI", "LEI COMPLEMENTAR": "LC", "DECRETO": "DECRETO", "DECRETO-LEI": "DL"}[
            law.group(1).upper()
        ]
        number, year = digits(law.group(2)), law.group(3)
        if len(year) == 2:
            year = ("19" if int(year) > 30 else "20") + year
        return f"{kind} {law_number(number)}/{year}"
    return clean


def law_number(number: str) -> str:
    number = number.lstrip("0") or "0"
    return f"{int(number):,}".replace(",", ".")


def article_key(value: str) -> str | None:
    match = ARTICLE.match(value.strip())
    if not match:
        return None
    number = match.group(1).replace(".", "")
    return number + (f"-{match.group(2)}" if match.group(2) else "")


def citation(tipo: str, chave: str | None, texto: str, origem: str) -> dict:
    return {"tipo": tipo, "chave": chave or "", "texto": " ".join(texto.split())[:300], "origem": origem}


def precedent_citations(text: str, court: str | None, origem: str) -> list[dict]:
    """Temas, súmulas, IRDR and IAC named in one fragment; the court comes from the fragment prefix."""
    found = []
    for m in PRECEDENT.finditer(text):
        if m.group("tema"):
            tribunal = "STF" if re.search(r"(?i)repercuss|RG|STF", m.group("tema")) else (court or "STJ")
            if tribunal == "STF":
                key = f"STF:tema_repercussao_geral:{int(digits(m.group('tema_n')))}"
            else:
                key = f"STJ:tema_repetitivo:{int(digits(m.group('tema_n')))}"
        elif m.group("sumula"):
            if m.group("vinc"):
                key = f"STF:sumula_vinculante:{int(digits(m.group('sumula_n')))}"
            elif court in {"STF", "STJ"}:
                key = f"{court}:sumula:{int(digits(m.group('sumula_n')))}"
            elif court == "TJSC":
                key = None  # Numbered per organ; the fragment rarely says which.
            else:
                key = f"STJ:sumula:{int(digits(m.group('sumula_n')))}"
        elif m.group("irdr"):
            key = f"TJSC:irdr:{int(m.group('irdr_n'))}" if court in {None, "TJSC"} else None
        else:
            key = f"TJSC:iac:{int(m.group('iac_n'))}" if court in {None, "TJSC"} else None
        found.append(citation("precedente", key, m.group(0), origem))
    return found


def tjsc_jurisprudence(line: str) -> list[dict]:
    """Items of "Jurisprudência relevante citada", separated by semicolons."""
    origem = "ementa_cnj:jurisprudencia_citada"
    body = re.sub(r"(?i)^\s*jurisprud[êe]ncia relevante citada\s*[:.]?\s*", "", line.strip())
    found = []
    for item in filter(None, (x.strip(" .") for x in body.split(";"))):
        prefix = TRIBUNAL_PREFIX.match(item)
        court = court_name(prefix.group("court")) if prefix else None
        precedents = precedent_citations(item, court, origem)
        found.extend(precedents)
        cnj = CNJ_NUMBER.search(item)
        if cnj:
            number = "".join(cnj.groups())
            tribunal = court or ("TJSC" if number[13:16] == "824" else None)
            found.append(citation("acordao", f"{tribunal}:{number}" if tribunal else None, item, origem))
            continue
        saj = SAJ_NUMBER.search(item)
        if saj and court in {None, "TJSC"}:
            found.append(citation("acordao", "TJSC:" + "".join(saj.groups()), item, origem))
            continue
        stj = STJ_CITATION.search(short_classes(item))
        if stj and court in {None, "STJ", "STF"}:
            tribunal = court or "STJ"
            key = f"{tribunal}:{stj_class(stj.group('classe'))}:{int(digits(stj.group('numero')))}"
            found.append(citation("acordao", key, item, origem))
        elif not precedents:
            found.append(citation("acordao", None, item, origem))
    return found


def tjsc_provisions(line: str) -> list[dict]:
    """Items of "Dispositivos relevantes citados": statute anchors, then article lists."""
    origem = "ementa_cnj:dispositivos_citados"
    body = re.sub(r"(?i)^\s*dispositivos relevantes citados\s*[:.]?\s*", "", line.strip())
    anchors = list(DIPLOMA_ANCHOR.finditer(body))
    found = []
    if not anchors and body:
        return [citation("dispositivo", None, body, origem)]
    for i, anchor in enumerate(anchors):
        diploma = diploma_key(anchor.group("diploma"))
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(body)
        segment = body[anchor.end() : end]
        segment = re.sub(r"(?i)^[\s,.:]*art(?:igo)?s?\.?\s*", "", segment)
        articles = []
        for clause in re.split(r"[;]", segment):
            for part in clause.split(","):
                part = part.strip(" .")
                if not part:
                    continue
                part = re.sub(r"(?i)^art(?:igo)?s?\.?\s*", "", part)
                head = re.match(r"^(\d{1,4}(?:\.\d{3})*(?:\s*[ºo°])?(?:-[A-Z])?)(.*)$", part)
                key = article_key(head.group(1)) if head else None
                if key and not COMPLEMENT.match(part):
                    articles.append([key, part])
                elif articles:
                    articles[-1][1] += ", " + part
                elif COMPLEMENT.match(part):
                    articles.append([None, part])
        if not articles:
            found.append(citation("dispositivo", f"{diploma}:*", anchor.group("diploma"), origem))
        for key, text in articles:
            chave = f"{diploma}:{key}" if key else None
            found.append(citation("dispositivo", chave, f"{anchor.group('diploma')}, art. {text}", origem))
    return found


def closing_lines(ementa: str) -> dict:
    """The two closing lines of the CNJ ementa, by the sections deriver or by their headings."""
    lines = {}
    for section in sections(ementa):
        if section["nome"] in {"dispositivos_citados", "jurisprudencia_citada"}:
            lines[section["nome"]] = ementa[section["inicio"] : section["fim"]]
    if lines:
        return lines
    # Sections may be ambiguous (repeated headings); fall back to the last occurrence of each line.
    for name, pattern in (
        ("dispositivos_citados", r"(?i)dispositivos relevantes citados\s*[:.]"),
        ("jurisprudencia_citada", r"(?i)jurisprud[êe]ncia relevante citada\s*[:.]"),
    ):
        hits = list(re.finditer(pattern, ementa))
        if hits:
            start = hits[-1].start()
            rest = ementa[start:]
            other = re.search(
                r"(?i)\r?\n\s*(?:dispositivos relevantes citados|jurisprud[êe]ncia relevante citada)",
                rest[1:],
            )
            lines[name] = rest[: other.start() + 1] if other else rest
    return lines


def extract_tjsc(body: dict) -> list[dict]:
    lines = closing_lines(body.get("ementa") or "")
    found = []
    if "dispositivos_citados" in lines:
        found += tjsc_provisions(lines["dispositivos_citados"])
    if "jurisprudencia_citada" in lines:
        found += tjsc_jurisprudence(lines["jurisprudencia_citada"])
    return found


def stj_law_key(reference: str) -> tuple[str | None, str]:
    """Statute key of one ``referenciasLegislativas`` entry and its alias, when any."""
    law = STJ_LAW.search(reference)
    alias = STJ_ALIAS.search(reference)
    alias = alias.group("alias") if alias else ""
    if not law:
        return None, alias
    kind, number, year = law.group("kind"), law.group("number").lstrip("0"), law.group("year")
    if kind == "SUM":
        return "SUM", alias
    if kind == "CFB":
        return "CF", alias
    if (kind, number, year) in STJ_CODES:
        return STJ_CODES[(kind, number, year)], alias
    if kind == "RGI" and alias.startswith("RISTJ"):
        return "RISTJ", alias
    if kind in STJ_KINDS and number.isdigit() and year.isdigit():
        return f"{STJ_KINDS[kind]} {law_number(number)}/{year}", alias
    return alias.split("-")[0] if alias else None, alias


def stj_laws(raw: dict) -> list[dict]:
    """``referenciasLegislativas``: súmulas as precedents, every ART as one provision."""
    found = []
    origem = "espelho_stj:referenciasLegislativas"
    for reference in raw.get("referenciasLegislativas") or []:
        key, alias = stj_law_key(reference)
        if key == "SUM":
            tribunal = "STF" if "STF" in alias else "STJ"
            species = "sumula_vinculante" if "VINC" in reference.upper() else "sumula"
            for m in STJ_SUMMARY.finditer(reference):
                chave = f"{tribunal}:{species}:{int(m.group('n'))}"
                found.append(citation("precedente", chave, reference, origem))
            continue
        articles = list(STJ_ARTICLE.finditer(reference))
        if not articles:
            found.append(citation("dispositivo", f"{key}:*" if key else None, reference, origem))
        for m in articles:
            article = str(int(m.group("n"))) + (f"-{m.group('suffix')}" if m.group("suffix") else "")
            found.append(citation("dispositivo", f"{key}:{article}" if key else None, reference, origem))
    return found


def stj_cited(raw: dict) -> list[dict]:
    """``jurisprudenciaCitada``: marked acórdãos, with the court of their line and the theme that follows."""
    found = []
    cited = raw.get("jurisprudenciaCitada") or ""
    origem = "espelho_stj:jurisprudenciaCitada"
    court, position = "STJ", 0
    for m in MARKED.finditer(cited):
        lines = list(COURT_LINE.finditer(cited, position, m.start()))
        if lines:
            court = lines[-1].group("court")
        position = m.start()
        key = f"{court}:{stj_class(m.group('classe'))}:{int(m.group('numero'))}"
        found.append(citation("acordao", key, m.group(0), origem))
        tail = cited[m.end() : m.end() + 60].split("<<")[0]
        theme = MARKED_THEME.search(tail)
        if theme and court == "STJ":
            chave = f"STJ:tema_repetitivo:{int(digits(theme.group('n')))}"
            found.append(citation("precedente", chave, tail, origem))
    return found


def extract_stj(raw: dict) -> list[dict]:
    found = stj_laws(raw) + stj_cited(raw)
    theme = re.search(r"(?i)tema\s+repetitivo\s+(\d+)", raw.get("tema") or "")
    if theme:
        chave = f"STJ:tema_repetitivo:{int(theme.group(1))}"
        found.append(citation("precedente", chave, raw["tema"], "espelho_stj:tema"))
    for similar in raw.get("acordaosSimilares") or []:
        m = SIMILAR.match(similar)
        key = f"STJ:{stj_class(m.group('classe'))}:{int(m.group('numero'))}" if m else None
        found.append(citation("similar", key, similar.splitlines()[0], "espelho_stj:acordaosSimilares"))
    return found


def extract(body: dict, raw) -> list[dict]:
    """Citations of one acórdão from its stored body and original; duplicates by (tipo, chave) kept once."""
    if body.get("tribunal") == "TJSC":
        found = extract_tjsc(body)
    elif body.get("tribunal") == "STJ" and isinstance(raw, dict):
        found = extract_stj(raw)
    else:
        found = []
    seen, unique = set(), []
    for item in found:
        marker = (item["tipo"], item["chave"] or item["texto"])
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


def split_court(value: str) -> tuple[str | None, str]:
    """Court named as prefix ("STJ, ...") or suffix ("... do STJ"), and the rest of the value."""
    prefix = TRIBUNAL_PREFIX.match(value)
    if prefix:
        return court_name(prefix.group("court")), value[prefix.end() :]
    suffix = re.search(r"(?i)\b(?:do\s+)?(STJ|STF|TJSC)\s*$", value)
    if suffix:
        return suffix.group(1).upper(), value[: suffix.start()]
    return None, value


def precedent_filter_key(value: str) -> str:
    if re.fullmatch(r"(?i)(STJ|STF|TJSC):[a-z_]+:(?:[A-Z]+:)?\d+", value):
        return value.split(":")[0].upper() + value[value.index(":") :]
    court, rest = split_court(value)
    found = [c for c in precedent_citations(rest, court, "") if c["chave"]]
    if len(found) != 1:
        raise ValueError("precedente")
    return found[0]["chave"]


def judgment_filter_key(value: str) -> str:
    cnj = CNJ_NUMBER.search(value)
    court, rest = split_court(value)
    if cnj:
        number = "".join(cnj.groups())
        court = court or ("TJSC" if number[13:16] == "824" else None)
        if not court:
            raise ValueError("tribunal")
        return f"{court}:{number}"
    saj = SAJ_NUMBER.search(rest)
    if saj:
        return "TJSC:" + "".join(saj.groups())
    stj = STJ_CITATION.search(short_classes(rest))
    if not stj:
        raise ValueError("acordao")
    return f"{court or 'STJ'}:{stj_class(stj.group('classe'))}:{int(digits(stj.group('numero')))}"


def provision_filter_key(value: str) -> str:
    anchor = DIPLOMA_ANCHOR.search(value)
    if not anchor:
        raise ValueError("diploma")
    rest = (value[: anchor.start()] + " " + value[anchor.end() :]).strip(" ,.;")
    rest = re.sub(r"(?i)^art(?:igo)?s?\.?\s*", "", rest).strip()
    if not rest:
        return f"{diploma_key(anchor.group('diploma'))}:*"
    head = re.match(r"^(\d{1,4}(?:\.\d{3})*(?:\s*[ºo°])?(?:-[A-Z])?)", rest)
    key = article_key(head.group(1)) if head else None
    if not key:
        raise ValueError("artigo")
    return f"{diploma_key(anchor.group('diploma'))}:{key}"


FILTER_KEYS = {
    "precedente": precedent_filter_key,
    "acordao": judgment_filter_key,
    "dispositivo": provision_filter_key,
}


def filter_key(tipo: str, value: str) -> str:
    """Key of a user-supplied citation filter, by the same normalization as the extraction."""
    value = " ".join((value or "").split())
    if not value or tipo not in FILTER_KEYS:
        raise ValueError("vazio")
    return FILTER_KEYS[tipo](value)
