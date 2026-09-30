# Piloto Render Free

Codigo de origem baseado em f4e5584. Implantar pelo Dockerfile.render da branch
reforma/f13-render-leitor do repositorio publico ecvllzz/flora-mcp. O operador
autorizou expressamente publicar o snapshot de leitura no GitHub em 30/09/2026.
Nao incluir chave, acervo.sqlite, raw, configuracao local ou logs.

O pacote inclui publicacoes.json e release.json em deploy/render/data. O build
baixa o arquivo unico completo da GitHub Release acervo-r1508 e confere SHA-256
do comprimido e do banco antes de iniciar. A imagem resultante conserva a publicacao nas
reinicializacoes, sem depender de disco persistente. Nunca baixar 600 MB a cada
consulta. Publicacao posterior exige novo pacote e implantacao; cursores da geracao
anterior nao sao preservados neste primeiro piloto.

Configurar instancia Free, Dockerfile.render, health check /healthz e segredo
FLORA_MCP_API_KEY. PORT e RENDER_EXTERNAL_HOSTNAME sao fornecidos pelo Render.
Endpoint do Copilot: https://<hostname>/mcp. Credenciais fornecidas pelo criador.

O Free dorme apos 15 minutos ocioso. Testar inicializacao fria e uso das quatro
ferramentas antes de publicar CERFS. Nao simular trafego para evitar a suspensao.

A distribuicao usa asset de GitHub Release, com URL e hashes fixados no codigo.
Nova geracao exige novo asset, atualizacao dos metadados e nova implantacao.
