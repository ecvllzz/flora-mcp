"""Render entrypoint for the existing authenticated read-only adapter."""

import os
from pathlib import Path

import uvicorn
from starlette.responses import JSONResponse

from flora_mcp.http_server import create_http_app, readable
from flora_mcp.store import Store


class Health:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/healthz":
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return
        await self.app(scope, receive, send)


def build_app():
    hostname = os.environ["RENDER_EXTERNAL_HOSTNAME"]
    port = int(os.environ.get("PORT", "10000"))
    store = Store(Path(os.environ.get("FLORA_MCP_DATA_DIR", "/app/acervo")))
    if not readable(store):
        raise ValueError("Publicacao de leitura ausente")
    app = create_http_app(
        store,
        api_key=os.environ["FLORA_MCP_API_KEY"],
        allowed_hosts=[hostname, f"127.0.0.1:{port}", f"localhost:{port}"],
    )
    return Health(app)


if __name__ == "__main__":
    uvicorn.run(
        build_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        access_log=False,
        log_level="warning",
    )
