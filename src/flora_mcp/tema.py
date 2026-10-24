"""Filtro de tema da coleta dirigida por consulta (educação), conferível pela verbetação da ementa.

O portal acha o termo em qualquer parte da ementa, e nas Câmaras de Direito Público "educação"
aparece sobretudo em matéria de servidor (magistério, Fundação Catarinense de Educação Especial). A
primeira versão (termo de educação na verbetação ou lei citada) teve 7 de 50 no tema na amostra de
24/10/2026, e o plano manda apertar o filtro. A segunda (marca do direito do aluno) teve 31 de 50:
o que sobrava eram contratos e licitações com o fornecedor (transporte escolar, obra de creche) e
servidor ou concurso. Esta versão exige, na verbetação, uma marca do direito do aluno; servidor,
remuneração, indenização e incidentes barram a marca fraca, e a vaga em creche ou escola passa por
cima deles; licitação, contrato, cobrança, execução fiscal, concurso e improbidade barram toda marca,
salvo o direito à educação expresso. Sem modelo de linguagem: a regra é a mesma para todos e o motivo
de cada decisão fica registrado.
"""

import re

from .model import folded
from .text import verbetacao

FILTRO = "educacao-3"

# Nome de órgão, não tema: sai da verbetação antes de qualquer teste.
ORGAOS = re.compile(
    r"FUNDACAO CATARINENSE DE EDUCACAO ESPECIAL|\bFCEE\b|SECRETARIA (?:DE ESTADO )?DA EDUCACAO"
)
ENSINO = r"(?:CRECHE|PRE-?ESCOLA|ESCOLA|ENSINO|EDUCACAO INFANTIL|UNIDADE ESCOLAR|CENTRO DE EDUCACAO)"
FORTES = (
    ("direito à educação", re.compile(r"DIREITO (?:FUNDAMENTAL |SOCIAL )?A EDUCACAO")),
    (
        "vaga",
        re.compile(r"\bVAGAS?\b[^.;]{0,40}?(?:CRECHE|PRE-?ESCOLA|EDUCACAO INFANTIL|ESCOLA|UNIDADE ESCOLAR)"),
    ),
)
DIREITO = FORTES[:1]
MARCAS = FORTES + (
    ("creche ou pré-escola", re.compile(r"\bCRECHES?\b|\bPRE-?ESCOLA|EDUCACAO INFANTIL")),
    (
        "acessibilidade",
        re.compile(r"ACESSIBILIDADE[^.;]{0,60}?" + ENSINO + "|" + ENSINO + r"[^.;]{0,60}?ACESSIBILIDADE"),
    ),
    ("transporte escolar", re.compile(r"TRANSPORTE ESCOLAR")),
    (
        "matrícula do aluno",
        re.compile(
            r"MATRICULA (?:ESCOLAR|(?:D[OA]S? |EM )(?:ALUNO|ESTUDANTE|EDUCANDO|CRIANCA|ESCOLA|CRECHE|ENSINO))"
        ),
    ),
    (
        "apoio ao aluno",
        re.compile(r"SEGUNDO PROFESSOR|PROFESSOR (?:AUXILIAR|DE APOIO|ASSISTENTE)|ACOMPANHANTE|MONITOR"),
    ),
    (
        "aluno com deficiência",
        re.compile(
            r"(?:ALUNO|ESTUDANTE|EDUCANDO|CRIANCA)\w*[^.;]{0,60}?(?:DEFICIEN|AUTIS|ESPECTRO|\bTEA\b|TDAH|INCLUS)"
        ),
    ),
    ("educação especial ou inclusiva", re.compile(r"EDUCACAO (?:ESPECIAL|INCLUSIVA)|ENSINO ESPECIAL")),
    (
        "estrutura da escola",
        re.compile(
            r"ESCOLA\w*[^.;]{0,60}?(?:REFORMA|REGULARIZ|INTERDI|INFRAESTRUTURA|ESTRUTURA|SALUBRIDADE|OBRAS?\b)|"
            r"(?:REFORMA|REGULARIZ|INTERDI|INFRAESTRUTURA|OBRAS?\b)[^.;]{0,40}?ESCOLA"
        ),
    ),
)
# Barram a marca fraca: a matéria é do servidor ou de incidente, e a escola só aparece no caso.
BARREIRAS = re.compile(
    r"SERVIDOR|MAGISTERIO|\bPISO\b|VENCIMENT|GRATIFICA|ADICIONA|APOSENTADORIA|PROGRESSAO|ABONO|REMUNERA|"
    r"SALARI|TEMPORARI|EXONERA|REMOCAO|FERIAS|PROCESSO SELETIVO|SELECAO|RESPONSABILIDADE CIVIL|INDENIZA|"
    r"PREVIDENCI|PRODUCAO ANTECIPADA|EXIBICAO"
)
# Barram toda marca, salvo o direito à educação expresso: o objeto é o contrato, o certame ou o erário.
OBJETO_ALHEIO = re.compile(
    r"LICITA|PREGAO|CONTRATO|RESCIS|EQUILIBRIO ECONOMICO|COBRANCA|MONITORIA|EXECUCAO FISCAL|CONCURSO|"
    r"NOMEACA|IMPROBIDADE"
)


def educacao(ementa: str) -> str | None:
    """Motivo pelo qual o acórdão entra no tema educação, ou None quando fica de fora."""
    head = ORGAOS.sub(" ", folded(verbetacao(ementa or "")))
    marcas = DIREITO if OBJETO_ALHEIO.search(head) else FORTES if BARREIRAS.search(head) else MARCAS
    for label, pattern in marcas:
        if pattern.search(head):
            return "verbetacao: " + label
    return None
