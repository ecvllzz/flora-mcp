# Estado do desenvolvimento

Data corrente: 29/09/2026. Versão do código e servidor: `0.2.0a1`. Responsável: Codex. Projeto autônomo chamado **Flora-MCP**, por decisão do operador. As seções históricas abaixo mantêm seus números e datas de execução.

## Reforma de precedentes e leitura — 29/09/2026

Modelo schema 2 aplicado ao banco real após backup consistente. Publicação de leitura por arquivos novos e manifesto atômico ativada; originais conferidos por hash. Preservados todos os 7.477 acórdãos, inclusive igualdade de identificadores, textos e referências com o backup anterior.

Implementados componentes de temas/súmulas, admissão e retirada auditáveis, triagem optativa, cobertura resumida/paginada, busca avançada optativa, seções literais de ementa, painel e exportação Markdown/JSON. Referências de publicação distinguem enunciado, mérito e embargos. O catálogo exportado exige ID vigente e hash para recuperação.

Seis pilotos conferidos foram admitidos e exportados: STJ IAC 2, Tema 1085 e Súmula 385; STF Súmula 380 e Súmula Vinculante 25; TJSC Súmula 67 do Grupo Civil. RG809 permanece pendente por falta de comprovação da publicação original da tese; não está disponível na consulta de uso. A carga é parcial. Ementas dos paradigmas ainda não foram obtidas.

85 testes passaram, Ruff e sintaxe JavaScript sem falhas; processo MCP novo contra o banco real recuperou os seis componentes com hashes e bloqueou o pendente. Painel local observado com os seis registros. Clientes Claude/Codex já abertos precisam recarregar o servidor para descobrir os parâmetros novos. Testes locais não demonstram conexão ou aceite no Studio/SharePoint.

[Contrato e comandos](precedentes-v2.md). [Estado e recibos da reforma](../../Flora/Flora/_meta/engenharia/biblioteca-codex-mcp/execucao-reforma-precedentes-20260929.md). A reforma integral continua em andamento: adaptadores de atualização dos catálogos, expansão conferida da carga, ensaio morfológico e aceite dos consumidores são pendências explícitas. Nenhum agendamento está autorizado ou ativado; a indicação antiga de ativá-lo como próximo marco foi superada pela decisão de atualização manual.

## Identificação completa nas respostas - 29/09/2026

Pesquisa e leitura de documentos passam a incluir referência com relatoria,
classe, número, tribunal, órgão e datas, recuperada do espelho original da mesma
versão. Dados ausentes são sinalizados. Servidor e ferramentas orientam a inclusão
da referência ao apresentar jurisprudência e usá-la em votos. Compatível com o
acervo existente, sem migração ou coleta. Trinta e nove testes aprovados e 7.477
registros conferidos, sem pendências de identificação; processo MCP novo
verificado com a configuração Codex. A conexão nativa já aberta ainda precisa
ser reconectada; não houve reinício forçado. [Contrato e evidências](referencias-citacao.md).

## Implementado

- Pacote Python independente, dependências travadas, configuração externa e dados fora do vault.
- Base SQLite/FTS5, arquivos oficiais preservados, versões, proveniência, transações, bloqueio de escritor e backup consistente.
- Coletor STJ por catálogo: detecção de novos recursos/metadados alterados, carga limitada, retomada e reconciliação por idade da última verificação.
- Coletor experimental TJSC por dia de publicação, nas duas câmaras: paginação completa, verificação de órgão/data/contagem, duplicações e primeira página; falha sem promover a janela.
- MCP local com três ferramentas de leitura, pesquisa lexical e leitura integral ou por blocos explícitos.
- Rotina administrativa de atualização independente de LLM e registrador de tarefa diária Windows, ainda não ativado.

## Verificação obtida

STJ: seis arquivos oficiais, julho e agosto de 2026, consultados nesta sessão; **5.021 documentos**. Terceira Turma: 2.458; Quarta Turma: 2.367; Segunda Seção: 196. Cinquenta e quatro recursos JSON do recorte configurado ainda estão pendentes. Arquivo de extração recente pode conter decisões antigas.

