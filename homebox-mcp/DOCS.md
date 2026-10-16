# Home Assistant Add-on: Homebox MCP Server

🇧🇷 [Versão em Português](DOCS-pt-br.md)

## About

This addon exposes an MCP (Model Context Protocol) server for managing
Homebox inventory. It allows AI assistants (like Claude) to list,
create, move, and search items in your home inventory.

## Installation

1. Add this repository to your Home Assistant add-on sources
2. Install the "Homebox MCP Server" add-on
3. Configure the Homebox credentials
4. Start the add-on

## Configuration

### Options

| Option             | Description                                       | Required |
| ------------------ | ------------------------------------------------- | -------- |
| `homebox_url`      | Homebox server URL                                | Yes      |
| `homebox_token`    | Homebox API Token                                 | Yes      |
| `mcp_auth_enabled` | Enable authentication on MCP endpoint             | No       |
| `mcp_auth_token`   | Token for authentication (generate in addon page) | No*      |
| `log_level`        | Log level (trace, debug, info, warning, error)    | No       |

*Required if `mcp_auth_enabled` is enabled

### Configuration Example

```yaml
homebox_url: "http://dac2a4a9-homebox:7745"
homebox_token: "YOUR_HOMEBOX_API_TOKEN"
mcp_auth_enabled: false
mcp_auth_token: ""
log_level: "info"
```

### Creating the Homebox API Token

1. Access Homebox
2. Go to **Profile** (user icon)
3. Click **API Tokens**
4. Click **Create Token**
5. Copy the generated token

## MCP Authentication (OAuth)

The addon supports optional Bearer token authentication to protect the MCP endpoint.

### Token Generation

When you enable `mcp_auth_enabled: true`, you need to generate and configure a secure token.

### Simplified Setup

1. **First**, test the connection with `mcp_auth_enabled: false`
2. **After** everything works:
   - Go to the addon web page
   - Click "Generate Token" and copy it
   - Configure `mcp_auth_token` in the addon settings
   - Enable `mcp_auth_enabled: true`
   - Restart the addon

### Manual Setup (Optional)

If you prefer to set your own token:

```yaml
homebox_url: "http://dac2a4a9-homebox:7745"
homebox_token: "YOUR_HOMEBOX_API_TOKEN"
mcp_auth_enabled: true
mcp_auth_token: "MY_CUSTOM_TOKEN"  # optional
log_level: "info"
```

### Claude.ai Configuration

Claude.ai custom connectors authenticate with OAuth or, in beta, with a fixed
**request header**. This addon uses a fixed Bearer token, so use the request
header route (Customize → Connectors → Add custom connector):

| Field                | Value                                                  |
| -------------------- | ------------------------------------------------------ |
| **MCP server URL**   | `https://your-domain.com/mcp`                          |
| **Transport**        | Streamable HTTP (under Advanced)                       |
| **Authentication**   | No sign-in                                             |
| **Request headers**  | `authorization` = `Bearer <token>` (include the space) |

**Important**: Claude sends the header value exactly as typed, so `Bearer` and
the token must be separated by a space. If the **Request headers** section is
missing from the dialog, your Claude.ai organization does not have the beta
yet; in that case run with `mcp_auth_enabled: false` behind a Cloudflare WAF
rule that only allows Anthropic's egress range (`160.79.104.0/21`).

### How to Configure the Token

1. Access the **addon web page** (click the "Homebox MCP" sidebar panel)
2. Click the **"🎲 Generate Token"** button
3. Click **"📋 Copy"**
4. In the **addon settings**:
   - Enable `mcp_auth_enabled`
   - Paste the token in `mcp_auth_token`
   - Click **Save**
5. Restart the addon, then enter the token in Claude.ai as a request header (table above)

### Recommended Homebox Addon

This fork is developed and tested against
[jscarrott/homebox-addon](https://github.com/jscarrott/homebox-addon) (Homebox v0.26.x, port 7745).
Upstream's original recommendation, [Crafter-Y/homebox-addon](https://github.com/Crafter-Y/homebox-addon),
should work as well.

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjscarrott%2Fhomebox-addon)

To install:

1. Add the repository: `https://github.com/jscarrott/homebox-addon`
2. Install the **Homebox Add-on**
3. Start and configure your inventory

### Finding the Homebox URL

If you have Homebox running as a Home Assistant addon:

1. Go to **Settings** → **Add-ons**
2. Click on the Homebox addon
3. In the "Info" tab, find the internal hostname
4. The URL will be something like: `http://dac2a4a9-homebox:7745`

If Homebox is running externally:

- Use the server IP or hostname: `http://192.168.1.100:7745`

## Available MCP Tools

### Locations

- **homebox_list_locations**: List all inventory locations (flat list)
- **homebox_get_location_tree**: Get the full location hierarchy tree
- **homebox_get_location**: Get location details
- **homebox_create_location**: Create a new location
- **homebox_update_location**: Update a location
- **homebox_delete_location**: Remove a location

### Items

- **homebox_list_items**: List items with optional filters
- **homebox_get_item**: Get complete item details
- **homebox_search**: Flexible search for items
- **homebox_create_item**: Create a new item
- **homebox_update_item**: Update item fields
- **homebox_move_item**: Move an item to another location
- **homebox_add_item_attachment**: Attach a photo or document (manual,
  warranty, receipt) to an item (base64-encoded JPEG/PNG/GIF/WEBP/HEIC/PDF,
  max 1 MB — low because the calling AI must generate the entire file as
  base64 text to make the call)
