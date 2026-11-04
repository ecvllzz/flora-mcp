# Avaliação da busca: método e linha de base do caminho real

Item M1 da revisão de 04/11/2026 (decisões `RM-D15`, `RM-D24`, `RM-D28`, `RM-D37` e `RM-D38`). Nada aqui muda a busca: tudo é leitura de uma cópia do acervo.

## Resultado em poucas linhas

- **O caminho real não ganha do modo simples.** Com filtro de câmara, a consulta avançada põe um relevante nos oito primeiros em 65% das perguntas, contra 67% a 69% do modo simples; pergunta a pergunta, nenhuma diferença passa do acaso. O avançado é mais estreito: a fração de perguntas sem nenhum relevante nos cem primeiros é de 22%, contra 4% a 8%.
- **O STJ traz cerca de um óbice a cada cinco posições.** Com filtro de tribunal, nas 30 perguntas só do STJ, os acórdãos que só aplicam óbice ocupam de 18% a 25% do topo. É o que M2 quer tirar, agora com linha de base.
- **Pergunta em frase inteira hoje é recusada.** Todas as 160 formulações longas escritas para este conjunto são recusadas pelo limite de 30 termos, e também 61 das 143 perguntas reais reescritas.
- **Parte automática:** a busca devolve nos oito primeiros o tema ou a súmula citados em 32% das ementas, e o acórdão citado em 23%, pela melhor formulação de cada bloco.

## O que há nesta pasta

| Arquivo | O que é |
|---|---|
| `conjunto-m1.json` | Parte com relevantes rotulados: 80 perguntas, 30 só do STJ |
| `conjunto-citacao-removida.json` | Parte automática: 300 ementas e o que citam, só identificadores |
| `perguntas-longas.json` | 143 perguntas reais reescritas, sem gabarito ainda |
| `medir.py`, `citacao_removida.py`, `medir_longas.py` | As três medidas, somente leitura |
| `preparar_julgamento.py` | Monta o lote cego da sessão que julga, fora do repositório |
| `resultados/2026-11-04-*.json` | Os números desta linha de base |
| `resultados/2026-10-23-*.json`, `relatorios/`, `hibrido/` | Medidas de outubro, saneadas |
| `conjunto.json`, `candidatas_indice.py`, `resultados/f6-*`, `resultados/r781-*` | Medida da F6, de 30/09, que mede outra coisa (citações das minutas) e não foi fundida |

## O conjunto

**Parte rotulada: 54 perguntas de outubro.** Tiradas em 23/10 dos registros de pesquisa do gabinete: cada acórdão que um papel leu e marcou vira julgamento da tese a que serve, com grau 2 (fundamento, apoio, citado), 1 (contraponto, analogia) ou 0 (descartado). Formulações `proposicao`, `assessor` e `curta` foram redigidas a partir do rótulo e da matéria, sem ler as ementas esperadas.

**Parte rotulada: 26 perguntas novas do STJ.** As 4 perguntas só do STJ passam a **30**. O número foi fixado antes de medir, e o conjunto foi gravado em commit antes dos resultados (`ea67236`). Motivo: com 30, uma pergunta vale 3,3 pontos e 6 ganhos sem perda, 20% do bloco, já passam no teste do sinal a 5%, o que basta para decidir M2; com 20, seria preciso 30%. Havia 32 proposições distintas no registro. Regra de escolha: primeiro as que têm acórdão marcado como fundamento (19), depois as com mais de um relevante (3), depois a que traz descartados por óbice, útil a M2 (1), e as demais pela ordem do número do acórdão (3). Nas novas, acórdão lido e não usado, com ratio sobre a proposição, recebe grau 1, e as formulações saíram da tese e da ratio registradas, em outras palavras.

**Formulação `avancada`.** Expressão do modo avançado, uma por pergunta, no formato dos registros: mediana de 2 AND e 2 OR, com frases e prefixo. Dos registros veio só o formato (238 consultas avançadas contra 1 simples, das que gravam o modo); nenhuma consulta foi copiada. Um subagente as redigiu numa passada só, recebendo apenas as proposições, sem registros, esperados nem resultados.

**Formulações longas.** `longa`, frase inteira de 48 a 63 palavras, e `hipotetica`, ementa imaginada, redigidas às cegas a partir da proposição, sem fatos.

**Perguntas longas reais (`RM-D38`).** Dos registros saíram 187 textos: 70 recusados pelos limites, 48 frases longas e 69 lacunas de pesquisa. Uma sessão os reescreveu, reduzindo o fato à categoria jurídica. Uma segunda, sem acesso aos originais nem à pasta do caso e cega quanto à origem, conferiu cada um em dois pontos: se sobrou o que identifique o caso e se a pergunta se preservou. Os números do lote e as duas conferências estão no recibo `docs/recibos/lote-perguntas-longas-20261104.json`. O original e a correspondência ficam só fora do repositório.

