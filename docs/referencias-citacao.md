# Identificação dos julgados nas consultas

Implementação e verificação: 29/09/2026. Responsável: sessão Codex
`01a0eda2-5880-7661-ba9b-c19ce9ac4050`. Pedido do operador: a referência deve
acompanhar o uso da jurisprudência por pessoas e agentes na redação de votos,
para permitir conferência humana.

## Comportamento

`pesquisar_jurisprudencia` entrega, em cada resultado, `relator`,
`classe_descricao`, `referencia`, `referencia_completa` e `referencia_pendencias`.
`obter_documento` entrega esses mesmos campos em `metadados`, em todos os blocos,
tanto para ementa quanto para espelho original. O texto e os hashes das ementas
continuam correspondendo exclusivamente ao conteúdo recebido da fonte.

A referência contém tribunal, classe, número, relatoria, órgão, julgamento e
publicação. A descrição da classe vem da fonte; quando ausente, usa-se a sigla
preservada. Não são deduzidos títulos, UF, gênero, diário ou datas. `j.` identifica
julgamento e `publ.` identifica publicação, sem transformar a data em D.E./DJe.
Publicação ambígua conserva a descrição original e gera pendência.

Ausências ficam explícitas na referência e em `referencia_pendencias`.
`referencia_completa` significa somente que os campos de identificação estão
presentes; não certifica autoridade, vigência, pertinência ou inteiro teor.

O servidor e as descrições das duas ferramentas orientam os agentes a apresentar
a referência junto da ementa ou citação usada em voto, conferir as pendências e
não inventar dados. A orientação é comum ao acesso stdio e HTTP.

## Origem e compatibilidade

`citation.py` lê a relatoria do espelho original correspondente ao **mesmo ID e
hash** do registro retornado: `ministroRelator` no STJ e `RELATOR`/`RELATORA` no
TJSC. A busca carrega essa versão junto dos resultados. Documentos já existentes
recebem os novos campos na leitura, sem migração, recoleta ou escrita no banco.
Não há associação de relatoria apenas por número de processo.

A descrição TJSC é extraída do campo PROCESSO (`/TJSC SIGLA - descrição`); no STJ,
de `descricaoClasse`. A resposta mantém os campos anteriores, filtros,
ordenação por data/relevância, cursores e identificação da revisão.

## Verificação

- 39 testes passaram: oito novos de identificação e 31 de armazenamento,
  consulta, relevância, protocolo stdio e HTTP. Aviso de depreciação do
  BlockingPortal no Starlette, sem falha.
- Ruff aprovado nos quatro arquivos de código/teste alterados ou adicionados.
- Conferência de todos os 7.477 registros na revisão 589: 5.021 STJ e 2.456 TJSC,
  todos com relatoria correspondente ao original e referência sem pendências.
- Processo MCP novo, com comando e ambiente registrados no Codex, entregou
  referências em busca e obtenção de documento real de cada tribunal. Texto e
  hash conferidos; banco com o mesmo SHA-256 antes e depois.
- A listagem legível desta conversa foi reexportada com referências completas e
  busca por relatoria. É uma cópia estática do acervo, não uma ferramenta MCP.

Evidência: [recibo](verificacao-referencias-20260929.json). Backup de fontes e
visualização, com tamanho e SHA-256 conferidos:
`C:\Users\Home\Documents\Flora\_Archive\backups\mcp-referencia-20260929-121828`.

## Carregamento nas conversas

A fonte local foi corrigida e um processo novo confirmou o comportamento.
A conexão nativa já aberta nesta conversa foi testada e ainda devolve a versão
anterior, sem os campos. Ela precisa ser reconectada/reiniciada para carregar o
código e as descrições atualizadas. Nenhuma conexão de outra conversa foi
interrompida e nenhuma nova versão de pacote foi publicada.

Até a reconexão, é possível recuperar a relatoria pelo `espelho_original`.
Disponibilizar campos e instruções no MCP não demonstra, por si, que todo agente
os incluirá em votos; essa observação depende do uso. Nenhum voto real ou skill
jurídica foi alterado nesta intervenção.

## Verificação nativa em nova conversa - 29/09/2026

Por autorização do operador, criada a conversa
`01a0edca-0317-7d70-8e65-4b49f2b16aa2` para verificar o carregamento nativo.
A busca por alimentos em TJSC e STJ, seguida de obter_documento, confirmou
os cinco campos de identificação e sua igualdade entre busca e leitura,
referencia_completa=true, pendências vazias e distinção das datas. IDs:
`TJSC:321790426352499139870548569765` e `STJ:1466726`.
A sessão fez somente chamadas nativas de leitura, sem iniciar servidor pelo terminal.

A conexão desta conversa de origem foi novamente consultada e ainda não entrega
os campos. Está demonstrado o carregamento na nova conversa, sem reiniciar o
aplicativo; isso não demonstra atualização das conexões antigas.
