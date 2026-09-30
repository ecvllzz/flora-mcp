"""Backup verificado do acervo e evidências, fora do diretório ativo."""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from flora_mcp.config import load_config
from flora_mcp.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--destino", type=Path)
    args = parser.parse_args()
    config = load_config(data_dir=args.data_dir)
    if not config.db_path.is_file():
        parser.error("Banco não encontrado; confira a pasta configurada.")
    target = (
        args.destino
        or config.data_dir.parent
        / (config.data_dir.name + "-backups")
        / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    ).resolve()
    if target == config.data_dir or config.data_dir in target.parents:
        parser.error("O destino deve ficar fora do acervo ativo.")
    with FileLock(str(config.data_dir / "collector.lock"), timeout=0):
        result = Store(config.data_dir).backup(target)
        for name in ("probes", "logs", "panel-logs"):
            if (config.data_dir / name).is_dir():
                shutil.copytree(config.data_dir / name, target / name)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