**Parte automática (`RM-D37`).** Gabarito que dispensa juízo: ementa do TJSC, no modelo CNJ, que cita o STJ na linha de jurisprudência citada. A consulta é a própria ementa sem a citação; acerta quem devolve o citado nos oito primeiros. Há dois blocos, com um documento por citado na ordem de `sha256(semente:id)`, para a súmula mais citada não dominar:

- `precedente`, 200 ementas, medido em `pesquisar_precedentes`, como pede `RM-D37`;
- `acordao`, 100 ementas, medido em `pesquisar_jurisprudencia`. Este vai além da decisão: tirar óbice ou mudar a ordem dos acórdãos não altera a busca de precedentes, e sem ele M2 e M8 não teriam medida automática que os alcançasse.

A amostra exclui processos com o número de algum caso do gabinete. O conjunto guarda só identificadores; texto e consulta se refazem do acervo ao medir.

## O que se mede

Cada linha é formulação, modo e filtro, sobre a ferramenta como o agente a chama, seguindo o cursor até oito itens. Filtros: `sem`; `tribunal`, com o tribunal de mais relevantes na pergunta; `camara`, a 10ª ou a 9ª, a do primeiro relevante, como a medida de 23/10. Com filtro, só contam os relevantes do recorte; pergunta sem relevante no recorte fica fora da linha. Registram-se hit@8, recall@8, nDCG@8, MRR@100, fração fora dos 100, vazias, recusas e, com a regra da R5, acórdãos do STJ que só aplicam óbice no topo (12.340 na publicação). O intervalo de 95% vem de 2.000 reamostras por pergunta. O modo avançado não foi medido com `proposicao` nem `assessor`: exigir todas as palavras de uma frase não é consulta que alguém escreva.

**Quem julgou, e com que calibração.**

- Graus de registro: quem pesquisou, no pipeline, ao ler o acórdão.
- `*_julgado`: os 1.365 graus cegos da R5, de 23/10, dados por 20 subagentes Claude, com controles (kappa 0,62 em relevante contra não relevante, 0,25 em três graus), **sem** calibração pelos votos do operador. Só no bloco de 54.
- Parte automática: não há juiz.
- Julgamento novo: **pendente**. 2.099 pares (pergunta, acórdão) do topo das linhas ainda não têm grau, entre eles todos os das perguntas novas do STJ. Por `RM-D37`, quem julga é sessão independente, que não muda a busca nem conduz a revisão, calibrada pelos 20 votos do operador, sem ver a origem dos resultados; `preparar_julgamento.py` monta o lote. No teste comparativo de 04/11 nenhum avaliador reproduziu o critério do operador (4 e 3 acertos em 9), e por isso a parte automática acompanha toda medida com juiz.

## Linha de base

Publicação `r3622-s2-422d7bab33-d1f6a0397baf`, em cópia somente leitura, com 82.367 acórdãos. Commit `c3bdf93`. Os hashes da cópia e da publicação não mudaram com a medida.

### O caminho real: filtro de câmara, 49 perguntas

| Linha | n | hit@8 | IC 95% | recall@8 | nDCG@8 | MRR@100 | fora dos 100 | vazias | hit julgado | nDCG julgado | não julgados |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proposição, simples | 49 | 0,673 | 0,55 a 0,82 | 0,488 | 0,417 | 0,490 | 6% | 0 | 0,959 | 0,715 | 89 |
| assessor, simples | 49 | 0,694 | 0,57 a 0,82 | 0,560 | 0,473 | 0,535 | 4% | 0 | 0,959 | 0,759 | 88 |
| curta, simples | 49 | 0,673 | 0,55 a 0,80 | 0,493 | 0,384 | 0,424 | 8% | 0 | 0,959 | 0,687 | 108 |
| avançada, avançado | 49 | 0,653 | 0,51 a 0,78 | 0,463 | 0,380 | 0,483 | 22% | 2 | 0,878 | 0,594 | 80 |
| curta, avançado | 49 | 0,592 | 0,45 a 0,73 | 0,452 | 0,363 | 0,403 | 26% | 2 | 0,898 | 0,610 | 59 |

Avançada contra simples, pergunta a pergunta, em hit@8 (ganha, perde): contra proposição, 5 e 6; contra assessor, 6 e 8; contra curta, 6 e 7.

### Só o STJ: filtro de tribunal, 30 perguntas

