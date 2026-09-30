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


def advanced_query(value: str) -> str:
    if len(value) > 500 or value.count('"') % 2:
        raise FloraError("consulta_invalida", "Consulta longa ou aspas sem fechamento.")
    tokens = re.findall(r'"[^"\n]+"|[()]|[^\s()"]+', value)
    if not tokens:
        return ""
    if len(tokens) > 90:
        raise FloraError("consulta_invalida", "Consulta excede o limite de expressões.")
    grammar = _Grammar(tokens)
    result = grammar.parse_or(0)
    if grammar.position != len(tokens):
        raise FloraError("consulta_invalida", "Parêntese ou termo fora de posição.")
    return result


HEADINGS = re.compile(
    r"(?im)^[ \t]*(?:[IVX]+[.\-–:][ \t]*)?"
    r"(?P<title>CASO EM EXAME|QUEST[ÃA]O EM DISCUSS[ÃA]O|RAZ[ÕO]ES DE DECIDIR|DISPOSITIVO E TESE|TESE DE "
    r"JULGAMENTO)"
    r"[ \t]*(?:[:.\-–][ \t]*|$)"
)
NAMES = {
    "CASO EM EXAME": "caso_em_exame",
    "QUESTÃO EM DISCUSSÃO": "questao_em_discussao",
    "QUESTAO EM DISCUSSAO": "questao_em_discussao",
    "RAZÕES DE DECIDIR": "razoes_de_decidir",
    "RAZOES DE DECIDIR": "razoes_de_decidir",
    "DISPOSITIVO E TESE": "dispositivo_e_tese",
    "TESE DE JULGAMENTO": "tese_na_ementa",
}


def sections(text):
    matches = list(HEADINGS.finditer(text))
    names = [{folded(k): v for k, v in NAMES.items()}[folded(m.group("title"))] for m in matches]
    if len(set(names)) != len(names):
        return []  # Ambiguous repeated headings: retain only the full ementa.
    return [
        {
            "nome": names[i],
            "inicio": m.start(),
            "fim": matches[i + 1].start() if i + 1 < len(matches) else len(text),
            "sha256_componente": digest(text.encode()),
            "derivador": "ementa-secoes-1",
        }
        for i, m in enumerate(matches)
    ]


HEADER_LIMIT = 400
WINDOW, LEAD = 320, 80


def header(text):
    """Verbetação: from the start up to the first section heading, else up to the first line break."""
    spans = sections(text)
    if spans and text[: spans[0]["inicio"]].strip():
        end = spans[0]["inicio"]
    else:
        start = len(text) - len(text.lstrip())
        newline = text.find("\n", start)
        end = newline if newline >= 0 else len(text)
    value = text[:end].strip()
    return value[:HEADER_LIMIT], len(value) > HEADER_LIMIT


def matched_window(text, marked):
    """Window around the first mark that FTS5 highlight() put in marked; offsets are in text."""
    position = marked.find("\x01") if marked else -1
    start = max(0, position - LEAD) if position >= 0 else 0
    value = text[start : start + WINDOW]
    return {"texto": value, "offset": start, "parcial": start > 0 or start + len(value) < len(text)}
