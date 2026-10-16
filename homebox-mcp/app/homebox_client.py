"""HTTP client for the Homebox API.

Homebox v0.26.0 introduced a breaking API change ("entity merge"): the
separate ``/items`` and ``/locations`` endpoints were removed and replaced by a
unified ``/entities`` API, and ``/labels`` became ``/tags``. See:
https://homebox.software/en/advanced/entity-merge-upgrade/

To keep working against every Homebox version, this client auto-detects which
API the server speaks on first use and transparently routes each call to the
right endpoints, normalizing the new "entity" objects back to the item/location
shape the rest of the addon (and the MCP tools) already expect.
"""

import asyncio
import ipaddress
import logging
import re
import socket
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from config import Config

logger = logging.getLogger(__name__)

# Number of entities to request per page when listing. Home inventories are
# small, so a single large page avoids paginating in the common case.
_ENTITIES_PAGE_SIZE = 10000

# Cap on uploaded attachment size. Matches Homebox's own default
# HBOX_WEB_MAX_UPLOAD_SIZE (10 MB) so oversized uploads are rejected locally
# with a clear message instead of a generic error from the server (whose
# actual configured limit may differ).
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Guards for add_item_attachment_from_url()'s server-side fetch of an
# LLM-supplied URL: cap on redirect hops followed, and a descriptive
# User-Agent (some image hosts/CDNs reject the default httpx one).
_MAX_REDIRECTS = 5
_DOWNLOAD_USER_AGENT = "homebox-mcp (+https://github.com/beausmith/homebox-mcp)"

# Homebox's own field length limits (Ent schema `.MaxLen()`, the real DB
# constraint). Some of these (name, description) are also cleanly rejected
# by Homebox's own request validator; others (notes, serial_number,
# warranty_details, sold_notes, color) are enforced only at the DB layer and
# fail with an opaque server error instead of a clean 4xx if exceeded — this
# map lets _check_max_length() catch both cases locally with a clear message.
_MAX_FIELD_LENGTHS: dict[str, int] = {
    "name": 255,
    "description": 1000,
    "notes": 1000,
    "serial_number": 255,
    "model_number": 255,
    "manufacturer": 255,
    "warranty_details": 1000,
    "purchase_from": 255,
    "sold_to": 255,
    "sold_notes": 1000,
    "color": 255,
}

# Extensions that are unambiguously NOT one of the supported attachment
# formats (JPEG/PNG/GIF/WEBP/HEIC/PDF). Used only as a fail-fast optimization
# in add_item_attachment_from_url() to skip downloading a URL that's
# obviously the wrong type — NOT a security boundary (a URL's extension is
# just a name and proves nothing about the actual content). The real gate
# is always _sniff_file() on the downloaded bytes. Deliberately not an
# allowlist: most legitimate image URLs (CDNs, Wikipedia, search results)
# have no extension at all or a query string after it, so only extensions
# recognized here as clearly wrong are rejected early — anything else
# (missing, unknown, or a supported one) proceeds to download + sniff.
_DISALLOWED_URL_EXTENSIONS = frozenset({
    # executables / installers
    "exe", "msi", "dmg", "apk", "bat", "sh", "bin", "deb", "rpm", "app",
    # archives
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz",
    # video
    "mp4", "mov", "avi", "mkv", "webm", "flv", "wmv", "m4v",
    # audio
    "mp3", "wav", "ogg", "flac", "m4a", "aac", "wma",
    # other documents / data / code
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "json",
    "xml", "html", "htm", "js", "css",
})

# Magic-byte signatures for the file formats accepted by
# HomeboxClient.add_item_attachment(). Detecting the real format from the
# file's content (rather than trusting a caller-supplied filename/content-type)
# means the upload is validated before anything is sent to Homebox.
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGICS = (b"GIF87a", b"GIF89a")
_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1")
_PDF_MAGIC = b"%PDF-"

# Homebox's attachment.Type enum values a caller may set explicitly
# ("thumbnail" is server-generated and deliberately excluded).
_VALID_ATTACHMENT_TYPES = frozenset({"photo", "manual", "warranty", "receipt", "attachment"})

# Every id a tool accepts is interpolated into a URL path. Homebox ids are
# UUIDs, so anything else is rejected before a request is built (an LLM
# supplied "../" or a stray query string must never reach the URL).
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Homebox returns this for a date field that was never set ("0001-01-01T...").
# Sending it back is harmless, but omitting it keeps the field empty and the
# payload readable.
_EMPTY_DATE_PREFIX = "0001-"

# Every scalar that PUT /entities/{id} (repo.EntityUpdate) accepts, per the
# Homebox v0.26.2 swagger. Used by _full_entity_body() so a full-replacement
# PUT never silently blanks a field the caller did not mention.
_ENTITY_SCALAR_FIELDS = (
    "name",
    "description",
    "quantity",
    "insured",
    "archived",
    "assetId",
    "serialNumber",
    "modelNumber",
    "manufacturer",
    "lifetimeWarranty",
    "warrantyExpires",
    "warrantyDetails",
    "purchasePrice",
    "purchaseDate",
    "purchaseFrom",
    "soldDate",
    "soldTo",
    "soldPrice",
    "soldNotes",
    "notes",
    "syncChildEntityLocations",
)


def _validate_id(value: str, name: str = "id") -> str:
    """Return `value` if it looks like a UUID, else raise ValueError."""
    if not isinstance(value, str) or not _UUID_RE.match(value):
        raise ValueError(f"Invalid {name}: expected a UUID, got {value!r}")
    return value


