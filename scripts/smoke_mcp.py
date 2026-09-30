"""Real subprocess MCP test against the local corpus. Produces a reproducible receipt and full examples."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from flora_mcp.config import load_config
from flora_mcp.model import digest, now


async def main():
    config = load_config()
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "flora_mcp.cli", "--data-dir", str(config.data_dir), "serve"],
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    report = {
        "verificado_em": now(),
        "transporte": "stdio",
        "cliente": "SDK Python MCP 2.2.0",
        "resultados": [],
    }
    lines = [
        "# Flora-MCP: exemplo executado",
        "",
        "Pesquisa real pelo protocolo MCP, em base local parcial.",
        "As ementas abaixo estão completas como armazenadas; não são inteiros teores.",
        "",
    ]
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            report["ferramentas"] = [t.name for t in (await session.list_tools()).tools]
            coverage = (await session.call_tool("consultar_cobertura", {})).structured_content
            report["grupos"] = coverage["grupos"]
            for tribunal, organ, terms in [
                ("STJ", "TERCEIRA TURMA", "alimentos"),
                ("TJSC", "9ª Câmara de Direito Civil", "agravo"),
                ("TJSC", "10ª Câmara de Direito Civil", "alimentos"),
            ]:
                results = (
                    await session.call_tool(
                        "pesquisar_jurisprudencia",
                        {"termos": terms, "tribunal": tribunal, "orgao": organ, "limite": 1},
                    )
                ).structured_content
                if not results.get("resultados"):
                    raise RuntimeError(f"Sem resultado de demonstração em {tribunal} / {organ}")
                row = results["resultados"][0]
                parts, cursor = [], None
                while True:
                    block = (
                        await session.call_tool(
                            "obter_documento", {"id": row["id"], "tamanho_bloco": 700, "cursor": cursor}
                        )
                    ).structured_content
                    parts.append(block["texto"])
                    cursor = block["proximo_cursor"]
                    if not cursor:
                        break
                complete = "".join(parts)
                assert complete == row["ementa"]
                assert digest(complete.encode()) == block["sha256_texto_completo"]
                report["resultados"].append(
                    {
                        "tribunal": tribunal,
                        "termos": terms,
                        "orgao": organ,
                        "id": row["id"],
                        "processo": row["processo"],
                        "caracteres": len(complete),
                        "blocos": len(parts),
                        "sha256_ementa": digest(complete.encode()),
                        "reconstrucao_integral": True,
                    }
                )
                lines += [
                    f"## {tribunal} — {organ}",
                    "",
                    f"Termo pesquisado na ementa: **{terms}**.",
                    "",
                    f"Processo: **{row['processo']}**.",
                    "",
                    f"Julgamento: {row['data_julgamento']}. Publicação: {row['data_publicacao']}.",
                    "",
                    "```text",
                    complete,
                    "```",
                    "",
                    f"[Fonte oficial do lote/consulta]({row['url_lote']})",
                    "",
                ]
                if row["url_documento"]:
                    lines += [
                        f"[Link do documento fornecido pelo portal]({row['url_documento']}) "
                        "(disponibilidade do inteiro teor não verificada nesta execução).",
                        "",
                    ]
    target = Path(__file__).resolve().parents[1] / "docs"
    target.mkdir(exist_ok=True)
    (target / "verificacao-mcp.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / "exemplo-real.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
