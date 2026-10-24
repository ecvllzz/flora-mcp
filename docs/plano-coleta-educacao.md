# Plano de coleta: educação e reforço de família

Plano para aprovação do operador. Nada aqui foi coletado; cada etapa de execução sobre o acervo depende de autorização expressa, como pede o `AGENTS.md`.

## Por que

A revisão do corpus da publicação r3376, feita na avaliação R5 de busca híbrida (branch `reforma/r5-hibrido-kit`), mostrou:

- **Educação não tem nenhum precedente no acervo.** Todo o TJSC vem das Câmaras de Direito Civil e das Câmaras Especiais de Enfrentamento de Acervos, e todo o STJ da 3ª e da 4ª Turma e da 2ª Seção. Vaga em creche e pré-escola, transporte escolar, professor auxiliar ou acompanhante para aluno com deficiência e matrícula ficam sem nada para os agentes.
- **Família está presente, mas diluída.** No STJ, só cerca de 6% das ementas trata de família ou criança pelo cabeçalho; o resto é direito privado em geral. Esse resto não é inútil: 9 dos 12 acórdãos do STJ relevantes no conjunto de avaliação são de processo civil vindos de outras matérias (gratuidade, cumprimento de sentença, réu revel). Por isso o plano não corta o STJ por tema.
- **Há ruído que não depende de tema.** No STJ, 12.424 ementas só aplicam óbice de admissibilidade, sem marca de tese; 1.334 embargos de declaração são rejeitados por falta de vício; 414 textos são cópias de outra ementa. A R5 mede o efeito de tirá-los no recorte `stj_enxuto`.

## Princípio: precisão antes de volume

O risco de uma coleta nova é encher o acervo de acórdãos fora do tema, que disputam os primeiros lugares da busca com os que interessam. Por isso:

1. **Órgão competente e filtro de tema, juntos.** Nenhuma fonte nova entra pelo órgão inteiro. O órgão restringe a matéria, e um filtro de tema decide o que entra.
2. **Filtro conferível.** O filtro usa o que a fonte oficial traz: a legislação citada no espelho do STJ e os termos da ementa no TJSC. Não há classificação por modelo de linguagem, coerente com a coleta sem LLM.
3. **Amostra antes de publicar.** De cada lote, 50 ementas sorteadas são julgadas no tema ou fora dele; o lote só é publicado com 90% ou mais no tema. Abaixo disso, o filtro aperta e o lote é refeito.
4. **Ruído marcado, não apagado.** Óbice sem tese, EDcl rejeitado e cópia recebem marca na ingestão. Se tiram ou não esses documentos da publicação, quem decide é o operador, com o número da R5 na mão.

## Fontes, por prioridade

### 1. Educação no TJSC

- **Órgãos** (nome exato do filtro `selOrgao[]`, lido do formulário em `tests/fixtures/tjsc/formulario-pesquisa.html`): 1ª a 5ª Câmara de Direito Público e Grupo de Câmaras de Direito Público. Os Núcleos Públicos de Justiça 4.0 ficam de fora na primeira etapa.
- **Filtro na consulta:** o campo de pesquisa do portal, um subtema por vez: creche; pré-escola; transporte escolar; professor auxiliar, segundo professor ou acompanhante terapêutico em escola; matrícula; vaga escolar; educação especial ou inclusiva; ensino; escola.
- **Filtro na ingestão:** o cabeçalho da ementa precisa trazer termo de educação ou citar ECA (Lei 8.069/1990, arts. 53 a 59 e 208), LDB (Lei 9.394/1996), CF arts. 205 a 214 ou Lei 13.146/2015 (arts. 27 e 28). Isso descarta o acórdão que só menciona "escola" de passagem.
- **Ritmo:** o mesmo do coletor atual (pausa de 2,5 s, sem paralelo), pelas regras de 30/09 e 09/10 do `DECISOES.md`.
- **O que muda no código:** a lista fechada `ORGAOS` em `src/flora_mcp/tjsc_orgaos.py` ganha os seis órgãos de direito público, com dataset próprio (`tjsc-1-camara-de-direito-publico` e afins), e a coleta por órgão passa a aceitar o termo de pesquisa. A coleta por número de processo (R1) já existe e pode completar o que o gabinete cita.

