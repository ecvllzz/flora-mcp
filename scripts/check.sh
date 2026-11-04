#!/bin/sh
# Portão de qualidade: traço de caso, testes, lint e formatação. Falha se qualquer etapa falhar.
set -e
cd "$(dirname "$0")/.."
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python
else PY=python3; fi
"$PY" scripts/conferir_traco_caso.py
"$PY" -m ruff format --check src tests scripts
"$PY" -m ruff check src tests scripts
"$PY" -m pytest -q -p no:cacheprovider