- **homebox_add_item_attachment_from_url**: Attach a photo or document to
  an item by downloading it from a URL (e.g. one found via web search)
  instead of base64 bytes the user supplied. Same format/size validation
  as homebox_add_item_attachment; refuses URLs resolving to
  private/internal addresses, including through redirects (SSRF guard)
- **homebox_delete_item**: Remove an item

### Labels

- **homebox_list_labels**: List all labels
- **homebox_create_label**: Create a new label
- **homebox_update_label**: Update a label
- **homebox_delete_label**: Remove a label

### Statistics

- **homebox_get_statistics**: Get inventory statistics

## Connecting to the MCP Server

The MCP server exposes a Streamable HTTP endpoint on port 8099 at `/mcp`.
The previous `/sse` path still works as an alias, so older client configs
need no change (but Claude.ai warns about SSE for URLs ending in `/sse`,
so prefer `/mcp` there).

### Local Access (Internal Network)

On the same network as Home Assistant:

```
http://homeassistant.local:8099/mcp
```

Or by IP:

```
http://192.168.X.X:8099/mcp
```

### External Access via Cloudflare Tunnel (Recommended)

Claude.ai connects from Anthropic's cloud, so the endpoint must be reachable from
the internet. Nabu Casa only proxies Home Assistant itself, and the Tailscale
addon's Funnel cannot share an addon port, so use the
[Cloudflared addon](https://github.com/homeassistant-apps/app-cloudflared)
(requires a domain whose DNS is on Cloudflare). Home Assistant itself stays
unexposed.

#### 1. Install the Cloudflared addon

Add the repository `https://github.com/homeassistant-apps/app-cloudflared` and
install **Cloudflared**.

#### 2. Configure the Cloudflared addon

Leave `external_hostname` empty and expose only this addon, using its internal
hostname from the **Info** tab (`<repository-id>-homebox-mcp`):

```yaml
external_hostname: ""
additional_hosts:
  - hostname: homebox-mcp.yourdomain.com
    service: http://ee45feb1-homebox-mcp:8099
```

#### 3. Authorize the tunnel

Start Cloudflared and open its log. Open the printed
`https://dash.cloudflare.com/argotunnel?...` link, sign in to the Cloudflare
account that owns the domain, pick the domain and click **Authorize**. The addon
then creates the tunnel and the DNS record itself. If no domain is offered,
re-open the link while signed in to the right account.

#### 4. Restrict the hostname to Anthropic (recommended)

In the Cloudflare dashboard, inside the zone: **Security → Security rules →
Create rule**, expression
`(http.host eq "homebox-mcp.yourdomain.com" and not ip.src in {160.79.104.0/21})`,
action **Block**. Afterwards the public URL answers 403 from everywhere except
Anthropic's egress range, including your own LAN - test with the internal URL.

#### 5. Final URL for Claude.ai

```
https://homebox-mcp.yourdomain.com/mcp
```

### Ingress Access (Alternative)

HA Ingress requires session authentication, which makes external access difficult.
Use only for local browser access:

```
https://your-home-assistant/api/hassio_ingress/<ingress_token>/mcp
```

### Configuring in Claude Desktop

Add to your `claude_desktop_config.json`:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "homebox": {
      "command": "npx",
      "args": ["mcp-remote", "https://homebox-mcp.yourdomain.com/mcp",
               "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

### Configuring in Claude.ai Web

Customize → Connectors → Add custom connector, as in the
[Claude.ai Configuration](#claudeai-configuration) table above: URL
`https://homebox-mcp.yourdomain.com/mcp`, No sign-in, request header
`authorization: Bearer <token>`.

### Testing the Connection

#### Via MCP Inspector (recommended)

The [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) is
the official testing tool and correctly speaks the Streamable HTTP handshake
(a raw `curl` request can't complete it, see below):

```bash
# Local test
npx @modelcontextprotocol/inspector --server-url http://homeassistant.local:8099/mcp --transport http

# Test via Cloudflare Tunnel
npx @modelcontextprotocol/inspector --server-url https://homebox-mcp.yourdomain.com/mcp --transport http
```

#### Via terminal (curl)

Send an MCP `initialize` request (a plain GET cannot complete the Streamable
HTTP handshake):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://homeassistant.local:8099/mcp \
  -H "Authorization: Bearer YOUR_MCP_TOKEN" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
```

`200` = server up and token accepted; `401` = token missing or wrong;
`403` from the public URL = blocked by the Cloudflare rule (expected from
outside Anthropic's range).

## Usage Examples

### List all items

```
User: List all items in my inventory
Claude: [uses homebox_list_items]
```

### Create a new item

```
User: Add a "Bosch Drill" to the garage
Claude: [uses homebox_list_locations to find "Garage"]
Claude: [uses homebox_create_item with name="Bosch Drill" and location_id=...]
```

### Move an item

```
User: Move the drill to the office
Claude: [uses homebox_search to find "drill"]
Claude: [uses homebox_list_locations to find "Office"]
Claude: [uses homebox_move_item]
```

### Search for items

```
User: Where are my tools?
Claude: [uses homebox_search with query="tool"]
```

## Troubleshooting

### Authentication Error

Check if:

- The API token is correct
- The token has the necessary permissions
- Homebox is accessible at the configured URL

### Connection Error

Check if:

- The Homebox URL is correct
- The Homebox addon is running
- There's no firewall blocking the connection

### Logs

To view addon logs:

1. Go to **Settings** → **Add-ons** → **Homebox MCP Server**
2. Click the "Log" tab

Or via command line:

```bash
ha addons logs homebox-mcp
```

## Support

For issues or suggestions:

- Open an issue on the [GitHub repository](https://github.com/beausmith/homebox-mcp)