### 2. Educação no STJ

- **Fonte:** dados abertos do STJ, datasets `espelhos-de-acordaos-primeira-turma`, `espelhos-de-acordaos-segunda-turma` e `espelhos-de-acordaos-primeira-secao`. O recurso mensal traz a produção inteira do órgão, sem filtro na fonte: o arquivo é baixado e só o espelho que passa no filtro é ingerido.
- **Filtro na ingestão:** `referenciasLegislativas` do espelho cita ECA, LDB, CF arts. 205 a 214 ou 227, Lei 13.146/2015 ou Lei 12.764/2012 (acompanhante especializado), e o cabeçalho da ementa traz termo de educação. Tributário, previdenciário e servidor público sem relação com o ensino ficam de fora mesmo citando a CF.
- **Decisão necessária:** o `DECISOES.md` de 30/09 deixa a Primeira Seção do STJ fora do recorte civil para temas e súmulas. A educação pede uma exceção por matéria, só para o que passar no filtro.
- **Volume:** a medir no catálogo, que não respondeu em 23/10 (tempo esgotado e erro 504). Como referência, a 3ª e a 4ª Turma e a 2ª Seção somam 37.691 espelhos desde 2025; com o filtro de educação, a expectativa é de algumas centenas a poucos milhares, mas o número sai da medida, não da estimativa.

### 3. STF: temas de repercussão geral

- **Por precedente, não por acórdão.** O STF entra pelo sistema de precedentes que já existe (`src/flora_mcp/precedent_sources/`), com tema, tese e julgados relacionados, por conferência individual como os do TJSC. É pouco volume e alto valor: os temas fixam o dever estatal que o TJSC aplica.
- **Exemplos a conferir na fonte:** Tema 548 (creche e pré-escola), Tema 822 (ensino domiciliar). O levantamento completo sai do portal de repercussão geral do STF, filtrando educação, criança e adolescente e família.
- **O que muda:** espécie `tema_rg` para o STF no contrato de precedentes, numa fase que declare contrato novo; a admissão segue por conferência.

### 4. Reforço de família

- **STJ, anos anteriores a 2025:** os mesmos datasets em uso (3ª e 4ª Turma, 2ª Seção), com o filtro de legislação citada: Código Civil arts. 1.511 a 1.783 e 1.784 a 2.027, Lei 5.478/1968, Lei 12.318/2010, ECA. Processo civil geral não entra por essa via, porque o acervo já tem volume suficiente dele.
- **TJSC, antes de 2024:** as dez Câmaras de Direito Civil, com o campo de pesquisa por subtema de família (alimentos, guarda, convivência, divórcio, união estável, partilha, curatela, adoção, alienação parental). O volume por câmara e ano é medido antes, para o operador escolher a profundidade.

## Ordem e dependência da R5

1. Medir os volumes (catálogo do STJ e contagens do portal do TJSC por subtema), sem ingerir.
2. Aprovar os filtros com uma amostra de 50 por fonte.
3. Coletar educação no TJSC, depois educação no STJ, depois os temas do STF, depois o reforço de família.
4. Cada lote publicado vale na hora para a busca lexical. Os vetores dos documentos novos são gerados quando a R5 tiver escolhido o modelo, com o mesmo modelo e a mesma versão usados no corpus, de modo incremental.

## Decisões pedidas ao operador

- Exceção da Primeira Seção e da 1ª e 2ª Turma do STJ, só para educação filtrada.
- Os seis órgãos de direito público do TJSC na lista do coletor, só com filtro de tema.
- O STF por temas de repercussão geral, em fase de contrato novo.
- O destino do ruído marcado (óbice sem tese, EDcl rejeitado, cópia): manter, rebaixar ou tirar da publicação, depois do número da R5.
- A profundidade do reforço de família no STJ (anos) e no TJSC (anos e câmaras).
