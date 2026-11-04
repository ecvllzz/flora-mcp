"""Monta uma pasta de leitura a partir de um arquivo de publicação (o publicacao.sqlite.gz de uma Release).

Uso: python scripts/instalar_publicacao.py --arquivo publicacao.sqlite.gz --destino <pasta> [--sha256 HEX]

A pasta ganha publicacoes/<id>.sqlite e publicacoes.json; depois, `flora-mcp --data-dir <pasta> serve`
atende as cinco ferramentas sem banco de trabalho, sem originais e sem coletor. `--sha256` é o hash
do arquivo descomprimido (o do manifesto de origem, quando se tem); sem ele, o hash calculado entra
no manifesto e fica no recibo impresso.
"""

import argparse
import json
import sys
from pathlib import Path

from flora_mcp.leitor import instalar
from flora_mcp.model import FloraError


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arquivo", required=True, help="publicacao.sqlite.gz ou .sqlite")
    parser.add_argument("--destino", required=True, help="pasta de leitura, nova ou já instalada")
    parser.add_argument("--sha256", help="SHA-256 esperado do arquivo .sqlite descomprimido")
    args = parser.parse_args()
    try:
        recibo = instalar(Path(args.arquivo), Path(args.destino).resolve(), sha256=args.sha256)
    except (FloraError, OSError, ValueError) as exc:
        print(json.dumps({"status": "erro", "mensagem": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(recibo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
