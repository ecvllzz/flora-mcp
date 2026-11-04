---
tipo: medida-de-frente
frente: recuperação e cobertura do Flora-MCP
fase: R3 (conjunto de avaliação)
trilha: Claude (Engenharia)
data: 2026-10-23
publicacao: r3376-s2-cd895f3434-f0a4721f447f
---

# R3: conjunto ampliado e linha de base

Conjunto de avaliação tirado dos registros de pesquisa dos casos e a medida da busca atual do Flora-MCP sobre ele. Nada foi alterado no Flora-MCP (código, acervo ou publicação); a medida só lê a publicação corrente.

## Como o conjunto foi montado

1. **Fonte.** Os 185 registros `Controle/pesquisa-*.json` do vault (sem `.trash`, `_lixo`, evidências e fixtures). Cada acórdão com `id` do acervo e rótulo de uso vira um julgamento de relevância da tese a que serve: grau 2 para fundamento, apoio, citado ou selecionado; grau 1 para contraponto, analogia, reforço ou orientação; grau 0 para descartado depois de lido. Item sem tese (210) ou sem rótulo fica fora. Só entram acórdãos presentes na publicação; temas e súmulas ficam para outra medida.
2. **Perguntas.** Uma por caso e tese, com o mesmo acórdão em papéis diferentes no maior grau; teses do mesmo caso com relevante em comum se fundem. Resultado bruto: 82 perguntas de 19 casos (`agrupar.py`).
3. **Curadoria** (`curadoria.py`). Rótulos da mesma proposição fundidos; nove descartados por rótulo insuficiente ou ambíguo, com o motivo no conjunto. Para cada pergunta, três formulações redigidas só a partir do rótulo e da matéria do caso, sem ler as ementas esperadas: `proposicao` (a proposição que a decisão enuncia, sem fatos do caso, como o canon de pesquisa pede), `assessor` (termos de uma vez) e `curta` (dois ou três termos). A quarta, `rotulo`, é o rótulo gravado, sem edição.
4. **Conjunto final** (`montar.py`, `conjunto-r3.json`, schema `flora-avaliacao-2`): 54 perguntas de 17 casos, 135 acórdãos relevantes (123 do TJSC, 12 do STJ) e 16 descartados rotulados. O campo `esperados` mantém compatibilidade com `scripts/avaliar.py` do repositório.

## Linha de base (publicação r3376)

A ferramenta como o agente a chama (`pesquisar_jurisprudencia`, modo simples, sem filtro, seguindo o cursor até oito itens), `medir.py`:

| Formulação | hit@8 | recall@8 | nDCG@8 | MRR@100 | sem relevante nos 100 | ampliadas |
|---|---|---|---|---|---|---|
| proposição | 0,519 | 0,356 | 0,274 | 0,327 | 40,7% | 31 de 54 |
| assessor | 0,500 | 0,365 | 0,311 | 0,402 | 31,5% | 33 de 54 |
| curta | 0,556 | 0,388 | 0,264 | 0,288 | 25,9% | 0 de 54 |
| rótulo | 0,519 | 0,351 | 0,280 | 0,350 | 37,0% | 27 de 54 |

Intervalo de 95% do hit@8 por reamostragem: cerca de 13 pontos para cada lado (proposição de 0,37 a 0,65). Com 54 perguntas, uma pergunta vale 1,9 ponto; o conjunto distingue diferenças grandes, não ajustes finos.

- **Filtro pela Câmara.** Nas 49 perguntas com relevante da 10ª ou da 9ª Câmara, contando só os relevantes dessa Câmara, o hit@8 sem filtro é de 0,49 a 0,53 e, com `orgao` dessa Câmara, de 0,59 a 0,61 (MRR de 0,41 a 0,48). O passo "desta Câmara" do canon ganha cerca de dez pontos, e ainda assim erra em quatro de cada dez perguntas.
- **Teto.** Em 42 das 54 perguntas alguma das quatro formulações põe um relevante nos oito primeiros; em 6, nenhuma das três redigidas traz relevante nos cem primeiros.
- **Descartados.** Só um acórdão descartado apareceu nos oito primeiros, em todas as formulações: os 16 rótulos de grau 0 não bastam para medir precisão.
- **Rótulo.** Seis respostas vazias e duas recusas por mais de 30 termos (`consulta_invalida`).

