# Portão de qualidade: traço de caso, testes, lint e formatação. Falha se qualquer etapa falhar.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"
& $py scripts\conferir_traco_caso.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m ruff format --check src tests scripts; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m ruff check src tests scripts; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m pytest -q -p no:cacheprovider; if ($LASTEXITCODE) { exit $LASTEXITCODE }
