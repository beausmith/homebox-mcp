# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.1] - 2026-10-16

### Changed

- **MCP endpoint moved to `/mcp`.** Claude.ai selects the deprecated SSE
  transport for any connector URL ending in `/sse` and shows a warning; `/mcp`
  is the conventional Streamable HTTP path. `/sse` remains an alias (the path
  is rewritten server-side), so existing mcp-remote / Claude.ai configs keep
  working.
- Dashboard and docs now describe the working Claude.ai setup: Streamable HTTP
  transport, **No sign-in**, and the token in a `authorization: Bearer <token>`
  request header (the "OAuth Client Secret" advice no longer works: Claude.ai
  runs real OAuth discovery when client credentials are entered).

## [0.7.0] - 2026-10-15

Built on MB901's `dev` branch (0.5.1dev9, the Homebox v0.26 compatibility work of
PR #3). Verified live against Homebox v0.26.2.

### Fixed

- **Nested locations flattened on Homebox v0.26.2.** Neither
  `GET /entities?isLocation=true` nor `GET /entities/{id}` returns `parent`,
  `children` or `itemCount` for a location on 0.26.2, so the parent-link tree
  builder put every location at the root. `homebox_get_location_tree` now reads
  `GET /entities/tree` (the endpoint the Homebox UI uses) and derives item
  counts from the item list; `homebox_get_location` fills `parent` and
  `children` in from the tree, which also keeps `homebox_update_location` from
  dropping a location's parent on rename.
- **Updates wiped custom fields.** `PUT /entities/{id}` is a full replacement;
  `homebox_update_item` and `homebox_update_location` now build the payload
  from the entity's complete current state (every `repo.EntityUpdate` scalar,
  parent, entity type, tags, custom `fields`, `syncChildEntityLocations`) and
  overlay only the requested changes. Homebox's "never set" date sentinel
  (`0001-01-01…`) is omitted so empty dates stay empty.
- `homebox_get_item` / `homebox_list_items` now include `fields` (custom
  fields) and `syncChildEntityLocations` in their output.

### Security

- Every id argument (item, location, label, parent, tag) is validated as a
  UUID before it is interpolated into a URL path (ported from
  sheepster-9k/homebox-mcp).
- Homebox HTTP errors are re-raised with only the status code, method, relative
  endpoint and Homebox's own error text - never the full URL, headers or token.

### Changed

- Version 0.7.0.

## [0.5.1dev9] - 2026-08-16

### Fixed

