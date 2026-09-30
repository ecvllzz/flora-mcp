# Aponta os hooks do git deste clone para .githooks (pre-commit roda scripts/check.sh).
Set-Location (Join-Path $PSScriptRoot "..")
git config core.hooksPath .githooks
Write-Output "core.hooksPath = $(git config core.hooksPath)"
