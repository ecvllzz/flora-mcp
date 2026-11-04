# Flora-MCP no Claude Desktop

O Claude Desktop inicia o servidor `stdio` pelo comando registrado em `mcpServers.flora-mcp` e encerra o processo ao sair. O arquivo de configuração é o que se abre por **Settings → Developer → Edit config** (`claude_desktop_config.json`).

## Entrada

```json
{
  "mcpServers": {
    "flora-mcp": {
      "command": "<pasta do projeto>\\.venv\\Scripts\\python.exe",
      "args": ["-m", "flora_mcp.cli", "--data-dir", "<pasta do acervo>", "serve"],
      "env": {"PYTHONUTF8": "1"}
    }
  }
}
```

- `<pasta do projeto>` é o clone onde `uv sync --frozen` criou o `.venv`; em Linux e macOS, o executável é `.venv/bin/python`. Trocar de branch nessa pasta muda o código de quem abrir sessão nova.
- `<pasta do acervo>` é a pasta com `acervo.sqlite` ou, numa instalação só de leitura montada a partir da Release (ver o README), a pasta com `publicacoes.json`. `--data-dir` vem antes de `serve`. Caminho absoluto dentro de AppData fica sujeito ao redirecionamento do aplicativo da Windows Store; por isso o acervo não mora lá.
- Acrescente só a entrada `flora-mcp` e preserve os demais campos do arquivo; guarde uma cópia do arquivo antes de editar.
- Nenhum arquivo do gabinete que mantém o projeto é necessário: o servidor lê só o acervo e, se houver, o `flora.local.toml` da pasta do projeto.

O Codex usa o mesmo comando em `~\.codex\config.toml` (`[mcp_servers.flora-mcp]`), com o acervo em `FLORA_MCP_DATA_DIR` em vez de `--data-dir`.

Nesta máquina, a instalação do Claude é a da Windows Store, o projeto roda do worktree principal (`Documents\Flora-MCP`, branch `main`) e o acervo é o de `AGENTS.md`.

## Carregar a mudança

Depois de alterar a configuração ou atualizar o código em `main`, encerre o Claude por **File → Exit** (ou **Quit/Sair**) e abra-o de novo. Em **Settings → Developer**, confira `flora-mcp` com estado **Running**. Use uma conversa nova: a conversa já aberta continua com as ferramentas que descobriu ao começar.

Para conferir, peça numa conversa nova `consultar_cobertura`, uma pesquisa curta em `pesquisar_jurisprudencia` e a leitura de um resultado com `obter_documento`, conferindo a referência e o relator.

Pedido de uso sugerido:

> Use o flora-mcp para pesquisar jurisprudência sobre [tema]. Apresente a ementa e a referência completa, com tribunal, classe, processo, relator, órgão julgador e datas. Informe eventuais dados ausentes, os limites da cobertura e o atraso da coleta.

## O que o cliente recebe

Cinco ferramentas de leitura: `pesquisar_jurisprudencia`, `pesquisar_precedentes`, `obter_documento`, `consultar_cobertura` e `conferir_referencias` (contrato em [CONTRATO.md](../CONTRATO.md)). A referência é montada pelo servidor a partir do espelho original preservado. O acervo é parcial e contém ementas e espelhos, sem inteiro teor dos votos. A descrição de cada ferramenta diz o que ela faz; o que a instalação quiser dizer a mais ao agente vai em `[flora.orientacoes]` de `flora.local.toml`.

A instalação e as verificações feitas quando o acervo mudou de pasta estão em [recibos/migracao-dados-20260929.md](recibos/migracao-dados-20260929.md).

Referência técnica: [configuração de um servidor local no Claude Desktop, documentação oficial do MCP Python SDK](https://py.sdk.modelcontextprotocol.io/get-started/real-host/#claude-desktop).