| Linha | n | hit@8 | IC 95% | recall@8 | nDCG@8 | MRR@100 | fora dos 100 | vazias | óbice no topo |
|---|---|---|---|---|---|---|---|---|---|
| proposição, simples | 30 | 0,800 | 0,67 a 0,93 | 0,689 | 0,642 | 0,699 | 7% | 0 | 47 de 240 |
| assessor, simples | 30 | 0,800 | 0,67 a 0,93 | 0,668 | 0,611 | 0,672 | 7% | 0 | 51 de 240 |
| curta, simples | 30 | 0,633 | 0,47 a 0,80 | 0,517 | 0,461 | 0,508 | 7% | 0 | 60 de 240 |
| avançada, avançado | 30 | 0,667 | 0,50 a 0,83 | 0,556 | 0,502 | 0,525 | 33% | 6 | 28 de 157 |
| curta, avançado | 30 | 0,700 | 0,53 a 0,83 | 0,583 | 0,498 | 0,516 | 27% | 3 | 41 de 172 |

### Todas as 80, sem filtro

| Linha | n | hit@8 | IC 95% | recall@8 | nDCG@8 | MRR@100 | fora dos 100 | vazias | óbice no topo |
|---|---|---|---|---|---|---|---|---|---|
| proposição, simples | 80 | 0,637 | 0,53 a 0,74 | 0,486 | 0,389 | 0,445 | 10% | 0 | 30 de 640 |
| assessor, simples | 80 | 0,650 | 0,55 a 0,75 | 0,505 | 0,429 | 0,502 | 10% | 0 | 34 de 640 |
| curta, simples | 80 | 0,525 | 0,41 a 0,64 | 0,367 | 0,266 | 0,300 | 16% | 0 | 52 de 640 |
| avançada, avançado | 80 | 0,600 | 0,50 a 0,70 | 0,434 | 0,336 | 0,388 | 28% | 4 | 21 de 556 |
| curta, avançado | 80 | 0,550 | 0,44 a 0,66 | 0,389 | 0,274 | 0,300 | 26% | 1 | 43 de 586 |

### Bloco de 54, contra a publicação de outubro

| Linha | n | hit@8 | IC 95% | recall@8 | nDCG@8 | MRR@100 | fora dos 100 | vazias | hit julgado | nDCG julgado | não julgados |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proposição, simples | 54 | 0,574 | 0,44 a 0,70 | 0,412 | 0,310 | 0,372 | 13% | 0 | 1,000 | 0,669 | 45 |
| assessor, simples | 54 | 0,593 | 0,46 a 0,72 | 0,442 | 0,362 | 0,440 | 13% | 0 | 1,000 | 0,732 | 40 |
| curta, simples | 54 | 0,519 | 0,39 a 0,65 | 0,340 | 0,245 | 0,283 | 18% | 0 | 0,981 | 0,575 | 85 |
| avançada, avançado | 54 | 0,593 | 0,46 a 0,72 | 0,408 | 0,316 | 0,391 | 24% | 1 | 0,963 | 0,579 | 118 |
| curta, avançado | 54 | 0,537 | 0,41 a 0,67 | 0,363 | 0,253 | 0,284 | 26% | 0 | 0,963 | 0,546 | 95 |

Hit@8 do bloco contra o ensaio de 23/10 (`r3376`): proposição, de 0,611 para 0,574; assessor, de 0,593 para 0,593; curta, de 0,556 para 0,519. Sem filtro, proposição e curta perdem duas perguntas cada, com o acervo maior; com filtro de câmara, os valores de hit@8 coincidem com os do ensaio.

### Perguntas longas

| Formulação | n | recusadas |
|---|---|---|
| longa | 80 | 80 |
| hipotetica | 80 | 80 |
| perguntas reais reescritas, recusada | 62 | 60 |
| perguntas reais reescritas, longa | 45 | 0 |
| perguntas reais reescritas, falha | 36 | 1 |
| perguntas reais reescritas, todas | 143 | 61 |

### Parte automática

| Bloco e consulta | n | hit@8 | IC 95% | MRR@8 | recusadas | vazias | ampliadas |
|---|---|---|---|---|---|---|---|
| precedente, cabecalho_30 | 200 | 0,315 | 0,26 a 0,38 | 0,207 | 0 | 0 | 200 |
| precedente, tese_30 | 200 | 0,275 | 0,22 a 0,34 | 0,177 | 0 | 0 | 200 |
| precedente, tese_inteira | 200 | 0,000 | 0,00 a 0,00 | 0,000 | 176 | 0 | 24 |
| acordao, cabecalho_30 | 100 | 0,230 | 0,15 a 0,31 | 0,156 | 0 | 0 | 0 |
| acordao, tese_30 | 100 | 0,190 | 0,12 a 0,27 | 0,116 | 0 | 0 | 0 |
| acordao, tese_inteira | 100 | 0,000 | 0,00 a 0,00 | 0,000 | 71 | 0 | 0 |

`tese_inteira` é o trecho sem corte: a recusa dela é a medida do limite. `cabecalho_30` e `tese_30` cortam nos 30 primeiros termos, para passar pelo limite de hoje.

### Perguntas que falham hoje

