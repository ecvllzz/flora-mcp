"""One bounded administrative update; suitable for an OS scheduler, with no LLM."""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from filelock import FileLock

from flora_mcp.config import load_config
from flora_mcp.model import now
from flora_mcp.sources import client, sync_stj
from flora_mcp.store import Store
from flora_mcp.tjsc import sync_tjsc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--data-dir")
    parser.add_argument("--precedents-package", type=Path,
                        help="Pacote oficial revisado de precedentes, após coleta e conferência")
    parser.add_argument("--tjsc-days", type=int, default=7, help="Janela móvel de 1 a 31 dias; padrão 7")
    args = parser.parse_args()
    if not 1 <= args.tjsc_days <= 31:
        parser.error("--tjsc-days deve ficar entre 1 e 31")
    config = load_config(args.config, args.data_dir)
    if not config.db_path.is_file():
        parser.error("Banco não encontrado na pasta configurada. Confira o caminho; "
                     "nenhum acervo será criado automaticamente.")
    report = {"inicio": now(), "rotina": "update_once", "execucoes": []}
    with FileLock(str(config.data_dir / "collector.lock"), timeout=0):
        store = Store(config.data_dir)
        store.initialize()
        if args.precedents_package:
            from flora_mcp.precedents import import_package

            import_package(store, args.precedents_package.resolve())
            backup_path = config.data_dir.parent / (config.data_dir.name + "-backups") / datetime.now().strftime("antes-atualizacao-%Y%m%d-%H%M%S-%f")
            report["backup"] = store.backup(backup_path)
            report["execucoes"].append(import_package(store, args.precedents_package.resolve(), apply=True))
        with client() as http:
            report["execucoes"].append(sync_stj(config, store, http))
            # This computer's local date; production must use a host in America/Sao_Paulo.
            end = datetime.now().astimezone().date()
            report["execucoes"].append(
                sync_tjsc(config, store, http, end - timedelta(days=args.tjsc_days - 1), end)
            )
        from flora_mcp.publication import MANIFEST, publish
        if (config.data_dir / MANIFEST).exists():
            report["publicacao"] = publish(store)
    report["fim"] = now()
    statuses = {r["status"] for r in report["execucoes"]}
    report["status"] = "error" if "error" in statuses else "partial" if "partial" in statuses else "ok"
    logs = config.data_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if report["status"] == "error":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
