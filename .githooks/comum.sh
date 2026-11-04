# Incluído pelos hooks. Com core.hooksPath absoluto, todo worktree roda os hooks e a conferência do
# worktree principal, inclusive o de branch antigo, que não tem nenhum dos dois.
RAIZ_HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$RAIZ_HOOKS/.venv/Scripts/python.exe" ]; then PY_HOOKS="$RAIZ_HOOKS/.venv/Scripts/python.exe"
elif [ -x "$RAIZ_HOOKS/.venv/bin/python" ]; then PY_HOOKS="$RAIZ_HOOKS/.venv/bin/python"
else PY_HOOKS=python3; fi
CONFERENCIA="$RAIZ_HOOKS/scripts/conferir_traco_caso.py"
