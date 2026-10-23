"""Exporta da publicacao os acordaos em ordem fixa: corpus-meta.json (metadados) e corpus-textos.jsonl.

Somente leitura (modo imutavel). Uso: python exportar_corpus.py <publicacao.sqlite> <pasta-saida>
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from comum import gravar_json, obice_stj

publicacao, saida = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
saida.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(publicacao.as_uri() + "?mode=ro&immutable=1", uri=True)
linhas = db.execute(
    "SELECT id, tribunal, organ, json_extract(body,'$.orgao'), class, json_extract(body,'$.ementa') "
    "FROM documents ORDER BY id"
).fetchall()
meta, h = [], hashlib.sha256()
with open(saida / "corpus-textos.jsonl", "w", encoding="utf-8", newline="\n") as f:
    for i, tribunal, organ, orgao, classe, ementa in linhas:
        ementa = ementa or ""
        meta.append(
            {
                "id": i,
                "tribunal": tribunal,
                "organ": organ,
                "orgao": orgao,
                "classe": classe,
                "obice_stj": obice_stj(tribunal, ementa),
                "caracteres": len(ementa),
            }
        )
        linha = json.dumps({"id": i, "texto": ementa}, ensure_ascii=False)
        f.write(linha + "\n")
        h.update(linha.encode() + b"\n")
pub = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()
gravar_json(
    saida / "corpus-meta.json",
    {
        "publicacao": publicacao.stem,
        "revisao": pub[0] if pub else None,
        "documentos": len(meta),
        "sha256_textos": h.hexdigest(),
        "obice_stj": sum(m["obice_stj"] for m in meta),
        "itens": meta,
    },
)
print(
    len(meta),
    "acordaos;",
    sum(m["obice_stj"] for m in meta),
    "do STJ com obice na verbetacao;",
    h.hexdigest(),
)
