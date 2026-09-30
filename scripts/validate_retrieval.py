"""Exercise the configured stdio server against a fixed, partial real corpus.

No ingestion or legal-validity claims. Saves complete answers for inspection.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
QUERIES = [
    ("alimentos", "alimentos"),
    ("guarda", '"guarda compartilhada"'),
    ("partilha", "partilha"),
    ("uniao", '"união estável"'),
    ("prisao", "alimentos prisão"),
    ("compensatorios", "compensatórios"),
]


async def main(data_dir: Path):
    config = {
        "command": sys.executable,
        "args": ["-m", "flora_mcp.cli", "--data-dir", str(data_dir), "serve"],
        "env": {"PYTHONUTF8": "1"},
    }
    database = data_dir / "acervo.sqlite"
    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    rows = [json.loads(r[0]) for r in db.execute("SELECT body FROM documents ORDER BY id")]
    db.close()
    by_id = {r["id"]: r for r in rows}
    groups = {}
    for row in rows:
        groups.setdefault((row["tribunal"], row["orgao"]), []).append(row)
    selected = [r for group in groups.values() for r in group[:6]]
    longest = max(rows, key=lambda r: len(r["ementa"]))
    if longest["id"] not in {r["id"] for r in selected}:
        selected.append(longest)
    report = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "corpus_count": len(rows),
        "queries": [],
        "documents": [],
        "limitations": [
            "Partial corpus",
            "Lexical search, not semantic ranking",
            "No legal currency or full judgment verification",
        ],
    }
    params = StdioServerParameters(
        command=config["command"], args=config["args"], env={**os.environ, **config["env"]}
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            report["tools"] = [t.name for t in (await session.list_tools()).tools]

            async def call(tool, args):
                result = await session.call_tool(tool, args)
                assert not result.is_error
                return result.structured_content

            report["coverage"] = await call("consultar_cobertura", {})
            for name, terms in QUERIES:
                for tribunal in ("STJ", "TJSC"):
                    args = {"termos": terms, "tribunal": tribunal, "limite": 3, "detalhe": "completo"}
                    answer = await call("pesquisar_jurisprudencia", args)
                    assert answer["status"] == "ok"
                    assert answer["cobertura"]["integral"] is False
                    for doc in answer["resultados"]:
                        assert doc["tribunal"] == tribunal
                        assert doc["ementa"] == by_id[doc["id"]]["ementa"]
                    report["queries"].append({"name": name, "args": args, "answer": answer})
            for row in selected:
                args = {"id": row["id"], "tamanho_bloco": 800}
                pieces = []
                while True:
                    answer = await call("obter_documento", args)
                    assert answer["status"] == "ok"
                    pieces.append(answer["texto"])
                    if not answer["proximo_cursor"]:
                        break
                    args["cursor"] = answer["proximo_cursor"]
                complete = "".join(pieces)
                assert complete == row["ementa"]
                assert hashlib.sha256(complete.encode()).hexdigest() == answer["sha256_texto_completo"]
                report["documents"].append(
                    {
                        "id": row["id"],
                        "tribunal": row["tribunal"],
                        "orgao": row["orgao"],
                        "characters": len(complete),
                        "blocks": len(pieces),
                        "sha256": answer["sha256_texto_completo"],
                        "complete": True,
                    }
                )
            checks = []
            for (tribunal, organ), group in groups.items():
                answer = await call(
                    "pesquisar_jurisprudencia", {"tribunal": tribunal, "orgao": organ, "limite": 5}
                )
                assert answer["total_encontrado"] == len(group)
                assert all(r["orgao"] == organ for r in answer["resultados"])
                checks.append({"filter": organ, "count": len(group)})
            first = await call("pesquisar_jurisprudencia", {"tribunal": "TJSC", "limite": 5})
            second = await call(
                "pesquisar_jurisprudencia",
                {"tribunal": "TJSC", "limite": 5, "cursor": first["proximo_cursor"]},
            )
            assert not {r["id"] for r in first["resultados"]} & {r["id"] for r in second["resultados"]}
            exact_row = groups[("TJSC", "10ª Câmara de Direito Civil")][0]
            exact = await call(
                "pesquisar_jurisprudencia", {"processo": exact_row["processo"], "tribunal": "TJSC"}
            )
            assert exact_row["id"] in {r["id"] for r in exact["resultados"]}
            dated = await call(
                "pesquisar_jurisprudencia",
                {"tribunal": "TJSC", "data_inicio": "2026-09-19", "data_fim": "2026-09-19"},
            )
            assert dated["total_encontrado"] == 23
            empty = await call("pesquisar_jurisprudencia", {"termos": "floraausenciacontrolexyz"})
            assert empty["total_encontrado"] == 0 and empty["cobertura"]["integral"] is False
            assert empty["motivo"] == "sem_correspondencia"
            missing = await session.call_tool("obter_documento", {"id": "controle-ausente"})
            assert missing.is_error
            assert missing.structured_content["codigo"] == "documento_nao_encontrado"
            report["checks"] = {
                "organ_filters": checks,
                "pagination_no_duplicates": True,
                "exact_process": True,
                "date_filter": True,
                "empty_with_partial_coverage": True,
                "missing_document": True,
            }
    report["status"] = "pass"
    target = ROOT / "docs" / "recibos" / "validacao-recuperacao.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "documents": len(selected),
                "queries": [
                    {
                        "query": q["name"],
                        "tribunal": q["args"]["tribunal"],
                        "count": q["answer"]["total_encontrado"],
                    }
                    for q in report["queries"]
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recuperacao real pelo protocolo MCP, somente leitura")
    parser.add_argument("--data-dir", required=True, type=Path, help="Pasta do acervo a consultar")
    asyncio.run(main(parser.parse_args().data_dir.resolve()))
