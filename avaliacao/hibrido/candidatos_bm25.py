"""Listas lexicais (BM25, como a ferramenta ordena) para cada pergunta, formulacao e recorte.

Sistemas: "atual" (E com todos os termos; OU sem palavras vazias quando o E zera, como o main) e "ou"
(OU sem palavras vazias, como o ensaio). Recortes: "geral" e "camara" (orgao da 10a ou da 9a Camara do
primeiro relevante dessa Camara, como medir.py). Somente leitura.

Uso: python candidatos_bm25.py <publicacao.sqlite> <conjunto.json> <saida.json>
"""

import sqlite3
import sys
from pathlib import Path

from comum import PROFUNDIDADE, consulta_atual, consulta_ou, gravar_json, ler_json

CAMARAS = ("10A CAMARA DE DIREITO CIVIL", "9A CAMARA DE DIREITO CIVIL")
ORDEM = (
    "SELECT d.id FROM documents d JOIN search ON search.id=d.id WHERE search MATCH ?{f} "
    "ORDER BY bm25(search), d.publication IS NULL, d.publication DESC, d.id LIMIT ?"
)
CONTAR = "SELECT count(*) FROM documents d JOIN search ON search.id=d.id WHERE search MATCH ?{f}"


def lista(db, consulta, organ):
    if not consulta:
        return [], 0
    f, extra = ("", []) if organ is None else (" AND d.organ=?", [organ])
    total = db.execute(CONTAR.format(f=f), [consulta, *extra]).fetchone()[0]
    ids = [r[0] for r in db.execute(ORDEM.format(f=f), [consulta, *extra, PROFUNDIDADE])]
    return ids, total


def main():
    publicacao = Path(sys.argv[1]).resolve()
    conjunto = ler_json(sys.argv[2])
    db = sqlite3.connect(publicacao.as_uri() + "?mode=ro&immutable=1", uri=True)
    organs = dict(db.execute("SELECT id, organ FROM documents"))
    saida = {"publicacao": publicacao.stem, "profundidade": PROFUNDIDADE, "perguntas": {}}
    for p in conjunto["perguntas"]:
        camara = next((organs[i] for i, g in p["graus"].items() if g > 0 and organs.get(i) in CAMARAS), None)
        registro = {"organ_camara": camara, "formulacoes": {}}
        for f in conjunto["formulacoes"]:
            texto = p.get(f)
            if not texto:
                continue
            e, ampliacao = consulta_atual(texto)
            ou = consulta_ou(texto)
            por_recorte = {}
            for recorte, organ in (("geral", None), ("camara", camara)):
                if recorte == "camara" and camara is None:
                    continue
                ids_e, total_e = lista(db, e, organ)
                ids_atual, total_atual, ampliada = ids_e, total_e, False
                if total_e == 0 and ampliacao is not None:
                    ids_amp, total_amp = lista(db, ampliacao, organ)
                    if total_amp:  # o OU vazio responde como a consulta pedida, sem ampliacao
                        ids_atual, total_atual, ampliada = ids_amp, total_amp, True
                ids_ou, total_ou = lista(db, ou, organ)
                por_recorte[recorte] = {
                    "atual": {
                        "consulta": ampliacao if ampliada else e,
                        "ampliada": ampliada,
                        "total": total_atual,
                        "ids": ids_atual,
                    },
                    "ou": {"consulta": ou, "total": total_ou, "ids": ids_ou},
                }
            registro["formulacoes"][f] = por_recorte
        saida["perguntas"][p["id"]] = registro
    gravar_json(sys.argv[3], saida)
    print(len(saida["perguntas"]), "perguntas;", "formulacoes:", conjunto["formulacoes"])


if __name__ == "__main__":
    main()
