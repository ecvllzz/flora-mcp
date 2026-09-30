# Coleta TJSC 2026: retomada concluída

Conferência em 29/09/2026. Escopo: acórdãos da 9ª e da 10ª Câmara de Direito
Civil, por data de publicação entre 01/01 e 29/09/2026.

## Resultado

| Câmara | Antes | Acrescentados | Total atual |
|---|---:|---:|---:|
| 9ª Câmara de Direito Civil | 282 | 172 | 454 |
| 10ª Câmara de Direito Civil | 1.152 | 850 | 2.002 |
| **TJSC** | **1.434** | **1.022** | **2.456** |

Nenhum documento anterior foi alterado ou removido nesta retomada. Os 5.021
registros STJ foram comparados com o backup e permaneceram iguais em identidade,
conteúdo, hash e recurso de origem. Total geral do Flora-MCP: **7.477 documentos**.

Foram concluídas as 183 janelas pendentes. As 361 já concluídas foram dispensadas
após conferir seus originais e quantidades. O período agora contém 544 combinações
de câmara e dia, inclusive as consultas que retornaram zero resultados.

## Conferência

- Banco SQLite íntegro, chaves estrangeiras e IDs do índice de busca conferidos.
- Hashes dos 544 originais TJSC correntes e das versões documentais conferidos.
- Quantidades das janelas compatíveis com observações e documentos armazenados.
- Busca e recuperação de ementa por ambas as câmaras verificadas pelo código e
  pelas ferramentas nativas do MCP, na revisão 589 da base.
- Últimas publicações encontradas: 28/09 na 9ª Câmara e 26/09 na 10ª.
- Execução encerrada como `ok`; sem coletor ativo no banco.
- Quatro testes da retomada e sete do coletor TJSC passaram; Ruff passou.

## Alcance

O conteúdo incorporado é **espelho com ementa de acórdão**. O inteiro teor dos
votos não foi baixado. O recorte é de publicação, que pode diferir da data do
julgamento. Janelas concluídas correspondem ao que o portal devolveu no momento
da respectiva consulta; não certificam a completude institucional do acervo.

O dia 29/09 é provisório por ser o dia corrente. Este preenchimento de lacunas
não revisitou janelas já concluídas para procurar indexações tardias. A rotina
não foi agendada, e nenhuma ficha foi catalogada no vault por consequência da
coleta. O bloqueio de distribuição da skill Biblioteca é uma frente independente.

## Retomada e evidências

O novo `scripts/resume_tjsc.py` planeja sem escrever e aplica somente pendências
com `--apply`, backup, lock e recibo. Conserva cada janela gravada e para na
primeira falha. A execução anterior e o seu recibo foram preservados.

- [Recibo da execução](coleta-tjsc-2026-retomada-20260929.json).
- [Verificação de integridade e quantidades](coleta-tjsc-2026-retomada-verificacao-20260929.json).
- [Busca e leitura pelo MCP nativo](coleta-tjsc-2026-mcp-nativo-20260929.json).

Backup anterior à escrita, conferido por integridade SQLite e hashes de 367
originais correntes, em:

C:\Users\Home\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\Flora-MCP-backups\antes-retomada-tjsc-20260929
