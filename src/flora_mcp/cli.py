import argparse
import json
import sys
from pathlib import Path

from filelock import FileLock, Timeout

from .config import load_config
from .model import FloraError
from .api import coverage, search
from .sources import client, probe_tjsc, sync_stj
from .store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Flora-MCP: acervo oficial local e MCP de leitura")
    parser.add_argument("--config", help="Arquivo TOML de configuração")
    parser.add_argument("--data-dir", help="Diretório do acervo (fora do código e de pastas sincronizadas)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Inicializa banco vazio")
    sync = sub.add_parser("sync-stj", help="Descobre e incorpora recursos oficiais; não exige LLM")
    sync.add_argument("--max-resources", type=int, help="Máximo por dataset nesta execução")
    sync.add_argument("--recheck", action="store_true", help="Rever bytes já importados, respeitando limite")
    sub.add_parser("probe-tjsc", help="Diagnostica acesso público; não ingere documentos")
    tjsc = sub.add_parser("sync-tjsc", help="Coleta experimental de janelas completas por publicação")
    tjsc.add_argument("--inicio", required=True, help="AAAA-MM-DD")
    tjsc.add_argument("--fim", required=True, help="AAAA-MM-DD; até 31 dias por execução")
    sub.add_parser("coverage", help="Cobertura e histórico de operação")
    sub.add_parser("migrate", help="Backup consistente e migração explícita do modelo")
    sub.add_parser("publish", help="Publica snapshot validado para todos os leitores")
    package = sub.add_parser("import-precedents", help="Valida pacote oficial revisado; simulação por padrão")
    package.add_argument("pacote", type=Path)
    package.add_argument("--apply", action="store_true", help="Importa após backup consistente")
    export = sub.add_parser("export", help="Exporta documentos e catálogo de leitura")
    export.add_argument("destino", type=Path)
    export.add_argument("--include-judgments", action="store_true", help="Inclui acórdãos ordinários")
    find = sub.add_parser("search", help="Pesquisa local, sem cliente MCP")
    find.add_argument("termos", nargs="?", default="")
    find.add_argument("--tribunal")
    find.add_argument("--orgao")
    find.add_argument("--processo")
    find.add_argument("--colecao", choices=["acordaos", "precedentes"], default="acordaos")
    find.add_argument("--campo", default="ementa")
    find.add_argument("--especie")
    find.add_argument("--numero")
    find.add_argument("--detalhe", choices=["completo", "triagem"], default="completo")
    find.add_argument(
        "--ordenar", choices=["mais_recentes", "mais_antigos", "relevancia"], default="mais_recentes"
    )
    sub.add_parser("serve", help="Servidor MCP stdio, exclusivamente de leitura")
    backup = sub.add_parser("backup", help="Backup consistente de banco e originais")
    backup.add_argument("destino", type=Path)
    return parser


def run_coverage(args, store):
    return coverage(store)


def run_search(args, store):
    return search(
        store,
        args.termos,
        processo=args.processo,
        tribunal=args.tribunal,
        orgao=args.orgao,
        ordenar=args.ordenar,
        colecao=args.colecao,
        campo=args.campo,
        especie=args.especie,
        numero=args.numero,
        detalhe=args.detalhe,
    )


def backup_before(config, store, label: str) -> dict:
    """Consistent backup beside the data directory, before an administrative write."""
    from datetime import datetime

    destination = (
        config.data_dir.parent
        / (config.data_dir.name + "-backups")
        / datetime.now().strftime(label + "-%Y%m%d-%H%M%S-%f")
    )
    return store.backup(destination)


def run_migrate(args, config, store):
    from .precedents import migrate

    saved = backup_before(config, store, "antes-migracao")
    return {**migrate(store), "backup": saved}


def run_import(args, config, store):
    from .precedents import import_package

    result = import_package(store, args.pacote.resolve())
    if args.apply:
        saved = backup_before(config, store, "antes-precedentes")
        result = {**import_package(store, args.pacote.resolve(), apply=True), "backup": saved}
    return result


def run_publish(args, config, store):
    from .publication import publish

    return publish(store)


def run_export(args, config, store):
    from .export import export_documents

    return export_documents(store, args.destino, include_judgments=args.include_judgments)


def run_init(args, config, store):
    return {"status": "ok", "banco": str(store.path)}


def run_backup(args, config, store):
    destination = args.destino.resolve()
    if destination == config.data_dir or config.data_dir in destination.parents:
        raise FloraError("destino_invalido", "Backup deve ficar fora do diretório do acervo.")
    return store.backup(destination)


def run_collection(args, config, store):
    if args.command == "sync-stj" and args.max_resources is not None:
        if args.max_resources < 1:
            raise FloraError("limite_invalido", "Máximo de recursos deve ser positivo.")
        config.max_resources = args.max_resources
    with client() as http:
        if args.command == "sync-stj":
            return sync_stj(config, store, http, force=args.recheck)
        if args.command == "sync-tjsc":
            from datetime import date
            from .tjsc import sync_tjsc

            return sync_tjsc(
                config, store, http, date.fromisoformat(args.inicio), date.fromisoformat(args.fim)
            )
        return probe_tjsc(config, store, http)


READERS = {"coverage": run_coverage, "search": run_search}
WRITERS = {
    "migrate": run_migrate,
    "import-precedents": run_import,
    "publish": run_publish,
    "export": run_export,
    "init": run_init,
    "backup": run_backup,
    "sync-stj": run_collection,
    "sync-tjsc": run_collection,
    "probe-tjsc": run_collection,
}


def run_locked(args, config, store):
    """Administrative commands run under the collector lock, on an existing database."""
    if args.command != "init" and not config.db_path.is_file():
        raise FloraError(
            "base_nao_inicializada",
            "Banco não encontrado na pasta configurada. "
            "Confira o caminho; a coleta não cria outro acervo automaticamente.",
        )
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(config.data_dir / "collector.lock"), timeout=0):
        store.initialize()
        result = WRITERS[args.command](args, config, store)
        if args.command in {"sync-stj", "sync-tjsc"} or (args.command == "import-precedents" and args.apply):
            from .publication import MANIFEST, publish

            if (store.directory / MANIFEST).exists():
                result["publicacao"] = publish(store)
    return result


def main():
    args = build_parser().parse_args()
    try:
        config = load_config(args.config, args.data_dir)
        store = Store(config.data_dir)
        if args.command == "serve":
            from .server import create_server

            create_server(store).run(transport="stdio")
            return
        if args.command in READERS:
            result = READERS[args.command](args, store)
        else:
            result = run_locked(args, config, store)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if result.get("status") == "error":
            raise SystemExit(2)
    except (FloraError, Timeout, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "erro",
                    "codigo": getattr(exc, "code", "configuracao_ou_lock"),
                    "mensagem": str(exc),
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
