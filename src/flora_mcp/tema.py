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
Nas Câmaras de Direito Civil a matéria vizinha é o contrato, o consumo e a posse, e a família aparece
muitas vezes só como origem do fato (o imóvel recebido por herança, a pensão do acidente). A marca vale
nos primeiros segmentos da verbetação, onde ficam o ramo, a classe e a ação: o cabeçalho de família ou
sucessões e a marca forte passam, salvo ação cível alheia sem ação de família nomeada; o estado de
família e a marca fraca só passam sem objeto alheio. Pela régua, ficam fora o desfecho só processual
(extinção sem mérito, competência, admissibilidade, embargos de declaração sem efeito) e o recurso
sobre gratuidade, honorários ou multa sem decisão de mérito; ato infracional e crime barram tudo. A
regra foi calibrada lendo amostras dos cíveis já publicados (2024 em diante), não os candidatos.
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
# Ação de família ou de sucessão nomeada: passa por cima das barreiras (a partilha pode ter contrato por
# objeto, e o inventário, um imóvel).
FAMILIA_FORTES = (
    ("direito de família ou sucessões", re.compile(r"DIREITO (?:DE |DA |DAS )?(?:FAMILIA|SUCESS)")),
    (
        "alimentos",
        re.compile(
            r"ALIMENTOS (?:PROVISORIOS|PROVISIONAIS|GRAVIDICOS|AVOENGOS|COMPENSATORIOS|DEFINITIVOS)|"
            r"PENSAO ALIMENTICIA|PRESTACAO ALIMENTICIA|OBRIGACAO ALIMENTAR|DEBITO ALIMENTAR|ALIMENTANTE|"
            r"ALIMENTAND|PRISAO CIVIL|BINOMIO|TRINOMIO|(?:ACAO|REVISIONAL|REVISAO|EXONERACAO|EXECUCAO|"
            r"CUMPRIMENTO DE SENTENCA|OFERTA|MAJORACAO|MINORACAO|REDUCAO|FIXACAO) DE ALIMENTOS"
        ),
    ),
    (
        "guarda",
        re.compile(
            r"GUARDA (?:COMPARTILHADA|UNILATERAL|ALTERNADA|AVOENGA|PROVISORIA|DEFINITIVA|D[EOA]S? (?:MENOR|"
            r"CRIANCA|FILH|NET[OA]|ADOLESCENTE|INFANTE))|"
            r"(?:ACAO|MODIFICACAO|REVERSAO|REGULAMENTACAO) DE GUARDA"
        ),
    ),
    (
        "convivência",
        re.compile(
            r"CONVIVENCIA (?:FAMILIAR|PATERN|MATERN|AVOENG|COM [OA]S? (?:FILH|GENITOR|PAI|MAE|NET))|"
            r"REGIME DE CONVIVENCIA|REGULAMENTACAO D[EA] (?:VISITAS?|CONVIVENCIA)|"
            r"VISITAS? (?:PATERN|MATERN|AVOENG)"
        ),
    ),
    (
        "divórcio e dissolução",
        re.compile(
            r"DIVORCIO|SEPARACAO (?:JUDICIAL|DE CORPOS|CONSENSUAL|LITIGIOSA)|"
            r"(?:RECONHECIMENTO|DISSOLUCAO) D[EA] (?:UNIAO|SOCIEDADE CONJUGAL)|PACTO ANTENUPCIAL"
        ),
    ),
    (
        "curatela",
        re.compile(
            r"CURATELA(?! ESPECIAL)|ACAO DE INTERDICAO|INTERDICAO (?:CIVIL|PARCIAL|TOTAL)|"
            r"LEVANTAMENTO DE INTERDICAO|TOMADA DE DECISAO APOIADA"
        ),
    ),
    (
        "adoção e poder familiar",
        re.compile(
            r"ACAO DE ADOCAO|ADOCAO (?:D[EOA]S? )?(?:MENOR|CRIANCA|ADOLESCENTE|INFANTE|ENTEAD|MAIOR)|"
            r"ADOCAO (?:UNILATERAL|POSTUMA|INTUITU|CONJUNTA|BILATERAL|INTERNACIONAL|SOCIOAFETIVA)|"
            r"HABILITACAO (?:PARA|A|DE PRETENDENTES?) (?:A )?ADOCAO|PODER FAMILIAR|"
            r"ACOLHIMENTO (?:INSTITUCIONAL|FAMILIAR)|TUTELA D[EOA]S? (?:MENOR|CRIANCA|ADOLESCENTE)"
        ),
    ),
    ("alienação parental", re.compile(r"ALIENACAO PARENTAL")),
    (
        "filiação",
        re.compile(
            r"(?:INVESTIGACAO|NEGATORIA|RECONHECIMENTO) DE (?:PATERNIDADE|MATERNIDADE|FILIACAO)|"
            r"PATERNIDADE SOCIOAFETIVA|MATERNIDADE SOCIOAFETIVA|MULTIPARENTALIDADE|EXAME DE DNA"
        ),
    ),
    ("ECA", re.compile(r"\bECA\b|ESTATUTO DA CRIANCA|MEDIDAS? DE PROTECAO|DIREITO DA CRIANCA")),
    (
        "sucessões",
        re.compile(
            r"INVENTARIO|ARROLAMENTO|HERANCA|SONEGADOS|COLACAO|TESTAMENT|SOBREPARTILHA|QUINHAO|"
            r"DIREITOS? HEREDITARIOS?|DIREITO REAL DE HABITACAO|"
            r"SUCESSAO (?:LEGITIMA|TESTAMENTARIA|HEREDITARIA|CAUSA MORTIS)"
        ),
    ),
)
# Estado de família sem ação nomeada e marca fraca: passam só sem objeto de contrato, consumo, seguro,
# posse ou dano, em que a família costuma aparecer só nas partes (a pensão à companheira do acidente).
FAMILIA_FRACAS = (
    (
        "casamento e união estável",
        re.compile(
            r"UNIAO (?:ESTAVEL|HOMOAFETIVA)|SOCIEDADE CONJUGAL|REGIME (?:DE|DA) (?:COMUNHAO|SEPARACAO|BENS|"
            r"PARTICIPACAO)|CASAMENTO|MEACAO|CONCUBIN|SOCIEDADE DE FATO"
        ),
    ),
    ("filiação", re.compile(r"\bPATERNIDADE|SOCIOAFETIV")),
    ("alimentos", re.compile(r"\bALIMENTOS\b")),
    ("genitores", re.compile(r"GENITOR|\bCONJUG|COMPANHEIR")),
    ("partilha", re.compile(r"PARTILHA")),
    ("herdeiros", re.compile(r"ALVARA JUDICIAL|DE CUJUS")),
)
# Barram a marca fraca: o objeto é contrato, consumo, seguro, posse ou dano, em que a família costuma
# aparecer só nas partes.
FAMILIA_BARREIRAS = re.compile(
    r"CONSUMIDOR|PRODUTO|INTOXICA|SEGURO|PLANO DE SAUDE|CONTRAT|BANC|FINANCIAMENTO|INDENIZA|DANO MORAL|"
    r"DANOS MORAIS|RESPONSABILIDADE CIVIL|USUCAPIAO|\bPOSSE|POSSESSORI|REINTEGRACAO|DESPEJO|LOCACAO|"
    r"EXECUCAO DE TITULO|EMBARGOS A EXECUCAO|EMBARGOS DE TERCEIRO|CHEQUE|DUPLICATA|PROTESTO|ACIDENTE|"
    r"TRANSITO|CONDOMINIO|COBRANCA|MONITORIA|FALENCIA|RECUPERACAO JUDICIAL|SOCIEDADE (?:EMPRESARIA|LIMITADA)|"
    r"EMPRESA|PENHORA|IMPENHORAB|EXIGIR CONTAS|PRESTACAO DE CONTAS|CONSTRICAO|PESQUISA PATRIMONIAL|SISBAJUD|"
    r"RENAJUD|EXECUTADO|EXECUTIV|COMPRA E VENDA|SIMULACAO|NEGOCIO JURIDICO"
)
# Barram toda marca, salvo o cabeçalho de família ou sucessões: a ação é de posse, propriedade, título ou
# dano, e a herança ou o divórcio são só a origem do direito discutido.
FAMILIA_ACAO_ALHEIA = re.compile(
    r"USUCAPIAO|REINTEGRACAO|MANUTENCAO DE POSSE|IMISSAO (?:NA|DE) POSSE|INTERDITO|DESPEJO|"
    r"DIVISAO E DEMARCACAO|DEMARCATORIA|"
    r"EXTINCAO DE CONDOMINIO|ALIENACAO JUDICIAL|EXECUCAO DE TITULO|ENTREGA DE COISA|EMBARGOS DE TERCEIRO|"
    r"QUERELA NULLITATIS|ACAO RESCISORIA|ADJUDICACAO COMPULSORIA|RESPONSABILIDADE CIVIL|INDENIZA|DANOS"
)
# A ação de família ou de sucessão nomeada, que mantém no tema a verbetação com ação cível alheia.
FAMILIA_ACAO = re.compile(
    r"(?:ACAO|REVISIONAL|REVISAO|EXONERACAO|EXECUCAO|CUMPRIMENTO DE SENTENCA|OFERTA|FIXACAO) DE ALIMENTOS|"
    r"ALIMENTOS PROVISORIOS|DIVORCIO|DISSOLUCAO DE (?:UNIAO|SOCIEDADE CONJUGAL)|GUARDA|CONVIVENCIA|VISITAS|"
    r"INTERDICAO|CURATELA|ADOCAO|PODER FAMILIAR|ALIENACAO PARENTAL|PATERNIDADE|INVENTARIO|ARROLAMENTO|"
    r"SOBREPARTILHA|SONEGADOS|TESTAMENT|PARTILHA DE BENS|PETICAO DE HERANCA"
)
# Desfecho só processual (régua do operador: só o mérito): extinção sem mérito, perda de objeto,
# competência, representação, admissibilidade, querela, embargos de declaração rejeitados.
FAMILIA_PROCESSUAL = re.compile(
    r"SEM (?:RESOLUCAO|JULGAMENTO|EXAME) D[OE] MERITO|PERDA (?:SUPERVENIENTE )?D[OE] (?:OBJETO|INTERESSE)|"
    r"CONFLITO (?:NEGATIVO |POSITIVO )?DE COMPETENCIA|REPRESENTACAO PROCESSUAL|INTEMPESTIV|DESERCAO|"
    r"QUERELA NULLITATIS|RECURSO NAO CONHECIDO\.?\s*$|EMBARGOS REJEITADOS|DIALETICIDADE|"
    r"NAO CONHECEU D[OE] (?:RECURSO|AGRAVO|APELO|RECLAMO)|"
    r"(?:INSURGENCIA|RECURSO|IRRESIGNACAO|INCONFORMISMO|INSURGE-SE)\w* (?:RESTRIT|LIMITAD|ADSTRIT)[OA]S? "
    r"(?:A|AO|AOS|AS) (?:CONDENACAO|HONORARIO|ONUS|MULTA|VERBA HONORARIA|CUSTAS|GRATUIDADE|JUSTICA GRATUITA|"
    r"SUCUMB|DISTRIBUICAO)"
)
# Nos primeiros segmentos: o recurso é embargos de declaração sem efeito no mérito, ou a ação é de honorários.
FAMILIA_PROCESSUAL_INICIO = re.compile(
    r"EMBARGOS DE DECLARACAO|(?:COBRANCA|EXECUCAO|CUMPRIMENTO DE SENTENCA|ARBITRAMENTO) DE HONORARIOS|"
    r"SUSPENSAO (?:D[OE] (?:PROCESSO|FEITO)|PROCESSUAL)|\bCOMPETENCIA|"
    r"HONORARIOS (?:SUCUMBENCIAIS|ADVOCATICIOS|CONTRATUAIS|PERICIAIS)"
)
FAMILIA_EMBARGOS_ACOLHIDOS = re.compile(
    r"INFRINGENTE|ACOLHID|ACOLHIMENTO|OMISSAO CONFIGURADA|OMISSAO (?:RECONHECIDA|SANADA)|"
    r"CONTRADICAO CONFIGURADA"
)
# Acessório: gratuidade, honorários, multa e má-fé ficam fora quando a verbetação não discute mais nada.
FAMILIA_ACESSORIO = re.compile(
    r"GRATUIDADE|JUSTICA GRATUITA|HONORARIO|SUCUMB|MULTA|ASTREINTE|LITIGANCIA|CUSTAS|ATO ATENTATORIO"
)
# Com o acessório nos primeiros segmentos, como objeto do recurso, só a decisão de mérito expressa o salva.
FAMILIA_DECISAO = re.compile(
    r"BINOMIO|TRINOMIO|MAJORA|MINORA|REDUCAO D[OA] (?:ENCARGO|VERBA|PENSAO|ALIMENTOS|OBRIGACAO|QUANTUM)|"
    r"EXONERA|PRISAO CIVIL|GUARDA (?:COMPARTILHADA|UNILATERAL)|"
    r"PARTILHA DE BENS|MEACAO|INVENTARIANTE|COLACAO|LEGITIMA|DESTITUICAO|ALIMENTOS PROVISORIOS"
)
FAMILIA_MERITO = re.compile(
    r"BINOMIO|TRINOMIO|NECESSIDADE|POSSIBILIDADE|CAPACIDADE|MAJORA|MINORA|REDUCAO|FIXACAO|EXONERA|"
    r"PRISAO CIVIL|DEBITO|PAGAMENTO|DESPESAS|GUARDA|CONVIVENCIA|VISITA|PARTILHA DE BENS|MEACAO|"
    r"INVENTARIANTE|COLACAO|AVALIACAO|ADJUDICA|LEGITIMA|TESTAMENT|DESTITUICAO|ACOLHIMENTO|CURADOR|"
    r"DECRETAD|RECONHECIMENTO|PATERNIDADE|REGIME|BENS|IMOVEL|QUINHAO|HERDEIR|ALIMENT"
)
# Direito à educação ou à saúde da criança é outro tema, salvo quando a verbetação traz a relação de família.
FAMILIA_OUTRO_DIREITO = re.compile(
    r"DIREITO A EDUCACAO|EDUCACAO INFANTIL|EDUCACIONAL|ESCOLAR|CRECHE|ENSINO|MEDICAMENTO|DIREITO A SAUDE|"
    r"TRATAMENTO MEDICO|PLANO DE SAUDE"
)
FAMILIA_RELACAO = re.compile(r"GUARDA|ALIMENT|PODER FAMILIAR|CONVIVENCIA|ADOCAO|ACOLHIMENTO|GENITOR")
FAMILIA_FORA = re.compile(r"ATO INFRACIONAL|CRIMINAL|\bCRIME")
SEGMENTO = re.compile(r"\.\s+|\s+-\s+|\n")


