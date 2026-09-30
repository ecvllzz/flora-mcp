# Flora-MCP no Claude Desktop

O Claude Desktop inicia o servidor `stdio` pelo comando registrado em `mcpServers.flora-mcp` e encerra o processo ao sair. Nesta máquina, a instalação é a da Windows Store, e o arquivo efetivo é o que se abre por **Settings → Developer → Edit config**: `C:\Users\Home\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`.

## Entrada

```json
{
  "mcpServers": {
    "flora-mcp": {
      "command": "C:\\Users\\Home\\Documents\\Flora-MCP\\.venv\\Scripts\\python.exe",
      "args": ["-m", "flora_mcp.cli", "--data-dir", "C:\\Users\\Home\\Documents\\Flora\\Dados\\Flora-MCP", "serve"],
      "env": {"PYTHONUTF8": "1"}
    }
  }
}
```

- O executável é o do ambiente Python do worktree principal (`Documents\Flora-MCP`), que roda o `main`. Trocar de branch ali muda o código de quem abrir sessão nova.
- `--data-dir` vem antes de `serve` e aponta para o acervo compartilhado, fora do cofre Obsidian e dos diretórios privados do pacote MSIX. Caminho absoluto dentro de AppData fica sujeito ao redirecionamento do aplicativo; por isso o acervo não mora lá.
- Acrescente só a entrada `flora-mcp` e preserve os demais campos do arquivo; guarde uma cópia do arquivo antes de editar.

O Codex usa o mesmo comando em `~\.codex\config.toml` (`[mcp_servers.flora-mcp]`), com o acervo em `FLORA_MCP_DATA_DIR` em vez de `--data-dir`.

## Carregar a mudança

Depois de alterar a configuração ou atualizar o código em `main`, encerre o Claude por **File → Exit** (ou **Quit/Sair**) e abra-o de novo. Em **Settings → Developer**, confira `flora-mcp` com estado **Running**. Use uma conversa nova: a conversa já aberta continua com as ferramentas que descobriu ao começar.

Para conferir, peça numa conversa nova `consultar_cobertura`, uma pesquisa curta em `pesquisar_jurisprudencia` e a leitura de um resultado com `obter_documento`, conferindo a referência e o relator.

Pedido de uso sugerido:

> Use o flora-mcp para pesquisar jurisprudência sobre [tema]. Apresente a ementa e a referência completa, com tribunal, classe, processo, relator, órgão julgador e datas. Informe eventuais dados ausentes, os limites da cobertura e o atraso da coleta.

## O que o cliente recebe

Quatro ferramentas de leitura: `pesquisar_jurisprudencia`, `pesquisar_precedentes`, `obter_documento` e `consultar_cobertura` (contrato em [CONTRATO.md](../CONTRATO.md)). A referência é montada pelo servidor a partir do espelho original preservado. O acervo é parcial e contém ementas e espelhos, sem inteiro teor dos votos.

A instalação e as verificações feitas quando o acervo mudou de pasta estão em [recibos/migracao-dados-20260929.md](recibos/migracao-dados-20260929.md).

Referência técnica: [configuração de um servidor local no Claude Desktop, documentação oficial do MCP Python SDK](https://py.sdk.modelcontextprotocol.io/get-started/real-host/#claude-desktop).
