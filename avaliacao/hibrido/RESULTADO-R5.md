---
tipo: resultado
frente: recuperação e cobertura do Flora-MCP
fase: R5 (busca híbrida), comparação de modelos
onde: PCDADU (RTX 3070, 8 GB; i7-12700F; 32 GB)
data: 23/10/2026
corpus: r3376-s2-cd895f3434-f0a4721f447f, sem as 1.988 cópias de texto (o que a publicação r3376-s2-422d7bab33-9701325cf7ff serve)
---

# R5: busca semântica no Flora-MCP

## Recomendação

**Não adotar vetor local.** Nenhum modelo de 0,6 B supera o OU: o q06 empata na proposição e perde no assessor; o JUÁ 0.6B não ganha em nada. **Adotar o OU como compilador lexical da integração:** ele supera a ferramenta atual com folga (nDCG@8 0,730 contra 0,552 na proposição). **A Voyage (voyage-4) é o único ganho medido,** e só na proposição (+0,040 de nDCG@8, IC95 de +0,014 a +0,066); no assessor e na curta, empata com o OU. Adotá-la depende de decisão sobre enviar cada consulta a serviço externo. **O q4 (4 bilhões, local) não foi indexado:** em CPU custa 1,6 s por proposição, 5,5 s por ementa hipotética e 16,5 s por ementa nova, com 4,7 GB de memória, para um ganho que a Voyage, maior, já mostra ser pequeno.

Decisão do operador em 23/10: com o hit@8 saturado, a regra se aplica pelo nDCG@8; sem modelo local, a Voyage é o único ganho, e o q4 foi medido em CPU sem indexar.

## O que foi medido

- **Conjunto:** `conjunto-r5.json`, as 54 perguntas de 17 casos de família do R3, com a ementa hipotética de cada pergunta (formulação `hipotetica`, 400 a 581 caracteres, escrita antes de qualquer resultado semântico). Conferência inicial: `atual` 0,519 e `ou` 0,611 de hit@8 na proposição geral, como na linha de base.
- **Recorte de decisão:** `sem_obice`, por decisão do operador. O acórdão do STJ com óbice na verbetação sai das listas e dos graus. A regra de óbice deixou de contar a Súmula 83, que reafirma a tese (15.652 marcados, eram 16.782). Ao lado: `geral`, `obice_estrito` (só o óbice sem marca de tese, 12.424) e `stj_enxuto` (o estrito mais os EDcl rejeitados e as cópias do STJ, 13.707).
- **Cópias de texto:** fora de todas as listas e dos graus (`--sem-copias`), como a produção passou a servir em 23/10.
- **Sistemas:** `atual`, `ou`, e para cada modelo `denso`, `hibrido` (RRF de pesos iguais), `rrfp` (RRF com o lexical pesando 1 e o denso 0,5) e `ouden` (os 100 primeiros do OU reordenados pelo cosseno). Pesos e profundidade fixados antes do julgamento.
- **Pool:** `ou`, `rrfp:q06`, `rrfp:jua06` e `rrfp:v4`, todas as formulações, recorte `sem_obice`: 1.365 acórdãos não julgados em 54 perguntas. O `rrfp` é a melhor fusão de cada modelo na tabela sem julgamento.
- **Julgamento:** cego, por 20 subagentes, um lote de perguntas cada; o juiz viu só a proposição e as ementas embaralhadas, sem sistema nem posição. Entraram, misturados e sem marca, 120 controles com grau do registro (os 16 descartados e 104 relevantes sorteados, semente 20261024). Prompt no fim deste relatório.

## Modelos

| Nome | Modelo | Revisão | Backend | Instrução da consulta | Documentos | ms por consulta (lote, GPU) |
|---|---|---|---|---|---|---|
| q06 | Qwen/Qwen3-Embedding-0.6B | 97b0c61 | sentence-transformers, fp16, lote 8 | português do kit | 4.882 s | 5,8 |
| q06en | o mesmo, só consultas | 97b0c61 | idem | inglês ("Given a Brazilian legal question...") | (vetores do q06) | 7,2 |
| jua06 | ufca-llms/Qwen3-Embedding-0.6B-jua-V2 | fb8d835 | idem | português do kit | não comparável: três execuções (ver limites) | 9,0 |
| v4 | voyage-4 (API da Voyage AI) | API, 23/10 | backend `voyage`, lote 128 | `input_type` query e document | 1.945 s; 57,7 milhões de tokens | 17,4 |

- Instrução: no q06, a em português ganhou na proposição (0,574 contra 0,519 de hit@8 sem julgamento) e não perdeu no assessor; foi usada nos Qwen3.
- Fora da medida: voyage-law-2 (a execução caiu com a sessão a 60 mil documentos, e o operador decidiu não relançar); EmbeddingGemma (fora por decisão do operador, já que o q06 não é lento em CPU); q4 e jua4 (só depois do julgamento, por decisão do operador). Preparados e não indexados: `Qwen3-Embedding-4B-Q8_0.gguf` (revisão f460253, SHA-256 b60ae5ce...6949d) e o jua-4B-mixed convertido para Q8_0 com o llama.cpp b11840 (revisão 57f491c, SHA-256 1d86e5cf...818133).
- Licença: o JUÁ 0.6B não declara licença no repositório; a família JUÁ 4B declara MIT. Não é adotável enquanto isso não se esclarecer com a UFCA.