def familia(ementa: str) -> str | None:
    """Motivo pelo qual o acórdão entra no tema família e sucessões, ou None quando fica de fora.

    A marca vale nos quatro primeiros segmentos da verbetação, onde ficam o ramo, a classe e a ação;
    depois deles, a família costuma ser só a origem do fato (o imóvel recebido por herança).
    """
    head = folded(verbetacao(ementa or ""))
    segmentos = [x for x in SEGMENTO.split(head) if x.strip()]
    inicio, resto = " / ".join(segmentos[:4]), " / ".join(segmentos[3:])
    objeto = " / ".join(segmentos[:5])
    if FAMILIA_FORA.search(head) or FAMILIA_PROCESSUAL.search(head):
        return None
    if FAMILIA_PROCESSUAL_INICIO.search(inicio) and not FAMILIA_EMBARGOS_ACOLHIDOS.search(head):
        return None
    if FAMILIA_ACESSORIO.search(head) and not FAMILIA_MERITO.search(resto):
        return None
    if FAMILIA_ACESSORIO.search(objeto) and not FAMILIA_DECISAO.search(resto):
        return None
    if FAMILIA_OUTRO_DIREITO.search(inicio) and not FAMILIA_RELACAO.search(inicio):
        return None
    cabecalho = FAMILIA_FORTES[0]
    # The heading alone does not hold a civil action; a named family action does.
    if FAMILIA_ACAO_ALHEIA.search(inicio) and not FAMILIA_ACAO.search(inicio):
        return None
    if cabecalho[1].search(inicio):
        return "verbetacao: " + cabecalho[0]
    marcas = FAMILIA_FORTES if FAMILIA_BARREIRAS.search(inicio) else FAMILIA_FORTES + FAMILIA_FRACAS
    for label, pattern in marcas:
        if pattern.search(inicio):
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
