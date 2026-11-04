# Regras do gabinete no código: inventário e destino

Inventário feito em 04/11/2026 (M4 do plano da revisão de 2026-11; `RM-D16`, `RM-D32`), sobre o `main` em `98f90c2`, antes de mudar o código. Lista cada regra que só vale para o gabinete que mantém o Flora-MCP e diz o que se fez com ela. O usuário de referência é outro gabinete ou serviço que queira o acervo oficial do STJ e do TJSC sem nada do Flora (`RM-D32`).

Três destinos possíveis:

- **configuração**: a regra sai do código e passa a ser lida de `flora.local.toml` (seção `[flora]`), com padrão quando ausente; a configuração vigente do gabinete (só `data_dir` e `request_delay`) reproduz o comportamento anterior, provado por `tests/test_regras_do_gabinete.py`;
- **padrão neutro**: o código deixa de afirmar a regra; quem a quiser a dá por configuração ou nas instruções do próprio agente;
- **fica no código**: a regra é vocabulário da fonte, do contrato ou de um procedimento com recibo, e mudá-la é mudança de contrato ou de coleta, não de instalação.

Linhas de arquivo são as do `main` em `98f90c2`.

## Regras que foram para configuração

| Regra | Onde estava | Chave | Padrão quando ausente |
|---|---|---|---|
| Lista de órgãos do TJSC coletados por janela de dia de publicação (as dez Câmaras de Direito Civil, decisão do operador de 30/09/2026) | `src/flora_mcp/tjsc_orgaos.py:21-23` (`PADRAO`), usada por `src/flora_mcp/tjsc.py:548` (`sync_tjsc`) e `src/flora_mcp/sources.py:246` (`probe_tjsc`) | `tjsc_orgaos`, lista de nomes exatos do filtro do portal | as dez Câmaras de Direito Civil, que são todas as câmaras de direito civil do portal e o que `atualizar` sempre coletou; outra instalação troca a lista |
| "Súmula bancária é apoio: apresente antes as de civil e processual civil", dito ao agente na descrição de `pesquisar_precedentes` | `src/flora_mcp/server.py:264-265`; repetido em `CONTRATO.md` (seção `pesquisar_precedentes`) e `README.md:40` | `[flora.orientacoes]`, texto por ferramenta acrescentado ao fim da descrição | nenhum texto: a descrição só diz que `materia` filtra e que cada item traz a sua. No gabinete a regra continua no canon do pipeline (`RM-D30`); quem quiser mantê-la na descrição põe `pesquisar_precedentes = "Súmula bancária é apoio: apresente antes as de civil e processual civil."` |
| Enumeração dos órgãos do acervo do gabinete na descrição de `pesquisar_jurisprudencia` ("STJ (Terceira e Quarta Turmas e Segunda Seção) e câmaras cíveis do TJSC, mais os de educação das Câmaras de Direito Público") | `src/flora_mcp/server.py:245-247` | `[flora.orientacoes]`, chave `pesquisar_jurisprudencia` | nenhum texto: a descrição remete a `consultar_cobertura`, que diz o que há |
| Caminho da nota do Obsidian que o atalho do painel abre | `scripts/start_panel.ps1:6` | `painel_nota` | sem a chave, o atalho abre o painel no navegador padrão em vez da nota |

## Regras que viraram padrão neutro

| Regra | Onde estava | O que mudou |
|---|---|---|
| Caminhos desta máquina como se fossem a instalação (`C:\Users\Home\...`) nos exemplos de conexão e na frase "Nesta máquina" | `README.md:56`, `README.md:62-88`, `docs/instalacao-claude.md`, `docs/painel-jurisprudencia.md` | Exemplos com `<pasta do projeto>` e `<pasta do acervo>`; o que vale para esta máquina fica em `AGENTS.md` e numa nota curta do guia do Claude |
| "O código próprio não tem licença de distribuição escolhida" | `README.md`, seção "Integridade e limites" | `LICENSE` (MIT) e `LICENCA-DADOS.md` (CC BY 4.0 para o acervo publicado), `RM-D40` |

