"""Temas da coleta dirigida por consulta (educação, família e sucessões), com filtro conferível pela
verbetação da ementa, e o registro de cada tema: órgãos, subtemas, período, texto do tema e filtro.

Educação. O portal acha o termo em qualquer parte da ementa, e nas Câmaras de Direito Público "educação"
aparece sobretudo em matéria de servidor (magistério, Fundação Catarinense de Educação Especial). A
primeira versão (termo de educação na verbetação ou lei citada) teve 7 de 50 no tema na amostra de
24/10/2026, e o plano manda apertar o filtro. A segunda (marca do direito do aluno) teve 31 de 50:
o que sobrava eram contratos e licitações com o fornecedor (transporte escolar, obra de creche) e
servidor ou concurso. Esta versão exige, na verbetação, uma marca do direito do aluno; servidor,
remuneração, indenização e incidentes barram a marca fraca, e a vaga em creche ou escola passa por
cima deles; licitação, contrato, cobrança, execução fiscal, concurso e improbidade barram toda marca,
salvo o direito à educação expresso. Sem modelo de linguagem: a regra é a mesma para todos e o motivo
de cada decisão fica registrado.

Família e sucessões (decisão do operador de 24/10/2026, com sucessões dentro e só o mérito como régua).
Nas Câmaras de Direito Civil a matéria vizinha é o contrato, o consumo e a posse: a marca forte (ação
de família ou de sucessão nomeada) passa sozinha; a fraca (alimentos sem qualificação, genitor,
partilha, herdeiro, espólio) só passa sem objeto alheio; ato infracional e crime barram tudo.
"""

import re
from dataclasses import dataclass
from typing import Callable

from .model import folded
from .text import verbetacao
from .tjsc_orgaos import PADRAO, PUBLICO

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


FILTRO_FAMILIA = "familia-1"
FAMILIA_FORTES = (
    ("direito de família ou sucessões", re.compile(r"DIREITO (?:DE |DA |DAS )?(?:FAMILIA|SUCESS)")),
    (
        "alimentos",
        re.compile(
            r"ALIMENTOS (?:PROVISORIOS|PROVISIONAIS|GRAVIDICOS|AVOENGOS|COMPENSATORIOS|DEFINITIVOS)|"
            r"PENSAO ALIMENTICIA|PRESTACAO ALIMENTICIA|OBRIGACAO ALIMENTAR|DEBITO ALIMENTAR|ALIMENTANTE|"
            r"ALIMENTAND|PRISAO CIVIL|BINOMIO|(?:ACAO|REVISIONAL|REVISAO|EXONERACAO|EXECUCAO|CUMPRIMENTO DE "
            r"SENTENCA|OFERTA|MAJORACAO|MINORACAO|REDUCAO|FIXACAO) DE ALIMENTOS"
        ),
    ),
    (
        "guarda",
        re.compile(
            r"GUARDA (?:COMPARTILHADA|UNILATERAL|ALTERNADA|PROVISORIA|DEFINITIVA|D[EOA]S? (?:MENOR|CRIANCA|"
            r"FILH|NET[OA]|ADOLESCENTE))|(?:ACAO|MODIFICACAO|REVERSAO) DE GUARDA"
        ),
    ),
    (
        "convivência",
        re.compile(
            r"CONVIVENCIA (?:FAMILIAR|PATERN|MATERN|AVOENG|COM [OA]S? (?:FILH|GENITOR|PAI|MAE|NET))|"
            r"REGULAMENTACAO D[EA] (?:VISITAS?|CONVIVENCIA)|DIREITO DE VISITA|"
            r"VISITAS? (?:PATERN|MATERN|AVOENG)"
        ),
    ),
    (
        "casamento e união estável",
        re.compile(
            r"DIVORCIO|SEPARACAO (?:JUDICIAL|DE CORPOS|CONSENSUAL|LITIGIOSA)|UNIAO (?:ESTAVEL|HOMOAFETIVA)|"
            r"DISSOLUCAO DE (?:UNIAO|SOCIEDADE CONJUGAL)|SOCIEDADE CONJUGAL|REGIME (?:DE|DA) (?:COMUNHAO|"
            r"SEPARACAO|BENS|PARTICIPACAO)|PACTO ANTENUPCIAL|CASAMENTO|MEACAO|CONCUBIN"
        ),
    ),
    ("curatela", re.compile(r"CURATELA|INTERDICAO|TOMADA DE DECISAO APOIADA")),
    (
        "adoção e poder familiar",
        re.compile(
            r"ADOCAO\s+(?:DE|DA|DO|DOS|DAS|POR)\s+(?!MEDIDA|PROVIDENCIA|PROCEDIMENTO|RITO|TESE|TEORIA|CRITERIO|"
            r"PRATICA|POSTURA|CONDUTA|SOLUCAO)|ADOCAO (?:UNILATERAL|POSTUMA|INTUITU|CONJUNTA|BILATERAL|"
            r"INTERNACIONAL)|HABILITACAO (?:PARA|A) ADOCAO|PODER FAMILIAR|"
            r"ACOLHIMENTO (?:INSTITUCIONAL|FAMILIAR)|"
            r"TUTELA D[EOA]S? (?:MENOR|CRIANCA|ADOLESCENTE)"
        ),
    ),
    ("alienação parental", re.compile(r"ALIENACAO PARENTAL")),
    (
        "filiação",
        re.compile(r"PATERNIDADE|MATERNIDADE|FILIACAO|SOCIOAFETIV|EXAME DE DNA|NEGATORIA|MULTIPARENTALIDADE"),
    ),
    ("ECA", re.compile(r"\bECA\b|ESTATUTO DA CRIANCA|MEDIDAS? DE PROTECAO")),
    (
        "sucessões",
        re.compile(
            r"INVENTARIO|ARROLAMENTO|HERANCA|SONEGADOS|COLACAO|TESTAMENT|SOBREPARTILHA|"
            r"DIREITOS? HEREDITARIOS?|"
            r"DIREITO REAL DE HABITACAO|SUCESSAO (?:LEGITIMA|TESTAMENTARIA|HEREDITARIA|CAUSA MORTIS)"
        ),
    ),
)
FAMILIA_FRACAS = (
    ("alimentos", re.compile(r"\bALIMENTOS\b")),
    ("genitores", re.compile(r"GENITOR|\bCONJUG|COMPANHEIR")),
    ("partilha", re.compile(r"PARTILHA")),
    ("herdeiros", re.compile(r"HERDEIR|ESPOLIO|DE CUJUS|SUCESSORES|\bLEGADO|ALVARA JUDICIAL")),
)
# Barram a marca fraca: o objeto é contrato, consumo, seguro, posse ou dano, e a família só aparece
# nas partes.
FAMILIA_BARREIRAS = re.compile(
    r"CONSUMIDOR|PRODUTO|INTOXICA|SEGURO|PLANO DE SAUDE|CONTRAT|BANC|FINANCIAMENTO|INDENIZA|DANO MORAL|"
    r"RESPONSABILIDADE CIVIL|USUCAPIAO|\bPOSSE|POSSESSORI|REINTEGRACAO|DESPEJO|LOCACAO|EXECUCAO DE TITULO|"
    r"EMBARGOS A EXECUCAO|CHEQUE|DUPLICATA|PROTESTO|ACIDENTE|TRANSITO|CONDOMINIO|COBRANCA|MONITORIA|"
    r"FALENCIA|RECUPERACAO JUDICIAL|SOCIEDADE (?:EMPRESARIA|LIMITADA)|EMPRESA"
)
FAMILIA_FORA = re.compile(r"ATO INFRACIONAL|CRIMINAL|\bCRIME")


