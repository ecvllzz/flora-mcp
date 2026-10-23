"""Regras comuns do kit: normalizacao, compiladores lexicais iguais aos do Flora-MCP, obice do STJ e metricas.

Os compiladores reproduzem src/flora_mcp/query.py do main (280622a) e do ensaio OU
(reforma/r3-ensaio-ou-simples).
"""

import json
import math
import re
import unicodedata

STOPWORDS = frozenset(
    """
    o a os as um uma uns umas
    ante apos ate com contra de desde em entre para perante por sem sob sobre
    ao aos do da dos das no na nos nas num numa pelo pela pelos pelas
    deste desta destes destas desse dessa desses dessas neste nesta nesse nessa
    e ou mas nem que se porque pois porem como quando
    qual quais quem onde cujo cuja cujos cujas quanto quanta quantos quantas
    pode podem deve devem cabe cabem foi foram ser sao esta estao ha
    """.upper().split()
)
JUDGMENT_STOPWORDS = STOPWORDS | frozenset("NAO SUA SUAS SEU SEUS ISSO ESSE ESSA ESTE".split())

# Obice de admissibilidade na verbetacao (primeiros 350 caracteres da ementa do STJ).
OBICE = re.compile(
    r"S[ÚU]MULAS?\s*(N[º°.]?\s*)?(5|7|83|211|282|283|284|356|518)\b|REEXAME|N[ÃA]O CONHECID|"
    r"PREQUESTIONAMENTO|FUNDAMENTA[ÇC][ÃA]O DEFICIENTE|INCID[ÊE]NCIA D[AE]S? S[ÚU]MULA",
    re.I,
)
CABECALHO_OBICE = 350
TOPO = 8
PROFUNDIDADE = 200
RRF_K = 60


def folded(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).upper()


def quoted(value):
    return '"' + value.replace('"', '""') + '"'


def tokens(termos):
    """(valor, frase) como lexical_tokens do Flora-MCP; None quando a ferramenta recusaria a consulta."""
    if len(termos) > 500 or termos.count('"') % 2:
        return None
    found = [(p, True) if p else (t, False) for p, t in re.findall(r'"([^"]+)"|(\S+)', termos)]
    return None if len(found) > 30 else found


def conteudo(toks, palavras_vazias):
    return [v for v, frase in toks if frase or re.sub(r"\W", "", folded(v)) not in palavras_vazias]


def consulta_atual(termos):
    """(E com todos os termos, OU da ampliacao ou None): o compilador simples do main."""
    toks = tokens(termos)
    if not toks:
        return None, None
    e = " AND ".join(quoted(v) for v, _ in toks)
    kept = conteudo(toks, STOPWORDS)
    ou = " OR ".join(quoted(v) for v in kept) if len(toks) >= 2 and kept else None
    return e, ou


def consulta_ou(termos):
    toks = tokens(termos)
    if not toks:
        return None
    kept = conteudo(toks, JUDGMENT_STOPWORDS) or [v for v, _ in toks]
    return " OR ".join(quoted(v) for v in kept)


def obice_stj(tribunal, ementa):
    return tribunal == "STJ" and bool(OBICE.search((ementa or "")[:CABECALHO_OBICE]))


def rrf(*listas, k=RRF_K):
    score = {}
    for lista in listas:
        for posicao, i in enumerate(lista):
            score[i] = score.get(i, 0.0) + 1.0 / (k + posicao + 1)
    return [i for i, _ in sorted(score.items(), key=lambda x: (-x[1], x[0]))]


def ndcg(ids, graus):
    ganho = sum((2 ** graus.get(i, 0) - 1) / math.log2(n + 2) for n, i in enumerate(ids))
    ideal = sorted((g for g in graus.values() if g > 0), reverse=True)[:TOPO]
    melhor = sum((2**g - 1) / math.log2(n + 2) for n, g in enumerate(ideal))
    return ganho / melhor if melhor else 0.0


def medida(lista, graus):
    """Metricas de uma lista ordenada contra graus {id: 0, 1 ou 2}."""
    alvo = [i for i, g in graus.items() if g > 0]
    topo = lista[:TOPO]
    pos = [lista.index(e) + 1 for e in alvo if e in lista[:100]]
    return {
        "hit": any(e in topo for e in alvo),
        "recall": sum(e in topo for e in alvo) / len(alvo) if alvo else 0.0,
        "ndcg": ndcg(topo, graus),
        "rr": 1 / min(pos) if pos else 0.0,
        "fora_dos_100": not pos,
        "nao_julgados_no_topo": sum(1 for i in topo if i not in graus),
    }


def agregado(linhas):
    n = len(linhas)
    if not n:
        return {"n": 0}
    soma = lambda k: sum(float(x[k]) for x in linhas)  # noqa: E731
    return {
        "n": n,
        "hit@8": round(soma("hit") / n, 3),
        "recall@8": round(soma("recall") / n, 3),
        "ndcg@8": round(soma("ndcg") / n, 3),
        "mrr@100": round(soma("rr") / n, 3),
        "fora_dos_100": round(soma("fora_dos_100") / n, 3),
        "nao_julgados_no_topo": int(soma("nao_julgados_no_topo")),
    }


def ler_json(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho, valor):
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump(valor, f, ensure_ascii=False, indent=1)
        f.write("\n")
