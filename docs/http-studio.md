# Transporte HTTP para o Studio

O adaptador HTTP é uma extensão do servidor stdio, que continua sendo o transporte principal. Ele expõe as mesmas quatro ferramentas de leitura (`pesquisar_jurisprudencia`, `pesquisar_precedentes`, `obter_documento` e `consultar_cobertura`, contrato em [CONTRATO.md](../CONTRATO.md)) sobre o mesmo acervo; não publica arquivos SQLite, coletor, APIs de escrita ou autos particulares. Não há hospedagem nem conexão com o Studio em funcionamento: a seção final lista o que falta.

## Executar

Defina `FLORA_MCP_API_KEY` no gerenciador de segredos do serviço: valor aleatório com ao menos 32 caracteres ASCII, sem espaços. Não grave a chave em código, instruções dos agentes, URL ou registro de evidência. Inicie, no ambiente Python já instalado do projeto:

```text
python -m flora_mcp.http_server --data-dir CAMINHO_DO_ACERVO --allowed-host HOST_PUBLICO --allowed-host 127.0.0.1:8765
```

O padrão escuta somente `127.0.0.1:8765` (`--host` e `--port` mudam isso); endpoint `/mcp`. `--allowed-host` é obrigatório e pode repetir-se; `--data-dir` e `--config` seguem a mesma precedência da CLI, e o acervo precisa existir. Configure um proxy HTTPS válido para encaminhar a esse processo, conservando `Host` e `x-flora-api-key`. Use host público exato, incluindo porta se não for a padrão. Conexão MCP é servidor a servidor; chamadas com Origin de navegador não são aceitas. Não desative a proteção de Host/Origin para resolver configuração do proxy.

Autenticação: API key no cabeçalho `x-flora-api-key`. Toda requisição HTTP exige a chave; credencial ausente/incorreta recebe 401. O processo usa Streamable HTTP sem estado de sessão e respostas JSON. Corpo máximo 64 KiB, suficiente para consultas e filtros; o limite não restringe tamanho da ementa retornada. Configure limite de taxa e controles operacionais no proxy. Banco em disco persistente local, coletor com sua trava própria e backup consistente. Não colocar banco ativo em pasta de sincronização.

## O que a implantação exige

Hospedagem contínua autorizada, domínio/TLS, configuração de segredo, volume persistente, reinício/monitoramento e um modo de rodar a coleta (`flora-mcp atualizar`) junto do acervo hospedado. A opção concreta depende da infraestrutura disponível ao operador. Este documento não cria nem contrata hospedagem.

No Studio novo: Ferramentas → adicionar MCP → endereço HTTPS `/mcp` → API key no cabeçalho acima. Confirmar descoberta das quatro ferramentas e testar cobertura, pesquisa e recuperação integral do componente em um caso sintético. Verificar políticas do ambiente antes de vincular o serviço. Não conceder acesso a autos por esse MCP de jurisprudência pública.

Referência: [MCP na experiência nova do Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/tools-add-mcp-server).