def familia(ementa: str) -> str | None:
    """Motivo pelo qual o acórdão entra no tema família e sucessões, ou None quando fica de fora."""
    head = folded(verbetacao(ementa or ""))
    if FAMILIA_FORA.search(head):
        return None
    marcas = FAMILIA_FORTES if FAMILIA_BARREIRAS.search(head) else FAMILIA_FORTES + FAMILIA_FRACAS
    for label, pattern in marcas:
        if pattern.search(head):
            return "verbetacao: " + label
    return None


@dataclass(frozen=True)
class Tema:
    """Um tema da coleta por consulta: onde e o que pesquisar, como filtrar e o que o juiz da amostra lê."""

    nome: str
    versao: str
    filtro: Callable[[str], str | None]
    orgaos: tuple
    termos: tuple
    inicio: str
    fim: str | None  # None: até hoje
    texto: str
    rotulo_backup: str


TEMAS = {
    "educacao": Tema(
        nome="educacao",
        versao=FILTRO,
        filtro=educacao,
        orgaos=PUBLICO,
        termos=(
            "creche",
            "pré-escola",
            "transporte escolar",
            "segundo professor",
            "professor auxiliar",
            "acompanhante terapêutico",
            "matrícula",
            "vaga escolar",
            "educação especial",
            "educação inclusiva",
            "ensino",
            "escola",
        ),
        inicio="2022-01-01",
        fim=None,
        texto=(
            "Direito à educação: acesso, permanência e condições de ensino da criança, do adolescente e "
            "da pessoa com deficiência (vaga em creche e pré-escola, matrícula, transporte escolar, "
            "professor de apoio ou acompanhante, educação especial e inclusiva, ensino superior quando "
            "o objeto é o próprio direito ao ensino). Fora do tema: servidor público do magistério "
            "(piso, carreira, vencimentos), contrato com instituição de ensino que só discute cobrança "
            "ou consumo sem direito ao ensino, registro de imóvel (matrícula imobiliária) e qualquer "
            "outra matéria."
        ),
        rotulo_backup="antes-coleta-educacao-tjsc",
    ),
    "familia": Tema(
        nome="familia",
        versao=FILTRO_FAMILIA,
        filtro=familia,
        orgaos=PADRAO,
        termos=(
            "alimentos",
            "guarda",
            "convivência",
            "divórcio",
            "união estável",
            "partilha",
            "curatela",
            "adoção",
            "alienação parental",
            "inventário",
            "herança",
            "testamento",
            "arrolamento",
            "sonegados",
        ),
        inicio="2022-01-01",
        fim="2023-12-31",
        texto=(
            "Direito de família, da criança e do adolescente e das sucessões, no mérito: alimentos "
            "(fixação, revisão, exoneração e execução quando decide débito, prisão civil ou pagamento), "
            "guarda, convivência e visitas, poder familiar, filiação e paternidade, adoção, divórcio, "
            "união estável, partilha e regime de bens, curatela e interdição, alienação parental, medidas de "
            "proteção do ECA, inventário e arrolamento, herança, partilha de bens do falecido, testamento, "
            "sonegados, colação e petição de herança. Fora do tema: acórdão que decide só honorários, só "
            "multa ou só questão processual de uma ação de família ou de sucessões; ato infracional e "
            "crime; matéria civil sem questão de família ou de sucessão (contratos, consumo, seguro, "
            "responsabilidade civil, posse e propriedade, execução de título)."
        ),
        rotulo_backup="antes-coleta-familia-tjsc",
    ),
}
