"""Homebox MCP Server - Main entry point."""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
import uvicorn

from config import config
from homebox_client import HomeboxClient
from tools import register_tools


class BearerAuthMiddleware:
    """Middleware to authenticate requests using Bearer or Basic auth.

    Implemented as raw ASGI (not starlette.middleware.base.BaseHTTPMiddleware)
    on purpose: BaseHTTPMiddleware buffers/re-wraps the downstream response via
    call_next(), which is incompatible with FastMCP's long-lived SSE stream and
    intermittently raises "AssertionError: Unexpected message: ...
    'http.response.start' ..." once a session has multiple in-flight requests.
    See https://github.com/jlowin/fastmcp/issues/858 and
    https://github.com/modelcontextprotocol/python-sdk/issues/883
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Only HTTP requests carry auth; pass lifespan/websocket scopes straight through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        path = request.url.path

        # Skip auth for dashboard pages (protected by HA auth) or when disabled.
        if path in ("/", "/api/status") or not config.mcp_auth_enabled:
            await self.app(scope, receive, send)
            return

        # Check for Authorization header
        auth_header = request.headers.get("Authorization", "")

        # Log headers for debugging (only on the MCP endpoint)
        if path == MCP_PATH:
            logger.info(f"Auth request to {path}")
            logger.info(f"Authorization header: {auth_header[:50] if auth_header else 'MISSING'}...")

        async def deny(content: str) -> None:
            response = Response(
                content=content,
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="MCP"'},
            )
            await response(scope, receive, send)

        if not auth_header:
            await deny("Missing Authorization header")
            return

        token = None

        # Try Bearer token first
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            logger.debug("Using Bearer authentication")

        # Try Basic auth (client_id:client_secret)
        elif auth_header.startswith("Basic "):
            import base64
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                # Format is client_id:client_secret, we use client_secret as the token
                parts = decoded.split(":", 1)
                if len(parts) == 2:
                    # Use the secret (second part) as the token
                    token = parts[1]
                    logger.debug("Using Basic authentication (client_secret)")
                else:
                    token = decoded
                    logger.debug("Using Basic authentication (single value)")
            except Exception as e:
                logger.error(f"Failed to decode Basic auth: {e}")

        if not token:
            await deny("Invalid Authorization header format")
            return

        if token != config.mcp_auth_token:
            logger.warning(f"Invalid token received (length: {len(token)})")
            await deny("Invalid token")
            return

        logger.debug("Authentication successful")
        await self.app(scope, receive, send)

# Configure logging
log_level = getattr(logging, config.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Create the MCP server
mcp = FastMCP("Homebox Inventory")

# Create the Homebox client
client = HomeboxClient(config)

# Register all tools
register_tools(mcp, client)

# Track connected clients
connected_clients: set[str] = set()
server_start_time = datetime.now()


@mcp.resource("homebox://info")
async def get_server_info() -> str:
    """Information about the Homebox MCP server."""
    return f"""# Homebox MCP Server

MCP Server connected to Homebox at: {config.homebox_url}

## Available Tools

### Locations
- homebox_list_locations - List all locations (flat list)
- homebox_get_location_tree - Get full location hierarchy tree
- homebox_get_location - Get location details with parent/children
- homebox_create_location - Create new location
- homebox_update_location - Update location
- homebox_delete_location - Remove location

### Items
- homebox_list_items - List items (with filters)
- homebox_get_item - Get item details
- homebox_search - Search for items
- homebox_create_item - Create new item
- homebox_update_item - Update item
- homebox_move_item - Move item to another location
- homebox_add_item_attachment - Attach a photo or document (e.g. PDF manual/receipt) to an item
- homebox_add_item_attachment_from_url - Attach a photo or document fetched from a URL to an item
- homebox_delete_item - Remove item

### Labels
- homebox_list_labels - List all labels
- homebox_create_label - Create new label
- homebox_update_label - Update label
- homebox_delete_label - Remove label

