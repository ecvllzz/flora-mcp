# Flora-MCP no Claude Desktop

## Estado em 29/09/2026

Configuração adicionada ao arquivo efetivo aberto por **Settings → Developer → Edit config** na instalação Windows Store do Claude. A primeira tentativa usou AppData e falhou no Claude por redirecionamento MSIX. O teste no contexto do Codex não demonstrava acesso pelo Claude. Migração para pasta compartilhada autorizada em 29/09/2026; acompanhar [estado e verificação](migracao-dados-20260929.md).

- Servidor: `flora-mcp`.
- Executável: `C:\Users\Home\Documents\Flora-MCP\.venv\Scripts\python.exe`.
- Argumentos após migração: `-m flora_mcp.cli --data-dir C:\Users\Home\Documents\Flora\Dados\Flora-MCP serve`.
- Ambiente: `PYTHONUTF8=1`.
- Base compartilhada ativa: `Documents\Flora\Dados\Flora-MCP`. Um caminho absoluto dentro de AppData continua sujeito ao redirecionamento do aplicativo; a afirmação anterior em sentido contrário estava errada.
- Configuração efetiva: `C:\Users\Home\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`.
- Backup exato e manifesto de hashes: `C:\Users\Home\Documents\Flora\_Archive\backups\claude-flora-mcp-20260929-135706`.

Foi acrescentado somente `mcpServers.flora-mcp`. Os campos anteriores foram preservados e comparados após a gravação.

## Verificação já feita

Após a migração, o Claude foi encerrado por **File → Exit** e reaberto. Na conversa nova **Flora-mcp technical verification**, chamou `consultar_cobertura`, `pesquisar_jurisprudencia` e `obter_documento` com sucesso. A leitura de `STJ:1466726` entregou ementa, referência completa e relator. Os processos novos usam explicitamente a pasta compartilhada. Caminhos antigos citados em recibos históricos de coleta não indicam o endereço atual do banco.

Cliente MCP independente iniciou o comando configurado, completou o protocolo, listou `pesquisar_jurisprudencia`, `obter_documento` e `consultar_cobertura`, e consultou um resultado para `alimentos`, com referência e relatoria presentes. A consulta encontrou 1.130 registros no acervo daquele momento.

Esse teste comprova o servidor e o comando; não comprova que a instância já aberta do Claude carregou a nova entrada.

## Em futuras alterações de configuração

Encerre o Claude pelo comando **Quit/Sair** do aplicativo e abra-o novamente. Em **Settings → Developer**, confira `flora-mcp` com estado **Running**. Use uma conversa nova para descobrir as ferramentas recém-carregadas.

Pedido de uso sugerido:

> Use o flora-mcp para pesquisar jurisprudência sobre [tema]. Apresente a ementa e a referência completa, com tribunal, classe, processo, relator, órgão julgador e datas. Informe eventuais dados ausentes e os limites da cobertura.

A referência é entregue pelo servidor, a partir do espelho original preservado. O acervo é parcial e contém ementas e espelhos, sem garantir o inteiro teor dos votos. As três ferramentas são de leitura.

Referência técnica: [configuração de um servidor local no Claude Desktop, documentação oficial do MCP Python SDK](https://py.sdk.modelcontextprotocol.io/get-started/real-host/#claude-desktop).