class HomeboxClient:
    """Async HTTP client for interacting with the Homebox API."""

    def __init__(self, config: Config):
        """Initialize the Homebox client.

        Args:
            config: Configuration object with Homebox connection details.
        """
        self.config = config
        self.base_url = config.api_base_url
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None
        # API flavor: None = not detected yet, "entities" = v0.26.0+, "legacy" = older.
        self._api_mode: str | None = None
        # Cached entity-type ids (entities mode only), resolved lazily.
        self._item_type_id: str | None = None
        self._location_type_id: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid authentication token."""
        if self._token is None:
            if not self.config.homebox_token:
                raise ValueError("Homebox API token not configured. Please set homebox_token in addon settings.")
            self._token = self.config.homebox_token
            logger.info("Using configured API token for Homebox authentication")

    def _get_headers(self) -> dict[str, str]:
        """Get headers for authenticated requests."""
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated request to the Homebox API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint (without base URL).
            **kwargs: Additional arguments to pass to httpx.

        Returns:
            JSON response data.
        """
        await self._ensure_authenticated()
        client = await self._get_client()

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        response = await client.request(method, url, headers=headers, **kwargs)

        # Handle authentication errors
        if response.status_code == 401:
            logger.error("Authentication failed. Please check your Homebox API token.")
            raise ValueError("Invalid or expired Homebox API token. Please generate a new token in Homebox settings.")

        if response.status_code >= 400:
            # Report the status, the relative endpoint and Homebox's own error
            # text (useful for the calling model to self-correct, e.g. a 422
            # validation message) - never the full URL, headers or token.
            detail = response.text[:300].strip()
            raise ValueError(
                f"Homebox API returned HTTP {response.status_code} for {method} {endpoint}"
                + (f": {detail}" if detail else "")
            )

        if response.status_code == 204:
            return None

        return response.json()

    # =========================================================================
    # API mode detection (legacy /items vs new /entities)
    # =========================================================================

    async def _get_api_mode(self) -> str:
        """Detect which Homebox API flavor the server speaks.

        Probes the ``/entities`` endpoint introduced in Homebox v0.26.0. If it
        exists, the modern unified API is used; otherwise we fall back to the
        legacy ``/items`` / ``/locations`` / ``/labels`` endpoints.

        Returns:
            Either "entities" (v0.26.0+) or "legacy".
        """
        if self._api_mode is None:
            await self._ensure_authenticated()
            client = await self._get_client()
            url = f"{self.base_url}/entities"
            response = await client.request(
                "GET", url, headers=self._get_headers(), params={"pageSize": 1}
            )

            if response.status_code == 401:
                raise ValueError(
                    "Invalid or expired Homebox API token. Please generate a new token in Homebox settings."
                )

            if response.status_code == 404:
                self._api_mode = "legacy"
            else:
                response.raise_for_status()
                self._api_mode = "entities"

            logger.info("Detected Homebox API mode: %s", self._api_mode)

        return self._api_mode

    async def _get_entity_type_id(self, is_location: bool) -> str | None:
        """Resolve an entity-type id for items or locations (entities mode).

        In the unified model, whether an entity behaves as a container
        (location) or a regular item is determined by its entity type's
        ``isLocation`` flag. Homebox seeds default types on migration; we pick
        the first matching one and cache it.

        Args:
            is_location: True to resolve a location type, False for an item type.

        Returns:
            The entity-type id, or None if none could be resolved (the server
            may then apply its own default).
        """
        cached = self._location_type_id if is_location else self._item_type_id
        if cached is not None:
            return cached

        types = await self._request("GET", "/entity-types")
        match = next(
            (t for t in (types or []) if bool(t.get("isLocation")) == is_location),
            None,
        )
        type_id = match.get("id") if match else None

        if is_location:
            self._location_type_id = type_id
        else:
            self._item_type_id = type_id

        if type_id is None:
            logger.warning(
                "No entity type found with isLocation=%s; the server default will be used.",
                is_location,
            )
        return type_id

    # =========================================================================
    # Normalization helpers (entities mode -> legacy item/location shape)
    # =========================================================================

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Expand a bare "YYYY-MM-DD" date into the full ISO 8601 timestamp
        Homebox's date fields (``purchaseTime``/``purchaseDate``, etc.)
        expect. Anything already containing a time component is passed
        through unchanged.
        """
        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
            return f"{date_str}T00:00:00.000Z"
        return date_str

    @staticmethod
    def _check_max_length(field_name: str, value: str | None) -> None:
        """Raise ValueError if `value` exceeds Homebox's known limit for
        `field_name`. Homebox enforces this cleanly for some fields (name,
        description) but only at the DB layer for others (notes,
        serial_number, warranty_details, sold_notes, color), where an
        over-limit value fails with an opaque server error instead of a
        clean validation message — checking client-side avoids that
        regardless of which Homebox API mode is active.
        """
        if value is None:
            return
        limit = _MAX_FIELD_LENGTHS[field_name]
        if len(value) > limit:
            raise ValueError(
                f"{field_name} exceeds Homebox's {limit}-character limit "
                f"({len(value)} characters given)."
            )

    @staticmethod
    def _normalize_item(entity: dict[str, Any]) -> dict[str, Any]:
        """Map an entity object to the legacy item shape expected by the tools."""
        parent = entity.get("parent") or {}
        tags = entity.get("tags") or []
        normalized = {
            "id": entity.get("id"),
            "name": entity.get("name"),
            "description": entity.get("description", ""),
            "quantity": entity.get("quantity", 1),
            "location": {"id": parent.get("id"), "name": parent.get("name")},
            "labels": [{"id": t.get("id"), "name": t.get("name")} for t in tags],
            "insured": entity.get("insured", False),
            "archived": entity.get("archived", False),
        }
        # Preserve extra detail fields (serial number, price, etc.) for get_item.
        for key in (
            "assetId",
            "serialNumber",
            "modelNumber",
            "manufacturer",
            "lifetimeWarranty",
            "warrantyExpires",
            "warrantyDetails",
            "purchasePrice",
            "purchaseDate",
            "purchaseFrom",
            "soldDate",
            "soldTo",
            "soldPrice",
            "soldNotes",
            "notes",
            "createdAt",
            "updatedAt",
            "imageId",
            "attachments",
            "entityType",
            "fields",
            "syncChildEntityLocations",
        ):
            if key in entity:
                normalized[key] = entity[key]
        return normalized

    @staticmethod
    def _full_entity_body(current: dict[str, Any]) -> dict[str, Any]:
        """Build a complete ``PUT /entities/{id}`` payload from an entity's
        current state (entities mode only).

        Homebox's entity update is a full replacement, not a patch: every
        field missing from the payload is reset server-side. This copies
        every scalar ``repo.EntityUpdate`` accepts, keeps the parent, the
        entity type, the tags (``tags`` objects -> ``tagIds``) and the custom
        ``fields`` list, and drops Homebox's "never set" date sentinel so
        empty dates stay empty. Callers overlay their changes on top.
        """
        body: dict[str, Any] = {"id": current.get("id")}
        for key in _ENTITY_SCALAR_FIELDS:
            if key not in current:
                continue
            value = current[key]
            if isinstance(value, str) and value.startswith(_EMPTY_DATE_PREFIX):
                continue
            body[key] = value
        parent = current.get("parent") or {}
        if parent.get("id"):
            body["parentId"] = parent["id"]
        entity_type = current.get("entityType") or {}
        if entity_type.get("id"):
            body["entityTypeId"] = entity_type["id"]
        body["tagIds"] = [t["id"] for t in (current.get("tags") or []) if t.get("id")]
        body["fields"] = current.get("fields") or []
        return body

    async def _list_entities(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """List entities (entities mode), returning the raw item array."""
        query: dict[str, Any] = {"pageSize": _ENTITIES_PAGE_SIZE}
        query.update(params)
        response = await self._request("GET", "/entities", params=query)
        if isinstance(response, dict) and "items" in response:
            return response["items"]
        return response or []

    # =========================================================================
    # Locations
    # =========================================================================

    async def get_locations(self) -> list[dict[str, Any]]:
        """Get all locations.

        Returns:
            List of location objects.
        """
        if await self._get_api_mode() == "legacy":
            return await self._request("GET", "/locations")

        # The plain (unfiltered) entities list excludes locations entirely
        # by default on the Homebox server side, for backward compatibility
        # with the old /items endpoint's behavior — there is no client-side
        # way to recover them from that call. ?isLocation=true is required
        # to get location entities back (and is also what makes the server
        # populate itemCount on each result).
        return await self._list_entities({"isLocation": True})

    async def get_location_tree(self) -> list[dict[str, Any]]:
        """Get the complete location hierarchy as a nested tree.

        Returns:
            List of root locations (no parent), each with a nested
            ``children`` array. Every node has id, name, description,
            item_count, children.
        """
        locations = await self.get_locations()

        if await self._get_api_mode() == "entities":
            return await self._get_location_tree_entities(locations)

        # The legacy /locations list doesn't include parent info (a
        # long-standing Homebox limitation), so each location's full
        # record must be fetched individually to learn its parent.
        parent_of: dict[str, str | None] = {}
        for loc in locations:
            detail = await self.get_location(loc["id"])
            parent = detail.get("parent")
            parent_of[loc["id"]] = parent.get("id") if parent else None

        nodes: dict[str, dict[str, Any]] = {
            loc["id"]: {
                "id": loc["id"],
                "name": loc.get("name"),
                "description": loc.get("description", ""),
                "item_count": loc.get("itemCount", 0),
                "children": [],
            }
            for loc in locations
        }

        roots: list[dict[str, Any]] = []
        for loc_id, node in nodes.items():
            parent_id = parent_of.get(loc_id)
            if parent_id and parent_id in nodes:
                nodes[parent_id]["children"].append(node)
            else:
                roots.append(node)

        return roots

    async def _get_location_tree_entities(
        self, locations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Entities-mode (Homebox v0.26+) implementation of get_location_tree().

        On Homebox v0.26.2 neither ``GET /entities?isLocation=true`` nor
        ``GET /entities/{id}`` carries ``parent`` or ``itemCount`` for a
        location, so building the tree from parent links flattens every
        nested location. The hierarchy therefore comes from
        ``GET /entities/tree`` (the endpoint the Homebox UI itself uses) and
        item counts are derived from the item list.
        """
        by_id = {loc.get("id"): loc for loc in locations}

        counts: dict[str, int] = {}
        for item in await self.get_items():
            parent_id = (item.get("location") or {}).get("id")
            if parent_id:
                counts[parent_id] = counts.get(parent_id, 0) + 1

        tree = await self._request("GET", "/entities/tree")

        def convert(node: dict[str, Any]) -> dict[str, Any]:
            node_id = node.get("id")
            loc = by_id.get(node_id, {})
            return {
                "id": node_id,
                "name": node.get("name", loc.get("name")),
                "description": loc.get("description", ""),
                "item_count": counts.get(node_id, 0),
                "children": [
                    convert(child)
                    for child in node.get("children") or []
                    if (child.get("type") or "location") == "location"
                ],
            }

        return [
            convert(node)
            for node in tree or []
            if (node.get("type") or "location") == "location"
        ]

    @staticmethod
    def _find_in_tree(
        nodes: list[dict[str, Any]], wanted: str, parent: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, dict[str, Any]] | None:
        """Depth-first search of a /entities/tree result for `wanted`.

        Returns (parent_node_or_None, node) or None if not found.
        """
        for node in nodes:
            if node.get("id") == wanted:
                return parent, node
            found = HomeboxClient._find_in_tree(node.get("children") or [], wanted, node)
            if found:
                return found
        return None

    async def get_location(self, location_id: str) -> dict[str, Any]:
        """Get a specific location by ID.

        Args:
            location_id: The location UUID.

        Returns:
            Location object (with parent/children when available).
        """
        _validate_id(location_id, "location_id")
        if await self._get_api_mode() == "legacy":
            return await self._request("GET", f"/locations/{location_id}")

        entity = await self._request("GET", f"/entities/{location_id}")

        # Homebox v0.26.2's entity detail carries neither `parent` nor
        # `children` for a location; fill both in from /entities/tree so
        # callers (and update_location's parent preservation) still work.
        if "parent" not in entity or "children" not in entity:
            try:
                tree = await self._request("GET", "/entities/tree")
            except ValueError as exc:
                logger.warning("Could not load the location tree: %s", exc)
                tree = None
            found = self._find_in_tree(tree or [], location_id)
            if found:
                parent, node = found
                if "parent" not in entity:
                    entity["parent"] = (
                        {"id": parent.get("id"), "name": parent.get("name")} if parent else None
                    )
                if "children" not in entity:
                    entity["children"] = [
                        {"id": c.get("id"), "name": c.get("name"), "type": c.get("type")}
                        for c in node.get("children") or []
                    ]
        return entity

    async def create_location(
        self,
        name: str,
        description: str | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new location.

        Args:
            name: Location name (max 255 characters).
            description: Optional description (max 1000 characters).
            parent_id: Optional parent location ID for hierarchy.

        Returns:
            Created location object.
        """
        self._check_max_length("name", name)
        self._check_max_length("description", description)
        if parent_id:
            _validate_id(parent_id, "parent_id")

        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description
        if parent_id:
            data["parentId"] = parent_id

        if await self._get_api_mode() == "legacy":
            return await self._request("POST", "/locations", json=data)

        type_id = await self._get_entity_type_id(is_location=True)
        if type_id:
            data["entityTypeId"] = type_id
        return await self._request("POST", "/entities", json=data)

    async def update_location(
        self,
        location_id: str,
        name: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Update a location.

        Args:
            location_id: The location UUID.
            name: New name (optional, max 255 characters).
            description: New description (optional, max 1000 characters).
            parent_id: New parent location ID (optional).

        Returns:
            Updated location object.
        """
        self._check_max_length("name", name)
        self._check_max_length("description", description)
        _validate_id(location_id, "location_id")
        if parent_id:
            _validate_id(parent_id, "parent_id")

        # Fetch current location to preserve fields not provided.
        current = await self.get_location(location_id)
        current_parent_id = (
            current.get("parent", {}).get("id") if current.get("parent") else None
        )

        data: dict[str, Any] = {
            "name": name if name is not None else current.get("name", ""),
            "description": (
                description if description is not None else current.get("description", "")
            ),
            "parentId": current_parent_id,
        }

        # If parent_id is explicitly provided, use it (empty string clears parent).
        if parent_id is not None:
            data["parentId"] = parent_id or None

        if await self._get_api_mode() == "legacy":
            return await self._request("PUT", f"/locations/{location_id}", json=data)

        # Entities mode: PUT is a full replacement, so start from the
        # location's complete current state (incl. entity type, tags, custom
        # fields) and overlay the requested changes.
        body = self._full_entity_body(current)
        body["id"] = location_id
        body["name"] = data["name"]
        body["description"] = data["description"]
        if data["parentId"]:
            body["parentId"] = data["parentId"]
        else:
            body.pop("parentId", None)
        return await self._request("PUT", f"/entities/{location_id}", json=body)

    async def delete_location(self, location_id: str) -> None:
        """Delete a location.

        Args:
            location_id: The location UUID.
        """
        _validate_id(location_id, "location_id")
        if await self._get_api_mode() == "legacy":
            await self._request("DELETE", f"/locations/{location_id}")
        else:
            await self._request("DELETE", f"/entities/{location_id}")

    # =========================================================================
    # Items
    # =========================================================================

    async def get_items(
        self,
        location_id: str | None = None,
        label_id: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get items with optional filters.

        Args:
            location_id: Filter by location ID.
            label_id: Filter by label ID.
            search: Search term for name/description.

        Returns:
            List of item objects.
        """
        if location_id:
            _validate_id(location_id, "location_id")
        if label_id:
            _validate_id(label_id, "label_id")
        if await self._get_api_mode() == "legacy":
            params: dict[str, str] = {}
            if location_id:
                params["locations"] = location_id
            if label_id:
                params["labels"] = label_id
            if search:
                params["q"] = search

            response = await self._request("GET", "/items", params=params)

            # The API returns {"items": [...]} wrapper
            if isinstance(response, dict) and "items" in response:
                return response["items"]
            return response

        # Entities mode: locations -> parentIds, labels -> tags, search -> q.
        params_e: dict[str, Any] = {}
        if location_id:
            params_e["parentIds"] = [location_id]
        if label_id:
            params_e["tags"] = [label_id]
        if search:
            params_e["q"] = search
        # Explicit for clarity: the server already excludes locations from
        # results when this is omitted (see get_locations), but spelling it
        # out here documents that behavior instead of relying on it silently.
        params_e["isLocation"] = False

        entities = await self._list_entities(params_e)
        return [self._normalize_item(e) for e in entities]

    async def get_item(self, item_id: str) -> dict[str, Any]:
        """Get a specific item by ID.

        Args:
            item_id: The item UUID.

        Returns:
            Item object with full details.
        """
        _validate_id(item_id, "item_id")
        if await self._get_api_mode() == "legacy":
            return await self._request("GET", f"/items/{item_id}")

        entity = await self._request("GET", f"/entities/{item_id}")
        return self._normalize_item(entity)

    async def create_item(
        self,
        name: str,
        location_id: str,
        description: str | None = None,
        quantity: float = 1,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new item.

        Args:
            name: Item name (max 255 characters).
            location_id: Location ID where the item will be stored.
            description: Optional description (max 1000 characters).
            quantity: Item quantity (default: 1). Fractional values (e.g.
                2.5) are supported on Homebox v0.25.0+; older versions
                accept whole numbers only.
            labels: Optional list of label IDs.

        Returns:
            Created item object.
        """
        self._check_max_length("name", name)
        self._check_max_length("description", description)
        _validate_id(location_id, "location_id")
        for label in labels or []:
            _validate_id(label, "label id")

        if await self._get_api_mode() == "legacy":
            data: dict[str, Any] = {
                "name": name,
                "locationId": location_id,
                "quantity": quantity,
            }
            if description:
                data["description"] = description
            if labels:
                data["labelIds"] = labels
            return await self._request("POST", "/items", json=data)

        data = {
            "name": name,
            "parentId": location_id,
            "quantity": quantity,
        }
        if description:
            data["description"] = description
        if labels:
            data["tagIds"] = labels
        type_id = await self._get_entity_type_id(is_location=False)
        if type_id:
            data["entityTypeId"] = type_id
        entity = await self._request("POST", "/entities", json=data)
        return self._normalize_item(entity)

    async def update_item(
        self,
        item_id: str,
        name: str | None = None,
        description: str | None = None,
        quantity: float | None = None,
        location_id: str | None = None,
        labels: list[str] | None = None,
        insured: bool | None = None,
        archived: bool | None = None,
        asset_id: str | None = None,
        serial_number: str | None = None,
        model_number: str | None = None,
        manufacturer: str | None = None,
        lifetime_warranty: bool | None = None,
        warranty_expires: str | None = None,
        warranty_details: str | None = None,
        purchase_price: float | None = None,
        purchase_date: str | None = None,
        purchase_from: str | None = None,
        sold_date: str | None = None,
        sold_to: str | None = None,
        sold_price: float | None = None,
        sold_notes: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Update an item.

        Args:
            item_id: The item UUID.
            name: New name (optional, max 255 characters).
            description: New description (optional, max 1000 characters).
            quantity: New quantity (optional). Fractional values (e.g.
                2.5) are supported on Homebox v0.25.0+; older versions
                accept whole numbers only.
            location_id: New location ID (optional).
            labels: New list of label IDs (optional).
            insured: Insurance status (optional).
            archived: Archive status (optional).
            asset_id: Asset ID (optional).
            serial_number: Serial number (optional, max 255 characters).
            model_number: Model number (optional, max 255 characters).
            manufacturer: Manufacturer (optional, max 255 characters).
            lifetime_warranty: Lifetime warranty flag (optional). Only
                applied in entities mode (Homebox v0.26.0+); ignored
                against the legacy API.
            warranty_expires: Warranty expiration date (optional), as
                "YYYY-MM-DD" or a full ISO 8601 timestamp. Only applied in
                entities mode (Homebox v0.26.0+); ignored against the
                legacy API.
            warranty_details: Warranty details/notes (optional, max 1000
                characters). Only applied in entities mode (Homebox
                v0.26.0+); ignored against the legacy API.
            purchase_price: Purchase price (optional).
            purchase_date: Purchase date (optional), as "YYYY-MM-DD" or a
                full ISO 8601 timestamp. Only applied in entities mode
                (Homebox v0.26.0+); ignored against the legacy API.
            purchase_from: Where the item was purchased (optional, max 255
                characters). Only applied in entities mode (Homebox
                v0.26.0+); ignored against the legacy API.
            sold_date: Date the item was sold (optional), as "YYYY-MM-DD"
                or a full ISO 8601 timestamp. Only applied in entities
                mode (Homebox v0.26.0+); ignored against the legacy API.
            sold_to: Who the item was sold to (optional, max 255
                characters). Only applied in entities mode (Homebox
                v0.26.0+); ignored against the legacy API.
            sold_price: Sale price (optional). Only applied in entities
                mode (Homebox v0.26.0+); ignored against the legacy API.
            sold_notes: Notes about the sale (optional, max 1000
                characters). Only applied in entities mode (Homebox
                v0.26.0+); ignored against the legacy API.
            notes: Notes (optional, max 1000 characters).

        Returns:
            Updated item object.
        """
        self._check_max_length("name", name)
        self._check_max_length("description", description)
        self._check_max_length("notes", notes)
        self._check_max_length("serial_number", serial_number)
        self._check_max_length("model_number", model_number)
        self._check_max_length("manufacturer", manufacturer)
        self._check_max_length("warranty_details", warranty_details)
        self._check_max_length("purchase_from", purchase_from)
        self._check_max_length("sold_to", sold_to)
        self._check_max_length("sold_notes", sold_notes)
        _validate_id(item_id, "item_id")
        if location_id:
            _validate_id(location_id, "location_id")
        for label in labels or []:
            _validate_id(label, "label id")

        if await self._get_api_mode() == "legacy":
            return await self._update_item_legacy(
                item_id=item_id,
                name=name,
                description=description,
                quantity=quantity,
                location_id=location_id,
                labels=labels,
                insured=insured,
                archived=archived,
                asset_id=asset_id,
                serial_number=serial_number,
                model_number=model_number,
                manufacturer=manufacturer,
                purchase_price=purchase_price,
                notes=notes,
            )

        # Entities mode. Homebox's PUT /entities/{id} is a full-replacement
        # update, not a partial patch: any field missing from the payload is
        # reset to its zero value server-side. Start from the entity's
        # complete current state (every scalar, parent, entity type, tags
        # and custom fields - see _full_entity_body) and overlay only what
        # the caller passed.
        current = await self._request("GET", f"/entities/{item_id}")
        data = self._full_entity_body(current)
        data["id"] = item_id
        data.setdefault("name", current.get("name", ""))
        data.setdefault("quantity", current.get("quantity", 1))

        overrides: dict[str, Any] = {
            "name": name,
            "description": description,
            "quantity": quantity,
            "insured": insured,
            "archived": archived,
            "assetId": asset_id,
            "serialNumber": serial_number,
            "modelNumber": model_number,
            "manufacturer": manufacturer,
            "lifetimeWarranty": lifetime_warranty,
            "warrantyExpires": (
                self._normalize_date(warranty_expires) if warranty_expires is not None else None
            ),
            "warrantyDetails": warranty_details,
            "purchasePrice": purchase_price,
            "purchaseDate": (
                self._normalize_date(purchase_date) if purchase_date is not None else None
            ),
            "purchaseFrom": purchase_from,
            "soldDate": self._normalize_date(sold_date) if sold_date is not None else None,
            "soldTo": sold_to,
            "soldPrice": sold_price,
            "soldNotes": sold_notes,
            "notes": notes,
        }
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
        if location_id is not None:
            data["parentId"] = location_id
        if labels is not None:
            data["tagIds"] = labels

        entity = await self._request("PUT", f"/entities/{item_id}", json=data)
        return self._normalize_item(entity)

    async def _update_item_legacy(
        self,
        item_id: str,
        name: str | None,
        description: str | None,
        quantity: float | None,
        location_id: str | None,
        labels: list[str] | None,
        insured: bool | None,
        archived: bool | None,
        asset_id: str | None,
        serial_number: str | None,
        model_number: str | None,
        manufacturer: str | None,
        purchase_price: float | None,
        notes: str | None,
    ) -> dict[str, Any]:
        """Update an item against the legacy ``/items`` endpoint."""
        # First get the current item to preserve existing values
        current = await self._request("GET", f"/items/{item_id}")

        data: dict[str, Any] = {
            "id": item_id,
            "name": name if name is not None else current.get("name", ""),
            "description": (
                description if description is not None else current.get("description", "")
            ),
            "quantity": quantity if quantity is not None else current.get("quantity", 1),
            "locationId": (
                location_id
                if location_id is not None
                else current.get("location", {}).get("id", "")
            ),
        }

        # Handle labels
        if labels is not None:
            data["labelIds"] = labels
        elif current.get("labels"):
            data["labelIds"] = [label["id"] for label in current["labels"]]

        # Optional fields
        if insured is not None:
            data["insured"] = insured
        if archived is not None:
            data["archived"] = archived
        if asset_id is not None:
            data["assetId"] = asset_id
        if serial_number is not None:
            data["serialNumber"] = serial_number
        if model_number is not None:
            data["modelNumber"] = model_number
        if manufacturer is not None:
            data["manufacturer"] = manufacturer
        if purchase_price is not None:
            data["purchasePrice"] = purchase_price
        if notes is not None:
            data["notes"] = notes

        return await self._request("PUT", f"/items/{item_id}", json=data)

    async def delete_item(self, item_id: str) -> None:
        """Delete an item.

        Args:
            item_id: The item UUID.
        """
        _validate_id(item_id, "item_id")
        if await self._get_api_mode() == "legacy":
            await self._request("DELETE", f"/items/{item_id}")
        else:
            await self._request("DELETE", f"/entities/{item_id}")

    async def move_item(self, item_id: str, location_id: str) -> dict[str, Any]:
        """Move an item to a different location.

        Args:
            item_id: The item UUID.
            location_id: The new location UUID.

        Returns:
            Updated item object.
        """
        return await self.update_item(item_id, location_id=location_id)

    @staticmethod
    def _sniff_file(data: bytes) -> tuple[str, str, bool] | None:
        """Identify a file's real format from its magic bytes.

        Ignores any filename/content-type the caller may have supplied and
        looks only at the file's actual content, so a mislabeled or
        unsupported upload is rejected before it reaches Homebox.

        Args:
            data: Raw file bytes.

        Returns:
            A (content_type, file_extension, is_image) tuple, or None if the
            data doesn't match any supported format.
        """
        if data.startswith(_JPEG_MAGIC):
            return "image/jpeg", "jpg", True
        if data.startswith(_PNG_MAGIC):
            return "image/png", "png", True
        if data.startswith(_GIF_MAGICS):
            return "image/gif", "gif", True
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp", "webp", True
        if data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
            return "image/heic", "heic", True
        if data.startswith(_PDF_MAGIC):
            return "application/pdf", "pdf", False
        return None

    @staticmethod
    def _check_url_extension(url: str) -> None:
        """Fail-fast check: raise ValueError if `url`'s path clearly ends
        in a known-unsupported extension (see _DISALLOWED_URL_EXTENSIONS),
        so add_item_attachment_from_url() can skip downloading a file
        that's obviously the wrong type. Not a security boundary — a
        URL's extension is just a name, easily missing, wrong, or
        spoofed. URLs with no extension or an unrecognized one pass
        through unchecked; _sniff_file() on the downloaded bytes remains
        the real gate either way.
        """
        path = urlsplit(url).path
        ext = PurePosixPath(unquote(path)).suffix.lstrip(".").lower()
        if ext in _DISALLOWED_URL_EXTENSIONS:
            raise ValueError(
                f"URL ends in '.{ext}', which isn't a supported attachment format "
                "(JPEG, PNG, GIF, WEBP, HEIC, PDF); refusing to download it."
            )

    @staticmethod
    def _check_public_host(hostname: str, candidates: list) -> None:
        """Raise ValueError if any resolved address isn't public.

        Used by _validate_public_url() as the SSRF guard for
        add_item_attachment_from_url(): the addon runs inside the user's
        Home Assistant network, so an LLM-supplied URL must not be able to
        reach internal-only services through this fetch.
        """
        for ip in candidates:
            mapped = getattr(ip, "ipv4_mapped", None)
            check_ip = mapped or ip
            if (
                check_ip.is_private
                or check_ip.is_loopback
                or check_ip.is_link_local
                or check_ip.is_reserved
                or check_ip.is_multicast
                or check_ip.is_unspecified
                or not check_ip.is_global
            ):
                raise ValueError(
                    f"URL host {hostname!r} resolves to a non-public address "
                    f"({check_ip}); refusing to fetch it."
                )

    @staticmethod
    async def _validate_public_url(url: str) -> None:
        """SSRF guard: raise ValueError unless `url` is http(s) and every
        address its host resolves to is public.

        Pre-flight check only: it does not close a DNS-rebinding TOCTOU
        gap between this check and the moment httpx opens its own
        connection a moment later. Accepted as proportionate to this
        addon's single-user home-network threat model.
        """
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"URL must be http:// or https://, got {parts.scheme!r} in {url!r}.")
        hostname = parts.hostname
        if not hostname:
            raise ValueError(f"URL has no hostname: {url!r}")

        try:
            candidates = [ipaddress.ip_address(hostname)]
        except ValueError:
            port = parts.port or (443 if parts.scheme == "https" else 80)
            try:
                addrinfo = await asyncio.to_thread(
                    socket.getaddrinfo, hostname, port, type=socket.SOCK_STREAM
                )
            except socket.gaierror as exc:
                raise ValueError(f"Could not resolve host {hostname!r}: {exc}") from exc
            candidates = [ipaddress.ip_address(info[4][0]) for info in addrinfo]

        HomeboxClient._check_public_host(hostname, candidates)

    async def _fetch_url_capped(self, url: str) -> bytes:
        """Download `url` with a streamed size cap.

        Re-validates the SSRF guard on every redirect hop actually
        followed: a URL that passes the check can still redirect to an
        internal address at request time, so redirects are followed
        manually (capped at _MAX_REDIRECTS) instead of via httpx's
        built-in follow_redirects, re-checking each Location header
        before following it.

        Args:
            url: http(s) URL to download.

        Returns:
            The downloaded bytes.
        """
        client = await self._get_client()
        headers = {"User-Agent": _DOWNLOAD_USER_AGENT}
        current_url = url

        for _ in range(_MAX_REDIRECTS + 1):
            await self._validate_public_url(current_url)
            try:
                async with client.stream(
                    "GET", current_url, headers=headers, follow_redirects=False
                ) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError(
                                f"URL returned a redirect ({response.status_code}) "
                                "with no Location header."
                            )
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > _MAX_ATTACHMENT_BYTES:
                            raise ValueError(
                                f"Remote file exceeds the {_MAX_ATTACHMENT_BYTES // 1_048_576} MB "
                                "limit for attachment uploads (download aborted)."
                            )
                    return bytes(data)
            except httpx.HTTPError as exc:
                raise ValueError(f"Failed to download file from URL: {exc}") from exc

        raise ValueError(
            f"URL redirected more than {_MAX_REDIRECTS} times; refusing to follow further."
        )

    async def add_item_attachment(
        self,
        item_id: str,
        data: bytes,
        filename: str | None = None,
        attachment_type: str | None = None,
        primary: bool = False,
    ) -> dict[str, Any]:
        """Attach a file to an item (photo, manual, warranty, receipt, ...).

        Validates the upload before sending anything to Homebox: rejects
        files over the size cap and rejects any data that isn't a
        recognized format (checked via magic bytes, not the supplied
        filename/content-type).

        Args:
            item_id: The item UUID.
            data: Raw file bytes.
            filename: File name to store, with extension (optional; a name
                is generated from the detected format if omitted).
            attachment_type: One of "photo", "manual", "warranty",
                "receipt", "attachment" (optional; defaults to "photo" for
                images and "attachment" for everything else, matching
                Homebox's own auto-detection when the type is omitted).
            primary: Whether to set this as the item's primary/cover photo
                (only meaningful for images).

        Returns:
            Homebox's response: the item, including its updated attachments list.
        """
        _validate_id(item_id, "item_id")
        if len(data) > _MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"File is {len(data) / 1_048_576:.1f} MB, which exceeds the "
                f"{_MAX_ATTACHMENT_BYTES // 1_048_576} MB limit for attachment uploads."
            )

        sniffed = self._sniff_file(data)
        if sniffed is None:
            raise ValueError(
                "Unrecognized file data: only JPEG, PNG, GIF, WEBP, HEIC images "
                "and PDF documents are accepted for attachment uploads."
            )
        content_type, extension, is_image = sniffed
        if not filename:
            filename = f"{'photo' if is_image else 'document'}.{extension}"

        if attachment_type is not None:
            if attachment_type not in _VALID_ATTACHMENT_TYPES:
                raise ValueError(
                    f"attachment_type must be one of {sorted(_VALID_ATTACHMENT_TYPES)}, "
                    f"got {attachment_type!r}."
                )
            resolved_type = attachment_type
        else:
            resolved_type = "photo" if is_image else "attachment"

        await self._ensure_authenticated()
        client = await self._get_client()
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        entity_kind = "items" if await self._get_api_mode() == "legacy" else "entities"
        url = f"{self.base_url}/{entity_kind}/{item_id}/attachments"

        # Deliberately not using _request(): it always sends
        # "Content-Type: application/json", which would break the multipart
        # body httpx builds from `files=`.
        response = await client.request(
            "POST",
            url,
            headers=headers,
            files={"file": (filename, data, content_type)},
            data={"name": filename, "type": resolved_type, "primary": "true" if primary else "false"},
        )

        if response.status_code == 401:
            raise ValueError(
                "Invalid or expired Homebox API token. Please generate a new token in Homebox settings."
            )
        response.raise_for_status()
        return response.json()

    async def add_item_attachment_from_url(
        self,
        item_id: str,
        url: str,
        filename: str | None = None,
        attachment_type: str | None = None,
        primary: bool = False,
    ) -> dict[str, Any]:
        """Download a file from a URL and attach it to an item.

        For files the caller found itself (e.g. a product photo from a web
        search) rather than ones the user supplied directly — see
        add_item_attachment() for that path. Delegates all format
        sniffing/size validation/upload logic to add_item_attachment() once
        the download completes; this method only adds URL validation (SSRF
        guard, see _validate_public_url; fail-fast extension check, see
        _check_url_extension) and a streamed size cap so an oversized or
        malicious response is never fully buffered.

        Args:
            item_id: The item UUID.
            url: http(s) URL to download the file from.
            filename: File name to store (optional; derived from the URL's
                path if it looks like one, else generated from the detected
                format like add_item_attachment() does).
            attachment_type: See add_item_attachment().
            primary: See add_item_attachment().

        Returns:
            Homebox's response: the item, including its updated attachments list.
        """
        _validate_id(item_id, "item_id")
        self._check_url_extension(url)

        if not filename:
            candidate = PurePosixPath(unquote(urlsplit(url).path)).name
            if candidate and "." in candidate:
                filename = candidate

        data = await self._fetch_url_capped(url)
        return await self.add_item_attachment(item_id, data, filename, attachment_type, primary)

    # =========================================================================
    # Labels / Tags
    # =========================================================================

    async def get_labels(self) -> list[dict[str, Any]]:
        """Get all labels (tags in the modern API).

        Returns:
            List of label objects.
        """
        if await self._get_api_mode() == "legacy":
            return await self._request("GET", "/labels")
        return await self._request("GET", "/tags")

    async def get_label(self, label_id: str) -> dict[str, Any]:
        """Get a specific label by ID.

        Args:
            label_id: The label UUID.

        Returns:
            Label object.
        """
        _validate_id(label_id, "label_id")
        if await self._get_api_mode() == "legacy":
            return await self._request("GET", f"/labels/{label_id}")
        return await self._request("GET", f"/tags/{label_id}")

    async def create_label(
        self,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> dict[str, Any]:
        """Create a new label (tag in the modern API).

        Args:
            name: Label name (max 255 characters).
            description: Optional description (max 1000 characters).
            color: Optional color (hex code, max 255 characters).

        Returns:
            Created label object.
        """
        self._check_max_length("name", name)
        self._check_max_length("description", description)
        self._check_max_length("color", color)

        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description
        if color:
            data["color"] = color

        if await self._get_api_mode() == "legacy":
            return await self._request("POST", "/labels", json=data)
        return await self._request("POST", "/tags", json=data)

    async def update_label(
        self,
        label_id: str,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> dict[str, Any]:
        """Update a label (tag in the modern API).

        Fetches the current label first and merges in the requested changes.
        Homebox's tag-update endpoint (``repo.TagUpdate``) takes a full
        replacement object where ``name`` is required even when it isn't
        changing, so sending only the fields the caller passed causes a
        422 Unprocessable Entity.

        Args:
            label_id: The label UUID.
            name: New name (optional, max 255 characters).
            description: New description (optional, max 1000 characters).
            color: New color (optional, max 255 characters).

        Returns:
            Updated label object.
        """
        self._check_max_length("name", name)
        self._check_max_length("description", description)
        self._check_max_length("color", color)

        current = await self.get_label(label_id)
        data: dict[str, Any] = {
            "id": label_id,
            "name": name if name is not None else current.get("name", ""),
            "description": (
                description if description is not None else current.get("description", "")
            ),
            "color": color if color is not None else current.get("color", ""),
        }
        icon = current.get("icon")
        if icon:
            data["icon"] = icon

        if await self._get_api_mode() == "legacy":
            return await self._request("PUT", f"/labels/{label_id}", json=data)

        # Tags mode also supports a parent (nested tags); preserve it so it
        # isn't silently cleared by this full-replacement update.
        parent_id = current.get("parentId") or (current.get("parent") or {}).get("id")
        if parent_id:
            data["parentId"] = parent_id
        return await self._request("PUT", f"/tags/{label_id}", json=data)

    async def delete_label(self, label_id: str) -> None:
        """Delete a label (tag in the modern API).

        Args:
            label_id: The label UUID.
        """
        _validate_id(label_id, "label_id")
        if await self._get_api_mode() == "legacy":
            await self._request("DELETE", f"/labels/{label_id}")
        else:
            await self._request("DELETE", f"/tags/{label_id}")

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_statistics(self) -> dict[str, Any]:
        """Get inventory statistics.

        Returns:
            Statistics object with counts and totals.
        """
        # Unchanged across API versions.
        return await self._request("GET", "/groups/statistics")
