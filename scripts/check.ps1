# Portão de qualidade: testes, lint e formatação. Falha se qualquer etapa falhar.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"
& $py -m ruff format --check src tests scripts; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m ruff check src tests scripts; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m pytest -q -p no:cacheprovider; if ($LASTEXITCODE) { exit $LASTEXITCODE }
