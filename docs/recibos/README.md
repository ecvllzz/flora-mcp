# Recibos

Documentos datados que registram uma execução, uma verificação ou o estado do projeto num momento. São evidência: não se reescrevem, e o `.gitattributes` os guarda byte a byte. Caminhos e contagens citados dentro deles valem para a data do recibo, não para o acervo atual. O que vale hoje está no [README](../../README.md), no [CONTRATO.md](../../CONTRATO.md) e no [DECISOES.md](../../DECISOES.md).

| Recibo | Data | O que registra |
|---|---|---|
| [instalacao-codex.json](instalacao-codex.json) | 22/09/2026 | Registro do servidor `flora-mcp` na configuração do Codex, com backup e hashes antes e depois |
| [conexao-codex.json](conexao-codex.json) | 22/09/2026 | Descoberta das três ferramentas de então por um processo separado do app-server do Codex |
| [validacao-recuperacao.json](validacao-recuperacao.json) | 22/09/2026 | Recuperação por cliente MCP com o comando configurado: ementas em blocos, hashes, filtros e paginação |
| [verificacao-mcp.json](verificacao-mcp.json) | 22/09/2026 | Verificação de protocolo stdio pelo SDK MCP sobre a amostra de três órgãos |
| [exemplo-real.md](exemplo-real.md) | 22/09/2026 | Ementas completas devolvidas pela pesquisa na verificação acima |
| [coleta-tjsc-2026-retomada-20260929.json](coleta-tjsc-2026-retomada-20260929.json) | 29/09/2026 | Execução da retomada da coleta TJSC de 2026 (plano, janelas e backup) |
| [coleta-tjsc-2026-retomada-verificacao-20260929.json](coleta-tjsc-2026-retomada-verificacao-20260929.json) | 29/09/2026 | Integridade e quantidades depois da retomada TJSC |
| [coleta-tjsc-2026-mcp-nativo-20260929.json](coleta-tjsc-2026-mcp-nativo-20260929.json) | 29/09/2026 | Busca e leitura pelo MCP nativo nas duas câmaras, na revisão 589 |
| [coleta-tjsc-2026-entrega-20260929.json](coleta-tjsc-2026-entrega-20260929.json) | 29/09/2026 | Entrega da retomada TJSC: testes e hashes dos arquivos |
| [coleta-tjsc-2026-retomada-20260929.md](coleta-tjsc-2026-retomada-20260929.md) | 29/09/2026 | Resumo da retomada TJSC de 2026 (1.022 acórdãos acrescentados) |
| [verificacao-referencias-20260929.json](verificacao-referencias-20260929.json) | 29/09/2026 | Conferência da referência completa e da relatoria nos 7.477 registros da revisão 589 |
| [referencias-citacao.md](referencias-citacao.md) | 29/09/2026 | Implementação e verificação da referência para citação nas respostas |
| [verificacao-migracao-20260929.json](verificacao-migracao-20260929.json) | 29/09/2026 | Caminho físico do banco e teste de protocolo com as configurações do Claude e do Codex após a migração |
| [migracao-dados-20260929.md](migracao-dados-20260929.md) | 29/09/2026 | Migração do acervo para `Documents\Flora\Dados\Flora-MCP` |
| [precedentes-v2.md](precedentes-v2.md) | 29/09/2026 | Contrato `flora-mcp-2` de temas e súmulas e formato de base do pacote `flora-precedentes-1` |
| [estado-ate-20260929.md](estado-ate-20260929.md) | 22/09 a 29/09/2026 | Estado do desenvolvimento até a reforma de 30/09 (antes `docs/estado.md`) |
| [reforma-2026-09-30.md](reforma-2026-09-30.md) | 30/09/2026 | Resumo da reforma de 30/09, fase por fase (F0 a F7) |

Os links relativos para fora do repositório dentro de `estado-ate-20260929.md` apontam para o vault a partir da posição antiga (`docs/`) e não foram corrigidos, porque o recibo não se reescreve.
