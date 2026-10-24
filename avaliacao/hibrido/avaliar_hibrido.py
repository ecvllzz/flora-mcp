"""Avalia sistemas lexicais, densos e hibridos no conjunto, nos recortes geral, sem_obice e camara.

Sistemas: atual, ou (de candidatos_bm25.json); denso:<nome>, hibrido:<nome> (RRF de ou com denso:<nome>),
rrfp:<nome> (RRF com o lexical pesando 1 e o denso 0,5) e ouden:<nome> (os 100 primeiros do ou reordenados
pelo cosseno do denso; pesos e profundidade fixados antes do julgamento),
para cada <nome> com <nome>-docs.npy e <nome>-consultas.json na pasta do corpus; e <sistema>+rr quando ha
arquivo de reordenacao. Recortes: geral; sem_obice (tira das listas e dos graus o acordao do STJ com
obice na verbetacao, pela regra atual de comum.py; a pergunta sem relevante sai da media);
obice_estrito (o mesmo, so para o obice sem marca de tese da Corte, para medir a perda da regra ampla);
stj_enxuto (o estrito mais os EDcl rejeitados e as copias de texto do STJ; o grau de uma copia passa a
primeira ocorrencia); camara
(lexical filtrado pelo orgao e denso restrito a ele). Graus: os do conjunto, completados e corrigidos
pelos julgamentos (pooling), quando dados.

Uso: python avaliar_hibrido.py --conjunto <conj> --bm25 <candidatos.json> --corpus <pasta> --nomes a b
       [--julgamentos julgamentos.json] [--reordenacao rr.json] [--saida resultado.json]
       [--exportar-pares SISTEMA --pares pares.json]
       [--pool pool.json --pool-sistemas s1 s2 --pool-formulacoes f1 f2 [--pool-recorte sem_obice]]
"""

import argparse
import json
from pathlib import Path

import numpy as np

from comum import (
    PROFUNDIDADE,
    TOPO,
    agregado,
    chave_texto,
    edcl_rejeitado,
    gravar_json,
    ler_json,
    medida,
    obice_stj,
    rrf,
    tese_stj,
)

RECORTES = ("geral", "sem_obice", "obice_estrito", "stj_enxuto", "camara")
PARES = 30
PESOS_RRFP = (1.0, 0.5)
REORDENA = 100
# A ementa hipotetica passa do limite de termos da busca lexical: a metade lexical vem da proposicao.
LEXICO_DE = {"hipotetica": "proposicao"}


def marcar_cortes(corpus, meta):
    """(obice, estrito, enxuto, copia_de). obice reaplica a regra atual aos marcados no corpus-meta (a
    regra so encolheu desde a exportacao); estrito e o obice sem marca de tese da Corte; enxuto soma ao
    estrito os EDcl rejeitados e as copias de texto do STJ. copia_de liga cada copia de texto, de qualquer
    tribunal, a primeira ocorrencia (a mesma regra da derivacao copias-texto-1 da publicacao)."""
    por_id = {m["id"]: m for m in meta["itens"]}
    obice, estrito, rejeitados, primeira, copia_de = set(), set(), set(), {}, {}
    with open(corpus / "corpus-textos.jsonl", encoding="utf-8") as fh:
        for linha in fh:
            d = json.loads(linha)
            m = por_id[d["id"]]
            chave = chave_texto(d["texto"])
            if chave in primeira:
                copia_de[d["id"]] = primeira[chave]
            else:
                primeira[chave] = d["id"]
            if m["tribunal"] != "STJ":
                continue
            if m["obice_stj"] and obice_stj("STJ", d["texto"]):
                obice.add(d["id"])
                if not tese_stj(d["texto"]):
                    estrito.add(d["id"])
            if edcl_rejeitado(m["classe"], d["texto"]):
                rejeitados.add(d["id"])
    copias_stj = {i for i in copia_de if por_id[i]["tribunal"] == "STJ"}
    return obice, estrito, estrito | rejeitados | copias_stj, copia_de


def sem_removidos(graus, removidos, copia_de):
    """Graus sem os acordaos removidos; o grau de uma copia removida passa a primeira ocorrencia, quando ela
    continua buscavel."""
    saida = {}
    for q, g in graus.items():
        novo = {i: v for i, v in g.items() if i not in removidos}
        for i, v in g.items():
            if i in removidos and i in copia_de and copia_de[i] not in removidos:
                novo[copia_de[i]] = max(novo.get(copia_de[i], 0), v)
        saida[q] = novo
    return saida


