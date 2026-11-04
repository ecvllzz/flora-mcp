"""Monta o lote cego da sessão que julga (RM-D37): pares (pergunta, acórdão) sem grau no topo das linhas.

O lote traz só a proposição, a ementa e um código, em ordem sorteada, sem linha, posição nem sistema. A chave
que liga o código ao par fica em arquivo à parte, que a sessão que julga não abre. Os dois ficam fora do
repositório, porque o lote repete ementas: `--pasta` é recusada dentro dele. Somente leitura, sobre
`FLORA_MCP_DATA_DIR`.

    python avaliacao/preparar_julgamento.py --resultado R.json [--resultado R2.json] --pasta PASTA
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from flora_mcp import api
from flora_mcp.store import Store

SEMENTE = 20261104
RAIZ = Path(__file__).resolve().parents[1]
CONJUNTO = RAIZ / "avaliacao" / "conjunto-m1.json"
JULGAMENTOS = RAIZ / "avaliacao" / "hibrido" / "julgamentos-graus.json"
LONGAS = RAIZ / "avaliacao" / "perguntas-longas.json"


def pares_sem_grau(resultados):
    conjunto = json.loads(CONJUNTO.read_text(encoding="utf-8"))
    julgados = json.loads(JULGAMENTOS.read_text(encoding="utf-8"))
    graus = {p["id"]: {**p["graus"], **julgados.get(p["id"], {})} for p in conjunto["perguntas"]}
    proposicoes = {p["id"]: p["proposicao"] for p in conjunto["perguntas"]}
    longas = json.loads(LONGAS.read_text(encoding="utf-8"))
    proposicoes |= {p["id"]: p["texto"] for p in longas["perguntas"]}
    pares = set()
    for arquivo in resultados:
        for pergunta in json.loads(Path(arquivo).read_text(encoding="utf-8"))["por_pergunta"]:
            for linha in pergunta["linhas"].values():
                ja = graus.get(pergunta["id"], {})
                pares.update((pergunta["id"], i) for i in linha["ids"] if i not in ja)
    return pares, proposicoes


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--resultado", action="append", required=True)
    parser.add_argument("--pasta", required=True)
    parser.add_argument("--data-dir", default=os.environ.get("FLORA_MCP_DATA_DIR"))
    args = parser.parse_args()
    pasta = Path(args.pasta).resolve()
    if not args.data_dir:
        parser.error("Informe --data-dir ou FLORA_MCP_DATA_DIR: esta medida roda sobre uma cópia.")
    if pasta.is_relative_to(RAIZ):
        parser.error("O lote repete ementas e fica fora do repositório.")
    pares, proposicoes = pares_sem_grau(args.resultado)
    ordem = sorted(pares, key=lambda p: hashlib.sha256(f"{SEMENTE}:{p[0]}:{p[1]}".encode()).hexdigest())
    view = api._view(Store(Path(args.data_dir).resolve()))
    lote, chave = [], {}
    with view.read() as db:
        for numero, (pergunta, documento) in enumerate(ordem, 1):
            codigo = f"j{numero:05d}"
            ementa = db.execute(
                "SELECT ementa FROM search WHERE rowid="
                "(SELECT fts_rowid FROM search_map WHERE document_id=?)",
                (documento,),
            ).fetchone()[0]
            lote.append({"codigo": codigo, "proposicao": proposicoes[pergunta], "ementa": ementa[:6000]})
            chave[codigo] = {"pergunta": pergunta, "documento": documento}
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "lote.json").write_text(json.dumps(lote, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    (pasta / "chave.json").write_text(
        json.dumps(chave, ensure_ascii=False, indent=0) + "\n", encoding="utf-8"
    )
    print(len(lote), "pares;", view.publication)


if __name__ == "__main__":
    main()
