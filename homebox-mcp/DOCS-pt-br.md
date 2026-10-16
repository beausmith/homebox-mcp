# Home Assistant Add-on: Homebox MCP Server

## Sobre

Este addon expõe um servidor MCP (Model Context Protocol) para gerenciar o
inventário do Homebox. Ele permite que assistentes de IA (como Claude) listem,
criem, movam e busquem itens no seu inventário doméstico.

## Instalação

1. Adicione este repositório às suas fontes de add-ons do Home Assistant
2. Instale o add-on "Homebox MCP Server"
3. Configure as credenciais do Homebox
4. Inicie o add-on

## Configuração

### Opções

| Opção              | Descrição                                              | Obrigatório |
| ------------------ | ------------------------------------------------------ | ----------- |
| `homebox_url`      | URL do servidor Homebox                                | Sim         |
| `homebox_token`    | API Token do Homebox                                   | Sim         |
| `mcp_auth_enabled` | Ativar autenticação no endpoint MCP                    | Não         |
| `mcp_auth_token`   | Token para autenticação (gere na página do addon)      | Não*        |
| `log_level`        | Nível de log (trace, debug, info, warning, error)      | Não         |

*Obrigatório se `mcp_auth_enabled` estiver ativo

### Exemplo de Configuração

```yaml
homebox_url: "http://dac2a4a9-homebox:7745"
homebox_token: "SEU_TOKEN_API_HOMEBOX"
mcp_auth_enabled: false
mcp_auth_token: ""
log_level: "info"
```

### Criando o API Token do Homebox

1. Acesse o Homebox
2. Vá em **Profile** (ícone de usuário)
3. Clique em **API Tokens**
4. Clique em **Create Token**
5. Copie o token gerado

## Autenticação MCP (OAuth)

O addon suporta autenticação Bearer token opcional para proteger o endpoint MCP.

### Geração do Token

Ao ativar `mcp_auth_enabled: true`, é necessário gerar e configurar manualmente
um token seguro (o addon não gera nenhum token sozinho).

### Configuração Simplificada

1. **Primeiro**, teste a conexão com `mcp_auth_enabled: false`
2. **Depois** que tudo funcionar:
   - Acesse a página web do addon
   - Clique em "Gerar Token" e copie-o
   - Configure `mcp_auth_token` nas configurações do addon
   - Ative `mcp_auth_enabled: true`
   - Reinicie o addon

### Configuração Manual (Opcional)

Se preferir definir seu próprio token:

```yaml
homebox_url: "http://dac2a4a9-homebox:7745"
homebox_token: "SEU_TOKEN_API_HOMEBOX"
mcp_auth_enabled: true
mcp_auth_token: "MEU_TOKEN_PERSONALIZADO"  # opcional
log_level: "info"
```

### Configuração no Claude.ai

Quando a autenticação está ativada:

| Campo                        | Valor                                         |
| ---------------------------- | --------------------------------------------- |
| **URL do servidor**          | `https://seu-dominio.com/mcp`                 |
| **ID do Cliente OAuth**      | `mcp` (ou qualquer texto)                     |
| **Segredo do Cliente OAuth** | Cole o token gerado na página web do addon    |

**Importante**: O token vai no campo **Segredo do Cliente OAuth**, não no ID do Cliente.

### Como Configurar o Token

1. Acesse a **página web do addon** (clique no painel lateral "Homebox MCP")
2. Clique no botão **"🎲 Gerar Token"**
3. Clique em **"📋 Copiar"**
4. Nas **configurações do addon**:
   - Ative `mcp_auth_enabled`
   - Cole o token em `mcp_auth_token`
   - Clique em **Salvar**
5. No **Claude.ai**, cole o mesmo token no campo **"Segredo do Cliente OAuth"**

### Addon Homebox Recomendado

