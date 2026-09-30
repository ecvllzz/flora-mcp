# Painel de jurisprudência

Abra **Jurisprudência Flora** na Área de Trabalho para iniciar o serviço local e abrir a nota de acesso no Obsidian. Depois, use o marcador ou o link **Consultar jurisprudência** da nota. Pelo menu do link, **Abrir link no visualizador web** mantém o painel dentro do Obsidian.

Endereço: `http://127.0.0.1:8766/`. Após reiniciar o Windows, use o atalho novamente. Não há inicialização automática instalada.

O painel oferece pesquisa de acórdãos e de temas e súmulas admitidos, filtros, leitura da ementa completa e cópia da ementa junto da referência. Mostra também as fontes com coleta em atraso, junto da data da última coleta. **Atualizar consulta** relê o acervo; não coleta novos julgados (a coleta é `flora-mcp atualizar`, descrita no [README](../README.md#atualização)). Acervo parcial e campos faltantes são sinalizados.

O código está em `src/flora_mcp/panel.py` e `src/flora_mcp/panel_assets/`. O início usa `scripts/start_panel.ps1`, que resolve o mesmo `flora.local.toml` usado pela CLI e recusa iniciar se a porta 8766 estiver ocupada por outro serviço. Dados ativos em `C:\Users\Home\Documents\Flora\Dados\Flora-MCP`; logs em `panel-logs` nessa pasta. O servidor escuta apenas em `127.0.0.1` e só lê o acervo.

Um processo de painel já aberto continua com o código com que foi iniciado; depois de atualizar o `main`, encerre-o e abra o atalho de novo.

O HTML tem CSS próprio inspirado na Home. O serviço funciona localmente; não é uma publicação na internet nem um endereço para outros computadores.

Transferência do acervo para a pasta atual: [recibos/migracao-dados-20260929.md](recibos/migracao-dados-20260929.md).
