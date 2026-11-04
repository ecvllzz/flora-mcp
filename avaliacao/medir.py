"""Mede a busca no caminho que o pipeline usa: modo avançado com filtro de câmara, ao lado do modo simples.

Somente leitura: abre a publicação corrente do acervo em modo imutável e não muda a busca. O acervo vem de
`--data-dir` ou de `FLORA_MCP_DATA_DIR`; sem um dos dois, recusa, para não ler por engano o da configuração.

    python avaliacao/medir.py --conjunto avaliacao/conjunto-m1.json --saida resultado.json

Cada linha é formulação|modo|filtro. Filtro `sem` mede todos os relevantes; `tribunal` restringe a busca e os
relevantes ao tribunal com mais relevantes na pergunta; `camara` restringe à 10ª ou à 9ª Câmara, a do primeiro
relevante dela, como a medida de 23/10. Pergunta sem relevante no recorte fica fora da linha.
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from flora_mcp import api
from flora_mcp.model import FloraError
from flora_mcp.store import Store

TOPO, PROFUNDIDADE = 8, 100
REAMOSTRAS, SEMENTE = 2000, 20261104
LINHAS = (
    ("proposicao", "simples"),
    ("assessor", "simples"),
    ("curta", "simples"),
    ("avancada", "avancado"),
    ("curta", "avancado"),
)
LINHAS_LONGAS = (("longa", "simples"), ("hipotetica", "simples"))
FILTROS = ("sem", "tribunal", "camara")
CAMARAS = {
    "10A CAMARA DE DIREITO CIVIL": "10a Camara de Direito Civil",
    "9A CAMARA DE DIREITO CIVIL": "9a Camara de Direito Civil",
}
ORDEM = """SELECT d.id FROM documents d JOIN search ON search.id=d.id WHERE search MATCH ?{filtro}
ORDER BY bm25(search), d.publication IS NULL, d.publication DESC, d.id LIMIT ?"""

# Regra da R5 para o acórdão do STJ que só aplica óbice (decisão RM-D14): óbice nos primeiros 350 caracteres
# da ementa, sem a Súmula 83, e sem marca de tese da Corte nos primeiros 1.500. Heurística sobre o texto.
OBICE = re.compile(
    r"S[ÚU]MULAS?\s*(N[º°.]?\s*)?(5|7|211|282|283|284|356|518)\b|REEXAME|N[ÃA]O CONHECID|"
    r"PREQUESTIONAMENTO|FUNDAMENTA[ÇC][ÃA]O DEFICIENTE|"
    r"INCID[ÊE]NCIA D[AE]S? S[ÚU]MULAS?\s*+(?:N[º°.]?\s*+)?+(?!83\b)",
    re.I,
)
TESE = re.compile(
    r"JURISPRUD[ÊE]NCIA (DESTA CORTE|DO STJ|CONSOLIDADA|PAC[IÍ]FICA)|ENTENDIMENTO (DESTA CORTE|DO STJ)|"
    r"FIRME NO SENTIDO",
    re.I,
)


def obices_estritos(db):
    consulta = (
        "SELECT d.id, substr(s.ementa, 1, 1500) FROM documents d JOIN search s ON s.id=d.id "
        "WHERE d.tribunal='STJ'"
    )
    return {i for i, e in db.execute(consulta) if OBICE.search(e[:350]) and not TESE.search(e)}


def buscar(store, texto, modo, filtros):
    """Os TOPO primeiros da ferramenta, seguindo o cursor; recusa conta como pergunta sem resultado."""
    try:
        resposta = api.search(store, texto, limite=TOPO, modo_busca=modo, **filtros)
        ids, pagina = [x["id"] for x in resposta["resultados"]], resposta
        while len(ids) < TOPO and pagina["proximo_cursor"]:
            pagina = api.search(
                store, texto, limite=TOPO, modo_busca=modo, cursor=pagina["proximo_cursor"], **filtros
            )
            ids += [x["id"] for x in pagina["resultados"]]
    except FloraError as exc:
        return {"total_encontrado": 0, "consulta_efetiva": "", "erro": exc.code}, []
    return resposta, ids[:TOPO]


def profundo(db, consulta, tribunal=None, orgao=None):
    if not consulta:
        return []
    filtro, params = "", [consulta]
    if tribunal:
        filtro, params = filtro + " AND d.tribunal=?", [*params, tribunal]
    if orgao:
        filtro, params = filtro + " AND d.organ=?", [*params, orgao.upper()]
    return [x[0] for x in db.execute(ORDEM.format(filtro=filtro), (*params, PROFUNDIDADE))]


def ndcg(ids, graus):
    ganho = sum((2 ** graus.get(i, 0) - 1) / math.log2(n + 2) for n, i in enumerate(ids))
    ideal = sorted((g for g in graus.values() if g > 0), reverse=True)[:TOPO]
    melhor = sum((2**g - 1) / math.log2(n + 2) for n, g in enumerate(ideal))
    return ganho / melhor if melhor else 0.0


def medida(resposta, ids, fundo, alvo, graus, obices, julgados):
    posicoes = {e: (fundo.index(e) + 1 if e in fundo else None) for e in alvo}
    no_topo = [e for e in alvo if e in ids]
    linha = {
        "total": resposta["total_encontrado"],
        "erro": resposta.get("erro"),
        "ampliada": "ampliacao" in resposta,
        "consulta_efetiva": resposta["consulta_efetiva"],
        "ids": ids,
        "posicoes": posicoes,
        "ordem_confere": ids == fundo[: len(ids)],
        "hit": bool(no_topo),
        "recall": len(no_topo) / len(alvo),
        "ndcg": ndcg(ids, {i: g for i, g in graus.items() if i in alvo or g == 0}),
        "rr": max((1 / p for p in posicoes.values() if p), default=0.0),
        "descartados_no_topo": sum(1 for i in ids if graus.get(i) == 0),
        "obice_no_topo": sum(1 for i in ids if i in obices),
    }
    if julgados is not None:
        relevantes = {i: g for i, g in julgados.items() if g > 0}
        linha["hit_julgado"] = any(i in relevantes for i in ids)
        linha["ndcg_julgado"] = ndcg(ids, julgados)
        linha["nao_julgados_no_topo"] = sum(1 for i in ids if i not in julgados)
    return linha


def intervalo(valores, sorteio):
    n = len(valores)
    medias = sorted(sum(sorteio.choices(valores, k=n)) / n for _ in range(REAMOSTRAS))
    return [round(medias[int(REAMOSTRAS * 0.025)], 3), round(medias[int(REAMOSTRAS * 0.975)], 3)]


def agregado(linhas):
    n = len(linhas)
    if not n:
        return {"n": 0}
    sorteio = random.Random(SEMENTE)
    resumo = {
        "n": n,
        "hit@8": round(sum(x["hit"] for x in linhas) / n, 3),
        "hit@8_ic95": intervalo([float(x["hit"]) for x in linhas], sorteio),
        "recall@8": round(sum(x["recall"] for x in linhas) / n, 3),
        "ndcg@8": round(sum(x["ndcg"] for x in linhas) / n, 3),
        "ndcg@8_ic95": intervalo([x["ndcg"] for x in linhas], sorteio),
        "mrr@100": round(sum(x["rr"] for x in linhas) / n, 3),
        "fora_dos_100": round(sum(all(p is None for p in x["posicoes"].values()) for x in linhas) / n, 3),
        "vazias": sum(x["total"] == 0 for x in linhas),
        "erros": sum(bool(x["erro"]) for x in linhas),
        "ampliadas": sum(x["ampliada"] for x in linhas),
        "descartados_no_topo": sum(x["descartados_no_topo"] for x in linhas),
        "obice_no_topo": sum(x["obice_no_topo"] for x in linhas),
        "itens_no_topo": sum(len(x["ids"]) for x in linhas),
        "ordem_diverge": sum(not x["ordem_confere"] for x in linhas),
    }
    julgadas = [x for x in linhas if "hit_julgado" in x]
    if julgadas:
        resumo["n_julgadas"] = len(julgadas)
        resumo["hit_julgado@8"] = round(sum(x["hit_julgado"] for x in julgadas) / len(julgadas), 3)
        resumo["ndcg_julgado@8"] = round(sum(x["ndcg_julgado"] for x in julgadas) / len(julgadas), 3)
        resumo["nao_julgados_no_topo"] = sum(x["nao_julgados_no_topo"] for x in julgadas)
    return resumo


def tribunal_de(alvo):
    contagem = {t: sum(e.startswith(t + ":") for e in alvo) for t in ("TJSC", "STJ")}
    return max(contagem, key=contagem.get)


def recortes(pergunta, orgaos):
    """Para cada filtro: os filtros da ferramenta, os da consulta profunda e os relevantes do recorte."""
    alvo = pergunta["esperados"]
    tribunal = tribunal_de(alvo)
    saida = {
        "sem": ({}, {}, alvo),
        "tribunal": (
            {"tribunal": tribunal},
            {"tribunal": tribunal},
            [e for e in alvo if e.startswith(tribunal + ":")],
        ),
    }
    na_camara = [e for e in alvo if orgaos.get(e) in CAMARAS]
    if na_camara:
        orgao = orgaos[na_camara[0]]
        filtros = {"tribunal": "TJSC", "orgao": CAMARAS[orgao]}
        saida["camara"] = (
            filtros,
            {"tribunal": "TJSC", "orgao": orgao},
            [e for e in na_camara if orgaos[e] == orgao],
        )
    return saida


def estrato(pergunta):
    tribunais = {e.split(":")[0] for e in pergunta["esperados"]}
    return tribunais.pop() if len(tribunais) == 1 else "misto"


def medir_pergunta(store, db, pergunta, orgaos, obices, julgamentos, linhas):
    julgados = None
    if pergunta["id"] in julgamentos:
        julgados = {**pergunta["graus"], **{i: int(g) for i, g in julgamentos[pergunta["id"]].items()}}
    linha = {"id": pergunta["id"], "bloco": pergunta["bloco"], "estrato": estrato(pergunta), "linhas": {}}
    for filtro, (da_ferramenta, do_fundo, alvo) in recortes(pergunta, orgaos).items():
        # O ideal do nDCG julgado só conta o que o filtro deixa a busca devolver.
        no_recorte = julgados and {
            i: g
            for i, g in julgados.items()
            if i.startswith(do_fundo.get("tribunal", ""))
            and orgaos.get(i) == do_fundo.get("orgao", orgaos.get(i))
        }
        for formulacao, modo in linhas:
            resposta, ids = buscar(store, pergunta[formulacao], modo, da_ferramenta)
            fundo = profundo(db, resposta["consulta_efetiva"], **do_fundo)
            chave = f"{formulacao}|{modo}|{filtro}"
            linha["linhas"][chave] = medida(resposta, ids, fundo, alvo, pergunta["graus"], obices, no_recorte)
    return linha


def resumir(por_pergunta, linhas, selecao=lambda _: True):
    chaves = [f"{f}|{m}|{x}" for x in FILTROS for f, m in linhas]
    return {
        k: agregado([p["linhas"][k] for p in por_pergunta if k in p["linhas"] and selecao(p)]) for k in chaves
    }


def commit_atual():
    raiz = Path(__file__).resolve().parent
    return subprocess.run(
        ["git", "-C", str(raiz), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data-dir", default=os.environ.get("FLORA_MCP_DATA_DIR"))
    parser.add_argument("--conjunto", required=True)
    parser.add_argument("--julgamentos", help="Graus do julgamento cego da R5, por pergunta")
    parser.add_argument("--saida", required=True)
    parser.add_argument("--longas", action="store_true", help="Mede só as formulações longas")
    args = parser.parse_args()
    linhas = LINHAS_LONGAS if args.longas else LINHAS
    if not args.data_dir:
        parser.error("Informe --data-dir ou FLORA_MCP_DATA_DIR: esta medida roda sobre uma cópia.")
    bruto = Path(args.conjunto).read_bytes()
    conjunto = json.loads(bruto)
    julgamentos = json.loads(Path(args.julgamentos).read_text(encoding="utf-8")) if args.julgamentos else {}
    store = Store(Path(args.data_dir).resolve())
    view = api._view(store)
    inicio = time.time()
    with view.read() as db:
        orgaos = dict(db.execute("SELECT id, organ FROM documents"))
        ausentes = sorted({i for p in conjunto["perguntas"] for i in p["graus"] if i not in orgaos})
        obices = obices_estritos(db)
        por_pergunta = []
        for pergunta in conjunto["perguntas"]:
            por_pergunta.append(medir_pergunta(store, db, pergunta, orgaos, obices, julgamentos, linhas))
            print(pergunta["id"], round(time.time() - inicio), flush=True)
    relatorio = {
        "schema": "flora-avaliacao-resultado-3",
        "medido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "publicacao_id": view.publication,
        "commit": commit_atual(),
        "conjunto": conjunto["schema"],
        "conjunto_sha256": hashlib.sha256(bruto).hexdigest(),
        "perguntas": len(por_pergunta),
        "segundos": round(time.time() - inicio, 1),
        "documentos": {"total": len(orgaos), "obice_estrito_stj": len(obices)},
        "graus_fora_da_publicacao": ausentes,
        "resumo": resumir(por_pergunta, linhas),
        "por_estrato": {
            "bloco_r3": resumir(por_pergunta, linhas, lambda p: p["bloco"] == "r3"),
            "stj": resumir(por_pergunta, linhas, lambda p: p["estrato"] == "STJ"),
            "tjsc": resumir(por_pergunta, linhas, lambda p: p["estrato"] == "TJSC"),
            "misto": resumir(por_pergunta, linhas, lambda p: p["estrato"] == "misto"),
        },
        "por_pergunta": por_pergunta,
    }
    Path(args.saida).write_text(json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("publicacao", view.publication, "perguntas", len(por_pergunta), "segundos", relatorio["segundos"])


if __name__ == "__main__":
    main()
