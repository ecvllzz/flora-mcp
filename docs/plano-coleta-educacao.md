# Plano de coleta: educação e reforço de família

Plano para aprovação do operador. Nada aqui foi coletado; cada etapa de execução sobre o acervo depende de autorização expressa, como pede o `AGENTS.md`.

## Por que

A revisão do corpus da publicação r3376, feita na avaliação R5 de busca híbrida (branch `reforma/r5-hibrido-kit`), mostrou:

- **Educação não tem nenhum precedente no acervo.** Todo o TJSC vem das Câmaras de Direito Civil e das Câmaras Especiais de Enfrentamento de Acervos, e todo o STJ da 3ª e da 4ª Turma e da 2ª Seção. Vaga em creche e pré-escola, transporte escolar, professor auxiliar ou acompanhante para aluno com deficiência e matrícula ficam sem nada para os agentes.
- **Família está presente, mas diluída.** No STJ, só cerca de 6% das ementas trata de família ou criança pelo cabeçalho; o resto é direito privado em geral. Esse resto não é inútil: 9 dos 12 acórdãos do STJ relevantes no conjunto de avaliação são de processo civil vindos de outras matérias (gratuidade, cumprimento de sentença, réu revel). Por isso o plano não corta o STJ por tema.
- **No TJSC, o tema separa bem, mas processo civil atravessa tudo.** Só 17% das 44.485 ementas do TJSC está no tema pelo cabeçalho (família, criança, educação, sucessões), e ali estão 104 dos 111 relevantes do TJSC no conjunto. Os 7 de fora são processo civil (gratuidade, honorários por equidade, execução de acordo, aluguel de imóvel comum), um deles um recurso não conhecido por intempestividade. Cortar por tema ou por não conhecimento perderia esses casos; marcar o tema e deixar o agente filtrar não perde.
- **Há ruído que não depende de tema.** No STJ, 12.424 ementas só aplicam óbice de admissibilidade, sem marca de tese; 1.334 embargos de declaração são rejeitados por falta de vício; 414 textos são cópias de outra ementa. No TJSC, 1.574 cópias e 1.238 embargos rejeitados. A R5 mede o efeito de tirar o ruído do STJ no recorte `stj_enxuto`.

## Princípio: precisão antes de volume

O risco de uma coleta nova é encher o acervo de acórdãos fora do tema, que disputam os primeiros lugares da busca com os que interessam. Por isso:

1. **Órgão competente e filtro de tema, juntos.** Nenhuma fonte nova entra pelo órgão inteiro. O órgão restringe a matéria, e um filtro de tema decide o que entra.
2. **Filtro conferível.** O filtro usa o que a fonte oficial traz: a legislação citada no espelho do STJ e os termos da ementa no TJSC. Não há classificação por modelo de linguagem, coerente com a coleta sem LLM.
3. **Amostra antes de publicar.** De cada lote, 50 ementas sorteadas são julgadas no tema ou fora dele; o lote só é publicado com 90% ou mais no tema. Abaixo disso, o filtro aperta e o lote é refeito.
4. **Ruído marcado; só a cópia sai.** Óbice sem tese e EDcl rejeitado recebem marca na ingestão e ficam até o número da R5. A cópia de texto sai da publicação (decisão do operador de 23/10), ficando a primeira ocorrência.
5. **Tema como marca, não como corte.** Cada ementa recebe o tema (família, criança e adolescente, educação, sucessões) a partir do cabeçalho e da legislação citada, e o agente pode filtrar por ele; nada sai do acervo por estar fora do tema.

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

- **STJ, 2024:** os mesmos datasets em uso (3ª e 4ª Turma, 2ª Seção), recursos de 2024, com o filtro de legislação citada: Código Civil arts. 1.511 a 1.783 e 1.784 a 2.027, Lei 5.478/1968, Lei 12.318/2010, ECA. Processo civil geral não entra por essa via, porque o acervo já tem volume suficiente dele.
- **TJSC, 2022 e 2023:** as dez Câmaras de Direito Civil, com o campo de pesquisa por subtema de família (alimentos, guarda, convivência, divórcio, união estável, partilha, curatela, adoção, alienação parental). O volume por câmara e ano é medido antes de coletar.

## Ordem e dependência da R5

1. Medir os volumes (catálogo do STJ e contagens do portal do TJSC por subtema), sem ingerir.
2. Aprovar os filtros com uma amostra de 50 por fonte.
3. Coletar educação no TJSC, depois educação no STJ, depois os temas do STF, depois o reforço de família.
4. Cada lote publicado vale na hora para a busca lexical. Os vetores dos documentos novos são gerados quando a R5 tiver escolhido o modelo, com o mesmo modelo e a mesma versão usados no corpus, de modo incremental.

