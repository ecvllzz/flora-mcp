# Precedentes e contrato Flora-MCP 2

Implementação em andamento em 29/09/2026. A ativação e a carga reais devem ser comprovadas pelo recibo da execução; a existência deste contrato não as demonstra.

## Interfaces de leitura

Os três nomes MCP permanecem. `pesquisar_jurisprudencia` sem novos parâmetros continua retornando três acórdãos com ementas completas. `limite=null` escolhe três no modo completo e oito na triagem; o máximo completo continua cinco.

- Temas/súmulas: `colecao="precedentes"`, `campo="todos"` ou componente explícito; filtros `tribunal`, `orgao`, `especie`, `numero`, datas de publicação.
- Componentes: `enunciado`, `questao_submetida`, `tese_firmada`, `modulacao`, `suspensao`. Uma ementa pertence ao julgado associado, nunca ao campo de tese por inferência.
- `detalhe="triagem"`: referência e identidade preservadas, trecho literal com offset, hash e indicação de parcialidade. Orçamento de 8 KiB do objeto JSON compacto, separado do envelope MCP.
- `modo_busca="avancado"`: frases, AND/OR, parênteses e prefixo*. O padrão simples conserva AND entre palavras. Não amplia a consulta para preencher resultados.
- `obter_documento`: ID e componente explícito; `hash_conteudo` e `publicacao_id` opcionais para conferir a versão. Componentes inexistentes geram erro com alternativas. Retiradas prevalecem sobre versões e cursores antigos.
- Ementas podem expor `secao:<nome>` quando títulos inequívocos delimitam a seção. Metadados incluem offsets Unicode no original e hash; `tese_na_ementa` não é tese qualificada.
- `consultar_cobertura`: padrão `resumo`, com grupos e catálogos inteiros, recursos por dataset/status, primeiro/último lote pendente e execuções sem eventos/janelas; preserva motivo, falhas e totais antes/depois registrados. `detalhe="completo"` (alias `legado`) conserva o conteúdo integral anterior. `recursos` aceita filtros opcionais `tribunal`/`dataset`; `recursos` e `execucoes` usam cursor, limite padrão 20 e máximo 50 (prefira 1 para execuções grandes). Filtros não são aceitos nos outros modos para evitar ignorá-los silenciosamente. Verificação no acervo em 29/09: 9.786 caracteres no texto efetivamente enviado pelo MCP, abaixo de 10 mil; o tamanho futuro depende dos diagnósticos registrados. `scripts/verify_coverage.py` repete essa verificação sem escrever no banco.
- Cursores são opacos. Reenviar os mesmos filtros e limite. Guardar o `publicacao_id` da pesquisa para obter o documento na mesma geração.
- Erros MCP mantêm objeto `{status:"erro",codigo,mensagem}`. As representações de texto e `structuredContent` do SDK são preservadas.

## Pacote de entrada administrativo: flora-precedentes-1

Objeto JSON com `schema="flora-precedentes-1"` e lista `registros`. Nenhuma ferramenta MCP importa dados. Cada registro contém:

| Campo | Contrato |
|---|---|
| tribunal | STJ, STF ou TJSC |
| especie | STJ: tema_repetitivo, iac, sumula; STF: tema_repercussao_geral, sumula_vinculante, sumula; TJSC: sumula |
| numero | Número positivo em string, sem prefixo ou zeros iniciais |
| orgao | Texto da fonte. TJSC restrito ao Grupo de Câmaras de Direito Civil |
| materia | civil ou processual_civil; outras/ausentes ficam pendentes |
| data_publicacao | AAAA-MM-DD com evidência; ausente impede admissão |
| tipo_publicacao | enunciado, acordao_merito ou acordao_embargos; tema/IAC exige identificação explícita. A referência distingue a publicação de embargos da publicação do mérito |
| situacao | vigente, cancelado, revogado, superado, suspenso, pendente ou desconhecido |
| pendencias | Lista; recurso/revisão pendente, conflito e incertezas concretas impedem admissão |
| componentes | Objeto de textos literais, usando apenas os componentes acima |
| fontes | Lista de `{url,sha256,arquivo,coletado_em}`; HTTPS oficial do tribunal, original relativo ao pacote, SHA-256 dos bytes, coleta ISO com fuso |
| evidencias | Objeto por chave, cada valor `{fonte_sha256,trecho,localizador}` |
| conferencia | `{evidencias_conferidas:true,responsavel,data}` somente após conferência efetiva |
| julgados_relacionados | Lista opcional de `{id,referencia,evidencia_vinculo}`; ementa opcional com `evidencia_ementa` |

