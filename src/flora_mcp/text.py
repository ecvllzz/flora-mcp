"""Bounded opt-in query grammar and conservative literal ementa sections."""

import re

from .model import FloraError, digest, folded


class _Grammar:
    """Recursive descent over the tokens: OR of ANDs of terms, phrases, prefixes and groups."""

    def __init__(self, tokens):
        self.tokens, self.position, self.terms = tokens, 0, 0

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def atom(self, depth):
        if depth > 8 or self.peek() is None:
            raise FloraError("consulta_invalida", "Expressão incompleta ou aninhamento excessivo.")
        token = self.tokens[self.position]
        self.position += 1
        if token == "(":
            return self.group(depth)
        if token in {"AND", "OR", ")"}:
            raise FloraError("consulta_invalida", "Operador sem termo.")
        return self.term(token)

    def group(self, depth):
        expression = self.parse_or(depth + 1)
        if self.peek() != ")":
            raise FloraError("consulta_invalida", "Parêntese sem fechamento.")
        self.position += 1
        return "(" + expression + ")"

    def term(self, token):
        self.terms += 1
        if self.terms > 30:
            raise FloraError("consulta_invalida", "Use até 30 termos.")
        if token.startswith('"'):
            return token
        prefix = token.endswith("*")
        literal = token[:-1] if prefix else token
        if not literal or "*" in literal:
            raise FloraError("consulta_invalida", "Prefixo exige termo seguido de um único asterisco.")
        return '"' + literal + '"' + ("*" if prefix else "")

    def parse_and(self, depth):
        expression = self.atom(depth)
        while self.peek() not in {None, ")", "OR"}:
            if self.peek() == "AND":
                self.position += 1
            expression += " AND " + self.atom(depth)
        return expression

    def parse_or(self, depth):
        expression = self.parse_and(depth)
        while self.peek() == "OR":
            self.position += 1
            expression += " OR " + self.parse_and(depth)
        return expression


# Without quotes, these words are operators in any case; a quoted "e" or "ou" stays a literal term.
OPERATORS = {"AND": "AND", "E": "AND", "OR": "OR", "OU": "OR"}
# Operators the grammar does not offer are refused: as literal terms they would answer something else.
UNSUPPORTED = re.compile(r"NOT|NEAR(?:/\d+)?", re.IGNORECASE)
UNSUPPORTED_UPPER = {"NAO", "NÃO"}  # Only in capitals: in lower case, "não" is an ordinary word.


def operator_token(token: str) -> str:
    if UNSUPPORTED.fullmatch(token) or token in UNSUPPORTED_UPPER:
        raise FloraError(
            "consulta_invalida",
            f"{token} não é aceito no modo avançado; use E, OU, parênteses, frases e prefixo*. "
            "Para procurar a palavra, ponha-a entre aspas.",
        )
    return OPERATORS.get(token.upper(), token)


def advanced_query(value: str) -> str:
    if len(value) > 500 or value.count('"') % 2:
        raise FloraError("consulta_invalida", "Consulta longa ou aspas sem fechamento.")
    tokens = re.findall(r'"[^"\n]+"|[()]|[^\s()"]+', value)
    if not tokens:
        return ""
    if len(tokens) > 90:
        raise FloraError("consulta_invalida", "Consulta excede o limite de expressões.")
    grammar = _Grammar([operator_token(token) for token in tokens])
    result = grammar.parse_or(0)
    if grammar.position != len(tokens):
        raise FloraError("consulta_invalida", "Parêntese ou termo fora de posição.")
    return result


HEADINGS = re.compile(
    r"(?im)^[ \t]*(?:[IVX]+[ \t]*[.\-\u2013:][ \t]*)?"
    r"(?P<title>CASO EM EXAME|HIP[ÓO]TESE EM EXAME|QUEST[ÃA]O EM DISCUSS[ÃA]O|RAZ[ÕO]ES DE DECIDIR|"
    r"DISPOSITIVO E TESE|(?-i:D)ISPOSITIVO(?=[ \t]*[:.\-–]?[ \t]*\r?$)|TESE DE JULGAMENTO|"
    r"DISPOSITIVOS RELEVANTES CITADOS|"
    r"JURISPRUD[ÊE]NCIA RELEVANTE CITADA)"
    r"[ \t]*(?:[:.\-\u2013][ \t]*|\r?$)"
)
NAMES = {
    "CASO EM EXAME": "caso_em_exame",
    "HIPOTESE EM EXAME": "caso_em_exame",
    "QUESTAO EM DISCUSSAO": "questao_em_discussao",
    "RAZOES DE DECIDIR": "razoes_de_decidir",
    "DISPOSITIVO E TESE": "dispositivo_e_tese",
    "DISPOSITIVO": "dispositivo_e_tese",
    "TESE DE JULGAMENTO": "tese_na_ementa",
    "DISPOSITIVOS RELEVANTES CITADOS": "dispositivos_citados",
    "JURISPRUDENCIA RELEVANTE CITADA": "jurisprudencia_citada",
}
SECTION_NAMES = ("cabecalho", *dict.fromkeys(NAMES.values()))
SECTIONS_DERIVER = "ementa-secoes-3"


