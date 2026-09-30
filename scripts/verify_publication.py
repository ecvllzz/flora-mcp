"""Read-only comparison of published judgments with their work-database originals."""

import argparse
import hashlib
import json
from pathlib import Path

from flora_mcp.api import coverage, search
from flora_mcp.citation import citation_metadata
from flora_mcp.config import load_config
from flora_mcp.model import canonical, now
from flora_mcp.publication import Reader
from flora_mcp.store import Store


def fingerprint(store):
    hasher = hashlib.sha256()
    count, complete = 0, 0
    with store.read() as db:
        db.execute("BEGIN")
        for row in db.execute(
            "SELECT d.id,d.hash,d.body,v.raw FROM documents d JOIN versions v ON v.document_id=d.id AND "
            "v.hash=d.hash ORDER BY d.id"
        ):
            body = json.loads(row["body"])
            citation = citation_metadata(body, json.loads(row["raw"]))
            hasher.update(canonical([row["id"], row["hash"], body, citation]).encode())
            count += 1
            complete += citation["referencia_completa"]
        groups = [
            dict(r)
            for r in db.execute(
                "SELECT tribunal,count(*) AS documentos FROM documents GROUP BY tribunal ORDER BY tribunal"
            )
        ]
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "documentos": count,
        "referencias_estruturalmente_completas": complete,
        "sha256_registros_e_referencias": hasher.hexdigest(),
        "grupos": groups,
        "integridade": integrity,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    store = Store(load_config(data_dir=args.data_dir).data_dir)
    view = Reader(store).resolve()
    if view.publication is None:
        parser.error("Nenhuma publicação ativada.")
    original, published = fingerprint(store), fingerprint(view)
    assert original == published, "Publicação diverge dos registros originais."
    assert original["integridade"] == "ok"
    triage = search(store, "alimentos", detalhe="triagem")
    summary = coverage(store)
    receipt = {
        "status": "ok",
        "conferido_em": now(),
        "publicacao_id": view.publication,
        "conteudo_preservado": original,
        "triagem_bytes": len(canonical(triage).encode()),
        "cobertura_resumo_caracteres": len(canonical(summary)),
        "cobertura_resumo_bytes": len(canonical(summary).encode()),
        "limite": "Igualdade estrutural e literal; não certifica autoridade jurídica dos acórdãos.",
    }
    assert receipt["triagem_bytes"] <= 8192
    assert receipt["cobertura_resumo_caracteres"] < 10000
    output = json.dumps(receipt, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == "__main__":
    main()
