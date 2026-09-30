"""Read-only connection check using the installed Codex app-server (no model turn)."""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path


async def main():
    process = await asyncio.create_subprocess_exec(
        shutil.which("codex"),
        "app-server",
        "--stdio",
        "-c",
        "features.plugins=false",
        "-c",
        "mcp_servers.node_repl.enabled=false",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=16 * 1024 * 1024,
    )

    async def call(identifier, method, params):
        print("Request:", method, flush=True)
        process.stdin.write(
            (json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode()
        )
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), 55)
            if not line:
                raise RuntimeError("Codex exited before response")
            result = json.loads(line)
            if result.get("id") == identifier:
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return result["result"]

    try:
        init = await call(1, "initialize", {"clientInfo": {"name": "flora_mcp_check", "version": "0.1"}})
        process.stdin.write(b'{"method":"initialized"}\n')
        await process.stdin.drain()
        status = await call(2, "mcpServerStatus/list", {"limit": 100, "detail": "toolsAndAuthOnly"})
        flora = [s for s in status.get("data", []) if s.get("name") == "flora-mcp"]
        report = {
            "checked_at": datetime.now().astimezone().isoformat(),
            "client": init,
            "flora": flora,
            "next_cursor": status.get("nextCursor"),
            "scope": (
                "Separate installed Codex app-server process; no model turn and no desktop conversation "
                "reload"
            ),
        }
        target = Path(__file__).resolve().parents[1] / "docs" / "conexao-codex.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"flora": flora, "receipt": str(target)}, ensure_ascii=False))
        assert flora and flora[0].get("tools"), "Tools not discovered by Codex"
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                pass


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), 90))
