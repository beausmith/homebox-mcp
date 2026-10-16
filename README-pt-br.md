# Homebox MCP Server - Home Assistant Add-on

> **Nota:** este arquivo documenta a versão upstream (oangelo/homebox-mcp) e não foi atualizado para este fork. Veja o [README em inglês](README.md) para as instruções atuais (endpoint `/mcp`, Cloudflare Tunnel, cabeçalho `authorization` no Claude.ai).

[![License][license-shield]](LICENSE.md)
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Servidor MCP (Model Context Protocol) para gerenciar o inventário do Homebox via assistentes de IA.

🇬🇧 [English Version](README.md)

## Pré-requisitos

Este addon foi desenvolvido para funcionar com o **Homebox** rodando no Home Assistant.

**Addon Homebox recomendado:** [homebox-addon](https://github.com/Crafter-Y/homebox-addon)

[![Abra sua instância do Home Assistant e mostre o diálogo de adicionar repositório de add-on com uma URL de repositório específica pré-preenchida.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCrafter-Y%2Fhomebox-addon)

<details>
<summary>Instalação manual</summary>

1. Adicione o repositório: `https://github.com/Crafter-Y/homebox-addon`
2. Instale o addon **Homebox**
3. Inicie e configure seu inventário

</details>

## Sobre

Este addon expõe um servidor MCP que permite que assistentes de IA (como Claude)
interajam com seu inventário do Homebox. Você pode:

- 📦 Listar, criar e gerenciar itens
- 📍 Organizar localizações hierárquicas
- 🏷️ Categorizar com labels
- 🔍 Buscar itens por nome ou descrição
- 📊 Obter estatísticas do inventário

## Instalação

### Instalação com um clique

[![Abra sua instância do Home Assistant e mostre a página do add-on Homebox MCP Server, pronta para instalar.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=homebox-mcp&repository_url=https%3A%2F%2Fgithub.com%2FMB901%2Fhomebox-mcp)

Isso adiciona o repositório e leva você direto à página do add-on — clique em **Instalar** por lá.

<details>
<summary>Instalação manual</summary>

1. No Home Assistant, vá em **Configurações** → **Add-ons** → **Loja de Add-ons**
2. Clique no menu (⋮) → **Repositórios**
3. Adicione: `https://github.com/MB901/homebox-mcp`
4. Clique em **Adicionar** → **Fechar**
5. Procure por "Homebox MCP Server" na loja
6. Clique em **Instalar**
7. Configure as credenciais do Homebox
8. Inicie o add-on

</details>

## Configuração

```yaml
homebox_url: "http://homeassistant.local:7745"
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

## Acesso Externo via Cloudflare Tunnel

Para usar com Claude.ai web ou acessar externamente, recomendamos usar o
[addon Cloudflared](https://github.com/homeassistant-apps/app-cloudflared)
para criar um tunnel seguro.

### Configurar Cloudflared

1. Instale o addon [Cloudflared](https://github.com/homeassistant-apps/app-cloudflared)
2. Configure o tunnel para expor a porta 8099:

```yaml
additional_hosts:
  - hostname: mcp.seudominio.com
    service: http://homeassistant:8099
```

3. Use a URL no Claude.ai: `https://mcp.seudominio.com/mcp`

### Acesso Local

Na rede local, acesse diretamente:

```
http://homeassistant.local:8099/mcp
```

## Autenticação MCP (Opcional)

O addon suporta autenticação Bearer token opcional para proteger o endpoint MCP.

### Configurar Token

1. Acesse a **página web do addon** (clique em "Homebox MCP" na barra lateral)
2. Clique no botão **"🎲 Gerar Token"**
3. Clique em **"📋 Copiar"**
4. Nas **configurações do addon**:
   - Ative `mcp_auth_enabled`
   - Cole o token em `mcp_auth_token`
   - Clique em **Salvar**

### Configuração no Claude.ai

| Campo                        | Valor                                           |
| ---------------------------- | ----------------------------------------------- |
| **URL do servidor**          | `https://seu-dominio.com/mcp`                   |
| **ID do Cliente OAuth**      | `mcp` (ou qualquer texto)                       |
| **Segredo do Cliente OAuth** | Cole o token gerado no addon                    |

## Uso com Claude

### Claude.ai Web (Experimental)

1. Acesse as configurações de MCP no Claude.ai
2. Adicione a URL: `https://mcp.seudominio.com/mcp`
3. Configure OAuth conforme mostrado acima (opcional mas recomendado)

### Claude Desktop

Adicione ao seu `claude_desktop_config.json`:

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

### Exemplos de Interação

```
Você: Liste todos os itens na garagem
Claude: [Lista itens filtrados por localização]

Você: Adicione uma "Furadeira Bosch" no armário de ferramentas
Claude: [Cria item na localização especificada]

Você: Onde está minha câmera?
Claude: [Busca e retorna localização do item]
```

## Ferramentas MCP

| Ferramenta                    | Descrição                              |
| ------------------------------ | ---------------------------------------- |
| `homebox_list_locations`      | Lista todas as localizações (lista simples) |
| `homebox_get_location_tree`   | Obtém a árvore completa de hierarquia   |
| `homebox_get_location`        | Detalhes da localização (pai/filhos)    |
| `homebox_create_location`     | Cria nova localização                   |
| `homebox_update_location`     | Atualiza localização                    |
| `homebox_delete_location`     | Remove localização                      |
| `homebox_list_items`          | Lista itens com filtros                 |
| `homebox_get_item`            | Detalhes completos do item              |
| `homebox_search`              | Busca por itens                         |
| `homebox_create_item`         | Cria novo item                          |
| `homebox_update_item`         | Atualiza campos do item                 |
| `homebox_move_item`           | Move item para outra localização        |
| `homebox_add_item_attachment` | Anexa uma foto ou documento (PDF, manual, garantia, recibo) a um item |
| `homebox_add_item_attachment_from_url` | Anexa uma foto ou documento baixando-o de uma URL |
| `homebox_delete_item`         | Remove item                             |
| `homebox_list_labels`         | Lista todas as labels                   |
| `homebox_create_label`        | Cria nova label                         |
| `homebox_update_label`        | Atualiza label                          |
| `homebox_delete_label`        | Remove label                            |
| `homebox_get_statistics`      | Estatísticas do inventário              |

[Documentação completa](homebox-mcp/DOCS-pt-br.md)

## Desenvolvimento Local

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
export HOMEBOX_URL="http://localhost:7745"
export HOMEBOX_TOKEN="seu-token-api"

# Executar servidor
cd homebox-mcp/app
python server.py

# Testar com MCP Inspector
npx @modelcontextprotocol/inspector --server-url http://localhost:8099/mcp --transport http
```

## Licença

MIT License - veja [LICENSE.md](LICENSE.md)

[license-shield]: https://img.shields.io/github/license/oangelo/homebox-mcp.svg
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
