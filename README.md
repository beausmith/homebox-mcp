# Homebox MCP Server - Home Assistant Add-on

[![License][license-shield]](LICENSE.md)
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

A Home Assistant add-on that runs an [MCP](https://modelcontextprotocol.io/) server for
[Homebox](https://homebox.software/), so an AI assistant such as Claude can list, search,
create, move and update the things in your home inventory.

This is a maintained fork. It runs against current Homebox (v0.26+) and includes complete,
tested instructions for connecting it to **Claude.ai** through a Cloudflare Tunnel. See
[History](#history-and-credits) for where the code comes from.

🇧🇷 The Portuguese files (`README-pt-br.md`, `homebox-mcp/DOCS-pt-br.md`) are upstream's and
have not been updated for this fork.

## Contents

- [What you get](#what-you-get)
- [Prerequisites](#prerequisites)
- [1. Install the add-on](#1-install-the-add-on)
- [2. Configure it](#2-configure-it)
- [3. Check that it works](#3-check-that-it-works)
- [4. Expose it to the internet](#4-expose-it-to-the-internet)
- [5. Lock it down](#5-lock-it-down)
- [6. Connect Claude.ai](#6-connect-claudeai)
- [Other clients](#other-clients)
- [MCP tools](#mcp-tools)
- [Gotchas we hit](#gotchas-we-hit)
- [Local development](#local-development)
- [History and credits](#history-and-credits)

## What you get

- An MCP server on port **8099**, Streamable HTTP at **`/mcp`** (`/sse` still works as an alias).
- Optional Bearer-token authentication on the endpoint.
- A small dashboard in the Home Assistant sidebar (Homebox MCP) with status, a token generator and
  the tool list.
- 20 tools covering locations (including the nested tree), items, attachments, labels and
  statistics. See [MCP tools](#mcp-tools).
- Automatic detection of the Homebox API generation: the pre-0.26 `/items` + `/locations` API and
  the 0.26+ "entity merge" API (`/entities` + `/tags`) are both supported.

## Prerequisites

### A running Homebox

We run Homebox as a Home Assistant add-on from
[jscarrott/homebox-addon](https://github.com/jscarrott/homebox-addon) (add-on "Homebox Add-on",
port 7745, packages Homebox v0.26.x). Upstream's original recommendation,
[Crafter-Y/homebox-addon](https://github.com/Crafter-Y/homebox-addon), should also work; the MCP
add-on only needs an HTTP URL and an API token.

[![Add the jscarrott/homebox-addon repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjscarrott%2Fhomebox-addon)

<details>
<summary>Manual install</summary>

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add `https://github.com/jscarrott/homebox-addon`
2. Install **Homebox Add-on**, start it, create your admin user

</details>

### A Homebox API token

In Homebox: **Profile (user icon) → API Tokens → Create Token**. Copy it; you will paste it into the
add-on configuration. Homebox 0.26 shows the token once.

### For Claude.ai only: a domain on Cloudflare

Claude.ai connects from Anthropic's cloud, so the endpoint must be reachable from the internet.
The route documented here is a free Cloudflare Tunnel, which needs a domain whose DNS is hosted by
Cloudflare. If you only use Claude Desktop or Claude Code from your LAN, you can skip steps 4 and 5.

## 1. Install the add-on

[![Open the Homebox MCP Server add-on page](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=homebox-mcp&repository_url=https%3A%2F%2Fgithub.com%2Fbeausmith%2Fhomebox-mcp)

<details>
<summary>Manual install</summary>

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add `https://github.com/beausmith/homebox-mcp`
2. Find **Homebox MCP Server** in the store and click **Install**. Supervisor builds the image
   locally; this takes a minute or two.

</details>

If you previously installed the upstream `oangelo/homebox-mcp` add-on, uninstall it first; both
use the slug `homebox-mcp` and Home Assistant will not run two. Copy its `homebox_token` out of its
configuration before you remove it.

## 2. Configure it

| Option             | Required | What to put                                                                 |
| ------------------ | -------- | --------------------------------------------------------------------------- |
| `homebox_url`      | yes      | How the add-on reaches Homebox. For the Homebox add-on use its internal hostname, shown on the add-on's **Info** tab, e.g. `http://84740097-homebox:7745`. An HTTPS URL on your own reverse proxy also works. |
| `homebox_token`    | yes      | The Homebox API token from above.                                           |
| `mcp_auth_enabled` | no       | `true` to require a Bearer token on the MCP endpoint. **Turn this on before exposing the endpoint.** |
| `mcp_auth_token`   | if auth  | The token clients must send. Click **🎲 Generate Token** on the add-on's dashboard page to get a random one, or set your own. |
| `log_level`        | no       | `trace`, `debug`, `info` (default), `warning`, `error`.                      |

```yaml
homebox_url: "http://84740097-homebox:7745"
homebox_token: "YOUR_HOMEBOX_API_TOKEN"
mcp_auth_enabled: true
mcp_auth_token: "a-long-random-token"
log_level: "info"
```

Save, then **Start** the add-on. Enable **Show in sidebar** if you want the dashboard.

## 3. Check that it works

Open the **Log** tab. A healthy start looks like:

```
Detected Homebox API mode: entities      <- "legacy" on Homebox < 0.26
MCP endpoint (Streamable HTTP) at: http://0.0.0.0:8099/mcp (alias /sse)
MCP Authentication: ENABLED - Bearer token required
```

The dashboard (sidebar → Homebox MCP) shows the Homebox connection and item/location counts.

To probe the endpoint from a shell on your network, send an MCP `initialize` request. A plain GET
cannot complete the Streamable HTTP handshake, so use POST:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://homeassistant.local:8099/mcp \
  -H "Authorization: Bearer YOUR_MCP_TOKEN" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
```

`200` means the server is up and the token is accepted. `401` means the token is wrong or missing.
The [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) gives a full interactive
test: `npx @modelcontextprotocol/inspector --server-url http://homeassistant.local:8099/mcp --transport http`.

## 4. Expose it to the internet

Claude.ai has to reach the server from Anthropic's cloud. Things that do **not** work for an
add-on port, so you do not waste time on them:

- **Nabu Casa / Home Assistant Cloud** only proxies Home Assistant itself (port 8123), not add-on
  ports. Add-on **ingress** through it needs a Home Assistant login session, which Claude.ai cannot
  provide.
- The **Tailscale add-on**'s Funnel option can only share Home Assistant itself, and its `services`
  option is tailnet-only (Serve, not Funnel).
- A LAN-only reverse proxy (NGINX add-on etc.) is not reachable from outside.

What does work, with no inbound port forward and without exposing Home Assistant itself:

### Cloudflare Tunnel via the Cloudflared add-on

1. Add the repository `https://github.com/homeassistant-apps/app-cloudflared` and install
   **Cloudflared**.
2. Configure it. Leave `external_hostname` **empty** (that option would expose Home Assistant; we
   only want the MCP server) and add one host. The service URL uses the MCP add-on's internal
   hostname from its **Info** tab, which is `<repository-id>-homebox-mcp`:

   ```yaml
   external_hostname: ""
   additional_hosts:
     - hostname: homebox-mcp.yourdomain.com
       service: http://ee45feb1-homebox-mcp:8099
   ```

3. Start the add-on and open its **Log**. It prints a `https://dash.cloudflare.com/argotunnel?...`
   link. Open it, sign in to the Cloudflare account that holds your domain, pick the domain and
   click **Authorize**. The page says "Success. Cloudflared has installed a certificate…" and the
   add-on continues on its own: it creates the tunnel and the DNS record for the hostname.

   If the page shows no domain to pick, you are signed into a Cloudflare account that does not own
   the zone, or the page loaded stale. Signing in to the right account and opening the link again
   fixed it for us.

4. The log should end with four `Registered tunnel connection` lines. A warning that the QUIC
   pre-check failed and `cloudflared will proceed using 'http2'` is harmless.
5. Test from outside your LAN with the `curl` from step 3 against
   `https://homebox-mcp.yourdomain.com/mcp`. Expect `401` without the token and `200` with it.

Instead of the browser login you can create the tunnel yourself in Cloudflare Zero Trust and give
the add-on a `tunnel_token`; then the hostname → service mapping is configured in the Cloudflare
dashboard instead of `additional_hosts`. Either way the result is the same.

## 5. Lock it down

The tunnel makes the endpoint public. Two layers protect it:

1. **The Bearer token** (`mcp_auth_enabled: true`). Every request without the right
   `Authorization: Bearer <token>` header gets a `401`. The dashboard and `/api/status` stay
   reachable only through Home Assistant ingress.
2. **A Cloudflare rule that only lets Anthropic in.** Anthropic publishes the IP range its MCP
   calls come from ([IP addresses](https://platform.claude.com/docs/en/api/ip-addresses), currently
   `160.79.104.0/21`). In the Cloudflare dashboard select your **zone** (the domain tile, not the
   account-level WAF page, which is a paid add-on), then **Security → Security rules** (older
   layout: **Security → WAF → Custom rules**) → **Create rule**:

   ```
   (http.host eq "homebox-mcp.yourdomain.com" and not ip.src in {160.79.104.0/21})
   ```

   Action **Block**, then **Deploy**. The free plan includes five such rules.

   Consequence: after this, the public URL answers `403` from everywhere except Anthropic,
   including your own house. Test from your LAN with the internal URL
   (`http://<addon-hostname>:8099/mcp`) instead, and if you also want Claude Desktop or Claude Code
   to use the public URL from home, add your home IP to the allowed set or use the LAN URL there.

## 6. Connect Claude.ai

In Claude.ai go to **Customize → Connectors → Add custom connector** (on Team/Enterprise plans an
Owner does this under Organization settings → Connectors).

| Field                | Value                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------- |
| Name                 | Homebox                                                                               |
| MCP server URL       | `https://homebox-mcp.yourdomain.com/mcp`                                              |
| Authentication       | **No sign-in**                                                                        |
| Request headers      | header `authorization`, value `Bearer YOUR_MCP_TOKEN`, **Required**                   |
| Advanced → Transport | leave the default (Streamable HTTP). Only a URL ending in `/sse` makes Claude pick the deprecated SSE transport and show a warning; that is why the endpoint is `/mcp`. |

Things we learned the hard way:

- **The space matters.** Claude sends the header value exactly as typed. `BearerYOUR_TOKEN` (no
  space) reaches the server and is rejected with `401`; the add-on log shows
  `Authorization header: Bearera1b2...`. Type `Bearer`, one space, then the token.
- **Request headers is a Claude.ai beta.** If the section is missing from the dialog, your
  organization does not have it yet. Then the only options are an authless server (set
  `mcp_auth_enabled: false` and rely entirely on the Cloudflare rule from step 5) or adding a real
  OAuth authorization server to this project.
- **Do not put the token in "OAuth Client Secret".** Older versions of this README (and upstream)
  said to. Current Claude.ai treats client credentials as a real OAuth setup, looks for
  `/.well-known/oauth-protected-resource`, finds nothing and fails with "Couldn't connect to the
  server".
- **Authentication settings cannot be edited.** To change the URL's auth or the header, remove the
  connector and add it again.

Click **Add**. Then in a chat open **+ → Connectors**, enable Homebox, and ask Claude to list your
locations. In the add-on log you should see `POST /mcp ... 200 OK` lines. A single `400 Bad
Request` at the very start is Claude retrying with a session id from a previous attempt; it is
harmless.

## Other clients

**Claude Code**

```bash
claude mcp add --transport http homebox https://homebox-mcp.yourdomain.com/mcp \
  --header "Authorization: Bearer YOUR_MCP_TOKEN"
```

**Claude Desktop** (`claude_desktop_config.json`), via `mcp-remote`:

```json
{
  "mcpServers": {
    "homebox": {
      "command": "npx",
      "args": [
        "mcp-remote", "https://homebox-mcp.yourdomain.com/mcp",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": { "AUTH_HEADER": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

The header value goes through an environment variable because Claude Desktop on Windows (and
Cursor) mangle spaces inside `args`; the `Authorization:${AUTH_HEADER}` form has no space.

From inside your LAN both can use `http://homeassistant.local:8099/mcp` instead, which also
sidesteps the Cloudflare IP rule.

## MCP tools

| Tool                                   | Description                                                        |
| -------------------------------------- | ------------------------------------------------------------------ |
| `homebox_list_locations`               | All locations as a flat list                                       |
| `homebox_get_location_tree`            | The nested location hierarchy with item counts                     |
| `homebox_get_location`                 | One location with its parent and children                          |
| `homebox_create_location`              | Create a location, optionally under a parent                       |
| `homebox_update_location`              | Rename / re-parent / re-describe a location (keeps everything else)|
| `homebox_delete_location`              | Delete a location                                                  |
| `homebox_list_items`                   | Items, filterable by location and label                            |
| `homebox_get_item`                     | Full item detail including custom fields                           |
| `homebox_search`                       | Free-text item search                                              |
| `homebox_create_item`                  | Create an item                                                     |
| `homebox_update_item`                  | Update any item fields, purchase/warranty/sold data included       |
| `homebox_move_item`                    | Move an item to another location                                   |
| `homebox_add_item_attachment`          | Attach a photo/document supplied as base64 (max 1 MB)              |
| `homebox_add_item_attachment_from_url` | Attach a photo/document downloaded from a URL (SSRF-guarded)       |
| `homebox_delete_item`                  | Delete an item                                                     |
| `homebox_list_labels`                  | All labels (tags on Homebox 0.26+)                                 |
| `homebox_create_label`                 | Create a label                                                     |
| `homebox_update_label`                 | Update a label                                                     |
| `homebox_delete_label`                 | Delete a label                                                     |
| `homebox_get_statistics`               | Inventory totals                                                   |

Full option and tool reference: [homebox-mcp/DOCS.md](homebox-mcp/DOCS.md) (also shown on the
add-on's **Documentation** tab).

## Gotchas we hit

- **Homebox 0.26 changed the API.** `/items`, `/locations` and `/labels` became `/entities` (with
  `isLocation`) and `/tags`. The add-on detects which generation it is talking to at start-up
  (`Detected Homebox API mode: entities` or `legacy`).
- **On 0.26.2 the location list and detail carry no parent, children or item count.** That is why
  the tree tool reads Homebox's own `/entities/tree` endpoint instead of rebuilding the hierarchy
  from parent links. Earlier versions showed every location at the root.
- **`PUT /entities/{id}` replaces the whole entity.** Updates therefore send the entity's complete
  current state with only the requested changes overlaid, otherwise custom fields, tags and the
  parent silently disappear. Homebox's "never set" date sentinel (`0001-01-01`) is dropped so empty
  dates stay empty.
- **Deleting an item seconds after attaching a photo can wedge Homebox.** The thumbnail job fails
  on the missing item, and on the SQLite backend every write then returns a 500 until the Homebox
  add-on is restarted. Give attachments a moment before deleting.
- **The Homebox add-on's API key pepper** (`/data/api_key_pepper` in jscarrott/homebox-addon ≥
  2.2.1) must not be deleted; doing so invalidates every API token, including the one in this
  add-on's configuration.
- **Docker build.** Supervisor builds the image on your machine at install time; the first install
  takes a couple of minutes and the add-on page shows nothing until it finishes.

## Local development

```bash
pip install -r requirements.txt            # fastmcp<3, httpx, pydantic, starlette, uvicorn
export HOMEBOX_URL="http://localhost:7745"
export HOMEBOX_TOKEN="your-api-token"
export MCP_AUTH_ENABLED=true MCP_AUTH_TOKEN=devtoken SERVER_PORT=8099
cd homebox-mcp/app && python server.py
npx @modelcontextprotocol/inspector --server-url http://localhost:8099/mcp --transport http
```

Changes are listed in [homebox-mcp/CHANGELOG.md](homebox-mcp/CHANGELOG.md). Bump `version` in
`homebox-mcp/config.yaml` for Supervisor to offer an update.

## History and credits

This add-on is a fork of **[oangelo/homebox-mcp](https://github.com/oangelo/homebox-mcp)** (MIT),
which created the add-on, the dashboard, the token generator and the original tool set. Upstream
has been inactive since February 2026 (last release 0.2.1) and targets the pre-0.26 Homebox API, so
it stops working after a Homebox upgrade.

The fork's `master` is built on:

- **[MB901/homebox-mcp](https://github.com/MB901/homebox-mcp)**, branch `dev` (0.5.1dev9). This is
  the bulk of the work beyond upstream: Homebox v0.26+ compatibility with API auto-detection,
  switching the transport from the legacy SSE pair of endpoints to Streamable HTTP (which fixed
  "Received request before initialization was complete" crashes with mcp-remote), fixing the
  auth-middleware and location/label bugs, item attachments (base64 and from URL, with an SSRF
  guard), purchase/warranty/sold fields, field-length validation, fractional quantities and the
  complete dashboard tool list. MB901 submitted the core of this as
  [oangelo/homebox-mcp PR #3](https://github.com/oangelo/homebox-mcp/pull/3) (August 2026), still
  unmerged with failing CI at the time of forking, which is why this fork exists.
- **[sheepster-9k/homebox-mcp](https://github.com/sheepster-9k/homebox-mcp)**: the UUID validation
  of every id argument before it is interpolated into a URL was ported from this fork. Its other
  changes (a rate-limiter memory cap, default host port 8100, relative ingress URLs, moving to
  fastmcp 3.x with unpinned dependencies) were reviewed and not taken: this fork pins `fastmcp<3`
  because the Alpine build of fastmcp 3 failed for them, keeps port 8099, and has no rate limiter.

On top of that, this fork adds (see the changelog for details):

- **0.7.0** (2026-10-15): nested location tree via `/entities/tree`, full-body item and location
  updates that preserve custom fields, tags and parent, UUID validation, sanitized error messages
  that never include the URL or token, metadata repointed here. Verified live against Homebox
  v0.26.2.
- **0.7.1** (2026-10-16): endpoint moved to `/mcp` with `/sse` kept as an alias, and the dashboard
  and docs rewritten around the Claude.ai setup that actually works (Streamable HTTP, No sign-in,
  token in an `authorization` request header).

All three repositories above are audited rather than blindly merged; each line of `master` is
traceable in `git log` (`upstream`, `MB901` and `sheepster` are configured as remotes).

## License

MIT License - see [LICENSE.md](LICENSE.md). Original work © oangelo; Homebox is © the
[sysadminsmedia/homebox](https://github.com/sysadminsmedia/homebox) project.

[license-shield]: https://img.shields.io/github/license/beausmith/homebox-mcp.svg
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
