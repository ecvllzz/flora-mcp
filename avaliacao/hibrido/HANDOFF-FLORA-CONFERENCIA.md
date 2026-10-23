---
tipo: handoff
frente: recuperação e cobertura do Flora-MCP
fase: R5 (busca híbrida), conferência dos julgamentos
de: sessão Claude Code de Engenharia no PCDADU
para: sessão do Flora (Claude desktop, skills do pipeline)
---

# Conferir 40 julgamentos de relevância da R5

## Contexto

A R5 mede se uma busca por significado (vetores), somada à busca atual por palavras, traz ementas melhores para o Flora-MCP. Para medir, cada acórdão que algum sistema pôs entre os 8 primeiros recebeu um grau de relevância contra a questão jurídica, dado às cegas por subagentes da sessão de Engenharia. Desses julgamentos, 40 foram sorteados com semente fixa para uma conferência independente. Esta sessão faz essa conferência, com o olhar de quem usa as ementas para fundamentar votos.

## O que você recebe

O arquivo `conferencia-r5.json`, entregue pelo operador, com 40 itens. Cada item traz `n` (número de 1 a 40), `proposicao` (a questão jurídica) e a ementa do acórdão (`id` e `texto`). Não traz o grau já dado, o sistema que trouxe o acórdão nem a posição dele na lista.

## O que fazer

Para cada item, leia a proposição e a ementa inteira e dê um grau:

- **2**: a ementa decide a proposição, no mesmo sentido ou no contrário;
- **1**: trata da mesma questão de modo parcial, ou de questão vizinha que serviria de apoio ou contraponto no voto;
- **0**: não trata da questão. Acórdão do STJ que só aplica óbice de admissibilidade (Súmula 7, falta de prequestionamento e afins), sem afirmar tese, é 0.

Julgue cada item por si, sem comparar com os outros nem tentar adivinhar o grau que ele recebeu.

## Entrega

Grave `conferencia-r5-respostas.json` no formato:

```json
{"1": {"grau": 2, "razao": "uma frase"}, "2": {"grau": 0, "razao": "uma frase"}}
```

e devolva ao operador, que leva o arquivo à sessão de Engenharia. Lá se calculam a concordância com os 40 julgamentos originais e os itens em que houve divergência; se quiser, a Engenharia devolve esses itens para você comentar.

## Regras

- Julgue só o que está no arquivo: não pesquise no acervo, em outras ferramentas ou na web.
- Nada do arquivo vai a serviço externo.
- Sem travessões em nenhum texto. Não cite nomes de relatores.
- Não altere skills, canons nem o vault: é só uma conferência.
