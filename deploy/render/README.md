# Piloto Render Free

Codigo de origem fixado em f4e5584. Implantar pelo Dockerfile.render em repositorio
privado separado. Nao incluir chave, acervo.sqlite, raw, configuracao local ou logs.

O pacote inclui somente publicacoes.json e a geracao de leitura atual, comprimida
em partes abaixo de 50 MiB em deploy/render/data. O build recompõe o arquivo e
confere SHA-256 antes de iniciar. A imagem resultante conserva a publicacao nas
reinicializacoes, sem depender de disco persistente. Nunca baixar 600 MB a cada
consulta. Publicacao posterior exige novo pacote e implantacao; cursores da geracao
anterior nao sao preservados neste primeiro piloto.

Configurar instancia Free, Dockerfile.render, health check /healthz e segredo
FLORA_MCP_API_KEY. PORT e RENDER_EXTERNAL_HOSTNAME sao fornecidos pelo Render.
Endpoint do Copilot: https://<hostname>/mcp. Credenciais fornecidas pelo criador.

O Free dorme apos 15 minutos ocioso. Testar inicializacao fria e uso das quatro
ferramentas antes de publicar CERFS. Nao simular trafego para evitar a suspensao.

O pacote Git com snapshot particionado e uma solucao de piloto. Antes de rotinas
frequentes de atualizacao, migrar a distribuicao de snapshots para armazenamento
de artefatos, evitando crescimento permanente do historico Git.
