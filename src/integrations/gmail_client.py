"""
Gmail Client for Sentience v3.0
Full-featured Gmail integration with OAuth2, email operations, and search.
"""

import base64
import email
import logging
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from enum import Enum
from pathlib import Path
from typing import Any, Optional, BinaryIO

import httpx
from bs4 import BeautifulSoup

from .oauth_manager import OAuthManager, OAuthProvider, OAuthError, TokenData

logger = logging.getLogger(__name__)


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]


class MessageFormat(Enum):
    """Gmail message formats."""
    MINIMAL = "minimal"
    FULL = "full"
    RAW = "raw"
    METADATA = "metadata"


@dataclass
class EmailAddress:
    """Email address structure."""
    email: str
    name: Optional[str] = None

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} <{self.email}>"
        return self.email


@dataclass
class GmailMessage:
    """Gmail message structure."""
    id: str
    thread_id: str
    subject: Optional[str] = None
    from_address: Optional[EmailAddress] = None
    to: list[EmailAddress] = field(default_factory=list)
    cc: list[EmailAddress] = field(default_factory=list)
    bcc: list[EmailAddress] = field(default_factory=list)
    date: Optional[datetime] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    snippet: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    attachments: list["Attachment"] = field(default_factory=list)
    raw: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "GmailMessage":
        """Parse Gmail API response into GmailMessage."""
        msg = cls(
            id=data["id"],
            thread_id=data["threadId"],
            snippet=data.get("snippet"),
            labels=data.get("labelIds", []),
        )

        # Parse headers
        if "payload" in data:
            headers = data["payload"].get("headers", [])
            for header in headers:
                name = header["name"].lower()
                value = header["value"]

                if name == "subject":
                    msg.subject = value
                elif name == "from":
                    msg.from_address = parse_email_address(value)
                elif name == "to":
                    msg.to.append(parse_email_address(value))
                elif name == "cc":
                    msg.cc.append(parse_email_address(value))
                elif name == "bcc":
                    msg.bcc.append(parse_email_address(value))
                elif name == "date":
                    try:
                        msg.date = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z")
                    except ValueError:
                        pass

            # Parse body
            msg._parse_body(data["payload"])

        if "raw" in data:
            msg.raw = data["raw"]

        return msg

    def _parse_body(self, payload: dict[str, Any]) -> None:
        """Parse message body from payload."""
        mime_type = payload.get("mimeType", "")

        if "body" in payload and "data" in payload["body"]:
            body_data = base64.urlsafe_b64decode(payload["body"]["data"])
            if mime_type == "text/plain":
                self.body_text = body_data.decode("utf-8", errors="replace")
            elif mime_type == "text/html":
                self.body_html = body_data.decode("utf-8", errors="replace")

        if "parts" in payload:
            for part in payload["parts"]:
                self._parse_body(part)

        # Extract text from HTML if no plain text
        if self.body_html and not self.body_text:
            soup = BeautifulSoup(self.body_html, "html.parser")
            self.body_text = soup.get_text(separator="\n", strip=True)


@dataclass
class Attachment:
    """Email attachment structure."""
    id: str
    filename: str
    mime_type: str
    size: int
    message_id: str

    @classmethod
    def from_api_response(cls, data: dict[str, Any], message_id: str) -> "Attachment":
        """Create attachment from API response."""
        return cls(
            id=data["body"]["attachmentId"],
            filename=data.get("filename", "attachment"),
            mime_type=data.get("mimeType", "application/octet-stream"),
            size=data["body"].get("size", 0),
            message_id=message_id,
        )