Em 9 das 80 nenhuma linha põe relevante nos oito primeiros: `r002`, `r019`, `r021`, `r026`, `r030`, `r031`, `r036`, `r046`, `r053`. As lacunas de pesquisa reescritas, tipo `falha` em `perguntas-longas.json`, são a outra fonte de pergunta que falha.

## Leitura

- **Não há ganho do avançado de uma só tentativa.** Com a mesma pergunta, o avançado acerta perto do simples e deixa mais perguntas sem nenhum relevante nos cem primeiros, porque o AND corta. Nos graus cegos, o nDCG@8 com câmara é 0,594, contra 0,687 a 0,759, mas o pool foi feito sobre o OU e favorece o simples.
- **Essa linha não diz que os agentes pesquisam mal.** No pipeline o agente refaz a consulta depois de ler o resultado, e aqui há uma tentativa só; o ganho do avançado pode estar em reformular, o que esta medida não vê.
- **O número útil para M2 é o par STJ.** Hit@8, nDCG@8 e óbice no topo da tabela do STJ são o antes de `RM-D14`.

## Limites

- **Relevante nunca lido conta como não relevante.** Os esperados saíram de buscas feitas com a própria ferramenta, o que favorece o lexical e, em especial, as consultas parecidas com as que acharam o esperado.
- **O bloco do STJ acerta mais do que o de outubro, e parte disso é efeito de método.** As novas foram escritas da ratio, cujo vocabulário é o da ementa. Compare-se antes e depois dentro do bloco, não contra o bloco de 54.
- **Casos correlacionados.** As 54 vêm de 17 casos; o campo de caso saiu, e o intervalo por pergunta é otimista.
- **Filtro de câmara escolhido sabendo a resposta:** vai à câmara do primeiro relevante, como em 23/10, e no pipeline o agente busca nas duas.
- **Publicação.** A cópia está em `r3622`; a produção já serve `r3667`, com mais família do TJSC. Refazer a linha de base sobre a publicação de partida antes de decidir M2.
- **Uma pessoa, uma passada.** Cada formulação vem de um só redator.
- **Parte automática:** cita-se o que a ementa quis citar, não tudo o que seria pertinente; a chave de citação é normalização por regra e tem defeitos conhecidos (`RM-D35`), que aqui só fazem o citado não aparecer no conjunto. Corte em 30 termos pega o começo do trecho, que pode não ser o miolo da tese.
- **Longas reais não têm gabarito:** por ora medem só a recusa.

## Medidas de outubro

- `resultados/2026-10-23-r3-linha-de-base.json`: modo simples, com E, sem filtro e com câmara.
- `resultados/2026-10-23-r3-ensaio-ou.json`, `-r3-compiladores.json` e `-f6-ensaio-ou.json`: o ensaio do OU e os compiladores candidatos.
- `hibrido/`: a R5, com os agregados e os graus, sem as razões do juiz nem as listas por pergunta.
- **24/10:** a medida que levou o OU à produção não tem arquivo próprio. Seus números estão na entrada de 24/10 do `DECISOES.md` e coincidem com os do ensaio de 23/10.

Saneamento: saíram `caso`, `origem` e `rotulo`, porque o rótulo gravado traz fatos de caso em algumas perguntas. Por isso a formulação `rotulo` deixou de ser medida; seus números de outubro continuam nos arquivos, sem o texto da consulta. Conferido por varredura dos nomes e números de todas as pastas de caso em todos os arquivos desta pasta, em que o único achado é uma palavra comum deste texto, e pela conferência de traço de caso do portão. Nenhum acórdão esperado é do processo do caso de onde saiu a pergunta. A curadoria e a origem de cada pergunta ficam só no vault.

## Reproduzir

Sempre sobre uma cópia, com `FLORA_MCP_DATA_DIR` apontando para ela:

```
python avaliacao/medir.py --conjunto avaliacao/conjunto-m1.json --julgamentos avaliacao/hibrido/julgamentos-graus.json --saida R.json
python avaliacao/medir.py --longas --conjunto avaliacao/conjunto-m1.json --saida R-longas.json
python avaliacao/citacao_removida.py medir --conjunto avaliacao/conjunto-citacao-removida.json --saida R-citacao.json
python avaliacao/medir_longas.py --conjunto avaliacao/perguntas-longas.json --saida R-reais.json
python avaliacao/preparar_julgamento.py --resultado R.json --resultado R-reais.json --pasta <fora do repositório>
```

A medida principal leva cerca de 55 minutos. O hash do conjunto medido está no resultado; o `conjunto-m1.json` atual difere do medido só por acrescentar `longa` e, nas 26 novas, `hipotetica`.

**Critério para mudança de busca (`RM-D28`, regra de 30/09):** publica só com ganho e sem piora em outra medida, e o resultado declara o critério e o número de cada medida, inclusive quem julgou e com que calibração.
