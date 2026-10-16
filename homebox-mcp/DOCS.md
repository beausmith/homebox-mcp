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

When authentication is enabled:

| Field                    | Value                                       |
| ------------------------ | ------------------------------------------- |
| **Server URL**           | `https://your-domain.com/sse`               |
| **OAuth Client ID**      | `mcp` (or any text)                         |
| **OAuth Client Secret**  | Paste the token from the addon dashboard    |

**Important**: The token goes in the **OAuth Client Secret** field, not the Client ID.

### How to Configure the Token

1. Access the **addon web page** (click the "Homebox MCP" sidebar panel)
2. Click the **"🎲 Generate Token"** button
3. Click **"📋 Copy"**
4. In the **addon settings**:
   - Enable `mcp_auth_enabled`
   - Paste the token in `mcp_auth_token`
   - Click **Save**
5. In **Claude.ai**, paste the same token in the **"OAuth Client Secret"** field

### Recommended Homebox Addon

This MCP was developed to work with the
[homebox-addon](https://github.com/Crafter-Y/homebox-addon).

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCrafter-Y%2Fhomebox-addon)

To install:

1. Add the repository: `https://github.com/Crafter-Y/homebox-addon`
2. Install the **Homebox** addon
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

The MCP server exposes a Streamable HTTP endpoint on port 8099, still mounted
at the `/sse` path for backward compatibility with existing client configs.

### Local Access (Internal Network)

On the same network as Home Assistant:

```
http://homeassistant.local:8099/sse
```

Or by IP:

```
http://192.168.X.X:8099/sse
```

### External Access via Cloudflare Tunnel (Recommended)

To expose the MCP securely on the internet (required for Claude.ai web),
use the [Cloudflared addon](https://github.com/homeassistant-apps/app-cloudflared).

#### 1. Install the Cloudflared addon

1. Add the repository to Home Assistant:
   ```
   https://github.com/homeassistant-apps/app-cloudflared
   ```
2. Install the **Cloudflared** addon

#### 2. Configure in Cloudflare

1. Access [Cloudflare Zero Trust](https://one.dash.cloudflare.com/)
2. Go to **Networks** → **Tunnels** → **Create a tunnel**
3. Choose **Cloudflared** and name the tunnel
4. Copy the generated token

#### 3. Configure the Cloudflared addon

Configure the addon to expose MCP port 8099:

```yaml
additional_hosts:
  - hostname: mcp.yourdomain.com
    service: http://homeassistant:8099
```

Or if you don't have your own domain, use a free Cloudflare subdomain:

```yaml
additional_hosts:
  - hostname: mcp-homebox.yourdomain.workers.dev
    service: http://homeassistant:8099
```

#### 4. Final URL for Claude.ai

After configured, use in Claude.ai:

```
https://mcp.yourdomain.com/sse
```

### Ingress Access (Alternative)

HA Ingress requires session authentication, which makes external access difficult.
Use only for local browser access:

```
https://your-home-assistant/api/hassio_ingress/<ingress_token>/sse
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
      "args": ["mcp-remote", "https://mcp.yourdomain.com/sse"]
    }
  }
}
```

### Configuring in Claude.ai Web (Experimental)

1. Access the MCP settings in Claude.ai
2. Add a new MCP server
3. Paste the URL: `https://mcp.yourdomain.com/sse`
4. OAuth: Configure Client ID as `mcp` and Client Secret as your token

### Testing the Connection

#### Via MCP Inspector (recommended)

The [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) is
the official testing tool and correctly speaks the Streamable HTTP handshake
(a raw `curl` request can't complete it, see below):

```bash
# Local test
npx @modelcontextprotocol/inspector --server-url http://homeassistant.local:8099/sse --transport http

# Test via Cloudflare Tunnel
npx @modelcontextprotocol/inspector --server-url https://mcp.yourdomain.com/sse --transport http
```

#### Via terminal (curl)

A plain `curl` GET can only confirm the server is reachable, not that MCP
itself works — it can't complete the protocol handshake, so expect a
`400 Bad Request` rather than a stream of data:

```bash
curl -i "http://homeassistant.local:8099/sse"
```

`400 Bad Request` (instead of a connection error or timeout) means the
server is up and reachable. If authentication is enabled, add
`-H "Authorization: Bearer YOUR_TOKEN"` and expect the same `400` (not a
`401 Unauthorized`) once the token is accepted.

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