def sections(text):
    """Literal sections of a CNJ-model ementa (Recomendação CNJ 154/2024), by character offsets.

    Recognizes the four numbered parts (the fourth titled DISPOSITIVO E TESE or DISPOSITIVO alone),
    the thesis and the two closing lines (dispositivos and jurisprudência citados), with CRLF or LF
    line endings. The text before the first heading is
    the cabecalho. Repeated headings make the division ambiguous, and nothing is returned.
    """
    matches = list(HEADINGS.finditer(text))
    names = [NAMES[folded(m.group("title"))] for m in matches]
    if len(set(names)) != len(names):
        return []
    whole = digest(text.encode())
    spans = []
    if matches and text[: matches[0].start()].strip():
        spans.append(("cabecalho", 0, matches[0].start()))
    spans += [
        (names[i], m.start(), matches[i + 1].start() if i + 1 < len(matches) else len(text))
        for i, m in enumerate(matches)
    ]
    return [
        {
            "nome": name,
            "inicio": start,
            "fim": end,
            "sha256_componente": whole,
            "sha256_secao": digest(text[start:end].encode()),
            "derivador": SECTIONS_DERIVER,
        }
        for name, start, end in spans
    ]


HEADER_LIMIT = 120
WINDOW, LEAD = 100, 25


# A numbered paragraph ("1.", "I -", "2)") or a blank line ends a verbetação without CNJ headings.
BODY_START = re.compile(r"\n[ \t]*(?:\r?\n|(?:\d{1,3}|[IVX]{1,5})[ \t]*[.)\-\u2013])")


def header(text):
    """Verbetação of the triage, cut at HEADER_LIMIT on a word boundary, and whether it was cut."""
    value = verbetacao(text)
    return value[: word_end(value, 0, HEADER_LIMIT)].rstrip(), len(value) > HEADER_LIMIT


def verbetacao(text):
    """Verbetação: up to the first section heading; else up to the first numbered paragraph or blank line.

    STJ ementas wrap the verbetação across several lines, so a single line break does not end it.
    """
    spans = [s for s in sections(text) if s["nome"] != "cabecalho"]
    start = len(text) - len(text.lstrip())
    if spans and not text[: spans[0]["inicio"]].strip():
        # The ementa opens with a heading: its first line stands for the verbetação.
        newline = text.find("\n", start)
        end = newline if newline >= 0 else len(text)
    else:
        found = BODY_START.search(text, start)
        end = min(found.start() if found else len(text), spans[0]["inicio"] if spans else len(text))
    return text[:end].strip()


def word_end(text, start, limit):
    """End of text[start:start + limit] at a word boundary; a single longer word is cut at the limit."""
    end = start + limit
    if end >= len(text) or text[end].isspace():
        return min(end, len(text))
    space = max(text.rfind(c, start, end) for c in " \t\r\n")
    return space if space > start else end


def window(text, position, size, lead):
    """(offset, texto): up to size characters from about lead before position, at word boundaries."""
    start = max(0, position - lead)
    if start and not text[start - 1].isspace():
        # The window opens on the next whole word, never after the position itself.
        found = re.search(r"\s+", text[start:position])
        start += found.end() if found else 0
    return start, text[start : word_end(text, start, size)].rstrip()


# Tokens of the triage window that FTS5 snippet() chooses: the run of this many tokens with the most
# distinct query terms (a repeated term counts almost nothing). 16 tokens run about 110 characters,
# the size of the window before, which showed a single occurrence.
SNIPPET_TOKENS = 16
MARK, END = "\x01", "\x02"
MARKED = re.compile(MARK + "(.*?)" + END)


def snippet_window(text, snippet):
    """{texto, offset, parcial} of the window snippet() chose: its literal text, located in text.

    The snippet is the text between the first and the last token of the window, so it is a
    substring of the ementa; the marks are removed and the first occurrence of the substring gives
    the offset. Without a snippet (no term in the text), the window opens at the start.
    """
    value = snippet.replace(MARK, "").replace(END, "") if snippet else ""
    start = text.find(value) if value else -1
    if start < 0:
        start, value = window(text, 0, WINDOW, LEAD)
    return {"texto": value, "offset": start, "parcial": start > 0 or start + len(value) < len(text)}


def plain(value):
    """Letters, digits and single spaces, without accents or case: how the index compares a token."""
    return " ".join(re.sub(r"[^\w\s]", " ", folded(value)).split())


def query_terms(fts_query):
    """(term, prefix) of every quoted term of a compiled FTS query, in order, once each."""
    found = {}
    for quoted, star in re.findall(r'"((?:[^"]|"")*)"(\*?)', fts_query):
        found.setdefault((quoted.replace('""', '"'), bool(star)), None)
    return list(found)


def present_terms(terms, marked):
    """Query terms that highlight() marked somewhere in the text, in query order."""
    spans = {plain(s) for s in MARKED.findall(marked or "")}
    found = []
    for term, prefix in terms:
        key = plain(term)
        if key and (key in spans or (prefix and any(s.startswith(key) for s in spans))):
            found.append(term + ("*" if prefix else ""))
    return found
