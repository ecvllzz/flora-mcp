---
tipo: ensaio-de-frente
frente: recuperação e cobertura do Flora-MCP
fase: R3 (primeira candidata medida no conjunto ampliado)
trilha: Claude (Engenharia)
data: 2026-10-23
publicacao: r3376-s2-cd895f3434-f0a4721f447f
branch: reforma/r3-ensaio-ou-simples (worktree Documents\Flora-MCP-ensaio-ou, sem commit, sem merge)
---

# Ensaio: busca simples de acórdãos com OU sem palavras vazias

## O que mudou

Só a busca simples de `pesquisar_jurisprudencia` (`JudgmentSearch`): em vez de ligar todas as palavras por E e ampliar para OU quando o E zera, a consulta liga por OU as palavras e frases que não são palavras vazias, e o BM25 põe à frente quem tem mais termos. A lista de palavras vazias é a da ampliação mais `não`, `sua`, `seu`, `isso`, `esse`, `essa` e `este` (`não` sozinho casava com 73.918 das 82.176 ementas). Frases entre aspas ficam inteiras; consulta só de palavras vazias continua como veio. Modo avançado, filtros, ordenação, triagem e a busca de precedentes não mudam. Diff de 11 linhas em `query.py`, guardado em [ensaio-ou-simples.patch](ensaio-ou-simples.patch).

## Testes

`ruff` passa. Dos 381 testes, 371 passam e 10 falham, todos por contrato: sete de `test_ampliacao.py`, os exemplos e a ordem dos motivos de resposta vazia em `test_contrato.py` e um de `test_precedents.py` que confere a ampliação numa busca de acórdãos. A consulta simples deixa de ter E e o bloco `ampliacao` deixa de aparecer em acórdãos; `total_encontrado` passa a contar quem tem qualquer termo (5.445 em vez de 52 no exemplo "redução de alimentos por desemprego do alimentante"). Por isso o branch ficou sem commit: o portão de qualidade recusaria, e a adoção pede contrato novo (`flora-mcp-3.4`), não ajuste de teste.

## Medida

Mesma publicação, mesmo `medir.py` e o `scripts/avaliar.py` do branch, somente leitura. hit@8 da linha de base para o ensaio, com ganhos e perdas pergunta a pergunta:

| Linha | n | hit@8 | recall@8 | MRR@100 | sem relevante nos 100 | ganha / perde |
|---|---|---|---|---|---|---|
| proposição | 54 | 0,519 para 0,611 | 0,356 para 0,426 | 0,327 para 0,372 | 41% para 13% | 5 / 0 |
| assessor | 54 | 0,500 para 0,593 | 0,365 para 0,442 | 0,402 para 0,441 | 32% para 13% | 5 / 0 |
| curta | 54 | 0,556 para 0,556 | 0,388 para 0,368 | 0,288 para 0,289 | 26% para 19% | 2 / 2 |
| rótulo | 54 | 0,519 para 0,556 | 0,351 para 0,386 | 0,350 para 0,372 | 37% para 30% | 2 / 0 |
| proposição, filtro da Câmara | 49 | 0,592 para 0,673 | 0,422 para 0,488 | 0,442 para 0,487 | 29% para 6% | 4 / 0 |
| assessor, filtro da Câmara | 49 | 0,592 para 0,694 | 0,465 para 0,560 | 0,475 para 0,534 | 22% para 4% | 5 / 0 |
| curta, filtro da Câmara | 49 | 0,612 para 0,673 | 0,462 para 0,493 | 0,407 para 0,425 | 25% para 8% | 4 / 1 |

Conjunto de 14 perguntas da F6: nada muda em acerto (assessor 0,286, natural 0,429, curta 0,500; zero ganhos e zero perdas), porque ali o E já zerava e a ferramenta já ampliava para OU na maior parte. A triagem fica maior (de 5,6 a 6,8 mil bytes para cerca de 7,1 mil bytes por página, em média), porque o trecho deixa de ser a palavra vazia ("DE") e passa a ser a ocorrência de um termo de conteúdo. A medida do R3 levou 920 s contra 799 s na linha de base, nas mesmas condições: a consulta com OU custa cerca de 15% a mais.

Leitura: com consulta longa, o E com as palavras vazias acha poucos acórdãos que contêm tudo e os põe à frente dos pertinentes; o OU tira de 19 a 28 pontos da fração de perguntas sem relevante nos cem primeiros. Com consulta curta e termos comuns, o E delimitava melhor: nas perdas, "honorários exclusão litisconsorte" e "fato superveniente apelação" iam de 53 e 408 acórdãos com E para 24.803 e 38.013 com OU, e o relevante saiu dos oito primeiros. Os ganhos de 5 sem perda têm p de cerca de 0,06 no teste do sinal: direção clara, amostra pequena.

## Regra mista, simulada

E quando a consulta tem até três termos de conteúdo e o E encontra algo; OU nos demais casos. Simulada das duas medidas acima (cada pergunta toma uma das duas respostas já medidas, o que é exato porque as duas são determinísticas na mesma publicação), não implementada:

| Linha | hit@8 | contra a linha de base | contra o OU puro |
|---|---|---|---|
| proposição | 0,611 | 5 / 0 | 0 / 0 |
| assessor | 0,593 | 5 / 0 | 0 / 0 |
| curta | 0,574 | 1 / 0 | 2 / 1 |
| rótulo | 0,537 | 1 / 0 | 0 / 1 |
| proposição, filtro da Câmara | 0,673 | 4 / 0 | 0 / 0 |
| assessor, filtro da Câmara | 0,694 | 5 / 0 | 0 / 0 |
| curta, filtro da Câmara | 0,633 | 1 / 0 | 1 / 3 |

É a única das três (E com ampliação, OU puro, mista) que não perde em nenhuma linha nem em nenhuma métrica contra a linha de base (recall e MRR da curta: 0,391 e 0,291; da curta filtrada: 0,468 e 0,412), que é a regra de adoção da F6. Também conserva o E e o bloco `ampliacao` para consulta curta, o que reduz a mudança de contrato.

## Limites

- Uma publicação, 54 perguntas, quase todas de família no TJSC; o STJ tem 4 perguntas só dele.
- Os relevantes vieram de buscas feitas com a ferramenta atual, o que favorece a linha de base; um OU que traz acórdãos nunca rotulados pode estar sendo punido por isso. Não houve leitura dos novos primeiros colocados.
- A regra mista é simulação; o limite de três termos foi escolhido olhando as perdas, logo está ajustado a este conjunto e precisa de confirmação em pergunta nova.
- A busca de precedentes não foi tocada nem medida.

## Estado

Worktree `C:\Users\Home\Documents\Flora-MCP-ensaio-ou`, branch `reforma/r3-ensaio-ou-simples` a partir de `main` em `280622a`, com o diff sem commit. `main` e o servidor em uso não mudaram. Resultados: [resultado-r3-ou.json](resultado-r3-ou.json) (R3) e [avaliar-f6-ou.json](avaliar-f6-ou.json) (14 perguntas); comparação por [comparar.py](comparar.py).