- **`quantity` was typed as an integer, rejecting the fractional
  quantities Homebox itself has supported since v0.25.0** (e.g. `2.5`
  units of something sold by partial amounts). `homebox_create_item` and
  `homebox_update_item` now accept `quantity` as a number; docstrings
  note that fractional values require Homebox v0.25.0+ (older versions
  accept whole numbers only). Unlike the entities-only fields added
  earlier in this changelog, this applies to both API modes: Homebox's
  fractional-quantity support (PR sysadminsmedia/homebox#1372) landed in
  the legacy `Item` model before the v0.26.0 entity merge, so it was
  never entities-specific.

## [0.5.1dev8] - 2026-08-16

### Changed

- **Recommended Homebox addon link updated.** The previously recommended
  [homebox-ingress-ha-addon](https://github.com/Oddiesea/homebox-ingress-ha-addon)
  no longer exists; replaced everywhere (`README.md`, `README-pt-br.md`,
  `DOCS.md`, `DOCS-pt-br.md`, the addon's dashboard footer) with
  [Crafter-Y/homebox-addon](https://github.com/Crafter-Y/homebox-addon).
- **Fixed this addon's own install instructions pointing at the upstream
  repo instead of this fork.** `README.md`/`README-pt-br.md` told users to
  add `https://github.com/oangelo/homebox-mcp` — the unmaintained upstream
  — instead of `https://github.com/MB901/homebox-mcp`, the repo this
  addon's own `config.yaml` (`url:`) actually points to and where every
  fix in this changelog lives.
- **Added "My Home Assistant" one-click install buttons** for both this
  addon and the recommended Homebox addon. For this addon, the button uses
  the `supervisor_addon` redirect (`addon` + `repository_url` params),
  which adds the repository and opens the addon's install page in one
  step, rather than just the `supervisor_add_addon_repository` redirect
  used for the Homebox addon link (add-repository only, then find and
  install manually).
- Collapsed each "Manual install" step list into a `<details>` dropdown
  below its one-click button, so the button is the first thing readers see.

## [0.5.1dev7] - 2026-08-16

### Changed

- **`homebox_add_item_attachment`'s size limit dropped from 10 MB to 1 MB.**
  Root cause of a reported "Claude hangs" issue: attaching a file through
  this base64 tool requires the *calling model* to generate the entire
  file as base64 text to compose the tool call — a 1 MB file is already
  ~1.37M characters of output. Confirmed via the MCP spec (through the
  2026-07-28 RC) and Claude's own host implementations that there is
  currently no way for a client to inject an uploaded file's bytes into a
  tool argument without the model generating them itself (MCP Resources
  only flow server→client; no Claude host auto-populates a tool argument
  from a chat attachment). A cap far below the old 10 MB limit — and a
  docstring that says so plainly — turns an oversized attempt into an
  immediate, clear error instead of a multi-minute (or failing)
  generation. `homebox_add_item_attachment_from_url` is unaffected and
  still capped at 10 MB: the server downloads the file directly, so the
  model only ever supplies a short URL, with no generation-cost problem.

## [0.5.1dev6] - 2026-08-15

### Added

- **Character-limit validation for text fields**, matching Homebox's own
  `name` (255), `description` (1000), `notes` (1000), `serial_number`
  (255), `model_number` (255), `manufacturer` (255), `warranty_details`
  (1000), `purchase_from` (255), `sold_to` (255), `sold_notes` (1000),
  and label `color` (255) limits. Exceeding a limit now raises a clear
  error from the MCP itself instead of reaching Homebox — this matters
  most for `notes`, `serial_number`, `warranty_details`, `sold_notes`,
  and `color`, which Homebox only enforces at the database layer, not
  via its request validator, so an over-limit value previously failed
  with an opaque server error rather than a clean rejection. Every
  affected tool's docstring now also states the limit up front.

## [0.5.1dev5] - 2026-08-15

### Added

- **`homebox_update_item` now supports 8 additional fields**:
  `lifetime_warranty`, `warranty_expires`, `warranty_details`,
  `purchase_from`, `sold_date`, `sold_to`, `sold_price`, `sold_notes`.
  These match fields Homebox's `EntityUpdate` API already supports but
  this MCP didn't expose. Like `purchase_date`, they only apply in
  entities mode (Homebox v0.26.0+) and are ignored against the legacy
  API. `homebox_get_item` also now surfaces these fields (when set)
  plus `attachments` and `entityType`, which were previously stripped
  out by `_normalize_item()`'s allowlist.

## [0.5.1dev4] - 2026-08-15

### Fixed

- **`homebox_update_item` (entities mode) silently wiped any field not
  explicitly passed** — `insured`, `archived`, `asset_id`,
  `serial_number`, `model_number`, `manufacturer`, `purchase_price`,
  `purchase_date`, and `notes` were only added to the PUT payload `if
  <param> is not None`, so an update call that omitted one reset it to
  empty/zero on Homebox's side instead of leaving it alone. Root cause:
  Homebox's `PUT /entities/{id}` is a full-replacement update, not a
  partial patch — any field missing from the JSON body is reset
  server-side, not preserved. `name`/`description`/`quantity`/`location_id`
  already correctly fell back to the item's current value when omitted;
  the other fields didn't follow that same pattern. All of them now do:
  every call first fetches the item's current state and every field in
  the PUT payload falls back to it when the caller didn't pass a new
  value, so a call that only changes one field no longer loses the rest.

## [0.5.1dev3] - 2026-08-15

### Added

- **New tool**: `homebox_add_item_attachment_from_url` - Attach a photo or
  document to an item by downloading it from a URL, for files found by
  Claude itself (e.g. a product photo from a web search) rather than ones
  the user uploaded in chat (that path already works via the existing
  `homebox_add_item_attachment` base64 tool). Delegates all
  format-sniffing/validation/upload logic to `add_item_attachment` (same
  10 MB cap, same JPEG/PNG/GIF/WEBP/HEIC/PDF allowlist by magic bytes).
  - **SSRF guard**: only `http://`/`https://` URLs are accepted, and the
    URL's host must resolve to a public IP address — private, loopback,
    link-local, reserved, multicast, and CGNAT (`100.64.0.0/10`)
    addresses are all refused, closing off requests to internal Home
    Assistant services or cloud metadata endpoints. Re-validated on every
    redirect hop actually followed (capped at 5), so a public URL can't
    bounce the request to an internal address after the fact.
  - **Fail-fast extension check**: a URL whose path clearly ends in a
    known-unsupported extension (`.zip`, `.exe`, `.mp4`, `.docx`, ...) is
    rejected before any network request, instead of downloading up to
    10 MB just to have `_sniff_file` reject it afterwards. Deliberately
    not an allowlist — most legitimate image URLs (CDNs, Wikipedia,
    search results) have no extension at all or a query string after
    one, so only recognized-wrong extensions are rejected early;
    everything else still goes through the real, content-based
    `_sniff_file` check after download.
  - The download itself is streamed and aborted as soon as more than
    10 MB has been read, rather than trusting a `Content-Length` header
    (which can be absent or wrong) or fully buffering an arbitrarily
    large response first.
  - Known limitation, accepted as proportionate to this addon's
    single-user home-network threat model: this is a pre-flight DNS
    check, not full DNS-rebinding protection (the resolved address could
    theoretically change between the check and the actual request a
    moment later).

## [0.5.1dev2] - 2026-08-15

### Fixed

- **`homebox_update_item` had no way to set an item's purchase date.** Adds
  a `purchase_date` parameter, accepting `"YYYY-MM-DD"` or a full ISO 8601
  timestamp. Only applied against the `/entities` API (Homebox v0.26.0+,
  field `purchaseDate`); ignored on the legacy `/items` API, which isn't
  a maintenance target going forward. Also added to the set of fields
  preserved when reading an item back, alongside `purchasePrice`.

## [0.5.1dev1] - 2026-08-15

### Added

- **New tool**: `homebox_add_item_attachment` - Attach a photo or document
  (manual, warranty, receipt) to an item. The MCP server previously had no
  way to add attachments at all. Files are passed base64-encoded (MCP tool
  arguments are JSON, so raw binary isn't an option) and validated
  **before** anything is uploaded to Homebox:
  - Only JPEG, PNG, GIF, WEBP, HEIC images and PDF documents are accepted,
    verified by sniffing the file's magic bytes rather than trusting the
    caller-supplied filename or content-type.
  - Uploads over 10 MB are rejected locally (matching Homebox's own
    default `HBOX_WEB_MAX_UPLOAD_SIZE`), instead of pushing a large
    payload through the MCP connection just to have the server reject it.
  - An optional `attachment_type` selects how Homebox classifies the file
    (`photo`, `manual`, `warranty`, `receipt`, `attachment`), defaulting to
    `photo` for images and `attachment` for documents.
  - Works against both the legacy `/items/{id}/attachments` and the
    v0.26.0+ `/entities/{id}/attachments` endpoints, matching whichever
    API mode the client already detected.

## [0.5.1] - 2026-08-15

### Fixed

- The addon dashboard's "🛠️ Available Tools" grid still listed only 8 of
  the 18 tools (a static HTML snippet in `server.py`, missed when the
  `homebox://info` MCP resource and the READMEs' tool tables were brought
  up to date). Now lists all 18.

## [0.5.0] - 2026-08-14

### Added

- **Compatibility with Homebox v0.26.0+ ("entity merge" API change).** In
  v0.26.0 Homebox removed `/items`, `/locations` and `/labels` in favor of a
  unified `/entities` API (+ `/entity-types`, `/tags`). The client now
  **auto-detects** which API the server speaks on first use and
  routes/normalizes calls accordingly, so the addon works unmodified on both
  older and newer Homebox versions with no reconfiguration. See the
  [entity merge migration guide](https://homebox.software/en/advanced/entity-merge-upgrade/).

### Fixed

- **MCP server crashed on every tool call** (`RuntimeError: Task group is not
  initialized`). The FastMCP app is now mounted with its `lifespan` passed to
  the parent Starlette app, required by modern FastMCP to start its session
  manager.
- **Intermittent `AssertionError: Unexpected message: ... 'http.response.start'
  ...`** crashing requests. `BearerAuthMiddleware` was built on
  `starlette.middleware.base.BaseHTTPMiddleware`, which buffers/re-wraps the
  downstream response — incompatible with FastMCP's streaming responses once
  a session has overlapping in-flight requests. Rewritten as raw ASGI
  middleware. See [fastmcp#858](https://github.com/jlowin/fastmcp/issues/858)
  and [python-sdk#883](https://github.com/modelcontextprotocol/python-sdk/issues/883).
- **`Received request before initialization was complete`, failing every
  tool call.** The legacy SSE transport splits a session across two
  independent requests (a `GET /sse` stream handing out a `session_id`, plus
  separate `POST /messages?session_id=...` calls) without checking the GET
  side finished its handshake before accepting POSTs on that session; a
  client reopening a second `/sse` connection (observed from `mcp-remote`)
  could race and land on an uninitialized session. Switched to the modern
  **Streamable HTTP** transport (still mounted at `/sse` for compatibility),
  which tracks sessions via an `Mcp-Session-Id` header instead of two
  endpoints racing over a query param. See
  [python-sdk#423](https://github.com/modelcontextprotocol/python-sdk/issues/423)
  and [python-sdk#1844](https://github.com/modelcontextprotocol/python-sdk/issues/1844).
- **`homebox_list_locations` / `homebox_get_location_tree` returned an empty
  list even when locations existed** (entities mode). Per Homebox's own
  server source, the plain `GET /entities` list excludes locations from its
  results unless `isLocation=true` is passed explicitly (an undocumented
  filter, missing from the swagger annotations) — "for backward
  compatibility" with the old items-only `/items` endpoint. Fixed by
  requesting `GET /entities?isLocation=true` directly, which is also what
  makes the server populate each result's `itemCount`.
- **`homebox_update_label` failed with `422 Unprocessable Entity`** (entities
  mode). Homebox's tag-update endpoint (`repo.TagUpdate`) requires a full
  replacement object where `name` is mandatory even when it isn't changing;
  the client only sent the fields the caller explicitly passed. Now fetches
  the current label first and merges in the requested changes, mirroring the
  pattern already used for items/locations (also preserves `parentId` for
  nested tags, matching the fix already applied to `update_location` in
  0.2.1).
- **`homebox_get_location_tree` made a redundant HTTP request per location.**
  It already got each location's direct parent for free from
  `get_locations()` (eager-loaded by the server), but was still calling
  `get_location()` again for every node to re-fetch the same information.
  Tree-building logic moved into `HomeboxClient.get_location_tree()`, which
  uses that parent directly in entities mode and only falls back to per-node
  fetches for legacy Homebox (whose old `/locations` list genuinely omits
  parent info).
- **`homebox_get_location`'s docstring promised a field that doesn't exist**
  (`items`); the actual field is `children` (a mix of sub-locations and/or
  items), plus `itemCount`.
- **`homebox_list_locations`'s docstring blamed "Homebox API limitations"**
  for omitting hierarchy info, which is only true for legacy Homebox; in
  entities mode the parent is available, this tool just omits it
  deliberately for a simpler flat view.

### Changed

- Dependency versions are now bounded (`fastmcp>=2.3.4,<3`, `httpx>=0.28.1`,
  `pydantic>=2.10.6`, `starlette>=0.41.0`, `uvicorn>=0.32.0`) to prevent a
  future breaking release from silently breaking the addon on the next
  image rebuild.

### Documentation

- `DOCS.md`/`DOCS-pt-br.md` were missing `homebox_get_location_tree` from the
  tool list entirely, and `README.md`/`README-pt-br.md`'s tool tables covered
  only 7 of the 18 available tools. Both now list all 18.
- The "Testing the Connection" section's `curl`/SSE example stopped working
  after the move to Streamable HTTP (a bare `GET /sse` now correctly returns
  `400 Bad Request` instead of an SSE handshake). Replaced with instructions
  that work against the transport actually in use, recommending the MCP
  Inspector — and fixed its install command, since `@anthropic/mcp-inspector`
  isn't a real package (the official one is `@modelcontextprotocol/inspector`).
- `DOCS-pt-br.md` had drifted out of sync with the current auth flow/code: it
  described automatic token generation on enabling `mcp_auth_enabled` (never
  true — the token must be generated via the dashboard button and copied
  into the config), told users to leave the OAuth Client ID blank (should be
  `mcp` or any text), and its "Authentication Error" troubleshooting section
  still referred to username/password login, removed in 0.3.0 in favor of
  API tokens.

## [0.2.0] - 2026-01-26

### Added

- **New tool**: `homebox_get_location_tree` - Returns complete location hierarchy tree
  - Addresses [Issue #1](https://github.com/oangelo/homebox-mcp/issues/1)
  - Fetches all locations with parent/children relationships
  - Returns nested tree structure for easy hierarchy visualization
- All tool docstrings translated to English

### Changed

- **Internationalization**: Project translated to English
- Dashboard UI now in English
- Documentation in English with Portuguese version available
- Added `README-pt-br.md` and `DOCS-pt-br.md` for Portuguese speakers
- `homebox_list_locations` now documents Homebox API limitation (parent_id always null)

### Fixed

- Documented workaround for Homebox API not returning parent_id in list endpoint

## [0.2.1] - 2026-01-26

### Fixed

- Preserve `parentId` when updating a location without specifying a new parent
  - Prevents accidental loss of hierarchy on location updates

## [0.1.8] - 2026-01-10

### Added

- Support for Basic Authentication (client_id:client_secret)
- Debug logging for Authorization headers
- Better error messages for authentication

### Changed

- Claude.ai now uses OAuth Client ID + Client Secret fields
- Client ID can be any text (e.g., "mcp")
- Client Secret should contain the authentication token

## [0.4.0] - 2026-01-09

### Added

- **Optional OAuth authentication** for the MCP endpoint
- New `mcp_auth_enabled` option to enable/disable authentication
- New `mcp_auth_token` option to set the Bearer token
- Dashboard shows authentication status
- Recommendation: test without auth first, then enable

### How to Use

1. Test the connection with `mcp_auth_enabled: false`
2. After it works, set a token in `mcp_auth_token`
3. Enable `mcp_auth_enabled: true`
4. In Claude.ai, configure: OAuth Client ID = `mcp`, OAuth Client Secret = your token

## [0.3.0] - 2026-01-09

### Changed

- **BREAKING**: Removed email/password authentication (didn't work correctly)
- Now uses only API Token authentication
- Simplified configuration: only `homebox_url`, `homebox_token`, and `log_level`

### How to Migrate

1. In Homebox, go to **Profile** → **API Tokens** → **Create Token**
2. Copy the generated token
3. Configure the addon with the token

## [0.2.2] - 2026-01-09

### Changed

- Dashboard now shows clear instructions for Cloudflare Tunnel configuration
- Internal address (`http://homeassistant:8099`) displayed for tunnel configuration
- Instructions on adding `/sse` to the tunnel address for Claude.ai

### Fixed

- FastMCP API fix: `sse_app()` → `http_app(transport="sse")`

## [0.2.0] - 2026-01-06

### Added

- Web status dashboard on the addon homepage
- Displays connection status with Homebox
- Shows count of locations, items, and labels
- Displays server uptime
- Shows MCP endpoint for easy configuration
- List of available tools in the dashboard
- API endpoint `/api/status` for programmatic queries
- Auto-refresh every 30 seconds

## [0.1.1] - 2026-01-06

### Added

- Port 8099 exposed directly for easier external connection
- Support for direct connection via `http://YOUR_IP:8099/sse`

### Fixed

- Removed deprecated `description` parameter from FastMCP
- Removed Alpine package version pinning

## [0.1.0] - 2026-01-06

### Added

- Initial MCP server with SSE support
- Integration with Homebox API v1
- Tools for location management:
  - `homebox_list_locations`
  - `homebox_get_location`
  - `homebox_create_location`
  - `homebox_update_location`
  - `homebox_delete_location`
- Tools for item management:
  - `homebox_list_items`
  - `homebox_get_item`
  - `homebox_search`
  - `homebox_create_item`
  - `homebox_update_item`
  - `homebox_move_item`
  - `homebox_delete_item`
- Tools for label management:
  - `homebox_list_labels`
  - `homebox_create_label`
  - `homebox_update_label`
  - `homebox_delete_label`
- Statistics tool:
  - `homebox_get_statistics`
- Automatic authentication with token renewal
- Configuration via Home Assistant addon options
- Supported architectures: amd64, aarch64