Este MCP foi desenvolvido para funcionar com o addon
[homebox-addon](https://github.com/Crafter-Y/homebox-addon).

[![Abra sua instância do Home Assistant e mostre o diálogo de adicionar repositório de add-on com uma URL de repositório específica pré-preenchida.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCrafter-Y%2Fhomebox-addon)

Para instalar:

1. Adicione o repositório: `https://github.com/Crafter-Y/homebox-addon`
2. Instale o addon **Homebox**
3. Inicie e configure seu inventário

### Encontrando a URL do Homebox

Se você tem o Homebox rodando como addon do Home Assistant:

1. Vá em **Configurações** → **Add-ons**
2. Clique no addon Homebox
3. Na aba "Informações", encontre o hostname interno
4. A URL será algo como: `http://dac2a4a9-homebox:7745`

Se o Homebox está rodando externamente:

- Use o IP ou hostname do servidor: `http://192.168.1.100:7745`

## Ferramentas MCP Disponíveis

### Localizações

- **homebox_list_locations**: Lista todas as localizações do inventário (lista simples)
- **homebox_get_location_tree**: Obtém a árvore completa de hierarquia de localizações
- **homebox_get_location**: Obtém detalhes de uma localização
- **homebox_create_location**: Cria uma nova localização
- **homebox_update_location**: Atualiza uma localização
- **homebox_delete_location**: Remove uma localização

### Itens

- **homebox_list_items**: Lista itens com filtros opcionais
- **homebox_get_item**: Obtém detalhes completos de um item
- **homebox_search**: Busca flexível por itens
- **homebox_create_item**: Cria um novo item
- **homebox_update_item**: Atualiza campos de um item
- **homebox_move_item**: Move um item para outra localização
- **homebox_add_item_attachment**: Anexa uma foto ou documento (manual,
  garantia, recibo) a um item (JPEG/PNG/GIF/WEBP/HEIC/PDF em base64,
  máximo 1 MB — baixo porque a IA que chama a ferramenta precisa gerar o
  arquivo inteiro como texto base64 para fazer a chamada)
- **homebox_add_item_attachment_from_url**: Anexa uma foto ou documento a
  um item baixando-o de uma URL (ex.: encontrada em uma busca na web) em
  vez de bytes em base64 fornecidos pelo usuário. Mesma validação de
  formato/tamanho do homebox_add_item_attachment; recusa URLs que
  resolvem para endereços privados/internos, inclusive por redirecionamentos
  (proteção contra SSRF)
- **homebox_delete_item**: Remove um item

### Labels

- **homebox_list_labels**: Lista todas as labels
- **homebox_create_label**: Cria uma nova label
- **homebox_update_label**: Atualiza uma label
- **homebox_delete_label**: Remove uma label

### Estatísticas

- **homebox_get_statistics**: Obtém estatísticas do inventário

## Conectando ao Servidor MCP

O servidor MCP expõe um endpoint Streamable HTTP na porta 8099, ainda
montado no caminho `/mcp` por compatibilidade com configurações existentes.

### Acesso Local (Rede Interna)

Na mesma rede do Home Assistant:

```
http://homeassistant.local:8099/mcp
```

Ou pelo IP:

```
http://192.168.X.X:8099/mcp
```

### Acesso Externo via Cloudflare Tunnel (Recomendado)

Para expor o MCP na internet de forma segura (necessário para Claude.ai web),
use o [addon Cloudflared](https://github.com/homeassistant-apps/app-cloudflared).

#### 1. Instalar o addon Cloudflared

1. Adicione o repositório ao Home Assistant:
   ```
   https://github.com/homeassistant-apps/app-cloudflared
   ```
2. Instale o addon **Cloudflared**

#### 2. Configurar no Cloudflare

1. Acesse [Cloudflare Zero Trust](https://one.dash.cloudflare.com/)
2. Vá em **Networks** → **Tunnels** → **Create a tunnel**
3. Escolha **Cloudflared** e dê um nome ao tunnel
4. Copie o token gerado

#### 3. Configurar o addon Cloudflared

Configure o addon para expor a porta 8099 do MCP:

```yaml
additional_hosts:
  - hostname: mcp.seudominio.com
    service: http://homeassistant:8099
```

Ou se não tiver domínio próprio, use um subdomínio gratuito do Cloudflare:

```yaml
additional_hosts:
  - hostname: mcp-homebox.seudominio.workers.dev
    service: http://homeassistant:8099
```

#### 4. URL Final para Claude.ai

Após configurado, use no Claude.ai:

```
https://mcp.seudominio.com/mcp
```

### Acesso via Ingress (alternativa)

O Ingress do HA requer autenticação por sessão, o que dificulta acesso externo.
Use apenas para acesso local via navegador:

```
https://seu-home-assistant/api/hassio_ingress/<ingress_token>/mcp
```

### Configurando no Claude Desktop

Adicione ao seu `claude_desktop_config.json`:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "homebox": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.seudominio.com/mcp"]
    }
  }
}
```

### Configurando no Claude.ai Web (Experimental)

1. Acesse as configurações de MCP no Claude.ai
2. Adicione um novo servidor MCP
3. Cole a URL: `https://mcp.seudominio.com/mcp`
4. OAuth: deixe desabilitado (não é necessário)

### Testando a Conexão

#### Via MCP Inspector (recomendado)

O [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) é a
ferramenta oficial de teste e fala corretamente o protocolo Streamable HTTP
(um `curl` simples não consegue completar esse handshake, veja abaixo):

```bash
# Teste local
npx @modelcontextprotocol/inspector --server-url http://homeassistant.local:8099/mcp --transport http

# Teste via Cloudflare Tunnel
npx @modelcontextprotocol/inspector --server-url https://mcp.seudominio.com/mcp --transport http
```

#### Via terminal (curl)

Um `curl` simples (GET) só confirma que o servidor está acessível, não que o
MCP funciona — ele não completa o handshake do protocolo, então espere um
`400 Bad Request` em vez de um stream de dados:

```bash
curl -i "http://homeassistant.local:8099/mcp"
```

`400 Bad Request` (em vez de erro de conexão ou timeout) significa que o
servidor está no ar e acessível. Se a autenticação estiver ativada, adicione
`-H "Authorization: Bearer SEU_TOKEN"` e espere o mesmo `400` (não um
`401 Unauthorized`) quando o token for aceito.

## Exemplos de Uso

### Listar todos os itens

```
Usuário: Liste todos os itens do meu inventário
Claude: [usa homebox_list_items]
```

### Criar um novo item

```
Usuário: Adicione um "Furadeira Bosch" na garagem
Claude: [usa homebox_list_locations para encontrar "Garagem"]
Claude: [usa homebox_create_item com name="Furadeira Bosch" e location_id=...]
```

### Mover um item

```
Usuário: Mova a furadeira para o escritório
Claude: [usa homebox_search para encontrar "furadeira"]
Claude: [usa homebox_list_locations para encontrar "Escritório"]
Claude: [usa homebox_move_item]
```

### Buscar itens

```
Usuário: Onde estão minhas ferramentas?
Claude: [usa homebox_search com query="ferramenta"]
```

## Solução de Problemas

### Erro de Autenticação

Verifique se:

- O token da API está correto
- O token tem as permissões necessárias
- O Homebox está acessível na URL configurada

### Erro de Conexão

Verifique se:

- A URL do Homebox está correta
- O addon Homebox está rodando
- Não há firewall bloqueando a conexão

### Logs

Para ver os logs do addon:

1. Vá em **Configurações** → **Add-ons** → **Homebox MCP Server**
2. Clique na aba "Log"

Ou via linha de comando:

```bash
ha addons logs homebox-mcp
```

## Suporte

Para problemas ou sugestões:

- Abra uma issue no [repositório GitHub](https://github.com/oangelo/homebox-mcp)