## Resultado julgado (recorte sem_obice, sem cópias)

hit@8 / nDCG@8, 54 perguntas.

| Sistema | proposição | assessor | curta | hipotética |
|---|---|---|---|---|
| atual | 0,963 / 0,552 | 0,963 / 0,620 | 0,981 / 0,663 | 0,963 / 0,552 |
| ou | 1,000 / 0,730 | 1,000 / 0,784 | 1,000 / 0,705 | 1,000 / 0,730 |
| rrfp:q06 | 1,000 / 0,750 | 1,000 / 0,759 | 1,000 / 0,700 | 1,000 / 0,752 |
| hibrido:q06 | 1,000 / 0,701 | 1,000 / 0,718 | 1,000 / 0,642 | 1,000 / 0,723 |
| rrfp:jua06 | 1,000 / 0,725 | 1,000 / 0,776 | 1,000 / 0,676 | 1,000 / 0,763 |
| hibrido:jua06 | 1,000 / 0,679 | 1,000 / 0,728 | 0,981 / 0,578 | 1,000 / 0,752 |
| rrfp:v4 | 1,000 / 0,770 | 1,000 / 0,793 | 1,000 / 0,691 | 1,000 / 0,797 |
| hibrido:v4 | 1,000 / 0,764 | 1,000 / 0,777 | 1,000 / 0,673 | 1,000 / 0,784 |

Fora do pool (com acórdãos não julgados no topo, punidos por isso): `ouden:v4` 0,662 e `denso:v4` 0,616 de nDCG@8 na proposição. O `atual` não entrou no pool, mas 94% a 96% do seu top 8 ficou julgado, e a comparação com ele vale.

**O hit@8 saturou:** todo sistema do pool acerta as 54 perguntas. A regra do handoff (superar o OU em hit@8 e nDCG@8) não separa ninguém, e a decisão do operador foi aplicá-la pelo nDCG@8.

**Diferença pareada contra o OU, nDCG@8, IC95 por bootstrap (2.000 reamostras):**

| Sistema | proposição | assessor | curta |
|---|---|---|---|
| rrfp:q06 | +0,020 [-0,012, +0,050]; ganha 26, perde 20 | -0,025 [-0,050, -0,002]; ganha 18, perde 29 | -0,005 [-0,038, +0,025] |
| rrfp:jua06 | -0,004 [-0,031, +0,022] | -0,008 [-0,031, +0,016] | -0,029 [-0,064, +0,004] |
| rrfp:v4 | +0,040 [+0,014, +0,066]; ganha 33, perde 13 | +0,010 [-0,007, +0,027] | -0,014 [-0,047, +0,016] |
| atual | -0,178 | -0,164 | -0,042 |

**nDCG@8 estrito** (só o grau 2 conta, o grau 1 vale 0, para tirar a leniência do juiz): proposição ou 0,626, atual 0,484, rrfp:q06 0,659, rrfp:jua06 0,629, rrfp:v4 0,673 (contra o OU: v4 +0,047 [+0,012, +0,081]; q06 +0,033 [-0,007, +0,072]; atual -0,142 [-0,211, -0,081]). Assessor: ou 0,672, rrfp:v4 0,681 (+0,009 [-0,017, +0,034]), rrfp:q06 0,646, rrfp:jua06 0,659. Curta: todos entre 0,557 e 0,590, sem diferença fora do acaso. A leitura não muda.

**Efeito do recorte sem_obice:** sobe o nDCG@8 de todos em cerca de 0,03 (ou de 0,698 para 0,730 na proposição; rrfp:v4 de 0,737 para 0,770), sem mudar a ordem. O `stj_enxuto` e o `obice_estrito` ficam a menos de 0,02 do `sem_obice` na tabela sem julgamento.

**Efeito da ementa hipotética:** a metade lexical continua a da proposição, e só o vetor usa a hipotética. Ajuda pouco os densos: rrfp:v4 0,797 contra 0,770 da proposição; rrfp:jua06 0,763 contra 0,725; rrfp:q06 igual. Em produção, exigiria que o agente escrevesse a ementa antes de buscar.

## Controles e conferência

- **Controles (120):** relevante contra não relevante, 91,7% de concordância com o registro (kappa 0,62); grau exato 0, 1 ou 2, 55,8% (kappa 0,25). O juiz é leniente: dos 49 controles de grau 1, 31 viraram grau 2; dos 16 descartados, 6 viraram relevantes. No pool, 87% dos acórdãos saíram relevantes (graus 0: 248, 1: 541, 2: 576).
- **Conferência pela sessão do Flora:** os 40 sorteados (semente 20261023) estão em `Documents\Flora\Dados\Flora-MCP-r5\conferencia\conferencia-r5.json`, pelo handoff `HANDOFF-FLORA-CONFERENCIA.md`. Resultado pendente. A concordância entre duas sessões Claude mede consistência, não validação humana; o operador pode conferir de 10 a 15 dos 40.

