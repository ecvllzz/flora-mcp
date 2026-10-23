---
tipo: handoff
frente: recuperação e cobertura do Flora-MCP
fase: R5 (busca híbrida), comparação de modelos na GPU
de: sessão Claude de Engenharia no notebook (23/10/2026)
para: sessão Claude Code no PCDADU (RTX 3070, 8 GB)
publicacao: r3376-s2-cd895f3434-f0a4721f447f
---

# Comparar modelos de busca semântica para o Flora-MCP

## Objetivo

Medir se vetores semânticos, fundidos com o BM25 atual, recuperam melhor os acórdãos pertinentes do que a busca lexical, e qual modelo vale servir no notebook (que só tem CPU). A GPU serve para indexar e comparar; quem vai atender as consultas depois é o notebook. O resultado é uma tabela por modelo e configuração, os julgamentos dos novos primeiros colocados e os vetores do modelo escolhido. Nada aqui altera o Flora-MCP, o acervo real ou o `main`.

## O que já se sabe (não refaça)

- Conjunto de avaliação: `conjunto-r3.json`, 54 perguntas de 17 casos de família, tiradas dos registros de pesquisa do vault, com graus 2 (fundamento), 1 (contraponto) e 0 (descartado) e quatro formulações (`proposicao`, `assessor`, `curta`, `rotulo`). Detalhe em `_meta/engenharia/flora-mcp-recuperacao/r3-avaliacao/r3-linha-de-base-2026-10-23.md` no vault.
- Linha de base (acerto nos 8 primeiros, proposição/assessor/curta): ferramenta atual 0,52/0,50/0,56; OU sem palavras vazias 0,61/0,59/0,56. O kit reproduz esses números exatamente com os sistemas `atual` e `ou`; se não reproduzir aí, pare e investigue antes de seguir.
- Cerca de 45% dos acórdãos do STJ têm óbice de admissibilidade na verbetação (16.782 de 37.691). O recorte `sem_obice` mede a busca sem eles.
- De 280 a 390 dos 432 lugares no topo são acórdãos que ninguém julgou: sem o julgamento do passo 6, a medida pune quem acha coisa nova.

## Preparação

