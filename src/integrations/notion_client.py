"""
Notion Client for Sentience v3.0
Full-featured Notion integration with OAuth, pages, databases, and search.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

import httpx

from .oauth_manager import OAuthManager, OAuthProvider, OAuthError, TokenData

logger = logging.getLogger(__name__)


NOTION_SCOPES = [
    "read.databases",
    "write.databases",
    "read.pages",
    "write.pages",
    "read.comments",
    "write.comments",
    "read.users",
]


class NotionColor(Enum):
    """Notion color options."""
    DEFAULT = "default"
    GRAY = "gray"
    BROWN = "brown"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PURPLE = "purple"
    PINK = "pink"
    RED = "red"


class NotionBlockType(Enum):
    """Notion block types."""
    PARAGRAPH = "paragraph"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    BULLETED_LIST_ITEM = "bulleted_list_item"
    NUMBERED_LIST_ITEM = "numbered_list_item"
    TO_DO = "to_do"
    TOGGLE = "toggle"
    CHILD_PAGE = "child_page"
    CHILD_DATABASE = "child_database"
    CODE = "code"
    CALLOUT = "callout"
    QUOTE = "quote"
    DIVIDER = "divider"
    IMAGE = "image"
    EMBED = "embed"
    VIDEO = "video"
    FILE = "file"
    PDF = "pdf"
    BOOKMARK = "bookmark"
    TABLE = "table"
    TABLE_ROW = "table_row"
    COLUMN_LIST = "column_list"
    COLUMN = "column"
    SYNCED_BLOCK = "synced_block"
    TEMPLATE = "template"
    LINK_PREVIEW = "link_preview"


class PropertyType(Enum):
    """Notion property types."""
    TITLE = "title"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    DATE = "date"
    PEOPLE = "people"
    FILES = "files"
    CHECKBOX = "checkbox"
    URL = "url"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    FORMULA = "formula"
    RELATION = "relation"
    ROLLUP = "rollup"
    CREATED_TIME = "created_time"
    CREATED_BY = "created_by"
    LAST_EDITED_TIME = "last_edited_time"
    LAST_EDITED_BY = "last_edited_by"
    STATUS = "status"


@dataclass
class RichText:
    """Notion rich text object."""
    plain_text: str
    type: str = "text"
    href: Optional[str] = None
    annotations: Optional[dict[str, Any]] = None
    link: Optional[str] = None

    def to_api(self) -> dict[str, Any]:
        """Convert to API format."""
        result = {
            "type": self.type,
            self.type: {"content": self.plain_text},
        }
        if self.href:
            result[self.type]["link"] = {"url": self.href}
        if self.annotations:
            result["annotations"] = self.annotations
        return result

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RichText":
        """Create from API response."""
        text_type = data.get("type", "text")
        text_data = data.get(text_type, {})
        return cls(
            plain_text=data.get("plain_text", ""),
            type=text_type,
            href=text_data.get("link", {}).get("url"),
            annotations=data.get("annotations"),
            link=text_data.get("link", {}).get("url"),
        )


@dataclass
class Block:
    """Notion block object."""
    id: str
    type: NotionBlockType
    created_time: Optional[datetime] = None
    last_edited_time: Optional[datetime] = None
    has_children: bool = False
    content: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Block":
        """Create from API response."""
        block_type = NotionBlockType(data["type"])
        content = data.get(block_type.value, {})

        created_time = None
        if "created_time" in data:
            created_time = datetime.fromisoformat(data["created_time"].replace("Z", "+00:00"))

        last_edited_time = None
        if "last_edited_time" in data:
            last_edited_time = datetime.fromisoformat(data["last_edited_time"].replace("Z", "+00:00"))

        return cls(
            id=data["id"],
            type=block_type,
            created_time=created_time,
            last_edited_time=last_edited_time,
            has_children=data.get("has_children", False),
            content=content,
        )

    def get_text(self) -> str:
        """Extract plain text from block."""
        if "rich_text" in self.content:
            return "".join(
                rt.get("plain_text", "")
                for rt in self.content["rich_text"]
            )
        return ""

    def to_create_api(self) -> dict[str, Any]:
        """Convert to API format for creating."""
        return {
            "type": self.type.value,
            self.type.value: self.content,
        }


@dataclass
class Page:
    """Notion page object."""
    id: str
    created_time: datetime
    last_edited_time: datetime
    title: Optional[str] = None
    icon: Optional[dict[str, Any]] = None
    cover: Optional[dict[str, Any]] = None
    parent: Optional[dict[str, Any]] = None
    properties: dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    archived: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Page":
        """Create from API response."""
        title = None
        properties = data.get("properties", {})

        # Extract title from properties
        for prop_name, prop_data in properties.items():
            if prop_data.get("type") == "title":
                title_list = prop_data.get("title", [])
                if title_list:
                    title = "".join(t.get("plain_text", "") for t in title_list)

        return cls(
            id=data["id"],
            created_time=datetime.fromisoformat(data["created_time"].replace("Z", "+00:00")),
            last_edited_time=datetime.fromisoformat(data["last_edited_time"].replace("Z", "+00:00")),
            title=title,
            icon=data.get("icon"),
            cover=data.get("cover"),
            parent=data.get("parent"),
            properties=properties,
            url=data.get("url"),
            archived=data.get("archived", False),
        )


@dataclass
class Database:
    """Notion database object."""
    id: str
    title: str
    created_time: datetime
    last_edited_time: datetime
    properties: dict[str, Any] = field(default_factory=dict)
    parent: Optional[dict[str, Any]] = None
    url: Optional[str] = None
    archived: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Database":
        """Create from API response."""
        title_list = data.get("title", [])
        title = "".join(t.get("plain_text", "") for t in title_list)

        return cls(
            id=data["id"],
            title=title,
            created_time=datetime.fromisoformat(data["created_time"].replace("Z", "+00:00")),
            last_edited_time=datetime.fromisoformat(data["last_edited_time"].replace("Z", "+00:00")),
            properties=data.get("properties", {}),
            parent=data.get("parent"),
            url=data.get("url"),
            archived=data.get("archived", False),
        )


@dataclass
class DatabaseQueryResult:
    """Result of database query."""
    results: list[Page]
    has_more: bool
    next_cursor: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "DatabaseQueryResult":
        """Create from API response."""
        return cls(
            results=[Page.from_api(p) for p in data.get("results", [])],
            has_more=data.get("has_more", False),
            next_cursor=data.get("next_cursor"),
        )


class NotionClient:
    """
    Full-featured Notion client with:
    - OAuth flow
    - Page operations (CRUD)
    - Database operations
    - Block manipulation
    - Search functionality
    """

    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"

    def __init__(self, oauth_manager: OAuthManager, user_id: Optional[str] = None):
        self.oauth_manager = oauth_manager
        self.user_id = user_id
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        token = await self.oauth_manager.get_or_refresh_token(
            OAuthProvider.NOTION, self.user_id
        )
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
            "Notion-Version": self.API_VERSION,
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Notion API."""
        headers = await self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        url = f"{self.BASE_URL}{path}"

        response = await self._http_client.request(
            method, url, headers=headers, **kwargs
        )

        if response.status_code == 401:
            # Notion tokens don't expire in the same way, but let's handle it
            error = response.json().get("message", "Unauthorized")
            raise NotionError(f"Unauthorized: {error}")

        if response.status_code >= 400:
            error_data = response.json()
            error_msg = error_data.get("message", response.text)
            logger.error(f"Notion API error: {error_msg}")
            raise NotionError(f"Notion API error: {error_msg}")

        return response.json()

    # ==================== Page Operations ====================

    async def get_page(self, page_id: str) -> Page:
        """Retrieve a page by ID."""
        data = await self._request("GET", f"/pages/{page_id}")
        return Page.from_api(data)

    async def create_page(
        self,
        parent: dict[str, Any],
        properties: dict[str, Any],
        children: Optional[list[Block]] = None,
        icon: Optional[dict[str, Any]] = None,
        cover: Optional[dict[str, Any]] = None,
    ) -> Page:
        """
        Create a new page.
        parent: {"database_id": "..."} or {"page_id": "..."}
        properties: Page properties dict
        children: List of blocks to add
        """
        body = {
            "parent": parent,
            "properties": properties,
        }

        if children:
            body["children"] = [b.to_create_api() for b in children]
        if icon:
            body["icon"] = icon
        if cover:
            body["cover"] = cover

        data = await self._request("POST", "/pages", json=body)
        logger.info(f"Created page {data['id']}")
        return Page.from_api(data)

    async def update_page(
        self,
        page_id: str,
        properties: Optional[dict[str, Any]] = None,
        archived: Optional[bool] = None,
        icon: Optional[dict[str, Any]] = None,
        cover: Optional[dict[str, Any]] = None,
    ) -> Page:
        """Update page properties."""
        body = {}

        if properties is not None:
            body["properties"] = properties
        if archived is not None:
            body["archived"] = archived
        if icon is not None:
            body["icon"] = icon
        if cover is not None:
            body["cover"] = cover

        data = await self._request("PATCH", f"/pages/{page_id}", json=body)
        return Page.from_api(data)

    async def delete_page(self, page_id: str) -> bool:
        """Delete (archive) a page."""
        data = await self._request(
            "PATCH", f"/pages/{page_id}", json={"archived": True}
        )
        logger.info(f"Archived page {page_id}")
        return data.get("archived", False)

    async def restore_page(self, page_id: str) -> Page:
        """Restore (unarchive) a page."""
        data = await self._request(
            "PATCH", f"/pages/{page_id}", json={"archived": False}
        )
        logger.info(f"Restored page {page_id}")
        return Page.from_api(data)

    async def get_page_properties(
        self,
        page_id: str,
        property_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get page properties or a specific property."""
        if property_id:
            return await self._request(
                "GET", f"/pages/{page_id}/properties/{property_id}"
            )
        return await self._request("GET", f"/pages/{page_id}/properties")

    # ==================== Database Operations ====================

    async def get_database(self, database_id: str) -> Database:
        """Retrieve a database by ID."""
        data = await self._request("GET", f"/databases/{database_id}")
        return Database.from_api(data)

    async def query_database(
        self,
        database_id: str,
        filter: Optional[dict[str, Any]] = None,
        sorts: Optional[list[dict[str, Any]]] = None,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> DatabaseQueryResult:
        """
        Query a database.
        filter: Notion filter object
        sorts: List of sort objects
        """
        body = {"page_size": page_size}

        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor

        data = await self._request(
            "POST", f"/databases/{database_id}/query", json=body
        )
        return DatabaseQueryResult.from_api(data)

    async def query_all(
        self,
        database_id: str,
        filter: Optional[dict[str, Any]] = None,
        sorts: Optional[list[dict[str, Any]]] = None,
    ) -> list[Page]:
        """Query all pages in database (handles pagination)."""
        results = []
        cursor = None

        while True:
            query_result = await self.query_database(
                database_id, filter, sorts, start_cursor=cursor
            )
            results.extend(query_result.results)

            if not query_result.has_more:
                break
            cursor = query_result.next_cursor

        return results

    async def create_database(
        self,
        parent: dict[str, Any],
        title: str,
        properties: dict[str, Any],
        icon: Optional[dict[str, Any]] = None,
        cover: Optional[dict[str, Any]] = None,
    ) -> Database:
        """
        Create a new database.
        parent: {"page_id": "..."} or {"workspace": True}
        properties: Property schema definitions
        """
        body = {
            "parent": parent,
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }

        if icon:
            body["icon"] = icon
        if cover:
            body["cover"] = cover

        data = await self._request("POST", "/databases", json=body)
        logger.info(f"Created database {data['id']}")
        return Database.from_api(data)

    async def update_database(
        self,
        database_id: str,
        title: Optional[str] = None,
        properties: Optional[dict[str, Any]] = None,
        icon: Optional[dict[str, Any]] = None,
        cover: Optional[dict[str, Any]] = None,
    ) -> Database:
        """Update database properties."""
        body = {}

        if title:
            body["title"] = [{"type": "text", "text": {"content": title}}]
        if properties:
            body["properties"] = properties
        if icon:
            body["icon"] = icon
        if cover:
            body["cover"] = cover

        data = await self._request("PATCH", f"/databases/{database_id}", json=body)
        return Database.from_api(data)

    # ==================== Block Operations ====================

    async def get_block(self, block_id: str) -> Block:
        """Retrieve a block by ID."""
        data = await self._request("GET", f"/blocks/{block_id}")
        return Block.from_api(data)

    async def get_block_children(
        self,
        block_id: str,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> list[Block]:
        """Get children of a block."""
        params = {"page_size": page_size}
        if start_cursor:
            params["start_cursor"] = start_cursor

        data = await self._request("GET", f"/blocks/{block_id}/children", params=params)
        return [Block.from_api(b) for b in data.get("results", [])]

    async def append_block_children(
        self,
        block_id: str,
        children: list[Block],
        after: Optional[str] = None,
    ) -> list[Block]:
        """Append blocks to a parent block."""
        body = {"children": [b.to_create_api() for b in children]}
        if after:
            body["after"] = after

        data = await self._request(
            "PATCH", f"/blocks/{block_id}/children", json=body
        )
        logger.info(f"Appended {len(children)} blocks to {block_id}")
        return [Block.from_api(b) for b in data.get("results", [])]

    async def update_block(
        self,
        block_id: str,
        content: dict[str, Any],
        archived: Optional[bool] = None,
    ) -> Block:
        """Update block content."""
        body = {}
        # Determine block type from content
        for key in content:
            if key in [t.value for t in NotionBlockType]:
                body["type"] = key
                body[key] = content[key]
                break

        if archived is not None:
            body["archived"] = archived

        data = await self._request("PATCH", f"/blocks/{block_id}", json=body)
        return Block.from_api(data)

    async def delete_block(self, block_id: str) -> bool:
        """Delete a block."""
        data = await self._request("DELETE", f"/blocks/{block_id}")
        logger.info(f"Deleted block {block_id}")
        return data.get("archived", False)

    # ==================== Helper Methods ====================

    def create_title_property(self, title: str) -> dict[str, Any]:
        """Create a title property for page creation."""
        return {
            "title": [{"type": "text", "text": {"content": title}}]
        }

    def create_rich_text_property(self, text: str) -> dict[str, Any]:
        """Create a rich_text property."""
        return {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }

    def create_select_property(self, name: str) -> dict[str, Any]:
        """Create a select property."""
        return {"select": {"name": name}}

    def create_multi_select_property(self, names: list[str]) -> dict[str, Any]:
        """Create a multi_select property."""
        return {
            "multi_select": [{"name": n} for n in names]
        }

    def create_number_property(self, number: Union[int, float]) -> dict[str, Any]:
        """Create a number property."""
        return {"number": number}

    def create_date_property(
        self,
        start: str,
        end: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a date property."""
        date_obj = {"start": start}
        if end:
            date_obj["end"] = end
        return {"date": date_obj}

    def create_checkbox_property(self, checked: bool) -> dict[str, Any]:
        """Create a checkbox property."""
        return {"checkbox": checked}

    def create_url_property(self, url: str) -> dict[str, Any]:
        """Create a URL property."""
        return {"url": url}

    def create_email_property(self, email: str) -> dict[str, Any]:
        """Create an email property."""
        return {"email": email}

    # ==================== Search ====================

    async def search(
        self,
        query: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
        sort: Optional[dict[str, Any]] = None,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """
        Search Notion.
        filter: {"property": "object", "value": "page|database"}
        sort: {"direction": "ascending|descending", "timestamp": "last_edited_time"}
        """
        body = {"page_size": page_size}

        if query:
            body["query"] = query
        if filter:
            body["filter"] = filter
        if sort:
            body["sort"] = sort
        if start_cursor:
            body["start_cursor"] = start_cursor

        data = await self._request("POST", "/search", json=body)
        return data

    async def search_pages(
        self,
        query: Optional[str] = None,
        page_size: int = 100,
    ) -> list[Page]:
        """Search for pages only."""
        data = await self.search(
            query=query,
            filter={"property": "object", "value": "page"},
            page_size=page_size,
        )
        return [Page.from_api(r) for r in data.get("results", [])]

    async def search_databases(
        self,
        query: Optional[str] = None,
        page_size: int = 100,
    ) -> list[Database]:
        """Search for databases only."""
        data = await self.search(
            query=query,
            filter={"property": "object", "value": "database"},
            page_size=page_size,
        )
        return [Database.from_api(r) for r in data.get("results", [])]

    # ==================== User Operations ====================

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """Get a user by ID."""
        return await self._request("GET", f"/users/{user_id}")

    async def list_users(self) -> list[dict[str, Any]]:
        """List all users."""
        data = await self._request("GET", "/users")
        return data.get("results", [])

    async def get_me(self) -> dict[str, Any]:
        """Get current bot user info."""
        return await self._request("GET", "/users/me")

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "NotionClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class NotionError(Exception):
    """Notion API error."""
    pass