TJSC: consulta HTTP pública atual, sem capturas históricas reaproveitadas. Dias de publicação **18 e 19/09/2026**, duas câmaras; **39 documentos**: seis da 9ª e 33 da 10ª. A janela da 10ª em 19/09 percorreu três páginas, recuperando 23 documentos. Repetição das quatro janelas: zero documentos novos/alterados e 39 inalterados. Uma janela explicitamente vazia foi reconhecida como tal. Total local: **5.060 documentos**.

Problemas encontrados e corrigidos: leitura da codificação ISO-8859-1 do TJSC; representação especial do portal para zero resultados; modelo de saída estruturada e nomes de atributos do SDK MCP 2.2.0. As falhas originais permanecem no histórico operacional, seguidas das execuções bem-sucedidas.

**27 testes automatizados aprovados**, análise estática sem falhas e recibo de protocolo em [verificação MCP](verificacao-mcp.json). O teste usa processo servidor real e cliente SDK, sem dependência de um aplicativo específico. Há testes de transações interrompidas, retomada, versões, filtros, recuperação de texto longo, mudanças entre páginas, restauração, bloqueio de escritor, conexão de leitura e inconsistências na paginação TJSC.

Backup real da amostra em `C:\Users\Home\AppData\Local\Flora-MCP-backups\alpha-20260922`, com integridade SQLite e hashes dos dez originais atuais conferidos. Script de registro de tarefa Windows passou por validação sintática, mas não foi executado nem instalado. Dependências instaladas apenas no ambiente virtual deste projeto.

## Próximos marcos

1. Concluída a verificação técnica de 31 documentos e seis temas nos dois tribunais, usando a configuração registrada no Codex. O app-server do Codex reconheceu as três ferramentas. Pendente: avaliação de recuperação/pertinência com o agente de uso final; os 31 documentos foram comparados com a base, não com uma coleção independente de casos conhecidos.
2. Observar coletas em dias diferentes, calibrar janela móvel/carga e ativar o agendamento quando esses resultados sustentarem operação contínua. Não confundir repetição no mesmo dia com estabilidade ao longo do tempo.
3. Completar o histórico STJ do recorte escolhido e ampliar TJSC, com reconciliação histórica rotativa para indexação tardia.
4. Validar obtenção/vinculação de inteiro teor em cada fonte, sem presumir acesso por existir um link.
5. Resolver política de conflitos entre extrações STJ, ausência de recursos no catálogo e eventual retirada pública de documentos.
6. Preparar distribuição e licença do código, quando decidido; transporte remoto com autenticação é etapa posterior.

## Fora desta entrega

Não houve alteração no pipeline judicial do Flora, em casos ou skills de redação. A configuração Codex foi instalada em 22/09/2026 e reconhecida por um processo separado do app-server; as ferramentas da conversa já aberta não foram recarregadas. Integração M365/Copilot, hospedagem remota, publicação e atualização diária automática continuam pendentes. A alpha não representa a conclusão do plano integral.

## Conexão Codex e preparação do piloto de biblioteca - 22/09/2026

- Servidor `flora-mcp` registrado pelo comando oficial, com backup e igualdade das demais configurações conferida. Recibo: [instalação](instalacao-codex.json).
- O app-server instalado do Codex iniciou o servidor e descobriu as três ferramentas; `toolsError: null`. Recibo: [conexão](conexao-codex.json). Teste sem turno de modelo, em processo separado; não prova carregamento nesta conversa.
- Recuperação via cliente MCP com o comando efetivamente configurado: 31 ementas recompostas em blocos de 800 caracteres, igualdade e hashes conferidos, seis temas em STJ/TJSC, filtros e paginação. Recibo: [validação](validacao-recuperacao.json). Os 27 testes de regressão passaram novamente.
- Amostra local de quatro autotextos e seis ementas completas preparada em `C:\Users\Home\Documents\Flora\Flora\_meta\engenharia\floramini\biblioteca-piloto`. Nada enviado ao Microsoft 365; nenhuma alteração no acervo canônico.
- Busca lexical por data pode devolver óbices processuais quando a demanda é material. Foram preparados cenários para verificar se o Copilot reconhece esse limite. Cobertura pequena do TJSC e ausência de inteiro teor permanecem limitações.

