"""Mede a recuperacao da busca contra o conjunto de referencia (avaliacao/conjunto.json).

Somente leitura: abre a publicacao corrente (ou --publicacao) em modo imutavel.
Mede a ferramenta como o agente a chama e, em paralelo, compiladores candidatos de
consulta sobre o mesmo indice, para decidir mudancas da F6 por ganho medido.

Uso: python scripts/avaliar.py --data-dir <acervo> [--publicacao ID] [--saida arquivo]
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from flora_mcp import api
from flora_mcp.model import canonical
from flora_mcp.store import Store

ROOT = Path(__file__).resolve().parents[1]
PROFUNDIDADE = 100
TOPO = 8
STOPWORDS = set(
    "a ao aos as com como da das de deve do dos e em entre foi na nas no nos o os ou para pela pelas "
    "pelo pelos pode por qual quais quando que quem se sem ser sobre um uma cabe sua seu suas seus "
    "ha nao isso esse essa este esta".split()
)


def fold(value):
    value = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in value if not unicodedata.combining(c))


def palavras(texto):
    return [w for w in re.findall(r"\w+", fold(texto)) if w not in STOPWORDS]


def quoted(value):
    return '"' + value.replace('"', '""') + '"'


def termo(w, corte):
    if corte and len(w) > corte:
        return quoted(w[:corte]) + "*"
    return quoted(w)


def compilador(operador, corte=None):
    def compilar(texto):
        ws = palavras(texto)
        return f" {operador} ".join(termo(w, corte) for w in ws) if ws else ""

    return compilar


CANDIDATOS = {
    "e": compilador("AND"),
    "e_p6": compilador("AND", 6),
    "ou": compilador("OR"),
    "ou_p6": compilador("OR", 6),
    "ou_p5": compilador("OR", 5),
}
# Recuo: E quando ha resultado, OU quando o E zera (o agente nao reformula).
RECUOS = {"e_senao_ou": ("e", "ou")}

RANQUEAR = """SELECT d.id FROM documents d JOIN search ON search.id=d.id
WHERE search MATCH ? ORDER BY bm25(search), d.publication IS NULL, d.publication DESC, d.id LIMIT ?"""


def posicoes(ids, esperados):
    return {e: (ids.index(e) + 1 if e in ids else None) for e in esperados}


def medidas(pos):
    ranks = [r for r in pos.values() if r]
    return {
        "hit": any(r <= TOPO for r in ranks),
        "recall": sum(1 for r in ranks if r <= TOPO) / len(pos),
        "rr": 1 / min(ranks) if ranks else 0.0,
    }


def ferramenta(store, texto, esperados):
    resultado = api.search(store, texto, limite=TOPO)
    ids = [r["id"] for r in resultado["resultados"]]
    pos = posicoes(ids, esperados)
    return {
        "total": resultado["total_encontrado"],
        "bytes": len(canonical(resultado).encode()),
        "ids": ids,
        "posicoes": pos,
        **medidas(pos),
    }, resultado.get("publicacao_id")


def candidato(db, compilar, texto, esperados):
    consulta = compilar(texto)
    if not consulta:
        ids = []
    else:
        ids = [r[0] for r in db.execute(RANQUEAR, (consulta, PROFUNDIDADE))]
    pos = posicoes(ids, esperados)
    return {"consulta": consulta, "retornados": len(ids), "posicoes": pos, **medidas(pos)}


def agregado(linhas):
    n = len(linhas)
    return {
        "hit@8": round(sum(x["hit"] for x in linhas) / n, 3),
        "recall@8": round(sum(x["recall"] for x in linhas) / n, 3),
        "mrr@100": round(sum(x["rr"] for x in linhas) / n, 3),
        "zeros": sum(1 for x in linhas if x.get("total", x.get("retornados")) == 0),
        **(
            {"bytes_medio": round(sum(x["bytes"] for x in linhas) / n)}
            if all("bytes" in x for x in linhas)
            else {}
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--conjunto", default=str(ROOT / "avaliacao" / "conjunto.json"))
    parser.add_argument("--publicacao")
    parser.add_argument("--saida")
    args = parser.parse_args()
    conjunto = json.loads(Path(args.conjunto).read_text(encoding="utf-8"))
    store = Store(Path(args.data_dir).resolve())
    view = api._view(store, publicacao_id=args.publicacao)
    formulacoes = tuple(conjunto.get("formulacoes") or ("assessor", "natural"))
    por_pergunta, publicacao = [], view.publication
    with view.read() as db:
        for p in conjunto["perguntas"]:
            linha = {"id": p["id"], "esperados": p["esperados"]}
            for f in formulacoes:
                linha[f] = {"ferramenta": ferramenta(store, p[f], p["esperados"])[0]}
                for nome, compilar in CANDIDATOS.items():
                    linha[f][nome] = candidato(db, compilar, p[f], p["esperados"])
                for nome, (primeiro, recuo) in RECUOS.items():
                    escolhido = primeiro if linha[f][primeiro]["retornados"] else recuo
                    linha[f][nome] = {**linha[f][escolhido], "usou": escolhido}
            por_pergunta.append(linha)
    nomes = ("ferramenta", *CANDIDATOS, *RECUOS)
    resumo = {f: {c: agregado([q[f][c] for q in por_pergunta]) for c in nomes} for f in formulacoes}
    relatorio = {
        "schema": "flora-avaliacao-resultado-1",
        "medido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "publicacao_id": publicacao,
        "conjunto": conjunto["schema"],
        "perguntas": len(por_pergunta),
        "resumo": resumo,
        "por_pergunta": por_pergunta,
    }
    saida = Path(args.saida) if args.saida else ROOT / "avaliacao" / "resultados" / f"{publicacao}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for f in formulacoes:
        print(f"== {f}")
        for c, m in resumo[f].items():
            print(f"  {c:11} " + "  ".join(f"{k}={v}" for k, v in m.items()))
    print(f"salvo em {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