## Decisões do operador em 23/10/2026

Entram no `DECISOES.md` com a implementação, uma por linha.

- **STJ de direito público só para educação filtrada.** 1ª e 2ª Turma e 1ª Seção entram apenas com o filtro de legislação citada e cabeçalho; o resto da Primeira Seção continua fora do recorte.
- **TJSC de direito público:** 1ª a 5ª Câmara de Direito Público e Grupo de Câmaras de Direito Público, só com filtro de tema; os Núcleos Públicos de Justiça 4.0 ficam fora.
- **STF por temas de repercussão geral,** com conferência individual, em fase de contrato novo (espécie `tema_rg`).
- **Cópias de texto saem da publicação já,** ficando a primeira ocorrência (1.574 no TJSC e 414 no STJ na r3376). Óbice sem tese e EDcl rejeitado ficam marcados até o número da R5.
- **Reforço de família:** STJ só de 2024 (o acervo já tem 2025 em diante); TJSC de 2022 e 2023.
- **Tema como marca filtrável** no TJSC e no STJ, sem corte por tema; campo novo no contrato, em fase própria.

## O que executa onde

O acervo real fica no notebook (`AGENTS.md`), e toda escrita nele segue a regra de lá: `collector.lock`, backup antes, ensaio numa cópia e recibo depois. A retirada das cópias é a primeira execução, por ser a menor e a única que não depende de coleta nova: ensaiar na cópia, conferir que a primeira ocorrência fica e publicar com recibo. As coletas novas vêm depois, na ordem acima, cada uma medida antes de ingerir.

## Executado

- **23/10/2026, cópias de texto.** Feito pela sessão do notebook, no branch `reforma/r6-copias-texto` (derivação `copias-texto-1`). Saíram 1.988 cópias em 937 grupos, e a publicação passou a r3376-s2-422d7bab33-9701325cf7ff, com 80.188 acórdãos (42.911 do TJSC e 37.277 do STJ). O ensaio no sandbox deu idêntico bit a bit, o backup é `20261023-214825-743033-antes-copias-texto` e o recibo, `docs/recibos/copias-texto-r6-20261023.json`. Mesclado em `main` (0155430).
- **24/10/2026, busca simples por relevância com OU** (contrato `flora-mcp-3.4`, branch `reforma/r7-busca-ou`, mesclado em `main` em 37bb93a, versão 0.5.0 em 3b6af3c). Os documentos novos desta coleta entram só na busca lexical, que é o OU; a R5 não adotou vetor.
- **24/10/2026, medida de volumes, sem ingerir** (sessão do notebook; recibo no vault, `_meta/engenharia/flora-mcp-recuperacao/coleta-educacao/medida-volumes-2026-10-24.json`). Foram 272 contagens do portal do TJSC, pesquisa na ementa, pausa de 2,5 s, sem erro nem verificação de acesso. As contagens conferem com o acervo: na 10ª Câmara, de fevereiro a setembro de 2026, "alimentos" dá 943 no portal e 910 no acervo, e "guarda", 532 e 519.
  - **Educação, de 2022 a 24/10/2026,** soma da 1ª à 5ª Câmara de Direito Público e do Grupo, por termo (os termos se sobrepõem): matrícula 987, educação especial 968, ensino 927, escola 338, creche 99, segundo professor 69, transporte escolar 68, professor auxiliar 48, educação inclusiva 20, pré-escola 14, vaga escolar 11, acompanhante terapêutico 1. "Matrícula", "ensino" e "educação especial" trazem falso positivo, e o filtro de ingestão é indispensável. O volume real deve ficar entre algumas centenas e pouco mais de mil acórdãos.
  - **Família em 2022** nas dez Câmaras de Direito Civil (a 8ª, a 9ª e a 10ª sem acórdão), de 41.936 no total: alimentos 654, guarda 443, partilha 386, adoção 382, união estável 261, divórcio 175, convivência 112, curatela 15, alienação parental 14.
  - **Família em 2023,** de 48.338 no total (a 8ª entra com 1.600): alimentos 749, adoção 591, guarda 517, partilha 450, união estável 298, divórcio 232, convivência 139, alienação parental 19, curatela 14.
  - Família de 2022 e 2023 é pouco volume, e a coleta por termo cabe em minutos por ano. Hipótese não verificada: os acórdãos de família em segredo de justiça daquela época não estavam no portal.
  - **STJ:** o catálogo de dados abertos não respondeu em nenhum dos seis conjuntos (tempo esgotado e erro 504), nem nos que funcionavam em 09/10; fica para nova tentativa. No acervo, a média é de 3.232 bytes por espelho.
- **Próximo passo:** a amostra de 50 por fonte e a mudança no coletor, cada uma com autorização do operador.
