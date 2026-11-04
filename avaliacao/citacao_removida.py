"""Perguntas com gabarito que dispensa juízo (RM-D37): acórdão do TJSC que cita o STJ, sem a citação.

A consulta é o trecho da própria ementa, tirada a menção ao que ela cita; a busca acerta se devolver o citado
nos oito primeiros. O conjunto guarda só identificadores: o texto se refaz do acervo na hora de medir, e nem a
consulta nem a ementa vão ao repositório. Somente leitura, sobre a publicação de `FLORA_MCP_DATA_DIR`.

    python avaliacao/citacao_removida.py montar --saida avaliacao/conjunto-citacao-removida.json
    python avaliacao/citacao_removida.py medir --conjunto CONJUNTO --saida resultado.json

`montar` aceita `--excluir ARQUIVO`, um número por linha: ficam fora as ementas de processos com esse número.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from medir import OBICE, TESE, TOPO, intervalo  # noqa: E402

from flora_mcp import api  # noqa: E402
from flora_mcp.model import FloraError  # noqa: E402
from flora_mcp.store import Store  # noqa: E402
from flora_mcp.text import sections  # noqa: E402

SEMENTE = 20261104
N_PRECEDENTES, N_ACORDAOS = 200, 100
LIMITE_TERMOS = 30
ORIGEM = "ementa_cnj:jurisprudencia_citada"
FORMULACOES = ("cabecalho_30", "tese_30", "tese_inteira")
SECOES_TESE = ("tese_na_ementa", "dispositivo_e_tese")
MENCAO = re.compile(
    r"\b(?:temas?|s[úu]mulas?|irdr|iac|repetitivos?)\b[^.;:)]{0,60}"
    r"|\b(?:resp|aresp|agint|agrg|edcl|recurso especial|stj|stf)\b[^.;:)]{0,60}",
    re.I,
)


def chave_sorteio(valor):
    return hashlib.sha256(f"{SEMENTE}:{valor}".encode()).hexdigest()


def trechos(ementa):
    """Cabeçalho e tese da ementa no modelo CNJ, sem menção a precedente; None fora do modelo."""
    por_nome = {s["nome"]: ementa[s["inicio"] : s["fim"]] for s in sections(ementa)}
    tese = next((por_nome[n] for n in SECOES_TESE if por_nome.get(n)), None)
    cabecalho = por_nome.get("cabecalho")
    if not tese or not cabecalho:
        return None
    return {
        nome: " ".join(MENCAO.sub(" ", texto).replace('"', " ").split())
        for nome, texto in [("cabecalho", cabecalho), ("tese", tese)]
    }


def consultas(ementa):
    partes = trechos(ementa)
    if not partes:
        return None
    return {
        "cabecalho_30": " ".join(partes["cabecalho"].split()[:LIMITE_TERMOS]),
        "tese_30": " ".join(partes["tese"].split()[:LIMITE_TERMOS]),
        "tese_inteira": partes["tese"],
    }


def citantes(db, tipo, excluidos):
    """Ementa do TJSC, com tese e cabeçalho, de cada citado do STJ daquele tipo no acervo."""
    consulta = """SELECT c.document_id, c.resolvido, d.process, s.ementa FROM document_citations c
    JOIN documents d ON d.id=c.document_id JOIN search s ON s.id=c.document_id
    WHERE d.tribunal='TJSC' AND c.origem=? AND c.tipo=? AND c.resolvido LIKE 'STJ:%'"""
    por_documento = {}
    for documento, citado, processo, ementa in db.execute(consulta, (ORIGEM, tipo)):
        digitos = re.sub(r"\D", "", processo or "")
        if tipo == "precedente" and not re.match(r"STJ:(tema_repetitivo|sumula):", citado):
            continue
        if (
            any(n in digitos for n in excluidos)
            or documento in por_documento
            and citado in por_documento[documento]
        ):
            continue
        if documento in por_documento or consultas(ementa):
            por_documento.setdefault(documento, []).append(citado)
    return por_documento


def sortear(por_documento, limite):
    """Um documento por citado, os dois na ordem de um hash com semente, para Súmula 54 não dominar."""
    vistos, escolhidos = set(), []
    for documento in sorted(por_documento, key=chave_sorteio):
        novos = [c for c in por_documento[documento] if c not in vistos]
        if novos and len(escolhidos) < limite:
            vistos.update(por_documento[documento])
            escolhidos.append({"documento": documento, "citados": sorted(set(por_documento[documento]))})
    return escolhidos


def montar(args, store):
    excluidos = set()
    if args.excluir:
        excluidos = {x for x in Path(args.excluir).read_text(encoding="utf-8").split() if x}
    view = api._view(store)
    with view.read() as db:
        precedentes = citantes(db, "precedente", excluidos)
        acordaos = citantes(db, "acordao", excluidos)
    blocos = {"precedente": sortear(precedentes, N_PRECEDENTES), "acordao": sortear(acordaos, N_ACORDAOS)}
    saida = {
        "schema": "flora-avaliacao-citacao-1",
        "montado_em": datetime.now().astimezone().date().isoformat(),
        "publicacao_de_referencia": view.publication,
        "semente": SEMENTE,
        "regra": (
            "Ementa do TJSC no modelo CNJ que cita tema, súmula ou acórdão do STJ resolvido no acervo, na "
            "linha "
            "de jurisprudência citada; um documento por citado, na ordem de sha256(semente:id)."
        ),
        "universo": {"precedente": len(precedentes), "acordao": len(acordaos)},
        "blocos": blocos,
    }
    Path(args.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in blocos.items()}, saida["universo"])


def buscar(store, bloco, texto):
    funcao = api.search_precedents if bloco == "precedente" else api.search
    try:
        resposta = funcao(store, texto, tribunal="STJ", limite=TOPO)
        ids, pagina = [x["id"] for x in resposta["resultados"]], resposta
        while len(ids) < TOPO and pagina["proximo_cursor"]:
            pagina = funcao(store, texto, tribunal="STJ", limite=TOPO, cursor=pagina["proximo_cursor"])
            ids += [x["id"] for x in pagina["resultados"]]
    except FloraError as exc:
        return {"total_encontrado": 0, "erro": exc.code}, []
    return resposta, ids[:TOPO]


def agregado(linhas):
    n = len(linhas)
    sorteio = random.Random(SEMENTE)
    return {
        "n": n,
        "hit@8": round(sum(x["hit"] for x in linhas) / n, 3),
        "hit@8_ic95": intervalo([float(x["hit"]) for x in linhas], sorteio),
        "mrr@8": round(sum(x["rr"] for x in linhas) / n, 3),
        "recusadas": sum(bool(x["erro"]) for x in linhas),
        "vazias": sum(x["total"] == 0 and not x["erro"] for x in linhas),
        "ampliadas": sum(x["ampliada"] for x in linhas),
        "obice_no_topo": sum(x["obice_no_topo"] for x in linhas),
        "itens_no_topo": sum(len(x["ids"]) for x in linhas),
    }


def medir(args, store):
    conjunto = json.loads(Path(args.conjunto).read_text(encoding="utf-8"))
    view = api._view(store)
    inicio = time.time()
    por_documento = []
    with view.read() as db:
        obices = {
            i
            for i, e in db.execute(
                "SELECT d.id, substr(s.ementa, 1, 1500) FROM documents d JOIN search s ON s.id=d.id "
                "WHERE d.tribunal='STJ'"
            )
            if OBICE.search(e[:350]) and not TESE.search(e)
        }
        for bloco, itens in conjunto["blocos"].items():
            for item in itens:
                ementa = db.execute(
                    "SELECT ementa FROM search WHERE rowid="
                    "(SELECT fts_rowid FROM search_map WHERE document_id=?)",
                    (item["documento"],),
                ).fetchone()[0]
                textos = consultas(ementa)
                linha = {"bloco": bloco, "documento": item["documento"], "linhas": {}}
                for formulacao in FORMULACOES:
                    resposta, ids = buscar(store, bloco, textos[formulacao])
                    posicoes = [ids.index(c) + 1 for c in item["citados"] if c in ids]
                    linha["linhas"][formulacao] = {
                        "total": resposta["total_encontrado"],
                        "erro": resposta.get("erro"),
                        "ampliada": "ampliacao" in resposta,
                        "ids": ids,
                        "hit": bool(posicoes),
                        "rr": 1 / min(posicoes) if posicoes else 0.0,
                        "obice_no_topo": sum(1 for i in ids if i in obices),
                    }
                por_documento.append(linha)
                print(bloco, len(por_documento), round(time.time() - inicio), flush=True)
    relatorio = {
        "schema": "flora-avaliacao-citacao-resultado-1",
        "medido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "publicacao_id": view.publication,
        "segundos": round(time.time() - inicio, 1),
        "resumo": {
            f"{b}|{f}": agregado([p["linhas"][f] for p in por_documento if p["bloco"] == b])
            for b in conjunto["blocos"]
            for f in FORMULACOES
        },
        "por_documento": por_documento,
    }
    Path(args.saida).write_text(json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("comando", choices=("montar", "medir"))
    parser.add_argument("--data-dir", default=os.environ.get("FLORA_MCP_DATA_DIR"))
    parser.add_argument("--conjunto")
    parser.add_argument("--excluir")
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()
    if not args.data_dir:
        parser.error("Informe --data-dir ou FLORA_MCP_DATA_DIR: esta medida roda sobre uma cópia.")
    store = Store(Path(args.data_dir).resolve())
    (montar if args.comando == "montar" else medir)(args, store)


if __name__ == "__main__":
    main()
