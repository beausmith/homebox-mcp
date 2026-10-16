# Homebox MCP Server - Home Assistant Add-on

[![License][license-shield]](LICENSE.md)
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

MCP (Model Context Protocol) server for managing Homebox inventory via AI assistants.

🇧🇷 [Versão em Português](README-pt-br.md)

## Prerequisites

This addon was designed to work with **Homebox** running on Home Assistant.

**Recommended Homebox addon:** [homebox-addon](https://github.com/Crafter-Y/homebox-addon)

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCrafter-Y%2Fhomebox-addon)

<details>
<summary>Manual install</summary>

1. Add the repository: `https://github.com/Crafter-Y/homebox-addon`
2. Install the **Homebox** addon
3. Start and configure your inventory

</details>

### Homebox version compatibility

This addon works with both older Homebox versions and **Homebox v0.26.0+**, which
introduced a breaking API change (the "entity merge": `/items` and `/locations`
were unified into `/entities`, and labels became tags). The addon **auto-detects**
which API your Homebox speaks, so no configuration change is needed after upgrading.

## About

This addon exposes an MCP server that allows AI assistants (like Claude) to
interact with your Homebox inventory. You can:

- 📦 List, create, and manage items
- 📍 Organize hierarchical locations
- 🏷️ Categorize with labels
- 🔍 Search items by name or description
- 📊 Get inventory statistics

## Installation

### One-click install

[![Open your Home Assistant instance and show the dashboard of the Homebox MCP Server add-on, ready to install.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=homebox-mcp&repository_url=https%3A%2F%2Fgithub.com%2Fbeausmith%2Fhomebox-mcp)

This adds the repository and takes you straight to the add-on's page — click **Install** there.

<details>
<summary>Manual install</summary>

1. In Home Assistant, go to **Settings** → **Add-ons** → **Add-on Store**
2. Click the menu (⋮) → **Repositories**
3. Add: `https://github.com/beausmith/homebox-mcp`
4. Click **Add** → **Close**
5. Search for "Homebox MCP Server" in the store
6. Click **Install**
7. Configure the Homebox credentials
8. Start the add-on

</details>

## Configuration

```yaml
homebox_url: "http://homeassistant.local:7745"
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

## External Access via Cloudflare Tunnel

To use with Claude.ai web or access externally, we recommend using the
[Cloudflared addon](https://github.com/homeassistant-apps/app-cloudflared)
to create a secure tunnel.

### Configure Cloudflared

1. Install the [Cloudflared addon](https://github.com/homeassistant-apps/app-cloudflared)
2. Configure the tunnel to expose port 8099:

```yaml
additional_hosts:
  - hostname: mcp.yourdomain.com
    service: http://homeassistant:8099
```

3. Use the URL in Claude.ai: `https://mcp.yourdomain.com/mcp`

### Local Access

On the local network, access directly:

```
http://homeassistant.local:8099/mcp
```

## MCP Authentication (Optional)

The addon supports optional Bearer token authentication to protect the MCP endpoint.

### Configure Token

1. Access the **addon web page** (click "Homebox MCP" in the sidebar)
2. Click the **"🎲 Generate Token"** button
3. Click **"📋 Copy"**
4. In the **addon settings**:
   - Enable `mcp_auth_enabled`
   - Paste the token in `mcp_auth_token`
   - Click **Save**

### Configure in Claude.ai

Customize → Connectors → **Add custom connector**:

| Field                | Value                                                  |
| -------------------- | ------------------------------------------------------ |
| **MCP server URL**   | `https://your-domain.com/mcp`                          |
| **Transport**        | Streamable HTTP (under Advanced)                       |
| **Authentication**   | No sign-in                                             |
| **Request headers**  | `authorization` = `Bearer <token>` (include the space) |

Claude sends the header value exactly as typed, so keep the space between
`Bearer` and the token. The **Request headers** section is a Claude.ai beta;
if it is missing, see DOCS.md for the fallback.

## Using with Claude

### Claude.ai Web

1. Expose the addon with a Cloudflare Tunnel (see DOCS.md)
2. Add `https://mcp.yourdomain.com/mcp` as a custom connector, configured as above

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "homebox": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.yourdomain.com/mcp"]
    }
  }
}
```

### Interaction Examples

```
You: List all items in the garage
Claude: [Lists items filtered by location]

You: Add a "Bosch Drill" to the tools cabinet
Claude: [Creates item in the specified location]

You: Where is my camera?
Claude: [Searches and returns item location]
```

## MCP Tools

| Tool                         | Description                          |
| ----------------------------- | ------------------------------------- |
| `homebox_list_locations`     | List all locations (flat list)       |
| `homebox_get_location_tree`  | Get full location hierarchy tree     |
| `homebox_get_location`       | Get location details (parent/children) |
| `homebox_create_location`    | Create new location                  |
| `homebox_update_location`    | Update location                      |
| `homebox_delete_location`    | Delete location                      |
| `homebox_list_items`         | List items with filters              |
| `homebox_get_item`           | Get complete item details            |
| `homebox_search`             | Search for items                     |
| `homebox_create_item`        | Create new item                      |
| `homebox_update_item`        | Update item fields                   |
| `homebox_move_item`          | Move item to another location        |
| `homebox_add_item_attachment` | Attach a photo or document (PDF, manual, warranty, receipt) to an item |
| `homebox_add_item_attachment_from_url` | Attach a photo or document by downloading it from a URL |
| `homebox_delete_item`        | Delete item                          |
| `homebox_list_labels`        | List all labels                      |
| `homebox_create_label`       | Create new label                     |
| `homebox_update_label`       | Update label                         |
| `homebox_delete_label`       | Delete label                         |
| `homebox_get_statistics`     | Get inventory statistics             |

[Full Documentation](homebox-mcp/DOCS.md)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export HOMEBOX_URL="http://localhost:7745"
export HOMEBOX_TOKEN="your-api-token"

# Run server
cd homebox-mcp/app
python server.py

# Test with MCP Inspector
npx @modelcontextprotocol/inspector --server-url http://localhost:8099/mcp --transport http
```

## License

MIT License - see [LICENSE.md](LICENSE.md)

[license-shield]: https://img.shields.io/github/license/oangelo/homebox-mcp.svg
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