Chaves obrigatórias para admissão em `evidencias`: `situacao`, `publicacao`, `materia` e `componente:<nome>` para cada componente. `evidencia_vinculo` e `evidencia_ementa` referenciam chaves adicionais desse mesmo objeto. Preservar textos literais e localizadores; o importador verifica estrutura, domínio, bytes e hashes, mas não faz juízo semântico autônomo sobre a evidência. A conferência deve validar que os trechos sustentam os campos. Um coletor não deve marcar essa conferência apenas porque a página respondeu HTTP 200.

Súmula exige enunciado; tema/IAC exige tese firmada para admissão. Ementa de paradigma ausente é limitação, não texto a fabricar. Identidades são geradas: `STJ:tema_repetitivo:123`, `STF:sumula_vinculante:25`, `TJSC:sumula:GCDC:1`. Exemplos ilustram formato, não admissão jurídica.

O pacote inteiro é validado antes de alterar o banco. A simulação é o padrão. A importação preserva versões e eventos administrativos, remove imediatamente do índice os itens excluídos/pendentes e é idempotente para o mesmo conteúdo. Não encontrar um registro numa listagem não gera retirada automática.

## Publicações e Microsoft

Banco de trabalho local com histórico; leitura por gerações SQLite novas, journal DELETE, hash, integridade e troca atômica de `publicacoes.json`. Três gerações permanecem acessíveis. O leitor só usa `immutable=1` para os arquivos fechados e conferidos. Não sobrescreve arquivo aberto no Windows. A identidade do diretório do acervo permanece estável.

Exportação canônica: Markdown completo e catálogo JSON por publicação, separado da Biblioteca curada. SharePoint/OneDrive transportam o pacote documental. SQLite ativo permanece fora da sincronização. A recuperação real de Markdown e a aplicação de retiradas no canal publicado exigem aceite da frente Copilot; não se presume indexação automática.

## Operação administrativa

No ambiente Python do produto:

```text
python -m flora_mcp.cli migrate
python -m flora_mcp.cli import-precedents caminho/pacote.json
python -m flora_mcp.cli import-precedents caminho/pacote.json --apply
python -m flora_mcp.cli publish
python -m flora_mcp.cli export caminho/exportacao
python scripts/verify_publication.py
```

`migrate` e importação com `--apply` fazem backup consistente antes de alterar o banco. `publish` valida também os originais referenciados. Após ativar o manifesto, CLI de coleta/importação, `update_once.py` e retomada TJSC publicam nova geração ao fim da operação. `update_once.py --precedents-package` aceita o pacote conferido; não equivale ainda a descoberta automática de todos os catálogos oficiais. Nenhum agendamento foi criado.

O catálogo exportado tem `schema=flora-catalogo-1`, `publicacao_id`, `registros` e `retirados`. Cada entrada contém ID, arquivo, SHA-256 do Markdown, versão do registro, tribunal/espécie, referência, situação e hashes por componente. Consumidores devem recuperar apenas entradas atuais e comparar o hash do arquivo. Falha ou propagação incompleta da sincronização não autoriza usar cópia divergente. Edição humana de arquivo gerado é detectada antes da atualização; arquivos não gerenciados não são sobrescritos.
