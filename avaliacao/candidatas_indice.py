"""F6: mede radicalizacao Snowball e peso de cabecalho sobre indices temporarios.

Le a publicacao (imutavel) e constroi indices FTS5 descartaveis em %TEMP%; nao escreve no acervo.
Candidatas que exigiriam reindexar (radicalizacao Snowball e peso do cabecalho), medidas
sem mudar o produto. snowballstemmer nao e dependencia do projeto; rode assim:

    $env:PYTHONPATH = "src"
    uv run --no-project --with snowballstemmer python avaliacao/candidatas_indice.py `
        PUBLICACAO.sqlite avaliacao/conjunto.json avaliacao/resultados/candidatas-indice-rNNN.json

Resultado de 30/09/2026 (r781) em avaliacao/resultados/candidatas-indice-r781.json; decisao
no DECISOES.md.
"""

import functools
import json
import re
import sqlite3
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

import snowballstemmer
from flora_mcp.text import header

STEM = snowballstemmer.stemmer("portuguese")
STOP = set(
    "a ao aos as com como da das de deve do dos e em entre foi na nas no nos o os ou para pela pelas "
    "pelo pelos pode por qual quais quando que quem se sem ser sobre um uma cabe sua seu suas seus "
    "ha nao isso esse essa este esta".split()
)


def fold(v):
    v = unicodedata.normalize("NFKD", v.lower())
    return "".join(c for c in v if not unicodedata.combining(c))


@functools.cache
def raiz(w):
    return fold(STEM.stemWord(w))


def radical(texto):
    return " ".join(raiz(w) for w in re.findall(r"\w+", texto.lower()))


def construir(pub, destino):
    src = sqlite3.connect(Path(pub).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    db = sqlite3.connect(destino)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    tok = "tokenize='unicode61 remove_diacritics 2'"
    for nome, cols in (("base", "t"), ("sec", "c, t"), ("stem", "t"), ("stemsec", "c, t")):
        db.execute(f"CREATE VIRTUAL TABLE {nome} USING fts5(id UNINDEXED, {cols}, {tok})")
    db.execute("CREATE TABLE docs(id TEXT PRIMARY KEY, pub TEXT)")
    t0 = time.time()
    for n, (corpo,) in enumerate(src.execute("SELECT body FROM documents"), 1):
        b = json.loads(corpo)
        e = b["ementa"]
        cab = header(e)[0] or ""
        re_ = radical(e)
        db.execute("INSERT INTO docs VALUES(?,?)", (b["id"], b.get("data_publicacao") or ""))
        db.execute("INSERT INTO base VALUES(?,?)", (b["id"], e))
        db.execute("INSERT INTO sec VALUES(?,?,?)", (b["id"], cab, e))
        db.execute("INSERT INTO stem VALUES(?,?)", (b["id"], re_))
        db.execute("INSERT INTO stemsec VALUES(?,?,?)", (b["id"], radical(cab), re_))
        if n % 5000 == 0:
            print(f"{n} docs {time.time() - t0:.0f}s", flush=True)
    db.commit()
    print(f"indices em {time.time() - t0:.0f}s", flush=True)
    return db


def termos(texto, radicalizar):
    ws = [w for w in re.findall(r"\w+", texto.lower()) if fold(w) not in STOP]
    return [fold(STEM.stemWord(w)) if radicalizar else fold(w) for w in ws]


def consulta(ws, op):
    return f" {op} ".join('"' + w + '"' for w in ws)


def ranquear(db, tabela, pesos, q):
    if not q:
        return []
    ordem = f"bm25({tabela}{pesos})"
    sql = f"SELECT id FROM {tabela} WHERE {tabela} MATCH ? ORDER BY {ordem}, id LIMIT 100"
    return [r[0] for r in db.execute(sql, (q,))]


VARIANTES = {
    "base": ("base", "", False),
    "sec_2": ("sec", ", 0, 2.0, 1.0", False),
    "sec_4": ("sec", ", 0, 4.0, 1.0", False),
    "stem": ("stem", "", True),
    "stemsec_2": ("stemsec", ", 0, 2.0, 1.0", True),
}


def main():
    pub, conjunto, saida = sys.argv[1:4]
    perguntas = json.loads(Path(conjunto).read_text(encoding="utf-8"))
    forms = list(perguntas["formulacoes"])
    tmp = Path(tempfile.gettempdir()) / "flora-f6-candidatas.sqlite"
    if tmp.exists():
        tmp.unlink()
    db = construir(pub, tmp)
    resumo, detalhe = {}, []
    for nome, (tabela, pesos, rad) in VARIANTES.items():
        for f in forms:
            for modo in ("e", "ou", "e_senao_ou"):
                hits = rr = zeros = 0
                for p in perguntas["perguntas"]:
                    ws = termos(p[f], rad)
                    ids = ranquear(db, tabela, pesos, consulta(ws, "AND"))
                    if modo == "ou" or (modo == "e_senao_ou" and not ids):
                        ids = ranquear(db, tabela, pesos, consulta(ws, "OR"))
                    pos = [ids.index(e) + 1 for e in p["esperados"] if e in ids]
                    hits += bool(pos and min(pos) <= 8)
                    rr += 1 / min(pos) if pos else 0
                    zeros += not ids
                    detalhe.append({"variante": nome, "form": f, "modo": modo, "id": p["id"], "pos": pos})
                n = len(perguntas["perguntas"])
                resumo[f"{nome}|{f}|{modo}"] = {
                    "hit@8": round(hits / n, 3),
                    "mrr": round(rr / n, 3),
                    "zeros": zeros,
                }
    Path(saida).write_text(
        json.dumps({"resumo": resumo, "detalhe": detalhe}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for k, v in resumo.items():
        print(k, v)
    db.close()
    tmp.unlink()


if __name__ == "__main__":
    main()