1. **Repositório.** Se o PCDADU não tiver o Flora-MCP, clone `https://github.com/ecvllzz/flora-mcp` em `Documents\Flora-MCP`; se tiver, `git fetch`. Use o branch `reforma/r5-hibrido-kit`; o kit está em `avaliacao/hibrido/`. Não troque o branch do worktree de produção (`main`), se ele existir aí; crie um worktree próprio.
2. **Acervo.** O operador traz por pendrive a publicação `r3376-s2-cd895f3434-f0a4721f447f.sqlite` (cerca de 1,1 GB). Copie para uma pasta fora do vault e fora do repositório, por exemplo `Documents\Flora\Dados\Flora-MCP-r5\`, e confira o SHA-256 contra o que o operador informar. Use só essa cópia, sempre somente leitura.
3. **Ambiente.** `nvidia-smi` deve mostrar a RTX 3070. Crie um ambiente Python próprio (3.11 ou 3.12) fora do Flora-MCP. Pacotes: `numpy`, `torch` com CUDA, `transformers`, `sentence-transformers`, `huggingface_hub` e, para os modelos de 4 bilhões, `llama-cpp-python` com CUDA. **Cada download (pacote grande ou modelo) só com confirmação do operador no chat, dizendo nome, origem e tamanho.** Modelos só dos repositórios oficiais no Hugging Face; anote a revisão (hash do commit) de cada um.

## Passos

Todos os comandos rodam de `avaliacao/hibrido/`, com `<C>` a pasta de trabalho (por exemplo `Dados\Flora-MCP-r5\corpus`) e `<P>` a publicação copiada.

1. **Corpus e listas lexicais** (cerca de 10 minutos):
   ```
   python exportar_corpus.py <P> <C>
   python candidatos_bm25.py <P> conjunto-r3.json <C>/candidatos-bm25.json
   python avaliar_hibrido.py --conjunto conjunto-r3.json --bm25 <C>/candidatos-bm25.json --corpus <C>
   ```
   Confira: 82.176 acórdãos, 16.782 com óbice, SHA-256 dos textos `46fa82bfe84b0ab4c8bad6292d549c6eb59c75514ec74308cc467607abbf5c2a`, e `atual`/`ou` em proposição geral com hit@8 0,519 e 0,611.
2. **Ementa hipotética** (antes de ver qualquer resultado semântico). Copie o conjunto para `conjunto-r5.json` e acrescente a cada pergunta o campo `hipotetica`: uma ementa no modelo CNJ (cabeçalho em maiúsculas com a matéria e o tema, e uma ou duas frases de tese), de 400 a 900 caracteres, escrita só a partir de `proposicao`, sem consultar o acervo nem os esperados, e sem inventar número de processo, relator ou precedente. Acrescente `"hipotetica"` à lista `formulacoes`. Escreva todas de uma vez, numa só passada, e não as reescreva depois de ver números. Rode de novo o passo 1 com `conjunto-r5.json` (saída `candidatos-bm25-r5.json`). A ementa hipotética passa do limite de 30 termos da busca lexical, então só a metade semântica a usa: nas linhas `hipotetica`, `atual` e `ou` repetem as da proposição, e o híbrido funde o OU da proposição com o vetor da hipotética.
3. **Indexação**, nesta ordem, cada uma com confirmação de download:
   | Nome | Modelo | Backend e perfil | Observação |
   |---|---|---|---|
   | `q06` | `Qwen/Qwen3-Embedding-0.6B` | `st`, `qwen3` | Apache-2.0; minutos na 3070 |
   | `jua06` | JUÁ 0.6B (UFCA, adaptação jurídica brasileira do Qwen3-0.6B) | `st`, `qwen3` | confirme o id exato e a licença no Hugging Face; se não houver versão pública, pule |
   | `q4` | `Qwen/Qwen3-Embedding-4B-GGUF`, arquivo Q8_0 | `gguf`, `qwen3` | 4 bilhões quantizados; é o mesmo arquivo que o notebook usaria em CPU |
   | `gemma` | `google/embeddinggemma-300m` | `st`, `gemma` | só se o operador aceitar os termos da Gemma |
   ```
   python indexar.py --corpus <C> --conjunto conjunto-r5.json --nome q06 --backend st --modelo Qwen/Qwen3-Embedding-0.6B --perfil qwen3 --lote 32
   python indexar.py --corpus <C> --conjunto conjunto-r5.json --nome q4 --backend gguf --modelo <caminho do .gguf> --perfil qwen3 --lote 8
   ```
   O `--max-caracteres 6000` padrão corta as ementas muito longas; mantenha-o igual em todos. No backend `gguf`, confirme no cartão do modelo que o pooling é o do último token (o kit usa `pooling_type=3`); se o resultado do `q4` ficar abaixo do `q06`, suspeite primeiro do pooling e do prefixo.
4. **Comparação:**
   ```
   python avaliar_hibrido.py --conjunto conjunto-r5.json --bm25 <C>/candidatos-bm25-r5.json --corpus <C> --nomes q06 q4 ... --saida <C>/resultado-sem-julgamento.json
   ```
5. **Reordenação** (opcional, sobre o melhor híbrido): exporte as listas com `--exportar-pares hibrido:<melhor> --pares <C>/pares.json`, rode `reordenar.py --backend qwen3 --modelo Qwen/Qwen3-Reranker-0.6B` (confira o formato do prompt contra o cartão do modelo) e avalie de novo com `--reordenacao`. Anote os segundos por lista: no notebook, sem GPU, isso pode ser lento demais para servir.
6. **Julgamento dos novos primeiros colocados:**
   ```
   python avaliar_hibrido.py ... --pool <C>/pool.json --pool-sistemas ou hibrido:<melhor> hibrido:<segundo> --pool-formulacoes proposicao hipotetica
   ```
   Para cada pergunta do `pool.json`, julgue cada acórdão listado contra a `proposicao`, lendo a ementa inteira em `corpus-textos.jsonl`:
   - **2**: a ementa decide a proposição, no mesmo sentido ou no contrário;
   - **1**: trata da mesma questão de modo parcial, ou de questão vizinha que serviria de apoio ou contraponto;
   - **0**: não trata da questão. Acórdão do STJ que só aplica óbice de admissibilidade é 0.
   No ensaio do kit, dois sistemas em duas formulações deram cerca de 800 acórdãos a julgar; com três sistemas, conte com 1.000 a 1.500. O julgamento é cego: quem julga vê só a proposição e a ementa, nunca o sistema que trouxe o acórdão nem a posição. Pode distribuir em subagentes, um lote de perguntas por vez, com essa regra no prompt. Grave `<C>/julgamentos.json` no formato `{"r001": {"TJSC:...": {"grau": 2, "razao": "uma frase"}}}`. Separe 40 julgamentos sorteados (semente 20261023) para o operador conferir e anote a concordância.
7. **Medida final** com `--julgamentos <C>/julgamentos.json --saida <C>/resultado-r5.json`.

## Regra de decisão

Recomende um modelo e uma configuração só se, depois do julgamento, o híbrido superar o `ou` em hit@8 e nDCG@8 na proposição e no assessor, sem piorar a curta além de uma pergunta. Entre modelos com resultado parecido (diferença de até duas perguntas), prefira o menor, porque o notebook vai calcular o vetor de cada consulta em CPU. Diga também o efeito do recorte `sem_obice` e da ementa hipotética.

## Entrega

- **No branch `reforma/r5-hibrido-kit`** (commit e push, com o portão de qualidade passando): `conjunto-r5.json`, `julgamentos.json`, `resultado-r5.json`, `resultado-sem-julgamento.json` e um relatório `RESULTADO-R5.md` com a tabela, os modelos e as revisões usadas, os tempos de indexação, a concordância do operador e a recomendação.
- **Por pendrive para o notebook**: `<nome>-docs.npy` e `<nome>-consultas.json` dos dois melhores modelos e o arquivo do modelo escolhido, se for GGUF.
- Não suba vetores, acervo ou modelo ao GitHub.

## Regras

- Acervo só na cópia, somente leitura. Nada de tocar no acervo real, no `main` ou nos branches de outras frentes.
- Nenhuma consulta ou texto vai a serviço externo; tudo roda na máquina.
- Sem travessões (U+2014) em nenhum texto. Não cite nomes de relatores do gabinete no relatório.
- Se um passo falhar ou um número não bater com o esperado, pare e relate antes de contornar.
