# Acervo compartilhado entre Claude, Codex e painel

## Estado em 29/09/2026

Migração física e configuração concluídas. Banco ativo em **`C:\Users\Home\Documents\Flora\Dados\Flora-MCP`**, fora do cofre Obsidian e dos diretórios privados MSIX. O caminho físico foi conferido por `GetFinalPathNameByHandleW`.

- 7.477 documentos: STJ 5.021; TJSC 2.456; revisão 589.
- `integrity_check` aprovado, nenhuma violação de chave estrangeira e índice com 7.477 registros.
- `Store.backup` verificou 550 originais atuais; a auditoria adicional verificou os 578 originais referenciados no histórico.
- Copiados e comparados por SHA-256 587 arquivos de originais/evidências/logs e 437 arquivos dos backups históricos.
- Um novo backup foi exercitado em `Dados\Flora-MCP-backups\20260929-155736-180254`.
- Painel ativo em `http://127.0.0.1:8766/`, com o novo caminho passado explicitamente. O atalho da Área de Trabalho permanece válido.
- Cliente MCP independente, usando cada configuração salva, validou cobertura, pesquisa, leitura, relatoria e referência. Isso é teste de protocolo, não substitui teste dentro de cada aplicativo.
- Claude reiniciado por **File → Exit**; teste nativo aprovado na conversa nova **Flora-mcp technical verification**. Chamou cobertura, pesquisa e leitura. A pesquisa STJ por `alimentos` encontrou 83 resultados; `obter_documento` retornou a ementa de `STJ:1466726`, com 1.609 caracteres, referência completa e relator, sem pendências na referência e com hash correspondente ao resultado da busca.
- A conexão nativa antiga desta conversa Codex está encerrada (`Transport closed`). Reiniciar o Codex e repetir a verificação nativa é a pendência de ativação.

## Configuração e prevenção de duplicatas

`flora.local.toml` na raiz do projeto contém o endereço compartilhado. O carregamento não depende da pasta de trabalho nem de AppData. Precedência: argumento `--data-dir`, variável `FLORA_MCP_DATA_DIR`, TOML. `--config` seleciona outro TOML. Ausência de caminho ou caminho relativo gera erro.

Claude recebeu o novo `--data-dir`; Codex recebeu o novo `FLORA_MCP_DATA_DIR`. Campos não relacionados foram preservados. O painel grava logs sob a pasta configurada e passa o endereço resolvido ao processo filho. O gerador de tarefa de coleta grava `--data-dir` explícito. Não havia tarefa agendada do Flora-MCP e nenhuma foi criada.

Coleta CLI, `update_once.py` e backup recusam banco inexistente. Apenas `init` cria banco por pedido explícito. Foram executados 70 testes, Ruff e análise sintática dos scripts PowerShell. O registrador foi exercitado somente com `-WhatIf`.

Os 14 processos Python encontrados no momento da troca eram sete pares de lançador/filho. Foram encerrados os processos específicos `flora_mcp.cli serve` e `flora_mcp.panel`, sem encerrar o Codex. A cópia aconteceu sob `collector.lock`, usando a API consistente de backup SQLite; leitores não impedem esse mecanismo. A revisão da origem foi reconferida antes da troca.

## Reserva e recibos

Origem preservada e aposentada em:

`C:\Users\Home\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\Flora-MCP.migrado-20260929`

O caminho antigo ativo não existe. Os backups históricos privados também foram copiados para a pasta neutra; as cópias anteriores foram preservadas como histórico.

Backup dos códigos e configurações, manifesto, script da transferência, inventário de processos e recibo detalhado de hashes:

`C:\Users\Home\Documents\Flora\_Archive\backups\migracao-acervo-20260929-155103`

Teste de protocolo e caminho físico: [verificacao-migracao-20260929.json](verificacao-migracao-20260929.json).

Recibos históricos podem citar o endereço antigo. Esses recibos foram preservados, não reescritos; seus caminhos relativos `raw` continuam válidos no novo acervo. Na resposta do teste, o Claude interpretou um desses caminhos históricos como endereço ativo. A configuração e os argumentos dos processos novos apontam para a pasta compartilhada, cujo caminho físico foi conferido; o diretório antigo ativo já não existe. A observação do Claude não demonstra uso da base antiga.

## Operação

Backup: `.venv\Scripts\python.exe scripts/backup_acervo.py`. Cria uma nova pasta datada em `Dados\Flora-MCP-backups`, incluindo SQLite, `raw` e diretórios de evidências disponíveis. O comando não instala agendamento.

Painel: atalho **Jurisprudência Flora**. A nota **Jurisprudência** permanece no cofre. Para ativar no Codex, encerre o aplicativo e abra novamente. Em nova conversa, peça `consultar_cobertura`, uma pesquisa por `alimentos` com limite 1 e a leitura do documento, conferindo referência e relator.

Reversão, se necessária: interromper coletas e leitores e conferir diferenças antes de retornar à reserva. Depois de novas coletas no destino, a reserva não representa mais o acervo atual. Não alternar entre duas bases ativas.
