# Aponta os hooks de todos os worktrees deste clone para .githooks do worktree principal.
# O caminho é absoluto e fica no .git comum: com caminho relativo, cada worktree rodaria a cópia do
# próprio branch, e um branch antigo enviaria commits sem a conferência de traço de caso.
Set-Location (Join-Path $PSScriptRoot "..")
$comum = git rev-parse --path-format=absolute --git-common-dir
$hooks = (Join-Path (Split-Path $comum -Parent) ".githooks").Replace("\", "/")
if (-not (Test-Path (Join-Path $hooks "pre-push"))) {
    Write-Error "$hooks ainda não tem o pre-push: traga o main do worktree principal antes de instalar."
    exit 1
}
git config core.hooksPath $hooks
Write-Output "core.hooksPath = $(git config core.hooksPath)"
