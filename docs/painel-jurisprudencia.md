# Painel de jurisprudência

Abra **Jurisprudência Flora** na Área de Trabalho para iniciar o serviço local e abrir a nota de acesso no Obsidian. Depois, use o marcador ou o link **Consultar jurisprudência** da nota. Pelo menu do link, **Abrir link no visualizador web** mantém o painel dentro do Obsidian.

Endereço: `http://127.0.0.1:8766/`. Após reiniciar o Windows, use o atalho novamente. Não há inicialização automática instalada.

O painel oferece busca textual, filtros, leitura da ementa completa e cópia da ementa junto da referência. **Atualizar consulta** relê o banco; não coleta novos julgados. Acervo parcial e campos faltantes são sinalizados.

O código está em `src/flora_mcp/panel.py` e `src/flora_mcp/panel_assets/`. O início usa `scripts/start_panel.ps1` e resolve o mesmo `flora.local.toml` usado pelas rotinas de coleta. Dados ativos em `C:\Users\Home\Documents\Flora\Dados\Flora-MCP`; logs em `panel-logs` nessa pasta. O servidor escuta apenas em `127.0.0.1` e usa consultas SQLite de leitura.

O HTML tem CSS próprio inspirado na Home. A Home e seus snippets não foram alterados. O serviço funciona localmente; não é uma publicação na internet nem um endereço para outros computadores.

Histórico e verificações da transferência: [migração de dados](migracao-dados-20260929.md).