## q4 em CPU (medido, não indexado)

llama-server b11840, `--device none`, 4 threads, `--pooling last`, Qwen3-Embedding-4B-Q8_0, i7-12700F. Consulta isolada: curta 1,1 s, proposição 1,6 s (máximo 1,9 s), ementa hipotética 5,5 s; ementa nova do acervo 16,5 s em média (máximo 34 s); 4,7 GB de memória. O notebook (i5-1145G7, 4 núcleos) deve ficar 1,5 a 2 vezes mais lento. Em CPU, o sentence-transformers carrega em bf16 por padrão, cerca de cinco vezes mais lento que em float32; o q06 em float32 deu 0,23 a 0,35 s por proposição.

## Limites

- **O juiz é leniente** (kappa de 0,25 em três graus), o que achata as diferenças; o nDCG estrito confirma a ordem.
- **O conjunto saturou o hit@8.** As 54 perguntas são de família, tiradas de pesquisas que deram certo; o próximo conjunto deve vir das buscas que falharam (itens não recuperados e lacunas dos registros de pesquisa do vault, a contar no notebook).
- **O pool tem uma rodada só.** Modelo novo exige julgamento incremental dos acórdãos que ele trouxer.
- **A Voyage é serviço externo:** cada consulta sairia da máquina, com custo por chamada e dependência de internet. No teste, só foram enviadas as ementas públicas e as 270 consultas do conjunto, sem nome de parte nem número de processo.
- A detecção de óbice e a marca de tese são heurísticas sobre o começo da ementa.
- O tempo total do JUÁ 0.6B é aproximado: a primeira execução morreu com a sessão, a segunda recebeu um Ctrl+C a 1.536 documentos do fim, e a terceira retomou dos blocos salvos.

## Mudanças no kit (branch `reforma/r5-hibrido-kit`)

- `indexar.py`: backends `servidor` (llama-server, porque o llama-cpp-python com CUDA pré-compilado para Windows não lê Qwen3) e `voyage`; `--tarefa`; salvamento por bloco com retomada.
- `avaliar_hibrido.py` e `comum.py`: regra de óbice sem a Súmula 83; óbice também fora dos graus; recortes `obice_estrito` e `stj_enxuto`; fusões `rrfp` e `ouden`; `--pool-recorte`; `--sem-copias`; `n` e `obice_no_topo` na saída.
- Commits: 0e8c1be, 702757e, 9e5ae30, 02e71bc, 9dbdd8a, d00fd0a, b9a58e1, ddb56f1, ee3b914, 052eaf9.

## Arquivos

- Neste branch: `conjunto-r5.json`, `julgamentos.json` (1.365, sem os controles), `controles.json`, `resultado-sem-julgamento.json`, `resultado-r5.json`, este relatório.
- Por pendrive para o notebook: os vetores dos dois melhores, voyage-4 e q06 (`v4-docs.npy`, `v4-consultas.json`, `q06-docs.npy`, `q06-consultas.json`), na pasta `Documents\Flora\Dados\Flora-MCP-r5\pendrive`, com os SHA-256 no `LEIA-ME.txt`. Nenhum GGUF, porque nenhum 4B foi escolhido. Nada de vetor, acervo ou modelo no GitHub.

## Prompt do juiz

```
Você é juiz de relevância jurídica numa avaliação cega de busca de jurisprudência. Não sabe, nem deve tentar descobrir, qual sistema trouxe cada acórdão nem em que posição.

Leia inteiro o arquivo {LOTE} com a ferramenta Read, em partes (offset e limit) até a última linha. O arquivo traz blocos "##### PERGUNTA", cada um com uma PROPOSICAO (a questão jurídica) e, abaixo dela, vários "=== ITEM <código>" com a ementa de um acórdão.

Para cada ITEM, julgue a ementa inteira contra a PROPOSICAO da pergunta a que ele pertence e dê um grau:
- 2: a ementa decide a proposição, no mesmo sentido ou no contrário;
- 1: trata da mesma questão de modo parcial, ou de questão vizinha que serviria de apoio ou contraponto;
- 0: não trata da questão. Acórdão do STJ que só aplica óbice de admissibilidade é 0.

Julgue cada item por si, sem comparar com os outros itens. Não leia nenhum outro arquivo, não use outra ferramenta além de Read e Write, não pesquise no acervo nem na web.

Grave com Write o arquivo {SAIDA}, um JSON no formato {"<código>": {"grau": 0, 1 ou 2, "razao": "uma frase"}}, com todos os itens do lote, sem faltar nenhum. Na razão, não use travessões e não cite nomes de relatores.

Ao terminar, responda só com o número de itens julgados e quantos ficaram em cada grau.
```

As ementas foram cortadas em 6.000 caracteres, como na indexação. Um juiz usou o Bash uma vez para contar as linhas do lote, sem ler outro arquivo.