@dataclass
class Label:
    """Gmail label structure."""
    id: str
    name: str
    type: str = "user"
    messages_total: int = 0
    messages_unread: int = 0
    color: Optional[dict[str, str]] = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "Label":
        """Create label from API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            type=data.get("type", "user"),
            messages_total=data.get("messagesTotal", 0),
            messages_unread=data.get("messagesUnread", 0),
            color=data.get("color"),
        )


def parse_email_address(value: str) -> EmailAddress:
    """Parse email address string into EmailAddress object."""
    value = value.strip()
    if "<" in value and ">" in value:
        name = value[:value.index("<")].strip().strip('"')
        email_addr = value[value.index("<") + 1 : value.index(">")].strip()
        return EmailAddress(email=email_addr, name=name)
    return EmailAddress(email=value)


class GmailClient:
    """
    Full-featured Gmail client with:
    - OAuth2 authentication
    - Send and receive emails
    - Label management
    - Attachment handling
    - Message search
    """

    BASE_URL = "https://gmail.googleapis.com/gmail/v1"

    def __init__(
        self,
        oauth_manager: OAuthManager,
        user_id: str = "me",
        email_address: Optional[str] = None,
    ):
        self.oauth_manager = oauth_manager
        self.user_id = user_id
        self.email_address = email_address
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        token = await self.oauth_manager.get_or_refresh_token(
            OAuthProvider.GOOGLE, self.user_id
        )
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Gmail API."""
        headers = await self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        url = f"{self.BASE_URL}/users/{self.user_id}{path}"

        response = await self._http_client.request(
            method, url, headers=headers, **kwargs
        )

        if response.status_code == 401:
            # Token might be invalid, try refresh
            token = await self.oauth_manager.get_or_refresh_token(
                OAuthProvider.GOOGLE, self.user_id
            )
            headers["Authorization"] = f"Bearer {token.access_token}"
            response = await self._http_client.request(
                method, url, headers=headers, **kwargs
            )

        if response.status_code >= 400:
            error = response.json().get("error", {}).get("message", response.text)
            raise GmailError(f"Gmail API error: {error}")

        return response.json()

    # ==================== Message Operations ====================

    async def get_message(
        self,
        message_id: str,
        format: MessageFormat = MessageFormat.FULL,
    ) -> GmailMessage:
        """Get a single message by ID."""
        data = await self._request(
            "GET",
            f"/messages/{message_id}",
            params={"format": format.value},
        )
        return GmailMessage.from_api_response(data)

    async def list_messages(
        self,
        query: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        max_results: int = 100,
        page_token: Optional[str] = None,
    ) -> tuple[list[dict[str, str]], Optional[str]]:
        """
        List messages matching query.
        Returns (messages, next_page_token).
        """
        params = {"maxResults": max_results}
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = ",".join(label_ids)
        if page_token:
            params["pageToken"] = page_token

        data = await self._request("GET", "/messages", params=params)
        messages = data.get("messages", [])
        next_token = data.get("nextPageToken")
        return messages, next_token

    async def search_messages(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[GmailMessage]:
        """Search messages and return full message objects."""
        messages, _ = await self.list_messages(query=query, max_results=max_results)

        results = []
        for msg in messages:
            try:
                full_msg = await self.get_message(msg["id"])
                results.append(full_msg)
            except GmailError as e:
                logger.warning(f"Failed to get message {msg['id']}: {e}")

        return results

    async def send_message(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        html_body: Optional[str] = None,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        from_address: Optional[str] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> GmailMessage:
        """
        Send an email message.
        attachments: list of (filename, content) tuples
        """
        # Create message
        if attachments:
            msg = MIMEMultipart("mixed")
            body_part = MIMEMultipart("alternative")
        else:
            msg = MIMEMultipart("alternative")

        # Set headers
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        if from_address or self.email_address:
            msg["From"] = from_address or self.email_address
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        if reply_to:
            msg["Reply-To"] = reply_to
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        # Add body parts
        if body:
            msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        # Add attachments
        if attachments:
            body_part.attach(MIMEText(body, "plain"))
            if html_body:
                body_part.attach(MIMEText(html_body, "html"))
            msg.attach(body_part)

            for filename, content in attachments:
                mime_type, _ = mimetypes.guess_type(filename)
                if not mime_type:
                    mime_type = "application/octet-stream"

                maintype, subtype = mime_type.split("/", 1)
                attachment = MIMEBase(maintype, subtype)
                attachment.set_payload(content)
                attachment.add_header(
                    "Content-Disposition", "attachment", filename=filename
                )
                msg.attach(attachment)

        # Encode message
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        # Send
        data = await self._request(
            "POST",
            "/messages/send",
            json={"raw": raw, "threadId": thread_id},
        )

        logger.info(f"Sent message {data['id']}")
        return await self.get_message(data["id"])

    async def draft_message(
        self,
        to: list[str],
        subject: str,
        body: str,
        **kwargs,
    ) -> str:
        """Create a draft message. Returns draft ID."""
        msg = MIMEMultipart("alternative")
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        if self.email_address:
            msg["From"] = self.email_address

        msg.attach(MIMEText(body, "plain"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        data = await self._request(
            "POST",
            "/drafts",
            json={"message": {"raw": raw}},
        )

        logger.info(f"Created draft {data['id']}")
        return data["id"]

    async def delete_message(self, message_id: str) -> bool:
        """Delete a message (move to trash)."""
        await self._request("POST", f"/messages/{message_id}/trash")
        logger.info(f"Deleted message {message_id}")
        return True

    async def trash_message(self, message_id: str) -> bool:
        """Move message to trash."""
        return await self.delete_message(message_id)

    async def untrash_message(self, message_id: str) -> bool:
        """Remove message from trash."""
        await self._request("POST", f"/messages/{message_id}/untrash")
        return True

    async def modify_message_labels(
        self,
        message_id: str,
        add_labels: Optional[list[str]] = None,
        remove_labels: Optional[list[str]] = None,
    ) -> bool:
        """Add or remove labels from a message."""
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        await self._request("POST", f"/messages/{message_id}/modify", json=body)
        return True

    async def mark_as_read(self, message_id: str) -> bool:
        """Mark message as read."""
        return await self.modify_message_labels(
            message_id, remove_labels=["UNREAD"]
        )

    async def mark_as_unread(self, message_id: str) -> bool:
        """Mark message as unread."""
        return await self.modify_message_labels(
            message_id, add_labels=["UNREAD"]
        )

    async def star_message(self, message_id: str) -> bool:
        """Star a message."""
        return await self.modify_message_labels(
            message_id, add_labels=["STARRED"]
        )

    async def unstar_message(self, message_id: str) -> bool:
        """Unstar a message."""
        return await self.modify_message_labels(
            message_id, remove_labels=["STARRED"]
        )

    # ==================== Attachment Operations ====================

    async def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
    ) -> tuple[str, bytes]:
        """Download attachment. Returns (filename, content)."""
        # First get message to find attachment filename
        msg = await self.get_message(message_id)

        filename = "attachment"
        for part in msg.attachments:
            if part.id == attachment_id:
                filename = part.filename
                break

        data = await self._request(
            "GET",
            f"/messages/{message_id}/attachments/{attachment_id}",
        )

        content = base64.urlsafe_b64decode(data["data"])
        return filename, content

    # ==================== Label Operations ====================

    async def list_labels(self) -> list[Label]:
        """Get all labels."""
        data = await self._request("GET", "/labels")
        return [Label.from_api_response(l) for l in data.get("labels", [])]

    async def get_label(self, label_id: str) -> Label:
        """Get a specific label."""
        data = await self._request("GET", f"/labels/{label_id}")
        return Label.from_api_response(data)

    async def create_label(
        self,
        name: str,
        color: Optional[dict[str, str]] = None,
        show_unread_count: bool = True,
    ) -> Label:
        """Create a new label."""
        body = {
            "name": name,
            "labelListVisibility": "labelShowIfUnread" if show_unread_count else "labelShow",
            "messageListVisibility": "show",
        }
        if color:
            body["color"] = color

        data = await self._request("POST", "/labels", json=body)
        logger.info(f"Created label {data['id']}: {name}")
        return Label.from_api_response(data)

    async def update_label(
        self,
        label_id: str,
        name: Optional[str] = None,
        color: Optional[dict[str, str]] = None,
    ) -> Label:
        """Update a label."""
        body = {}
        if name:
            body["name"] = name
        if color:
            body["color"] = color

        data = await self._request("PATCH", f"/labels/{label_id}", json=body)
        return Label.from_api_response(data)

    async def delete_label(self, label_id: str) -> bool:
        """Delete a label."""
        await self._request("DELETE", f"/labels/{label_id}")
        logger.info(f"Deleted label {label_id}")
        return True

    # ==================== Thread Operations ====================

    async def get_thread(self, thread_id: str) -> list[GmailMessage]:
        """Get all messages in a thread."""
        data = await self._request("GET", f"/threads/{thread_id}")
        return [GmailMessage.from_api_response(m) for m in data.get("messages", [])]

    async def list_threads(
        self,
        query: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        max_results: int = 100,
    ) -> list[dict[str, str]]:
        """List threads."""
        params = {"maxResults": max_results}
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = ",".join(label_ids)

        data = await self._request("GET", "/threads", params=params)
        return data.get("threads", [])

    # ==================== Profile Operations ====================

    async def get_profile(self) -> dict[str, Any]:
        """Get user profile."""
        return await self._request("GET", "/profile")

    async def get_unread_count(self) -> int:
        """Get unread message count."""
        labels = await self.list_labels()
        for label in labels:
            if label.id == "UNREAD":
                return label.messages_total
        return 0

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "GmailClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class GmailError(Exception):
    """Gmail API error."""
    pass
