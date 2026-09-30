# Flora-MCP: instruções para agentes

Servidor MCP de jurisprudência (STJ e TJSC, temas e súmulas) sobre um acervo SQLite local, coletado de fontes oficiais sem LLM. Pacote `flora_mcp` em `src/`, testes em `tests/`, scripts administrativos em `scripts/`.

## Acervo real

O acervo em uso fica em `C:\Users\Home\Documents\Flora\Dados\Flora-MCP` (configurado em `flora.local.toml`, que não é versionado). Ele é lido por Claude, Codex, painel e Copilot.

- Nunca escreva nele sem `collector.lock` (os comandos do CLI já o adquirem), backup consistente antes (`flora-mcp backup` ou o backup embutido do comando) e recibo depois.
- Toda operação nova sobre o acervo é ensaiada antes numa cópia. Para trabalhar sem risco, defina `FLORA_MCP_DATA_DIR` para uma cópia (por exemplo `C:\Users\Home\Documents\Flora\Dados\Flora-MCP-sandbox`); a variável tem precedência sobre o TOML.
- Coleta (`sync-stj`, `sync-tjsc`, `scripts/update_once.py`, `scripts/resume_tjsc.py`), `migrate`, `import-precedents --apply`, `publish` e `export` só rodam quando a tarefa pede expressamente.

## Portão de qualidade

`scripts/check.ps1` (Windows) ou `scripts/check.sh`: `ruff format --check`, `ruff check` (inclui linha de 110 e complexidade 12) e `pytest`. O hook `pre-commit` roda o mesmo portão; instale com `scripts/install-hooks.ps1`. Funções marcadas com `# noqa: C901` são dívida registrada; não acrescente novas sem justificar no commit.

## Regras

- Recibos em `docs/recibos/` são evidência e não se reescrevem; o `.gitattributes` os guarda byte a byte. Execução nova sobre o acervo grava recibo novo ali, com data no nome. Em `docs/` ficam só os guias vigentes.
- O contrato das ferramentas MCP está em `CONTRATO.md`. Mudança de contrato só em fase que a declare.
- Decisão que muda o que o Flora-MCP é ou como se opera entra no fim do `DECISOES.md`, com data e uma linha de razão.
- Trabalho de reforma em branch `reforma/fN-descricao`, commits pequenos, mensagens em português.
- Sem travessões (caractere U+2014) em textos, mensagens de commit e documentos.
- Plano da reforma em curso: `C:\Users\Home\Documents\Flora\Flora\_meta\engenharia\Reformas\reforma-flora-mcp-2026-10\plano.md`.
