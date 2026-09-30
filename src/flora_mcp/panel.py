"""Loopback-only human interface, using the same read-only queries as MCP."""

import argparse
import hashlib
import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from .config import load_config
from .model import FloraError
from .api import search
from .publication import Reader
from .precedents import available
from .store import Store

ASSETS = Path(__file__).with_name("panel_assets")
APP_ID = "flora-jurisprudencia"
PANEL_VERSION = "1"


class LocalOnly:
    def __init__(self, app, *, port):
        self.app = app
        self.host = f"127.0.0.1:{port}"
        self.origin = "http://" + self.host

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode("latin1")
        origin = headers.get(b"origin", b"").decode("latin1")
        if host != self.host or (origin and origin != self.origin):
            return await JSONResponse({"mensagem": "Origem não permitida."}, status_code=403)(
                scope, receive, send
            )
        if scope["path"].startswith("/api/") and headers.get(b"sec-fetch-site") == b"cross-site":
            return await JSONResponse({"mensagem": "Origem não permitida."}, status_code=403)(
                scope, receive, send
            )

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; "
                            b"connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                            b"frame-ancestors 'none'",
                        ),
                    ]
                )
            await send(message)

        await self.app(scope, receive, secure_send)


SEARCH_FIELDS = {
    "termos",
    "tribunal",
    "orgao",
    "classe",
    "processo",
    "relator",
    "data_inicio",
    "data_fim",
    "tipo_data",
    "ordenar",
    "cursor",
    "colecao",
    "campo",
    "especie",
    "numero",
}


def status_payload(reader: Reader, store: Store) -> dict:
    view = reader.resolve()
    with view.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        count = db.execute("SELECT count(*) FROM documents").fetchone()[0]
    return {
        "app": APP_ID,
        "version": PANEL_VERSION,
        "revisao": revision,
        "publicacao_id": view.publication,
        "documentos": count,
        "acervo_key": hashlib.sha256(str(store.path.resolve()).encode()).hexdigest(),
    }


def qualified_groups(db, view) -> list:
    if not available(db):
        return []
    return [
        dict(r)
        for r in db.execute(
            "SELECT tribunal,json_extract(body,'$.orgao') AS orgao,species AS especie,count(*) "
            "AS documentos FROM precedents WHERE admission='admitido' AND id NOT IN (SELECT "
            "value FROM json_each(?)) GROUP BY tribunal,organ,species ORDER BY tribunal,organ,"
            "species",
            (json.dumps(sorted(view.withdrawn)),),
        )
    ]


def catalog_payload(reader: Reader) -> dict:
    view = reader.resolve()
    with view.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        groups = [
            dict(r)
            for r in db.execute("""SELECT tribunal,json_extract(body,'$.orgao') AS orgao,
            count(*) AS documentos,max(publication) AS ultima_publicacao
            FROM documents GROUP BY tribunal,organ ORDER BY tribunal,organ""")
        ]
        classes = [
            dict(r)
            for r in db.execute("""SELECT tribunal,json_extract(body,'$.classe') AS classe
            FROM documents GROUP BY tribunal,class ORDER BY tribunal,class""")
        ]
        collected = db.execute("SELECT max(checked) FROM resources WHERE status='ok'").fetchone()[0]
        qualified = qualified_groups(db, view)
    return {
        "grupos": groups,
        "classes": classes,
        "revisao": revision,
        "precedentes": qualified,
        "publicacao_id": view.publication,
        "ultima_coleta": collected,
        "cobertura_integral": False,
    }


def check_query(values):
    if (
        not isinstance(values, dict)
        or set(values) - SEARCH_FIELDS
        or any(not isinstance(v, (str, type(None))) for v in values.values())
    ):
        raise ValueError("Parâmetros inválidos.")
    if any(len(v) > 2048 for v in values.values() if isinstance(v, str)):
        raise ValueError("Consulta muito longa.")


async def search_response(store: Store, request) -> JSONResponse:
    try:
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"mensagem": "Envie JSON."}, status_code=415)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 8192:
                return JSONResponse({"mensagem": "Consulta muito longa."}, status_code=413)
        values = json.loads(raw)
        check_query(values)
        # Blocking SQLite work belongs on Starlette's worker pool.
        from starlette.concurrency import run_in_threadpool

        result = await run_in_threadpool(search, store, **values, limite=5)
        return JSONResponse(result)
    except FloraError as exc:
        return JSONResponse({"codigo": exc.code, "mensagem": str(exc)}, status_code=400)
    except (ValueError, TypeError):
        return JSONResponse({"mensagem": "Consulta inválida. Confira os campos."}, status_code=400)


def create_panel_app(store: Store, *, port: int = 8766):
    reader = Reader(store)

    def status(request):
        return JSONResponse(status_payload(reader, store))

    def catalog(request):
        return JSONResponse(catalog_payload(reader))

    async def find(request):
        return await search_response(store, request)

    def asset(filename, media_type):
        def serve(request):
            return FileResponse(ASSETS / filename, media_type=media_type)

        return serve

    return Starlette(
        routes=[
            Route("/", asset("index.html", "text/html")),
            Route("/panel.css", asset("panel.css", "text/css")),
            Route("/panel.js", asset("panel.js", "text/javascript")),
            Route("/api/status", status),
            Route("/api/catalog", catalog),
            Route("/api/search", find, methods=["POST"]),
        ],
        middleware=[Middleware(LocalOnly, port=port)],
    )


def main():
    parser = argparse.ArgumentParser(description="Painel local de jurisprudência Flora")
    parser.add_argument("--data-dir")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Porta deve estar entre 1024 e 65535.")
    store = Store(load_config(data_dir=args.data_dir).data_dir)
    if not store.path.is_file():
        parser.error("Acervo inexistente. Confira o diretório configurado.")
    import uvicorn

    uvicorn.run(
        create_panel_app(store, port=args.port),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