### Statistics
- homebox_get_statistics - Inventory statistics
"""


async def get_status_data() -> dict[str, Any]:
    """Get status data for the dashboard."""
    status = {
        "homebox_url": config.homebox_url,
        "homebox_connected": False,
        "homebox_error": None,
        "locations_count": 0,
        "items_count": 0,
        "labels_count": 0,
        "server_uptime": str(datetime.now() - server_start_time).split(".")[0],
        "mcp_endpoint": MCP_PATH,
        "mcp_auth_enabled": config.mcp_auth_enabled,
    }

    try:
        # Test connection and get counts
        locations = await client.get_locations()
        status["locations_count"] = len(locations)
        status["homebox_connected"] = True

        items = await client.get_items()
        status["items_count"] = len(items)

        labels = await client.get_labels()
        status["labels_count"] = len(labels)

    except Exception as e:
        status["homebox_connected"] = False
        status["homebox_error"] = str(e)
        logger.error(f"Error connecting to Homebox: {e}")

    return status


async def homepage(request):
    """Serve the status dashboard."""
    status = await get_status_data()

    connection_status = "✅ Connected" if status["homebox_connected"] else "❌ Disconnected"
    connection_class = "connected" if status["homebox_connected"] else "disconnected"
    error_html = ""
    if status["homebox_error"]:
        error_html = f'<p class="error">Error: {status["homebox_error"]}</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Homebox MCP Server</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e8e8e8;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding: 40px 20px;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 2.5rem;
            font-weight: 300;
            color: #00d9ff;
            text-shadow: 0 0 30px rgba(0, 217, 255, 0.3);
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #8892b0;
            font-size: 1.1rem;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 24px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }}
        .card-title {{
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #8892b0;
            margin-bottom: 12px;
        }}
        .card-value {{
            font-size: 2.5rem;
            font-weight: 600;
            color: #00d9ff;
        }}
        .card-value.connected {{
            color: #00ff88;
        }}
        .card-value.disconnected {{
            color: #ff4757;
        }}
        .status-card {{
            grid-column: 1 / -1;
        }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }}
        .status-item {{
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}
        .status-label {{
            font-size: 0.85rem;
            color: #8892b0;
        }}
        .status-value {{
            font-size: 1.1rem;
            color: #e8e8e8;
            word-break: break-all;
        }}
        .error {{
            background: rgba(255, 71, 87, 0.2);
            border: 1px solid rgba(255, 71, 87, 0.5);
            border-radius: 8px;
            padding: 12px;
            margin-top: 15px;
            color: #ff6b7a;
        }}
        .endpoint-box {{
            background: rgba(0, 217, 255, 0.1);
            border: 1px solid rgba(0, 217, 255, 0.3);
            border-radius: 12px;
            padding: 24px;
            margin-top: 30px;
        }}
        .endpoint-box h3 {{
            color: #00d9ff;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        .endpoint-section {{
            margin-bottom: 10px;
        }}
        .endpoint-label {{
            font-size: 0.9rem;
            color: #e8e8e8;
            margin-bottom: 8px;
            font-weight: 500;
        }}
        .endpoint-url {{
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 12px 15px;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 0.9rem;
            color: #00ff88;
            word-break: break-all;
        }}
        .endpoint-hint {{
            margin-top: 8px;
            color: #8892b0;
            font-size: 0.85rem;
        }}
        .info-box {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 15px;
            font-size: 0.9rem;
            color: #e8e8e8;
        }}
        .info-box code {{
            background: rgba(0, 217, 255, 0.2);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 0.85rem;
            color: #00d9ff;
        }}
        .tools-section {{
            margin-top: 30px;
        }}
        .tools-section h3 {{
            color: #00d9ff;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        .tools-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
        }}
        .tool-item {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 15px;
        }}
        .tool-name {{
            font-family: 'Fira Code', 'Consolas', monospace;
            color: #00d9ff;
            font-size: 0.9rem;
            margin-bottom: 5px;
        }}
        .tool-desc {{
            color: #8892b0;
            font-size: 0.85rem;
        }}
        footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: #8892b0;
            font-size: 0.9rem;
        }}
        footer a {{
            color: #00d9ff;
            text-decoration: none;
        }}
        footer a:hover {{
            text-decoration: underline;
        }}
        .refresh-btn {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #00d9ff;
            color: #1a1a2e;
            border: none;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            font-size: 1.5rem;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(0, 217, 255, 0.4);
            transition: transform 0.3s ease;
        }}
        .refresh-btn:hover {{
            transform: scale(1.1);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📦 Homebox MCP Server</h1>
            <p class="subtitle">Model Context Protocol for inventory management</p>
        </header>

        <div class="cards">
            <div class="card status-card">
                <div class="card-title">Connection Status</div>
                <div class="card-value {connection_class}">{connection_status}</div>
                {error_html}
                <div class="status-grid">
                    <div class="status-item">
                        <span class="status-label">Homebox URL</span>
                        <span class="status-value">{status["homebox_url"]}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Server Uptime</span>
                        <span class="status-value">{status["server_uptime"]}</span>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">📍 Locations</div>
                <div class="card-value">{status["locations_count"]}</div>
            </div>

            <div class="card">
                <div class="card-title">📦 Items</div>
                <div class="card-value">{status["items_count"]}</div>
            </div>

            <div class="card">
                <div class="card-title">🏷️ Labels</div>
                <div class="card-value">{status["labels_count"]}</div>
            </div>
        </div>

        <div class="endpoint-box">
            <h3>🔌 MCP Configuration</h3>
            
            <div class="endpoint-section">
                <div class="endpoint-label">🔐 MCP Authentication</div>
                <div class="endpoint-url" style="color: {'#00ff88' if status['mcp_auth_enabled'] else '#ff6b7a'};">
                    {'🔒 ENABLED' if status['mcp_auth_enabled'] else '🔓 DISABLED - Endpoint is open'}
                </div>
            </div>
            
            <div class="info-box" style="margin-top: 20px; background: rgba(0, 217, 255, 0.1); border-color: rgba(0, 217, 255, 0.3);">
                <strong>🎲 Token Generator</strong>
                <p style="margin-top: 10px; color: #8892b0;">Generate a secure token and copy to addon settings:</p>
                <div style="margin: 15px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <button onclick="generateToken()" style="background: #00d9ff; color: #1a1a2e; border: none; border-radius: 8px; padding: 12px 20px; cursor: pointer; font-weight: bold;">🎲 Generate Token</button>
                    <input type="text" id="generatedToken" readonly placeholder="Click Generate" style="flex: 1; min-width: 200px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 12px; color: #00ff88; font-family: monospace;">
                    <button onclick="copyToken()" style="background: rgba(255,255,255,0.1); color: #e8e8e8; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 12px 20px; cursor: pointer;">📋 Copy</button>
                </div>
                <p style="color: #8892b0; font-size: 0.9rem;">After copying, paste in <strong>addon settings</strong> → <code>mcp_auth_token</code> field</p>
            </div>
            
            {'<div class="info-box" style="margin-top: 15px; background: rgba(0, 255, 136, 0.1); border-color: rgba(0, 255, 136, 0.3);"><strong>✅ Token configured</strong><p style="margin-top: 8px; color: #8892b0;">Use the same token in Claude.ai → <strong>OAuth Client Secret</strong> field</p></div>' if status['mcp_auth_enabled'] and config.mcp_auth_token else ('<div class="info-box" style="margin-top: 15px; background: rgba(255, 200, 50, 0.1); border-color: rgba(255, 200, 50, 0.3);"><strong>⚠️ Token not configured</strong><p style="margin-top: 8px; color: #8892b0;">Generate a token above and configure in <code>mcp_auth_token</code> in addon options.</p></div>' if status['mcp_auth_enabled'] else '<div class="info-box" style="margin-top: 15px; background: rgba(255, 107, 122, 0.1); border-color: rgba(255, 107, 122, 0.3);"><strong>⚠️ Authentication disabled</strong><p style="margin-top: 8px; color: #8892b0;">Recommended: enable <code>mcp_auth_enabled</code> and configure a token.</p></div>')}
            
            <div class="endpoint-section" style="margin-top: 20px;">
                <div class="endpoint-label">📍 Internal Address (for Cloudflare Tunnel configuration)</div>
                <div class="endpoint-url">http://homeassistant:8099</div>
                <p class="endpoint-hint">
                    Use this address in Cloudflare Tunnel → Additional hosts → Service
                </p>
            </div>
            
            <div class="endpoint-section" style="margin-top: 20px;">
                <div class="endpoint-label">🌐 Address for Claude.ai</div>
                <div class="endpoint-url">https://your-domain.com<span style="color: #00ff88;">/mcp</span></div>
                <p class="endpoint-hint">
                    After configuring the tunnel, use your domain address + <strong>/mcp</strong> in Claude.ai
                    (the old <code>/sse</code> path still works as an alias)
                </p>
            </div>
            
            <div class="info-box" style="margin-top: 20px;">
                <strong>📋 Setup steps:</strong>
                <ol style="margin: 10px 0 0 20px; color: #8892b0;">
                    <li>Click <strong>🎲 Generate Token</strong> above and copy</li>
                    <li>In addon settings: enable <code>mcp_auth_enabled</code> and paste the token in <code>mcp_auth_token</code></li>
                    <li>Configure Cloudflare Tunnel → <code>http://&lt;addon-hostname&gt;:8099</code> (the hostname shown on the add-on's Info tab)</li>
                    <li>In Claude.ai (Customize → Connectors → Add custom connector):
                        <ul style="margin-top: 5px;">
                            <li>URL: <code>https://your-domain.com/mcp</code>, Transport: <strong>Streamable HTTP</strong></li>
                            <li>Authentication: <strong>No sign-in</strong></li>
                            <li>Request headers → <code>authorization</code> = <code>Bearer &lt;token&gt;</code> (with the space)</li>
                        </ul>
                    </li>
                </ol>
            </div>
        </div>

        <div class="tools-section">
            <h3>🛠️ Available Tools</h3>
            <div class="tools-grid">
                <div class="tool-item">
                    <div class="tool-name">homebox_list_locations</div>
                    <div class="tool-desc">List all locations (flat list)</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_get_location_tree</div>
                    <div class="tool-desc">Get full hierarchy tree</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_get_location</div>
                    <div class="tool-desc">Get location details</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_create_location</div>
                    <div class="tool-desc">Create new location</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_update_location</div>
                    <div class="tool-desc">Update location</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_delete_location</div>
                    <div class="tool-desc">Delete location</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_list_items</div>
                    <div class="tool-desc">List items with filters</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_get_item</div>
                    <div class="tool-desc">Get complete item details</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_search</div>
                    <div class="tool-desc">Search for items</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_create_item</div>
                    <div class="tool-desc">Create new item</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_update_item</div>
                    <div class="tool-desc">Update item fields</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_move_item</div>
                    <div class="tool-desc">Move item to another location</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_add_item_attachment</div>
                    <div class="tool-desc">Attach a photo or document to an item</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_add_item_attachment_from_url</div>
                    <div class="tool-desc">Attach a photo or document fetched from a URL</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_delete_item</div>
                    <div class="tool-desc">Delete item</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_list_labels</div>
                    <div class="tool-desc">List all labels</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_create_label</div>
                    <div class="tool-desc">Create new label</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_update_label</div>
                    <div class="tool-desc">Update label</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_delete_label</div>
                    <div class="tool-desc">Delete label</div>
                </div>
                <div class="tool-item">
                    <div class="tool-name">homebox_get_statistics</div>
                    <div class="tool-desc">Inventory statistics</div>
                </div>
            </div>
        </div>

        <footer>
            <p>
                <a href="https://github.com/oangelo/homebox-mcp" target="_blank">GitHub</a> ·
                Designed for use with the <a href="https://github.com/Crafter-Y/homebox-addon" target="_blank">Homebox HA Addon</a>
            </p>
        </footer>
    </div>

    <button class="refresh-btn" onclick="location.reload()" title="Refresh">↻</button>

    <script>
        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);
        
        // Generate a secure random token (client-side)
        function generateToken() {{
            const array = new Uint8Array(32);
            crypto.getRandomValues(array);
            const token = Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
            document.getElementById('generatedToken').value = token;
        }}
        
        // Copy token to clipboard
        function copyToken() {{
            const input = document.getElementById('generatedToken');
            if (!input.value) {{
                alert('Generate a token first!');
                return;
            }}
            navigator.clipboard.writeText(input.value).then(() => {{
                alert('Token copied!\\n\\nNow paste in addon settings:\\n→ mcp_auth_token\\n\\nAnd also in Claude.ai:\\n→ OAuth Client Secret');
            }});
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(html)


async def api_status(request):
    """API endpoint for status data."""
    status = await get_status_data()
    return JSONResponse(status)


# Build the MCP ASGI app once so we can reuse its lifespan.
# IMPORTANT: FastMCP starts its session manager inside the app's lifespan.
# When mounting it under a custom Starlette app, that lifespan MUST be passed
# to the parent app, otherwise the first request fails with
# "RuntimeError: Task group is not initialized" (nested lifespans are ignored).
#
# transport="http" (Streamable HTTP) rather than the legacy "sse" transport:
# the old SSE transport splits a session across two independent HTTP requests
# (a long-lived GET stream that hands out a session_id, plus separate POST
# .../messages?session_id=... calls) with no server-side check that the GET
# side has actually finished the initialize handshake before POSTs on that
# session are accepted. If a client (re)opens a second GET/sse connection —
# which mcp-remote can do — requests can race and land on a session before it
# is marked initialized, raising "Received request before initialization was
# complete" and making every tool call fail. Streamable HTTP uses a single
# endpoint keyed by an `Mcp-Session-Id` header instead of two endpoints
# racing over a session_id query param, which avoids this class of bug.
# See https://github.com/modelcontextprotocol/python-sdk/issues/423 and
# https://github.com/modelcontextprotocol/python-sdk/issues/1844.
# The endpoint lives at `/mcp` (the conventional Streamable HTTP path; Claude.ai
# warns that a URL ending in `/sse` will use the deprecated SSE transport).
# `/sse` is kept as an alias by rewriting the path in `LegacyPathAlias`, so
# existing mcp-remote / Claude.ai configs keep working without changes.
MCP_PATH = "/mcp"
LEGACY_MCP_PATH = "/sse"
mcp_app = mcp.http_app(transport="http", path=MCP_PATH)


class LegacyPathAlias:
    """Rewrite requests for the legacy `/sse` path onto the `/mcp` endpoint."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == LEGACY_MCP_PATH:
            scope = dict(scope)
            scope["path"] = MCP_PATH
            scope["raw_path"] = MCP_PATH.encode()
        await self.app(scope, receive, send)


# Create custom Starlette app with MCP mounted and auth middleware
app = Starlette(
    routes=[
        Route("/", homepage),
        Route("/api/status", api_status),
        Mount("/", app=mcp_app),
    ],
    middleware=[
        Middleware(LegacyPathAlias),
        Middleware(BearerAuthMiddleware),
    ],
    lifespan=mcp_app.lifespan,
)


if __name__ == "__main__":
    logger.info(f"Starting Homebox MCP Server on {config.server_host}:{config.server_port}")
    logger.info(f"Connecting to Homebox at: {config.homebox_url}")
    logger.info(f"Dashboard available at: http://{config.server_host}:{config.server_port}/")
    logger.info(f"MCP endpoint (Streamable HTTP) at: http://{config.server_host}:{config.server_port}{MCP_PATH} (alias {LEGACY_MCP_PATH})")

    if config.mcp_auth_enabled:
        logger.info("MCP Authentication: ENABLED - Bearer token required")
    else:
        logger.warning("MCP Authentication: DISABLED - Endpoint is open to anyone")

    uvicorn.run(
        app,
        host=config.server_host,
        port=config.server_port,
        log_level=config.log_level.lower(),
    )
