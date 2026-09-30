import argparse
import json
import sys
from pathlib import Path

from filelock import FileLock, Timeout

from .config import load_config
from .model import FloraError
from .api import coverage, search, search_precedents
from .precedents import COMPONENTS, SPECIES
from .sources import client, probe_tjsc, sync_stj
from .store import Store


def add_page_options(parser):
    parser.add_argument("--ordenar", choices=["relevancia", "mais_recentes", "mais_antigos"])
    parser.add_argument("--detalhe", choices=["triagem", "completo"], default="triagem")
    parser.add_argument("--modo-busca", choices=["simples", "avancado"], default="simples")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--cursor")


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
    find = sub.add_parser("search", help="Pesquisa acórdãos, sem cliente MCP")
    find.add_argument("termos", nargs="?", default="")
    find.add_argument("--tribunal", choices=["STJ", "TJSC"])
    find.add_argument("--orgao")
    find.add_argument("--classe")
    find.add_argument("--relator")
    find.add_argument("--processo")
    find.add_argument("--data-inicio")
    find.add_argument("--data-fim")
    find.add_argument("--tipo-data", choices=["publicacao", "julgamento"], default="publicacao")
    add_page_options(find)
    qualified = sub.add_parser(
        "precedentes",
        help="Pesquisa temas e súmulas, sem cliente MCP; 'precedentes preparar' e 'precedentes amostra' "
        "montam pacotes (para pesquisar essas palavras, use 'precedentes -- preparar')",
    )
    qualified.add_argument("termos", nargs="?", default="")
    qualified.add_argument("--tribunal", choices=["STJ", "STF", "TJSC"])
    qualified.add_argument("--especie", choices=sorted(set.union(*SPECIES.values())))
    qualified.add_argument("--numero")
    qualified.add_argument("--orgao")
    qualified.add_argument("--campo", choices=[*COMPONENTS, "todos"], default="todos")
    qualified.add_argument("--data-inicio")
    qualified.add_argument("--data-fim")
    add_page_options(qualified)
    sub.add_parser("serve", help="Servidor MCP stdio, exclusivamente de leitura")
    backup = sub.add_parser("backup", help="Cópia integral de banco e originais (formato antigo)")
    backup.add_argument("destino", type=Path)
    update = sub.add_parser("atualizar", help="Backup, coleta STJ e TJSC, publicação e log, sob a trava")
    update.add_argument("--stj-lotes", type=int, default=2, help="Lotes por dataset do STJ; padrão 2")
    update.add_argument("--tjsc-dias", type=int, default=7, help="Janela até hoje, de 1 a 31 dias; padrão 7")
    only = update.add_mutually_exclusive_group()
    only.add_argument("--so-stj", action="store_true", help="Coleta apenas o STJ")
    only.add_argument("--so-tjsc", action="store_true", help="Coleta apenas o TJSC")
    kept = sub.add_parser("backups", help="Backups com depósito de originais compartilhado")
    action = kept.add_subparsers(dest="acao", required=True)
    create = action.add_parser("criar", help="Novo backup de banco e manifesto; copia só originais novos")
    create.add_argument("--rotulo")
    create.add_argument("--raiz", type=Path, help="Raiz dos backups; padrão <acervo>-backups")
    prune = action.add_parser("podar", help="Mantém os N mais recentes e o último de cada mês")
    prune.add_argument("--manter", type=int, default=5)
    prune.add_argument("--raiz", type=Path)
    prune.add_argument("--aplicar", action="store_true", help="Apaga; sem esta opção mostra só o plano")
    restore = action.add_parser("restaurar", help="Monta acervo utilizável num diretório novo")
    restore.add_argument("nome")
    restore.add_argument("destino", type=Path)
    restore.add_argument("--raiz", type=Path)
    return parser


# Package actions of "flora-mcp precedentes": files only, no collection, no lock, no network.
PACKAGE_ACTIONS = {"preparar", "amostra"}


