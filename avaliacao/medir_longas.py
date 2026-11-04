"""Linha de base das perguntas longas de RM-D38: quantas a busca simples recusa e o que devolve nas demais.

Sem gabarito: o resultado alimenta o lote cego de `preparar_julgamento.py` e não dá acerto. Somente leitura,
sobre a publicação de `FLORA_MCP_DATA_DIR`.

    python avaliacao/medir_longas.py --conjunto avaliacao/perguntas-longas.json --saida resultado.json
"""

import argparse
import collections
import json
import os
from datetime import datetime
from pathlib import Path

from flora_mcp import api
from flora_mcp.model import FloraError
from flora_mcp.store import Store

TOPO = 8


def buscar(store, texto):
    try:
        resposta = api.search(store, texto, limite=TOPO)
        ids, pagina = [x["id"] for x in resposta["resultados"]], resposta
        while len(ids) < TOPO and pagina["proximo_cursor"]:
            pagina = api.search(store, texto, limite=TOPO, cursor=pagina["proximo_cursor"])
            ids += [x["id"] for x in pagina["resultados"]]
    except FloraError as exc:
        return {"erro": exc.code, "total": 0, "ids": []}
    return {"erro": None, "total": resposta["total_encontrado"], "ids": ids[:TOPO]}


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data-dir", default=os.environ.get("FLORA_MCP_DATA_DIR"))
    parser.add_argument("--conjunto", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()
    if not args.data_dir:
        parser.error("Informe --data-dir ou FLORA_MCP_DATA_DIR: esta medida roda sobre uma cópia.")
    conjunto = json.loads(Path(args.conjunto).read_text(encoding="utf-8"))
    store = Store(Path(args.data_dir).resolve())
    por_pergunta = []
    for pergunta in conjunto["perguntas"]:
        linha = buscar(store, pergunta["texto"])
        por_pergunta.append(
            {
                "id": pergunta["id"],
                "tipo": pergunta["tipo"],
                "acima_dos_limites": pergunta["acima_dos_limites"],
                "linhas": {"longa_real|simples|sem": linha},
            }
        )
    resumo = collections.defaultdict(lambda: {"n": 0, "recusadas": 0, "vazias": 0})
    for linha in por_pergunta:
        for chave in (linha["tipo"], "todas"):
            item = linha["linhas"]["longa_real|simples|sem"]
            resumo[chave]["n"] += 1
            resumo[chave]["recusadas"] += bool(item["erro"])
            resumo[chave]["vazias"] += item["total"] == 0 and not item["erro"]
    relatorio = {
        "schema": "flora-avaliacao-longas-resultado-1",
        "medido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "publicacao_id": api._view(store).publication,
        "resumo": dict(resumo),
        "por_pergunta": por_pergunta,
    }
    Path(args.saida).write_text(json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(dict(resumo))


if __name__ == "__main__":
    main()
