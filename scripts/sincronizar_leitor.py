"""Copia a publicação corrente e o manifesto para uma cópia de leitura (sem banco de trabalho nem coletor).

Uso: python scripts/sincronizar_leitor.py --origem <acervo> --destino <pasta do leitor> [--manter 2]

A origem é a pasta do acervo onde a coleta roda; o destino é a pasta que o adaptador HTTP do leitor
usa como --data-dir. O destino não pode ser pasta sincronizada (OneDrive, SharePoint).
"""

import argparse
import json
import sys
from pathlib import Path

from flora_mcp.leitor import sincronizar


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--manter", type=int, default=2)
    args = parser.parse_args()
    origem, destino = Path(args.origem).resolve(), Path(args.destino).resolve()
    if origem == destino or destino.is_relative_to(origem):
        parser.error("O destino precisa ficar fora da pasta do acervo.")
    print(json.dumps(sincronizar(origem, destino, args.manter), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
