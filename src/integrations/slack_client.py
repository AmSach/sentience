"""
Slack Client for Sentience v3.0
Full-featured Slack integration with OAuth, messaging, and channels.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import httpx

from .oauth_manager import OAuthManager, OAuthProvider, OAuthError

logger = logging.getLogger(__name__)


SLACK_SCOPES = [
    "channels:read",
    "channels:history",
    "channels:manage",
    "channels:join",
    "chat:write",
    "chat:write.public",
    "files:write",
    "files:read",
    "groups:read",
    "groups:history",
    "groups:write",
    "im:read",
    "im:history",
    "im:write",
    "mpim:read",
    "mpim:history",
    "mpim:write",
    "users:read",
    "users:read.email",
    "team:read",
    "search:read",
]


class SlackMessageType(Enum):
    """Slack message types."""
    MESSAGE = "message"
    FILE_SHARE = "file_share"
    BOT_MESSAGE = "bot_message"
    JOINED_CHANNEL = "joined_channel"
    LEFT_CHANNEL = "left_channel"


class SlackChannelType(Enum):
    """Channel types."""
    PUBLIC = "public_channel"
    PRIVATE = "private_channel"
    MPIM = "mpim"
    IM = "im"


@dataclass
class SlackUser:
    """Slack user."""
    id: str
    name: str
    real_name: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    avatar_url: Optional[str] = None
    is_bot: bool = False
    is_admin: bool = False
    is_owner: bool = False
    is_restricted: bool = False
    is_ultra_restricted: bool = False
    tz: Optional[str] = None
    tz_label: Optional[str] = None
    tz_offset: Optional[int] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SlackUser":
        """Create from API response."""
        profile = data.get("profile", {})

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            real_name=data.get("real_name"),
            display_name=profile.get("display_name"),
            email=profile.get("email"),
            title=profile.get("title"),
            avatar_url=profile.get("image_512") or profile.get("image_192"),
            is_bot=data.get("is_bot", False),
            is_admin=data.get("is_admin", False),
            is_owner=data.get("is_owner", False),
            is_restricted=data.get("is_restricted", False),
            is_ultra_restricted=data.get("is_ultra_restricted", False),
            tz=data.get("tz"),
            tz_label=data.get("tz_label"),
            tz_offset=data.get("tz_offset"),
        )


@dataclass
class SlackChannel:
    """Slack channel."""
    id: str
    name: str
    is_channel: bool = True
    is_private: bool = False
    is_im: bool = False
    is_mpim: bool = False
    is_group: bool = False
    is_archived: bool = False
    is_general: bool = False
    creator: Optional[str] = None
    created: Optional[datetime] = None
    num_members: int = 0
    topic: Optional[str] = None
    purpose: Optional[str] = None
    members: list[str] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SlackChannel":
        """Create from API response."""
        created = None
        if "created" in data:
            created = datetime.fromtimestamp(data["created"])

        channel = cls(
            id=data["id"],
            name=data.get("name", ""),
            is_channel=data.get("is_channel", False),
            is_private=data.get("is_private", False),
            is_im=data.get("is_im", False),
            is_mpim=data.get("is_mpim", False),
            is_group=data.get("is_group", False),
            is_archived=data.get("is_archived", False),
            is_general=data.get("is_general", False),
            creator=data.get("creator"),
            created=created,
            num_members=data.get("num_members", 0),
        )

        if "topic" in data:
            channel.topic = data["topic"].get("value")
        if "purpose" in data:
            channel.purpose = data["purpose"].get("value")
        if "members" in data:
            channel.members = data["members"]

        return channel


@dataclass
class SlackMessage:
    """Slack message."""
    ts: str
    channel: str
    text: Optional[str] = None
    user: Optional[str] = None
    username: Optional[str] = None
    bot_id: Optional[str] = None
    type: SlackMessageType = SlackMessageType.MESSAGE
    thread_ts: Optional[str] = None
    parent_user_id: Optional[str] = None
    files: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    reactions: list[dict[str, Any]] = field(default_factory=list)
    permalink: Optional[str] = None
    deleted: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any], channel: str) -> "SlackMessage":
        """Create from API response."""
        msg_type = SlackMessageType.MESSAGE
        subtype = data.get("subtype")
        if subtype:
            try:
                msg_type = SlackMessageType(subtype)
            except ValueError:
                pass

        return cls(
            ts=data["ts"],
            channel=channel,
            text=data.get("text"),
            user=data.get("user"),
            username=data.get("username"),
            bot_id=data.get("bot_id"),
            type=msg_type,
            thread_ts=data.get("thread_ts") or data.get("ts"),
            parent_user_id=data.get("parent_user_id"),
            files=data.get("files", []),
            attachments=data.get("attachments", []),
            blocks=data.get("blocks", []),
            reactions=data.get("reactions", []),
            permalink=data.get("permalink"),
            deleted=data.get("subtype") == "tombstone",
        )

    @property
    def timestamp(self) -> datetime:
        """Convert ts to datetime."""
        try:
            return datetime.fromtimestamp(float(self.ts))
        except (ValueError, TypeError):
            return datetime.now()


@dataclass
class SlackFile:
    """Slack file."""
    id: str
    name: str
    title: Optional[str] = None
    mimetype: Optional[str] = None
    filetype: Optional[str] = None
    size: int = 0
    created: Optional[datetime] = None
    user: Optional[str] = None
    url_private: Optional[str] = None
    url_private_download: Optional[str] = None
    permalink: Optional[str] = None
    channels: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    ims: list[str] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SlackFile":
        """Create from API response."""
        created = None
        if "created" in data:
            created = datetime.fromtimestamp(data["created"])

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            title=data.get("title"),
            mimetype=data.get("mimetype"),
            filetype=data.get("filetype"),
            size=data.get("size", 0),
            created=created,
            user=data.get("user"),
            url_private=data.get("url_private"),
            url_private_download=data.get("url_private_download"),
            permalink=data.get("permalink"),
            channels=data.get("channels", []),
            groups=data.get("groups", []),
            ims=data.get("ims", []),
        )


class SlackClient:
    """
    Full-featured Slack client with:
    - OAuth authentication
    - Message posting
    - Channel management
    - File uploads
    """

    BASE_URL = "https://slack.com/api"

    def __init__(
        self,
        oauth_manager: OAuthManager,
        user_id: Optional[str] = None,
    ):
        self.oauth_manager = oauth_manager
        self.user_id = user_id
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        token = await self.oauth_manager.get_or_refresh_token(
            OAuthProvider.SLACK, self.user_id
        )
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Slack API."""
        headers = await self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        url = f"{self.BASE_URL}/{endpoint}"

        response = await self._http_client.request(
            method, url, headers=headers, **kwargs
        )

        if response.status_code == 401:
            token = await self.oauth_manager.get_or_refresh_token(
                OAuthProvider.SLACK, self.user_id
            )
            headers["Authorization"] = f"Bearer {token.access_token}"
            response = await self._http_client.request(
                method, url, headers=headers, **kwargs
            )

        if response.status_code != 200:
            raise SlackError(f"Slack API error: HTTP {response.status_code}")

        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "Unknown error")
            raise SlackError(f"Slack API error: {error}")

        return data

    # ==================== User Operations ====================

    async def get_user(self, user_id: str) -> SlackUser:
        """Get a user by ID."""
        data = await self._request("GET", "users.info", params={"user": user_id})
        return SlackUser.from_api(data["user"])

    async def get_users(self, limit: int = 100) -> list[SlackUser]:
        """List all users."""
        users = []
        cursor = None

        while True:
            params = {"limit": limit}
            if cursor:
                params["cursor"] = cursor

            data = await self._request("GET", "users.list", params=params)
            users.extend(SlackUser.from_api(u) for u in data.get("members", []))

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return users

    async def get_user_by_email(self, email: str) -> SlackUser:
        """Get user by email address."""
        data = await self._request("GET", "users.lookupByEmail", params={"email": email})
        return SlackUser.from_api(data["user"])

    async def get_me(self) -> SlackUser:
        """Get the authenticated user's identity."""
        data = await self._request("GET", "users.identity")
        return SlackUser.from_api(data["user"])

    # ==================== Channel Operations ====================

    async def list_channels(
        self,
        types: Optional[list[SlackChannelType]] = None,
        exclude_archived: bool = True,
        limit: int = 100,
    ) -> list[SlackChannel]:
        """List all channels."""
        params = {
            "limit": limit,
            "exclude_archived": str(exclude_archived).lower(),
        }

        if types:
            params["types"] = ",".join(t.value for t in types)

        data = await self._request("GET", "conversations.list", params=params)
        return [SlackChannel.from_api(c) for c in data.get("channels", [])]

    async def get_channel(self, channel_id: str) -> SlackChannel:
        """Get a channel by ID."""
        data = await self._request("GET", "conversations.info", params={"channel": channel_id})
        return SlackChannel.from_api(data["channel"])

    async def create_channel(
        self,
        name: str,
        is_private: bool = False,
        description: Optional[str] = None,
        team_id: Optional[str] = None,
        invite_users: Optional[list[str]] = None,
    ) -> SlackChannel:
        """Create a channel."""
        params = {
            "name": name,
            "is_private": str(is_private).lower(),
        }

        if description:
            params["description"] = description
        if team_id:
            params["team_id"] = team_id

        data = await self._request("GET", "conversations.create", params=params)
        channel = SlackChannel.from_api(data["channel"])

        # Invite users if specified
        if invite_users:
            await self.invite_to_channel(channel.id, invite_users)

        logger.info(f"Created channel {channel.id}: {name}")
        return channel

    async def join_channel(self, channel_id: str) -> bool:
        """Join a channel."""
        data = await self._request("POST", "conversations.join", params={"channel": channel_id})
        return data.get("ok", False)

    async def leave_channel(self, channel_id: str) -> bool:
        """Leave a channel."""
        data = await self._request("POST", "conversations.leave", params={"channel": channel_id})
        return data.get("ok", False)

    async def invite_to_channel(
        self,
        channel_id: str,
        user_ids: list[str],
    ) -> bool:
        """Invite users to a channel."""
        data = await self._request(
            "POST",
            "conversations.invite",
            params={"channel": channel_id, "users": ",".join(user_ids)},
        )
        return data.get("ok", False)

    async def archive_channel(self, channel_id: str) -> bool:
        """Archive a channel."""
        data = await self._request("POST", "conversations.archive", params={"channel": channel_id})
        return data.get("ok", False)

    async def unarchive_channel(self, channel_id: str) -> bool:
        """Unarchive a channel."""
        data = await self._request("POST", "conversations.unarchive", params={"channel": channel_id})
        return data.get("ok", False)

    async def set_channel_topic(self, channel_id: str, topic: str) -> bool:
        """Set channel topic."""
        data = await self._request("POST", "conversations.setTopic", params={"channel": channel_id, "topic": topic})
        return data.get("ok", False)

    async def set_channel_purpose(self, channel_id: str, purpose: str) -> bool:
        """Set channel purpose."""
        data = await self._request("POST", "conversations.setPurpose", params={"channel": channel_id, "purpose": purpose})
        return data.get("ok", False)

    async def get_channel_members(
        self,
        channel_id: str,
        limit: int = 100,
    ) -> list[str]:
        """Get members of a channel."""
        members = []
        cursor = None

        while True:
            params = {"channel": channel_id, "limit": limit}
            if cursor:
                params["cursor"] = cursor

            data = await self._request("GET", "conversations.members", params=params)
            members.extend(data.get("members", []))

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return members

    # ==================== Message Operations ====================

    async def post_message(
        self,
        channel: str,
        text: Optional[str] = None,
        blocks: Optional[list[dict[str, Any]]] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
        reply_broadcast: bool = False,
        username: Optional[str] = None,
        icon_url: Optional[str] = None,
        icon_emoji: Optional[str] = None,
        unfurl_links: bool = True,
        unfurl_media: bool = True,
        parse: str = "none",
    ) -> SlackMessage:
        """Post a message to a channel."""
        params = {
            "channel": channel,
            "parse": parse,
            "unfurl_links": str(unfurl_links).lower(),
            "unfurl_media": str(unfurl_media).lower(),
        }

        if text:
            params["text"] = text
        if blocks:
            params["blocks"] = str(blocks) if isinstance(blocks, list) else blocks
        if attachments:
            params["attachments"] = str(attachments) if isinstance(attachments, list) else attachments
        if thread_ts:
            params["thread_ts"] = thread_ts
            params["reply_broadcast"] = str(reply_broadcast).lower()
        if username:
            params["username"] = username
        if icon_url:
            params["icon_url"] = icon_url
        if icon_emoji:
            params["icon_emoji"] = icon_emoji

        data = await self._request("POST", "chat.postMessage", params=params)
        return SlackMessage.from_api(data.get("message", {}), channel)

    async def post_ephemeral(
        self,
        channel: str,
        user: str,
        text: Optional[str] = None,
        blocks: Optional[list[dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
    ) -> str:
        """Post an ephemeral message (only visible to one user)."""
        params = {
            "channel": channel,
            "user": user,
        }

        if text:
            params["text"] = text
        if blocks:
            params["blocks"] = str(blocks) if isinstance(blocks, list) else blocks
        if thread_ts:
            params["thread_ts"] = thread_ts

        data = await self._request("POST", "chat.postEphemeral", params=params)
        return data.get("message_ts", "")

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: Optional[str] = None,
        blocks: Optional[list[dict[str, Any]]] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
    ) -> SlackMessage:
        """Update an existing message."""
        params = {
            "channel": channel,
            "ts": ts,
        }

        if text:
            params["text"] = text
        if blocks:
            params["blocks"] = str(blocks) if isinstance(blocks, list) else blocks
        if attachments:
            params["attachments"] = str(attachments) if isinstance(attachments, list) else attachments

        data = await self._request("POST", "chat.update", params=params)
        return SlackMessage.from_api(data.get("message", {}), channel)

    async def delete_message(
        self,
        channel: str,
        ts: str,
    ) -> bool:
        """Delete a message."""
        data = await self._request("POST", "chat.delete", params={"channel": channel, "ts": ts})
        return data.get("ok", False)

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        inclusive: bool = False,
    ) -> list[SlackMessage]:
        """Get messages from a channel."""
        params = {
            "channel": channel,
            "limit": limit,
            "inclusive": str(inclusive).lower(),
        }

        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

        data = await self._request("GET", "conversations.history", params=params)
        return [SlackMessage.from_api(m, channel) for m in data.get("messages", [])]

    async def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
    ) -> list[SlackMessage]:
        """Get replies in a thread."""
        data = await self._request(
            "GET",
            "conversations.replies",
            params={"channel": channel, "ts": thread_ts, "limit": limit},
        )
        return [SlackMessage.from_api(m, channel) for m in data.get("messages", [])]

    async def get_permalink(
        self,
        channel: str,
        message_ts: str,
    ) -> str:
        """Get a permalink for a message."""
        data = await self._request(
            "GET",
            "chat.getPermalink",
            params={"channel": channel, "message_ts": message_ts},
        )
        return data.get("permalink", "")

    async def send_direct_message(
        self,
        user_id: str,
        text: str,
        **kwargs,
    ) -> SlackMessage:
        """Send a direct message to a user."""
        # Open or get IM channel
        data = await self._request("POST", "conversations.open", params={"users": user_id})
        channel_id = data["channel"]["id"]

        return await self.post_message(channel_id, text, **kwargs)

    # ==================== File Operations ====================

    async def upload_file(
        self,
        file_path: Union[str, Path],
        channels: Optional[list[str]] = None,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> SlackFile:
        """Upload a file."""
        file_path = Path(file_path)

        params = {}
        if channels:
            params["channels"] = ",".join(channels)
        if title:
            params["title"] = title
        if initial_comment:
            params["initial_comment"] = initial_comment
        if thread_ts:
            params["thread_ts"] = thread_ts

        headers = await self._get_headers()
        headers.pop("Accept", None)  # Form data doesn't use JSON accept

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            response = await self._http_client.post(
                f"{self.BASE_URL}/files.upload",
                headers=headers,
                data=params,
                files=files,
            )

        if response.status_code != 200:
            raise SlackError(f"File upload failed: HTTP {response.status_code}")

        data = response.json()
        if not data.get("ok"):
            raise SlackError(f"File upload failed: {data.get('error')}")

        return SlackFile.from_api(data["file"])

    async def upload_file_content(
        self,
        content: bytes,
        filename: str,
        channels: Optional[list[str]] = None,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> SlackFile:
        """Upload file content directly."""
        params = {"filename": filename}
        if channels:
            params["channels"] = ",".join(channels)
        if title:
            params["title"] = title
        if initial_comment:
            params["initial_comment"] = initial_comment
        if thread_ts:
            params["thread_ts"] = thread_ts

        headers = await self._get_headers()
        headers.pop("Accept", None)

        files = {"file": (filename, content)}
        response = await self._http_client.post(
            f"{self.BASE_URL}/files.upload",
            headers=headers,
            data=params,
            files=files,
        )

        if response.status_code != 200:
            raise SlackError(f"File upload failed: HTTP {response.status_code}")

        data = response.json()
        if not data.get("ok"):
            raise SlackError(f"File upload failed: {data.get('error')}")

        return SlackFile.from_api(data["file"])

    async def get_file(self, file_id: str) -> SlackFile:
        """Get file info."""
        data = await self._request("GET", "files.info", params={"file": file_id})
        return SlackFile.from_api(data["file"])

    async def list_files(
        self,
        channel: Optional[str] = None,
        user: Optional[str] = None,
        types: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[SlackFile]:
        """List files."""
        params = {"count": limit}

        if channel:
            params["channel"] = channel
        if user:
            params["user"] = user
        if types:
            params["types"] = ",".join(types)

        data = await self._request("GET", "files.list", params=params)
        return [SlackFile.from_api(f) for f in data.get("files", [])]

    async def delete_file(self, file_id: str) -> bool:
        """Delete a file."""
        data = await self._request("POST", "files.delete", params={"file": file_id})
        return data.get("ok", False)

    async def download_file(
        self,
        file: SlackFile,
    ) -> bytes:
        """Download file content."""
        if not file.url_private_download:
            raise SlackError("No download URL available")

        headers = await self._get_headers()
        response = await self._http_client.get(
            file.url_private_download,
            headers=headers,
        )

        if response.status_code != 200:
            raise SlackError(f"File download failed: HTTP {response.status_code}")

        return response.content

    # ==================== Reaction Operations ====================

    async def add_reaction(
        self,
        channel: str,
        ts: str,
        name: str,
    ) -> bool:
        """Add a reaction to a message."""
        data = await self._request(
            "POST",
            "reactions.add",
            params={"channel": channel, "timestamp": ts, "name": name},
        )
        return data.get("ok", False)

    async def remove_reaction(
        self,
        channel: str,
        ts: str,
        name: str,
    ) -> bool:
        """Remove a reaction from a message."""
        data = await self._request(
            "POST",
            "reactions.remove",
            params={"channel": channel, "timestamp": ts, "name": name},
        )
        return data.get("ok", False)

    async def get_reactions(
        self,
        channel: str,
        ts: str,
        full: bool = True,
    ) -> list[dict[str, Any]]:
        """Get reactions on a message."""
        data = await self._request(
            "GET",
            "reactions.get",
            params={"channel": channel, "timestamp": ts, "full": str(full).lower()},
        )
        return data.get("message", {}).get("reactions", [])

    # ==================== Search ====================

    async def search_messages(
        self,
        query: str,
        count: int = 20,
        page: int = 1,
        sort: str = "score",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        """Search for messages."""
        data = await self._request(
            "GET",
            "search.messages",
            params={
                "query": query,
                "count": count,
                "page": page,
                "sort": sort,
                "sort_dir": sort_dir,
            },
        )
        return data.get("messages", {})

    async def search_files(
        self,
        query: str,
        count: int = 20,
        page: int = 1,
    ) -> dict[str, Any]:
        """Search for files."""
        data = await self._request(
            "GET",
            "search.files",
            params={"query": query, "count": count, "page": page},
        )
        return data.get("files", {})

    # ==================== Team Info ====================

    async def get_team_info(self) -> dict[str, Any]:
        """Get team info."""
        data = await self._request("GET", "team.info")
        return data.get("team", {})

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "SlackClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class SlackError(Exception):
    """Slack API error."""
    pass