## Regras que ficam no código, com a razão

| Regra | Onde está | Razão |
|---|---|---|
| Nomes dos órgãos do TJSC que o coletor aceita (`ORGAOS`, `ESPECIAIS`, `PUBLICO`): Câmaras de Direito Civil de 1 a 10, 1ª a 3ª Câmaras Especiais de Enfrentamento de Acervos, 1ª a 5ª Câmaras de Direito Público e Grupo de Câmaras de Direito Público | `src/flora_mcp/tjsc_orgaos.py:16-28` | É o vocabulário do portal, lido do formulário de pesquisa em 30/09/2026 (fixture em `tests/fixtures/tjsc/`), com os homônimos excluídos. Nome fora da lista chegaria ao portal como filtro desconhecido, cuja resposta não se distingue de um dia vazio. `tjsc_orgaos` escolhe entre os nomes aceitos; acrescentar um nome é uma linha, depois de conferido no formulário do portal |
| Câmaras de Direito Público entram só por consulta de tema, nunca por janela de dia (`window_name`, `orgao_so_por_tema`; decisão do operador de 23/10/2026) | `src/flora_mcp/tjsc_orgaos.py:39-44` | Protege o acervo de uma janela que traria o órgão inteiro, quando só o tema de educação foi medido e autorizado. Outra instalação que queira direito público inteiro por janela muda uma tupla; por ora é regra de coleta com recibo, não de instalação |
| Datasets do STJ coletados por padrão (Terceira e Quarta Turmas e Segunda Seção) | `src/flora_mcp/config.py:21-27` | Já é configuração (`datasets`); o padrão é o recorte civil do gabinete e fica, porque mudar o padrão mudaria o que `atualizar` coleta sem chave na configuração |
| Limiares de atraso por fonte (45 dias para o STJ, 7 para o TJSC) | `src/flora_mcp/config.py:8,19-20`; `src/flora_mcp/store.py:11,356` | Já é configuração (`atraso_stj_dias`, `atraso_tjsc_dias`). O padrão vem da cadência da fonte (lote mensal do STJ, publicação diária do TJSC), não do gabinete |
| Primeira e Terceira Seções do STJ ficam pendentes na admissão (`secao_fora_do_recorte_civil`) | `src/flora_mcp/precedent_sources/common.py:62-72` | Regra de admissão do pacote `flora-precedentes-1`, declarada em `CONTRATO.md` (3.1); o registro não se perde, fica pendente com o motivo. Liberar é decisão sobre o acervo, com recibo, não configuração |
| Tabela de ramos admitidos (`RAMOS`: civil, consumidor, empresarial, processual civil, bancário) e prioridade entre ramos mistos (`PRIORIDADE`: civil, depois processual civil, depois bancário) | `src/flora_mcp/precedent_sources/stj_sumulas.py:19-26`, `src/flora_mcp/precedent_sources/stj_temas.py:33`, `src/flora_mcp/precedent_sources/common.py:75-90` | Define o campo `materia` do contrato (`civil`, `processual_civil`, `bancario`, enum do esquema). Outro ramo é valor novo no enum, isto é, contrato novo; a prioridade está declarada em `CONTRATO.md` (3.2) |
| Temas de coleta do TJSC (educação e família e sucessões: órgãos, subtemas, períodos, filtros `educacao-3` e `familia-1`) | `src/flora_mcp/tema.py:311-380` | Receitas de coleta com filtro versionado e amostra cega julgada, que só rodam por script e por ordem expressa; não afetam o servidor. Outra instalação define o seu tema no mesmo lugar, com a sua amostra |
| Padrão histórico do script de lacunas (`RETOMADA`: 9ª e 10ª Câmaras) | `scripts/resume_tjsc.py:21-22` | Documentado no README e sobreposto por `--camaras` e `--orgaos`; trocar o padrão mudaria o que o operador obtém sem opção |
| Guia do transporte HTTP escrito para o Copilot Studio | `docs/http-studio.md` | Guia de uma integração específica; o adaptador HTTP em si é genérico. Não há hospedagem em uso |
