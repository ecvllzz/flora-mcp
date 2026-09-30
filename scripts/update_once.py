"""One bounded administrative update; suitable for an OS scheduler, with no LLM.

Thin wrapper around `flora-mcp atualizar`, kept for the scheduled task already registered.
"""

import argparse
import json
from pathlib import Path

from flora_mcp.atualizacao import update
from flora_mcp.config import load_config
from flora_mcp.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--data-dir")
    parser.add_argument(
        "--precedents-package",
        type=Path,
        help="Pacote oficial revisado de precedentes, após coleta e conferência",
    )
    parser.add_argument("--tjsc-days", type=int, default=7, help="Janela móvel de 1 a 31 dias; padrão 7")
    args = parser.parse_args()
    if not 1 <= args.tjsc_days <= 31:
        parser.error("--tjsc-days deve ficar entre 1 e 31")
    config = load_config(args.config, args.data_dir)
    if not config.db_path.is_file():
        parser.error(
            "Banco não encontrado na pasta configurada. Confira o caminho; "
            "nenhum acervo será criado automaticamente."
        )
    report = update(
        config,
        Store(config.data_dir, atrasos=config.atrasos),
        stj_lotes=config.max_resources,
        tjsc_dias=args.tjsc_days,
        precedents_package=args.precedents_package,
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if report["status"] == "error":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