def sem(xs, excluir):
    return [x for x in xs if x not in excluir]


def carregar_densos(corpus, nomes, meta):
    densos = {}
    for nome in nomes:
        docs = np.load(corpus / f"{nome}-docs.npy").astype(np.float32)
        q = ler_json(corpus / f"{nome}-consultas.json")
        assert docs.shape[0] == len(meta["itens"]), f"{nome}: vetores fora do corpus"
        assert q["publicacao"] == meta["publicacao"], f"{nome}: outra publicacao"
        vet = {
            tuple(k): np.asarray(v, dtype=np.float32) for k, v in zip(q["chaves"], q["vetores"], strict=True)
        }
        densos[nome] = (docs, vet, q)
    return densos


def lista_densa(docs, vetor, ids, mascara=None):
    s = docs @ vetor
    if mascara is not None:
        s = np.where(mascara, s, -np.inf)
    topo = np.argpartition(-s, PROFUNDIDADE)[:PROFUNDIDADE]
    topo = topo[np.argsort(-s[topo], kind="stable")]
    return [ids[i] for i in topo if np.isfinite(s[i])]


def main():  # noqa: C901
    a = argparse.ArgumentParser()
    a.add_argument("--conjunto", required=True)
    a.add_argument("--bm25", required=True)
    a.add_argument("--corpus", required=True)
    a.add_argument("--nomes", nargs="*", default=[])
    a.add_argument("--julgamentos")
    a.add_argument("--reordenacao")
    a.add_argument("--saida")
    a.add_argument("--exportar-pares")
    a.add_argument("--pares")
    a.add_argument("--pool")
    a.add_argument("--pool-sistemas", nargs="*", default=[])
    a.add_argument("--pool-formulacoes", nargs="*", default=["proposicao"])
    a.add_argument("--pool-recorte", choices=RECORTES, default="geral")
    a.add_argument(
        "--sem-copias",
        action="store_true",
        help="tira de todas as listas as copias de texto, como a producao",
    )
    args = a.parse_args()
    corpus = Path(args.corpus)
    conjunto, bm25 = ler_json(args.conjunto), ler_json(args.bm25)
    meta = ler_json(corpus / "corpus-meta.json")
    assert bm25["publicacao"] == meta["publicacao"], "candidatos e corpus de publicacoes diferentes"
    ids = [m["id"] for m in meta["itens"]]
    posicao = {i: n for n, i in enumerate(ids)}
    organ = np.array([m["organ"] for m in meta["itens"]])
    obice, estrito, enxuto, copia_de = marcar_cortes(corpus, meta)
    print(
        f"STJ: {len(obice)} com obice pela regra atual, {len(estrito)} sem marca de tese; stj_enxuto tira "
        f"{len(enxuto)}; {len(copia_de)} copias de texto no corpus"
    )
    fora = {"sem_obice": obice, "obice_estrito": estrito, "stj_enxuto": enxuto}
    copias = set(copia_de) if args.sem_copias else set()
    if copias:
        print(len(copias), "copias de texto fora de todas as listas e dos graus")
    densos = carregar_densos(corpus, args.nomes, meta)
    julg = ler_json(args.julgamentos) if args.julgamentos else {}
    rr = ler_json(args.reordenacao) if args.reordenacao else {}

    listas = {}  # (pergunta, formulacao, recorte, sistema) -> ids
    for p in conjunto["perguntas"]:
        b = bm25["perguntas"][p["id"]]
        for f in conjunto["formulacoes"]:
            por_recorte = b["formulacoes"].get(LEXICO_DE.get(f, f))
            if por_recorte is None:
                continue
            for recorte in RECORTES:
                base = por_recorte.get("geral" if recorte in fora else recorte)
                if base is None:
                    continue
                excluir = fora.get(recorte, set()) | copias
                listas[p["id"], f, recorte, "atual"] = sem(base["atual"]["ids"], excluir)
                listas[p["id"], f, recorte, "ou"] = sem(base["ou"]["ids"], excluir)
                mascara = organ == b["organ_camara"] if recorte == "camara" else None
                for nome, (docs, vet, _) in densos.items():
                    if (p["id"], f) not in vet:
                        continue
                    d = sem(lista_densa(docs, vet[p["id"], f], ids, mascara), excluir)
                    listas[p["id"], f, recorte, f"denso:{nome}"] = d
                    ou = listas[p["id"], f, recorte, "ou"]
                    listas[p["id"], f, recorte, f"hibrido:{nome}"] = rrf(ou, d)
                    listas[p["id"], f, recorte, f"rrfp:{nome}"] = rrf(ou, d, pesos=PESOS_RRFP)
                    cos = docs[[posicao[i] for i in ou[:REORDENA]]] @ vet[p["id"], f]
                    topo = [ou[n] for n in np.argsort(-cos, kind="stable")]
                    listas[p["id"], f, recorte, f"ouden:{nome}"] = topo + ou[REORDENA:]
    for (q, f, recorte, s), xs in list(listas.items()):
        chave = f"{q}|{f}|{recorte}|{s}"
        if chave in rr:
            notas = rr[chave]
            topo = sorted(xs[:PARES], key=lambda i: -notas.get(i, -1e9))
            listas[q, f, recorte, s + "+rr"] = topo + xs[PARES:]

    if args.exportar_pares:
        textos = {}
        with open(corpus / "corpus-textos.jsonl", encoding="utf-8") as fh:
            for linha in fh:
                d = json.loads(linha)
                textos[d["id"]] = d["texto"]
        perguntas = {p["id"]: p for p in conjunto["perguntas"]}
        pares = [
            {
                "chave": f"{q}|{f}|{r}|{s}",
                "consulta": perguntas[q][f],
                "documentos": [{"id": i, "texto": textos[i][:4000]} for i in xs[:PARES]],
            }
            for (q, f, r, s), xs in listas.items()
            if s == args.exportar_pares
        ]
        gravar_json(args.pares, pares)
        print(len(pares), "listas para reordenar em", args.pares)
        return

    graus = {}
    for p in conjunto["perguntas"]:
        g = dict(p["graus"])
        g.update({i: int(v["grau"]) for i, v in julg.get(p["id"], {}).items()})
        graus[p["id"]] = g
    graus = sem_removidos(graus, copias, copia_de)
    # Nos recortes de corte o acordao retirado nao e buscavel: sai tambem dos graus.
    graus_de = {r: sem_removidos(graus, x, copia_de) for r, x in fora.items()}

    sistemas = sorted({s for (_, _, _, s) in listas})
    resumo, por_pergunta = {}, {}
    for f in conjunto["formulacoes"]:
        for recorte in RECORTES:
            for s in sistemas:
                linhas, obice_no_topo = [], 0
                for p in conjunto["perguntas"]:
                    xs = listas.get((p["id"], f, recorte, s))
                    g = graus_de.get(recorte, graus)[p["id"]]
                    if xs is None or not any(v > 0 for v in g.values()):
                        continue
                    m = medida(xs, g)
                    linhas.append(m)
                    obice_no_topo += sum(i in obice for i in xs[:TOPO])
                    por_pergunta.setdefault(p["id"], {})[f"{f}|{recorte}|{s}"] = {**m, "topo": xs[:TOPO]}
                if linhas:
                    resumo[f"{f}|{recorte}|{s}"] = {**agregado(linhas), "obice_no_topo": obice_no_topo}
    if args.pool:
        perguntas = {p["id"]: p for p in conjunto["perguntas"]}
        pool = {}
        for (q, f, recorte, s), xs in listas.items():
            if recorte == args.pool_recorte and s in args.pool_sistemas and f in args.pool_formulacoes:
                novos = [i for i in xs[:TOPO] if i not in graus[q]]
                if novos:
                    item = pool.setdefault(q, {"proposicao": perguntas[q]["proposicao"], "ids": []})
                    item["ids"] = sorted(set(item["ids"]) | set(novos))
        gravar_json(args.pool, pool)
        print(
            "pool:",
            sum(len(v["ids"]) for v in pool.values()),
            "acordaos nao julgados em",
            len(pool),
            "perguntas",
        )
    relatorio = {
        "schema": "flora-avaliacao-hibrida-1",
        "publicacao": meta["publicacao"],
        "modelos": {
            n: {k: v for k, v in q.items() if k not in ("chaves", "vetores")}
            for n, (_, _, q) in densos.items()
        },
        "julgamentos": sum(len(v) for v in julg.values()),
        "resumo": resumo,
        "por_pergunta": por_pergunta,
    }
    if args.saida:
        gravar_json(args.saida, relatorio)
    for k, m in resumo.items():
        f, recorte, s = k.split("|")
        if recorte != "camara" or f == "proposicao":
            print(f"{f:11} {recorte:9} {s:28} " + "  ".join(f"{x}={y}" for x, y in m.items()))


if __name__ == "__main__":
    main()
