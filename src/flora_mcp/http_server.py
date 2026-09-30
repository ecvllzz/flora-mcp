"""Authenticated Streamable HTTP adapter. Run behind an HTTPS reverse proxy."""

import argparse
import hmac
import os

from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from .config import load_config
from .publication import MANIFEST
from .server import create_server
from .store import Store


def readable(store: Store) -> bool:
    """A work database, or only published generations: a reader copy has no collector."""
    return store.path.is_file() or (store.directory / MANIFEST).is_file()


class ApiKeyMiddleware:
    """Require the configured header on every HTTP request, before MCP dispatch."""

    def __init__(self, app, *, api_key: str):
        if len(api_key) < 32 or not api_key.isascii() or any(c.isspace() for c in api_key):
            raise ValueError("FLORA_MCP_API_KEY deve conter ao menos 32 caracteres ASCII sem espaços.")
        self.app = app
        self.api_key = api_key.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            values = [value for key, value in scope["headers"] if key.lower() == b"x-flora-api-key"]
            if len(values) != 1 or not hmac.compare_digest(values[0], self.api_key):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                response.headers["Cache-Control"] = "no-store"
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_http_app(store: Store, *, api_key: str, allowed_hosts: list[str]):
    """Reuse exactly the read-only MCP tools; no collector or filesystem routes."""
    if not allowed_hosts or any(not h or "*" in h or "/" in h for h in allowed_hosts):
        raise ValueError("Informe hosts explícitos, sem curingas nem esquema/caminho.")
    app = create_server(store).streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=64 * 1024,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=[],
        ),
    )
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)
    # Validate at construction, not only at the first request.
    ApiKeyMiddleware(app, api_key=api_key)
    return app


def main():
    parser = argparse.ArgumentParser(description="Flora-MCP HTTP autenticado, atrás de proxy HTTPS")
    parser.add_argument("--config")
    parser.add_argument("--data-dir")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allowed-host", action="append", required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config, args.data_dir)
        store = Store(config.data_dir, atrasos=config.atrasos)
        if not readable(store):
            raise ValueError("Acervo inexistente: sem banco de trabalho nem manifesto de publicações.")
        app = create_http_app(
            store,
            api_key=os.environ.get("FLORA_MCP_API_KEY", ""),
            allowed_hosts=args.allowed_host,
        )
    except ValueError as exc:
        parser.error(str(exc))
    import uvicorn

    # No URL/arguments are written to access logs. TLS and rate limiting belong to the proxy.
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
