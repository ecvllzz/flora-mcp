"""Filtro de tema da coleta dirigida por consulta (educação), conferível pelo texto da ementa.

O portal acha o termo em qualquer parte da ementa, e "matrícula", "ensino" ou "especial" aparecem
em acórdãos de outras matérias. Entra o acórdão cuja verbetação traz termo de educação, ou cuja
ementa cita a legislação do direito à educação (decisão do operador de 23/10/2026): ECA, arts. 53 a
59 e 208; LDB (Lei 9.394/1996); CF, arts. 205 a 214; Lei 13.146/2015, arts. 27 e 28. Sem modelo de
linguagem: a regra é a mesma para todos e o motivo de cada decisão fica registrado.
"""

import re

from .model import folded
from .text import verbetacao

# Na verbetação, já sem acentos e em maiúsculas. "Professor" só nas funções de apoio ao aluno: piso
# e carreira do magistério são servidor público, não direito à educação.
VERBETES = re.compile(
    r"\b(EDUCACA[OÕ]|EDUCACIONA\w*|ENSINO|ESCOLA\w*|CRECHE\w*|PRE-?ESCOLA\w*|ALUNO\w*|ESTUDANTE\w*|"
    r"SEGUNDO PROFESSOR|PROFESSOR (?:AUXILIAR|DE APOIO|ASSISTENTE)|ACOMPANHANTE TERAPEUTICO|"
    r"MONITOR ESCOLAR|TRANSPORTE ESCOLAR)\b"
)
ARTIGO = r"\bART(?:IGO)?S?\.?\s*(?:N[O.]?\s*)?"  # sem acentos, "nº" vira "NO"
PERTO = r"[^;\n]{0,60}?"
ECA = r"(?:\bECA\b|8\.?069|ESTATUTO DA CRIANCA)"
CF = r"(?:\bCF\b|\bCRFB\b|CONSTITUICAO)"
LBI = r"(?:13\.?146|ESTATUTO DA PESSOA COM DEFICIENCIA|\bLBI\b)"
LEIS = (
    ("ECA, arts. 53 a 59 ou 208", re.compile(ARTIGO + r"(5[3-9]|208)\b" + PERTO + ECA)),
    ("ECA, arts. 53 a 59 ou 208", re.compile(ECA + PERTO + ARTIGO + r"(5[3-9]|208)\b")),
    ("LDB", re.compile(r"\bLEI\s*(?:N[O.]?\s*)?9\.?394\b|\bLDB\b|DIRETRIZES E BASES DA EDUCACAO")),
    ("CF, arts. 205 a 214", re.compile(ARTIGO + r"(20[5-9]|21[0-4])\b" + PERTO + CF)),
    ("CF, arts. 205 a 214", re.compile(CF + PERTO + ARTIGO + r"(20[5-9]|21[0-4])\b")),
    ("Lei 13.146, arts. 27 e 28", re.compile(ARTIGO + r"(2[78])\b" + PERTO + LBI)),
    ("Lei 13.146, arts. 27 e 28", re.compile(LBI + PERTO + ARTIGO + r"(2[78])\b")),
)


def educacao(ementa: str) -> str | None:
    """Motivo pelo qual o acórdão entra no tema educação, ou None quando fica de fora."""
    found = VERBETES.search(folded(verbetacao(ementa or "")))
    if found:
        return "verbetacao: " + found[0].lower()
    text = folded(ementa or "")
    for label, pattern in LEIS:
        if pattern.search(text):
            return "legislacao: " + label
    return None