def build_package_parser() -> argparse.ArgumentParser:
    from .precedent_sources import ADAPTERS

    parser = argparse.ArgumentParser(
        prog="flora-mcp precedentes", description="Pacotes flora-precedentes-1 de fontes estruturadas"
    )
    action = parser.add_subparsers(dest="acao", required=True)
    build = action.add_parser("preparar", help="Gera o pacote a partir de originais já coletados, sem rede")
    build.add_argument("--fonte", choices=ADAPTERS, required=True)
    build.add_argument("--originais", type=Path, required=True, help="Pasta com originais e recibos")
    build.add_argument("--saida", type=Path, required=True, help="Arquivo do pacote; originais ao lado")
    sample = action.add_parser("amostra", help="Sorteia a amostra e grava o esqueleto da conferência")
    sample.add_argument("pacote", type=Path)
    sample.add_argument("--semente", type=int, required=True)
    return parser


def package_action(argv: list[str]) -> list[str] | None:
    """Arguments of a package action, when the command line is 'precedentes preparar|amostra'."""
    index = 0
    while index < len(argv) and argv[index] in {"--config", "--data-dir"}:
        index += 2
    rest = argv[index:]
    if len(rest) > 1 and rest[0] == "precedentes" and rest[1] in PACKAGE_ACTIONS:
        return rest[1:]
    return None


def run_package_action(argv: list[str]) -> dict:
    from .precedent_sources.pacote import prepare_package, sample_skeleton

    args = build_package_parser().parse_args(argv)
    if args.acao == "preparar":
        return prepare_package(args.fonte, args.originais.resolve(), args.saida.resolve())
    return sample_skeleton(args.pacote.resolve(), args.semente)


def run_coverage(args, store):
    return coverage(store)


def run_search(args, store):
    return search(
        store,
        args.termos,
        processo=args.processo,
        tribunal=args.tribunal,
        orgao=args.orgao,
        classe=args.classe,
        relator=args.relator,
        data_inicio=args.data_inicio,
        data_fim=args.data_fim,
        tipo_data=args.tipo_data,
        ordenar=args.ordenar,
        detalhe=args.detalhe,
        modo_busca=args.modo_busca,
        limite=args.limite,
        cursor=args.cursor,
    )


def run_precedents(args, store):
    return search_precedents(
        store,
        args.termos,
        tribunal=args.tribunal,
        especie=args.especie,
        numero=args.numero,
        orgao=args.orgao,
        campo=args.campo,
        data_inicio=args.data_inicio,
        data_fim=args.data_fim,
        ordenar=args.ordenar,
        detalhe=args.detalhe,
        modo_busca=args.modo_busca,
        limite=args.limite,
        cursor=args.cursor,
    )


def backup_before(config, store, label: str) -> dict:
    """Backup in the shared-depot format, before an administrative write; caller holds the lock."""
    from . import backups

    return backups.create(store, backups.default_root(config.data_dir), label)


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


def run_update(args, config, store):
    from .atualizacao import update

    return update(
        config,
        store,
        stj_lotes=args.stj_lotes,
        tjsc_dias=args.tjsc_dias,
        stj=not args.so_tjsc,
        tjsc=not args.so_stj,
    )


def run_backups(args, config, store):
    from . import backups

    root = (args.raiz or backups.default_root(config.data_dir)).resolve()
    if args.acao == "podar":
        return backups.prune(root, args.manter, apply=args.aplicar)
    if args.acao == "restaurar":
        return backups.restore(root, args.nome, args.destino)
    if not config.db_path.is_file():
        raise FloraError("base_nao_inicializada", "Banco não encontrado na pasta configurada.")
    with FileLock(str(config.data_dir / "collector.lock"), timeout=0):
        return backups.create(store, root, args.rotulo)


READERS = {"coverage": run_coverage, "search": run_search, "precedentes": run_precedents}
# Commands that take the locks they need themselves.
SELF_LOCKED = {"atualizar": run_update, "backups": run_backups}
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


def main(argv: list[str] | None = None):
    argv = sys.argv[1:] if argv is None else argv
    action = package_action(argv)
    args = None if action is not None else build_parser().parse_args(argv)
    try:
        if action is not None:
            print(json.dumps(run_package_action(action), ensure_ascii=True, indent=2))
            return
        config = load_config(args.config, args.data_dir)
        store = Store(config.data_dir, atrasos=config.atrasos)
        if args.command == "serve":
            from .server import create_server

            create_server(store).run(transport="stdio")
            return
        if args.command in READERS:
            result = READERS[args.command](args, store)
        elif args.command in SELF_LOCKED:
            result = SELF_LOCKED[args.command](args, config, store)
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
