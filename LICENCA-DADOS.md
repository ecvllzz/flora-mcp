# Licença do acervo publicado

Esta nota vale para o acervo que o Flora-MCP publica (as gerações em `publicacoes/`, o arquivo `publicacao.sqlite.gz` das Releases e as exportações de `flora-mcp export`). O código do servidor e do coletor tem licença própria, MIT, em [LICENSE](LICENSE). Decisão `RM-D40` da revisão de 2026-11, registrada em [DECISOES.md](DECISOES.md).

## O que o acervo contém e de onde vem

| Camada | O que é | De onde vem | Condição |
|---|---|---|---|
| Texto das decisões | Ementas, espelhos de acórdãos, enunciados de súmulas, teses e questões de temas | Publicados pelos tribunais | Texto de decisão judicial não é objeto de proteção autoral (Lei n. 9.610/1998, art. 8º, IV) |
| Originais do STJ | Espelhos de acórdãos e catálogos de precedentes | [Dados abertos do STJ](https://dadosabertos.web.stj.jus.br/), que o catálogo declara sob licença `cc-by`, com atribuição ao STJ | CC BY, atribuição ao Superior Tribunal de Justiça |
| Originais do TJSC | Páginas de resultado do portal de jurisprudência e cartões de acórdão | [Portal de jurisprudência do TJSC](https://www.tjsc.jus.br/web/jurisprudencia) | Texto oficial do tribunal, preservado byte a byte com hash e data de coleta; o acervo não acrescenta camada editorial a ele |
| Seleção, recibos e publicação | O recorte (órgãos, períodos, temas e números coletados), a admissão de precedentes com evidência por campo, os recibos em `docs/recibos/`, os derivadores (seções, citações, cópias, catálogo) e a geração publicada | Trabalho do gabinete que mantém o Flora-MCP | CC BY 4.0, com a atribuição abaixo |

Os originais são preservados como recebidos, com SHA-256, URL e data de coleta em cada registro. O acervo é parcial e declarado como tal: nada nele afirma vigência material de precedente, superação ou atualidade editorial.

## Licença

A seleção, os recibos, os derivadores e a publicação estão sob a licença [Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/deed.pt-br). Você pode copiar, redistribuir, adaptar e usar o acervo para qualquer fim, inclusive comercial, desde que dê o crédito, indique a licença e marque as mudanças que fizer.

Os textos oficiais que o acervo preserva não ganham restrição nova por esta licença: continuam livres pelo art. 8º, IV, da Lei n. 9.610/1998 e, no caso dos dados abertos do STJ, sob a CC BY declarada pelo tribunal, que pede atribuição ao STJ.

## Atribuição sugerida

> Acervo do Flora-MCP (https://github.com/ecvllzz/flora-mcp), seleção, recibos e publicação pelo gabinete que mantém o projeto, CC BY 4.0. Acórdãos e precedentes do Superior Tribunal de Justiça (dados abertos, CC BY) e do Tribunal de Justiça de Santa Catarina (portal de jurisprudência). Publicação `<publicacao_id>`.

Ao citar um documento, use a `referencia` que a ferramenta devolve, que identifica tribunal, classe, número, relator, órgão e datas a partir do original, e exponha `referencia_pendencias` quando houver.

## O que esta nota não diz

- Não afirma que o acervo seja completo nem que represente a jurisprudência dos tribunais: só o que `consultar_cobertura` informa está carregado.
- Não cobre produtos editoriais dos tribunais (resenhas, pesquisas prontas, jurisprudência em teses), que não entram no acervo sem licença ou permissão localizada.
- Não substitui os termos de acesso de cada fonte: a coleta respeita os limites de acesso do portal e dos dados abertos, e redistribuir o acervo não dispensa quem o usa de respeitá-los ao coletar por conta própria.
