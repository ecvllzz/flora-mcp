"""Read-only acceptance check through a fresh MCP process and the configured archive."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from flora_mcp.api import coverage
from flora_mcp.config import load_config
from flora_mcp.model import canonical
from flora_mcp.store import Store


async def main():
    store = Store(load_config().data_dir)
    complete = coverage(store, "completo")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "flora_mcp.cli", "--data-dir", str(store.directory), "serve"],
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool = next(t for t in (await session.list_tools()).tools if t.name == "consultar_cobertura")
            assert tool.input_schema["properties"]["detalhe"]["default"] == "resumo"
            response = await session.call_tool("consultar_cobertura", {})
            assert not response.is_error
            text = "".join(c.text for c in response.content if c.type == "text")
            result = response.structured_content
            assert len(text) < 10000, len(text)
            for key in ("grupos", "catalogos", "limites", "tjsc", "inteiros_teores", "cobertura_integral"):
                assert result[key] == complete[key]
            assert sum(g["total"] for g in result["recursos"]) == len(complete["recursos"])
            for before, after in zip(complete["execucoes_recentes"], result["execucoes_recentes"], strict=True):
                assert before["id"] == after["id"] and before["status"] == after["status"]
                for key in ("motivo", "falhas", "antes", "depois", "erro", "error"):
                    if before["detail"].get(key):
                        assert before["detail"][key] == after["detail"][key]
            page = await session.call_tool("consultar_cobertura", {"detalhe": "recursos", "tribunal": "TJSC", "limite": 2})
            assert page.structured_content["total"] == sum(r["dataset"].startswith("tjsc-") for r in complete["recursos"])
            receipt = {
                "status": "ok", "banco_ativo": str(store.path),
                "publicacao_id": result.get("publicacao_id"),
                "resumo_mcp_caracteres": len(text),
                "completo_json_compacto_caracteres": len(canonical(complete)),
                "recursos": len(complete["recursos"]),
                "pendentes": sum(g["pendentes"] for g in result["recursos"]),
                "grupos": len(result["grupos"]), "execucoes": len(result["execucoes_recentes"]),
                "diagnosticos_preservados": True,
            }
    output = json.dumps(receipt, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
