# Coleta por lista e carga seletiva do STJ: amostra e ensaio (M3)

Execução em 04/11/2026, em branch `reforma/m3-coleta-por-lista`. Tudo sobre a cópia `Flora-MCP-sandbox-m3`, restaurada do backup `20261104-084229-233508-antes-retomada-tjsc`. O acervo real não foi escrito: depois do ensaio, ele tem zero recursos `stj-selecao` e zero execuções `STJ-numero`.

## Amostra: os arquivos localizam um número?

Sim. A conferência cruzou as fichas do STJ do gabinete com todos os arquivos que o catálogo oferecia (10 datasets de espelhos, 539 arquivos, 999 MB, 886.320 registros). As 4 fichas de súmula ficam fora, porque súmula não é número de processo. Os números da amostra não aparecem em nome de pasta de caso.

| Fichas de acórdão | Total | Localizadas | Com acórdão na mesma data da ficha | Não localizadas |
|---|---:|---:|---:|---:|
| Já no acervo pelo número | 45 | 45 | 44 | 0 |
| Fora do acervo | 106 | 100 | 98 | 6 |

- Dos 100 localizados fora do acervo, 51 estão no ZIP histórico e 49 só nos JSON mensais. O ZIP é necessário.
- Os 6 não localizados têm julgamento declarado entre 2015 e 2024. O mesmo número não aparece na classe da ficha. Três deles foram ao ensaio e saíram como não oferecidos. A causa não foi apurada: pode ser ausência na fonte ou número errado na ficha.
- Em 3 das fichas localizadas, 2 delas fora do acervo, nenhum acórdão tem a data da ficha, e uma das 3 traz `[VERIFICAR]` no lugar da data.
- Carregar os 106 números traria 134 acórdãos e guardaria 61 arquivos inteiros, 8 deles ZIP, com 422 MB de originais. Esse é o custo de guardar o arquivo inteiro (`RM-D27`).

O detalhe por ficha não entra no repositório. Fica fora dele, no arquivo `m3-amostra-fichas-stj.json` das notas desta frente.

O que a amostra mudou no código, com teste para cada ponto:

- **Classe sem separador.** `AgIntAREsp` e `EDclEAREsp`, como parte das fichas escreve, davam falso não oferecido em 5 números. Agora as classes incidentais no começo da palavra caem.
- **Arquivo quebrado na fonte.** `espelhos-de-acordaos-segunda-secao/20240229.json` tem 599 bytes declarados no catálogo, um espelho e uma chave a mais, e não abre como JSON. Sem tratamento, nenhuma leitura seria completa.
- **Classe com quebra de linha.** Arquivos antigos trazem `REsp\n`. O modelo passa a limpar a classe. Nenhum documento do STJ no acervo tinha esse defeito, então nada muda no que já está carregado.
- **Mesma chave, mais de um registro.** 6.784 de 818.765 chaves têm mais de um registro, quase todas de `REsp` (6.504) e `AREsp` (230). Nos exemplos examinados, são `EREsp` e `EAREsp` registrados depois com o número do recurso, e por isso ficam com ele. Uma só chave da amostra teve esse caso. O recibo traz o registro de cada acórdão, para conferência.
- **Mesmo id em mais de um arquivo.** 1.656 ids se repetem nos arquivos e 543 deles com diferença. Entre arquivos, vale a extração mais recente, como já valia. Dentro do ZIP, vale o membro mais novo, e o recibo aponta o conflito.

## Ensaio

| Recibo | O que testa | Resultado |
|---|---|---|
| `coleta-por-numero-m3-ensaio-20261104.json` | Lista mista em texto: 25 números do STJ, 1 número fictício do TJSC, 2 inválidos. Leitura completa, pausa de 2,5 s | `ok`, 1h40. 539 arquivos com hash, 1.047 MB lidos, 20 guardados (185 MB). 22 números selecionados, 30 notas de acórdão, 3 não oferecidos, 2 recusados, nenhuma falha, 1 arquivo ilegível que não afetou nenhum número |
| `coleta-por-numero-m3-ensaio-20261104-2.json` | Outro número no mesmo arquivo já guardado, com recorte | `ok`, 1 novo, 1 inalterado, 0 removido. Sem ausência declarada, porque houve recorte |
| `coleta-por-numero-m3-ensaio-20261104-3.json` | A mesma lista de novo | `ok`, nenhum arquivo gravado, revisão do banco inalterada |

Na lista principal, 2 dos acórdãos já estavam na coleta corrente e ficaram onde estavam. Entraram 27 documentos novos na cópia, de 84.374 para 84.401, todos do STJ. O número fictício do TJSC concluiu com zero documentos e consta em `nao_oferecidos`.

Depois da publicação (`r3646-s2-422d7bab33-80d7805e7c0b`, 8 min 49 s), conferi na cópia:

- **Originais.** Os 20 conferem com o hash do recibo, e 4 são ZIP.
- **Só o selecionado entra.** Esses arquivos somam 276.372 registros, dos quais 276.344 ficam fora de `documents` e da busca.
- **Selecionado.** Os 27 acórdãos novos têm linha no índice publicado; um deles vem em dois arquivos e soma 28 conferências. Um acórdão, conferido em detalhe, é achado por número, tem referência completa e abre por `obter_documento`. Na busca por texto com 8 termos, 21 das 28 conferências ficaram entre os 8 primeiros resultados; as outras 7 têm linha no índice, mas ficaram abaixo na ordenação, e não apurei por quê.
- **Não selecionado.** Um acórdão do mesmo ZIP não aparece por número nem por texto.
- **Cobertura.** `consultar_cobertura` mostra `stj-selecao` como STJ, com 20 recursos. A última coleta do STJ, que mede o atraso, continua sendo a de 09/10.

## Custo e limites

- Uma leitura completa baixa cerca de 1 GB e leva perto de duas horas com pausa de 2,5 s. O comando não guarda cache dos arquivos lidos.
- Um número conferido hoje como não oferecido pode aparecer depois, em lote novo. A prova vale para o catálogo do dia, e os hashes do recibo dizem qual era.
- O backup roda mesmo quando a lista não traz nada novo.
- A execução real não foi feita. Depende de ordem do operador, assim como a origem da lista (`RM-D07`, `RM-D29`).
