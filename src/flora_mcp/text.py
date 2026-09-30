"""Bounded opt-in query grammar and conservative literal ementa sections."""

import re

from .model import FloraError, digest, folded


def advanced_query(value: str) -> str:  # noqa: C901
    if len(value) > 500 or value.count('"') % 2:
        raise FloraError("consulta_invalida", "Consulta longa ou aspas sem fechamento.")
    tokens = re.findall(r'"[^"\n]+"|[()]|[^\s()"]+', value)
    if not tokens:
        return ""
    if len(tokens) > 90:
        raise FloraError("consulta_invalida", "Consulta excede o limite de expressões.")
    position, terms = 0, 0

    def atom(depth):
        nonlocal position, terms
        if depth > 8 or position >= len(tokens):
            raise FloraError("consulta_invalida", "Expressão incompleta ou aninhamento excessivo.")
        token = tokens[position]
        position += 1
        if token == "(":
            expression = parse_or(depth + 1)
            if position >= len(tokens) or tokens[position] != ")":
                raise FloraError("consulta_invalida", "Parêntese sem fechamento.")
            position += 1
            return "(" + expression + ")"
        if token in {"AND", "OR", ")"}:
            raise FloraError("consulta_invalida", "Operador sem termo.")
        terms += 1
        if terms > 30:
            raise FloraError("consulta_invalida", "Use até 30 termos.")
        if token.startswith('"'):
            return token
        prefix = token.endswith("*")
        literal = token[:-1] if prefix else token
        if not literal or "*" in literal:
            raise FloraError("consulta_invalida", "Prefixo exige termo seguido de um único asterisco.")
        return '"' + literal + '"' + ("*" if prefix else "")

    def parse_and(depth):
        nonlocal position
        expression = atom(depth)
        while position < len(tokens) and tokens[position] not in {")", "OR"}:
            if tokens[position] == "AND":
                position += 1
            expression += " AND " + atom(depth)
        return expression

    def parse_or(depth):
        nonlocal position
        expression = parse_and(depth)
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            expression += " OR " + parse_and(depth)
        return expression

    result = parse_or(0)
    if position != len(tokens):
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