## Compiladores candidatos (`scripts/avaliar.py` do repositório, sem alteração)

| Formulação | ferramenta | E sem palavras vazias | OU sem palavras vazias | OU com prefixo de 6 |
|---|---|---|---|---|
| proposição | 0,519 | 0,111 | **0,611** | 0,556 |
| assessor | 0,500 | 0,130 | 0,611 | **0,648** |
| curta | 0,556 | 0,556 | 0,556 | 0,556 |

Pergunta a pergunta, o OU sem palavras vazias nunca perde para a ferramenta nas formulações longas e ganha em 5 (proposição) e 6 (assessor); o OU com prefixo de 6 ganha em 8 e não perde nenhuma no assessor (teste do sinal, p de cerca de 0,01), mas na proposição ganha 7 e perde 5. Na curta, empate. Leitura: com consulta longa, exigir todos os termos (E, com as palavras vazias mantidas) acha poucos acórdãos que contêm tudo e os põe à frente dos pertinentes; o BM25 sobre OU já premia quem tem mais termos. Isto é medida, não decisão: a mudança do compilador é do repositório e segue a regra de adoção por ganho sem piora.

## Limites

- Os esperados são os acórdãos que um papel leu e marcou, não todos os relevantes do acervo: relevante nunca devolvido conta como não relevante, o que subestima todas as linhas por igual.
- Os registros vieram de buscas feitas com a própria ferramenta, o que favorece o lexical atual; um ordenador diferente pode achar relevantes que ninguém rotulou e ser punido por isso. Comparar candidatas pede leitura dos novos primeiros colocados (pooling), não só o número.
- 123 dos 135 relevantes são do TJSC e quase todos de família; o STJ tem 4 perguntas só dele, pouco para conclusão por tribunal.
- As formulações redigidas são de uma só pessoa; a de rótulo é enviesada, porque alguns rótulos descrevem o julgado achado.
- O conjunto de 14 perguntas da F6 (`avaliacao/conjunto.json`) continua valendo e mede outra coisa (citações das minutas); não foi fundido a este.

## Reproduzir

Com o `python` do vault para os três primeiros e o da `.venv` do Flora-MCP para a medida, todos somente leitura:

```
python agrupar.py <vault> <publicacao.sqlite> perguntas-brutas.json
python montar.py perguntas-brutas.json <publicacao_id> conjunto-r3.json
<Flora-MCP>\.venv\Scripts\python.exe medir.py <acervo> conjunto-r3.json resultado-r3.json
<Flora-MCP>\.venv\Scripts\python.exe <Flora-MCP>\scripts\avaliar.py --data-dir <acervo> --conjunto <conjunto sem a formulacao rotulo> --saida avaliar-repo-r3.json
```

A medida leva cerca de 13 minutos na máquina principal. Registro novo de pesquisa entra rodando de novo `agrupar.py`; pergunta bruta nova sem destino faz `montar.py` recusar até a curadoria decidir.

## Pergunta dupla

- **Conjunto e `medir.py`.** Substituem a medida de 14 perguntas como régua das fases R4 e R5, que a frente condiciona a "número antes e depois"; compensam porque quadruplicam as perguntas e trazem graus, filtro de Câmara e formulação pela proposição, que o canon de pesquisa usa e a F6 não media.
- **`agrupar.py`, `curadoria.py`, `montar.py`.** Ficam porque o conjunto cresce com cada caso novo, de graça, e a curadoria precisa ser refeita do disco; sem eles o conjunto vira arquivo congelado. Scripts exploratórios desta sessão não ficam.