## Extensão HTTP — 28/09/2026

Foi acrescentado o [adaptador HTTP autenticado](http-studio.md) para Streamable HTTP, mantendo as três ferramentas de leitura. Testes locais de autenticação, Host/Origin e protocolo usam acervo sintético. Ainda não há hospedagem nem conexão com o Studio. As observações anteriores sobre ausência de transporte remoto referem-se ao estado anterior a esta extensão; inteiro teor continua pendente.

## Pesquisa por relevância textual - 29/09/2026

Acrescentada a opção `ordenar: relevancia` à ferramenta `pesquisar_jurisprudencia` e `--ordenar relevancia` ao CLI. Usa BM25 do FTS5, com datas e ID para desempate; exige termos. Mantém ementas integrais, filtros, paginação e ordenação cronológica padrão. Não altera schema, acervo ou coletores.

Verificação: 23 testes de consulta, armazenamento e protocolo aprovados (18 anteriores e cinco novos), Ruff sem falhas nos arquivos alterados. Processo MCP novo com a configuração Codex pesquisou o acervo real, percorreu duas páginas e recuperou a ementa com hash conferido. A conexão nativa já aberta ainda rejeita a opção nova: reconexão pendente, sem reinício forçado. Não houve publicação de versão.

A frente Codex está restrita a acórdãos e catalogação jurisprudencial em massa; autotextos e sincronização com o vault não entram no MCP. Ampliação temática e organização por filtros avaliadas no [plano da frente](../../Flora/Flora/_meta/engenharia/biblioteca-codex-mcp/plano-de-trabalho.md). [Recibo](../../Flora/Flora/_meta/engenharia/biblioteca-codex-mcp/verificacao-relevancia-2026-09-29.json).

## Retomada TJSC 2026 concluída - 29/09/2026

Por nova autorização do operador, concluídas as 183 janelas pendentes de 2026
até 29/09: 1.022 documentos novos, total TJSC de 2.456 (9ª: 454; 10ª: 2.002).
As 544 janelas do período têm conclusão registrada; as antigas foram conferidas
e dispensadas da recoleta. STJ preservado em 5.021; total do acervo 7.477.
Banco, originais, versões e índice íntegros; busca e leitura nativas verificadas
na revisão 589. São espelhos e ementas, sem inteiro teor dos votos. O dia corrente
é provisório e indexações tardias anteriores não foram reconciliadas.

Adicionado `scripts/resume_tjsc.py` para plano de lacunas, aplicação explícita com
backup/lock e retomada por janela. Quatro testes novos e sete do coletor passaram;
análise estática aprovada. Nenhum agendamento ou catalogação no vault foi feito.
[Resultado, backup e evidências](coleta-tjsc-2026-retomada-20260929.md).

## Cobertura compacta — 29/09/2026

`consultar_cobertura` agora retorna resumo por padrão. O conteúdo de texto MCP foi medido em 9.786 caracteres no acervo real; 604 recursos viraram cinco agregados, sem perder as 54 pendências, falhas ou motivos de interrupção registrados. `detalhe=completo`/`legado` conserva a resposta anterior. Recursos aceitam filtro tribunal/dataset e paginação; execuções também são paginadas. Pesquisa e documento não foram modificados nesta correção. 87 testes passaram; verificação específica em `scripts/verify_coverage.py`. Banco ativo em `Documents\Flora\Dados\Flora-MCP`; caminhos MSIX presentes nos recibos antigos são históricos. Recarga de clientes já abertos permanece necessária.
