"""
Google Calendar Client for Sentience v3.0
Full-featured Google Calendar integration with OAuth and event management.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import httpx

from .oauth_manager import OAuthManager, OAuthProvider, OAuthError

logger = logging.getLogger(__name__)


CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class EventStatus(Enum):
    """Event status."""
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class Visibility(Enum):
    """Event visibility."""
    DEFAULT = "default"
    PUBLIC = "public"
    PRIVATE = "private"


class Transparency(Enum):
    """Event transparency (availability)."""
    OPAQUE = "opaque"  # Shows as busy
    TRANSPARENT = "transparent"  # Shows as available


class ReminderMethod(Enum):
    """Reminder methods."""
    EMAIL = "email"
    POPUP = "popup"


@dataclass
class EventReminder:
    """Event reminder settings."""
    method: ReminderMethod
    minutes: int

    def to_api(self) -> dict[str, Any]:
        """Convert to API format."""
        return {
            "method": self.method.value,
            "minutes": self.minutes,
        }

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "EventReminder":
        """Create from API response."""
        return cls(
            method=ReminderMethod(data["method"]),
            minutes=data["minutes"],
        )


@dataclass
class EventAttendee:
    """Event attendee."""
    email: str
    name: Optional[str] = None
    response_status: Optional[str] = None  # needsAction, declined, tentative, accepted
    optional: bool = False
    organizer: bool = False
    self: bool = False

    def to_api(self) -> dict[str, Any]:
        """Convert to API format."""
        result = {"email": self.email}
        if self.name:
            result["displayName"] = self.name
        if self.optional:
            result["optional"] = True
        return result

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "EventAttendee":
        """Create from API response."""
        return cls(
            email=data["email"],
            name=data.get("displayName"),
            response_status=data.get("responseStatus"),
            optional=data.get("optional", False),
            organizer=data.get("organizer", False),
            self=data.get("self", False),
        )


@dataclass
class EventDateTime:
    """Event date/time."""
    date: Optional[str] = None  # YYYY-MM-DD for all-day events
    datetime: Optional[datetime] = None  # For timed events
    timezone: Optional[str] = None

    def to_api(self) -> dict[str, Any]:
        """Convert to API format."""
        result = {}
        if self.date:
            result["date"] = self.date
        elif self.datetime:
            result["dateTime"] = self.datetime.isoformat()
        if self.timezone:
            result["timeZone"] = self.timezone
        return result

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "EventDateTime":
        """Create from API response."""
        event_dt = cls(timezone=data.get("timeZone"))

        if "date" in data:
            event_dt.date = data["date"]
        elif "dateTime" in data:
            # Parse datetime
            dt_str = data["dateTime"]
            event_dt.datetime = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

        return event_dt


@dataclass
class CalendarEvent:
    """Calendar event."""
    id: str
    summary: str
    start: EventDateTime
    end: EventDateTime
    status: EventStatus = EventStatus.CONFIRMED
    description: Optional[str] = None
    location: Optional[str] = None
    visibility: Visibility = Visibility.DEFAULT
    transparency: Transparency = Transparency.OPAQUE
    attendees: list[EventAttendee] = field(default_factory=list)
    reminders: list[EventReminder] = field(default_factory=list)
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    creator: Optional[dict[str, Any]] = None
    organizer: Optional[dict[str, Any]] = None
    recurring_event_id: Optional[str] = None
    html_link: Optional[str] = None
    hangout_link: Optional[str] = None
    conference_data: Optional[dict[str, Any]] = None
    extended_properties: Optional[dict[str, Any]] = None
    calendar_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any], calendar_id: Optional[str] = None) -> "CalendarEvent":
        """Create from API response."""
        event = cls(
            id=data["id"],
            summary=data.get("summary", ""),
            start=EventDateTime.from_api(data["start"]),
            end=EventDateTime.from_api(data["end"]),
            status=EventStatus(data.get("status", "confirmed")),
            calendar_id=calendar_id,
        )

        if "description" in data:
            event.description = data["description"]
        if "location" in data:
            event.location = data["location"]
        if "visibility" in data:
            event.visibility = Visibility(data["visibility"])
        if "transparency" in data:
            event.transparency = Transparency(data["transparency"])
        if "attendees" in data:
            event.attendees = [EventAttendee.from_api(a) for a in data["attendees"]]
        if "reminders" in data and "overrides" in data["reminders"]:
            event.reminders = [
                EventReminder.from_api(r) for r in data["reminders"]["overrides"]
            ]
        if "created" in data:
            event.created = datetime.fromisoformat(data["created"].replace("Z", "+00:00"))
        if "updated" in data:
            event.updated = datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
        if "creator" in data:
            event.creator = data["creator"]
        if "organizer" in data:
            event.organizer = data["organizer"]
        if "recurringEventId" in data:
            event.recurring_event_id = data["recurringEventId"]
        if "htmlLink" in data:
            event.html_link = data["htmlLink"]
        if "hangoutLink" in data:
            event.hangout_link = data["hangoutLink"]
        if "conferenceData" in data:
            event.conference_data = data["conferenceData"]
        if "extendedProperties" in data:
            event.extended_properties = data["extendedProperties"]

        return event

    def to_api(self) -> dict[str, Any]:
        """Convert to API format for create/update."""
        result = {
            "summary": self.summary,
            "start": self.start.to_api(),
            "end": self.end.to_api(),
        }

        if self.description:
            result["description"] = self.description
        if self.location:
            result["location"] = self.location
        if self.visibility != Visibility.DEFAULT:
            result["visibility"] = self.visibility.value
        if self.transparency != Transparency.OPAQUE:
            result["transparency"] = self.transparency.value
        if self.attendees:
            result["attendees"] = [a.to_api() for a in self.attendees]
        if self.reminders:
            result["reminders"] = {
                "useDefault": False,
                "overrides": [r.to_api() for r in self.reminders],
            }

        return result


@dataclass
class Calendar:
    """Calendar object."""
    id: str
    summary: str
    description: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    primary: bool = False
    access_role: Optional[str] = None
    selected: bool = False
    background_color: Optional[str] = None
    foreground_color: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Calendar":
        """Create from API response."""
        return cls(
            id=data["id"],
            summary=data.get("summary", ""),
            description=data.get("description"),
            location=data.get("location"),
            timezone=data.get("timeZone"),
            primary=data.get("primary", False),
            access_role=data.get("accessRole"),
            selected=data.get("selected", False),
            background_color=data.get("backgroundColor"),
            foreground_color=data.get("foregroundColor"),
        )


@dataclass
class FreeBusyPeriod:
    """Free/busy time period."""
    start: datetime
    end: datetime

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "FreeBusyPeriod":
        """Create from API response."""
        return cls(
            start=datetime.fromisoformat(data["start"].replace("Z", "+00:00")),
            end=datetime.fromisoformat(data["end"].replace("Z", "+00:00")),
        )


@dataclass
class FreeBusyResponse:
    """Free/busy query response."""
    time_min: datetime
    time_max: datetime
    calendars: dict[str, list[FreeBusyPeriod]]
    groups: dict[str, list[FreeBusyPeriod]] = field(default_factory=dict)


class GoogleCalendarClient:
    """
    Full-featured Google Calendar client with:
    - OAuth setup
    - Create/update/delete events
    - Free/busy queries
    - Calendar list management
    """

    BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        oauth_manager: OAuthManager,
        user_id: str = "me",
    ):
        self.oauth_manager = oauth_manager
        self.user_id = user_id
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        token = await self.oauth_manager.get_or_refresh_token(
            OAuthProvider.GOOGLE, self.user_id
        )
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Calendar API."""
        headers = await self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        url = f"{self.BASE_URL}{path}"

        response = await self._http_client.request(
            method, url, headers=headers, **kwargs
        )

        if response.status_code == 401:
            token = await self.oauth_manager.get_or_refresh_token(
                OAuthProvider.GOOGLE, self.user_id
            )
            headers["Authorization"] = f"Bearer {token.access_token}"
            response = await self._http_client.request(
                method, url, headers=headers, **kwargs
            )

        if response.status_code >= 400:
            error = response.json().get("error", {}).get("message", response.text)
            raise CalendarError(f"Calendar API error: {error}")

        if response.status_code == 204:
            return {}

        return response.json()

    # ==================== Calendar Operations ====================

    async def list_calendars(self) -> list[Calendar]:
        """List all calendars."""
        data = await self._request("GET", "/users/me/calendarList")
        return [Calendar.from_api(c) for c in data.get("items", [])]

    async def get_calendar(self, calendar_id: str) -> Calendar:
        """Get a specific calendar."""
        data = await self._request("GET", f"/users/me/calendarList/{calendar_id}")
        return Calendar.from_api(data)

    async def get_primary_calendar(self) -> Calendar:
        """Get the primary calendar."""
        data = await self._request("GET", "/calendars/primary")
        return Calendar.from_api(data)

    # ==================== Event Operations ====================

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> CalendarEvent:
        """Get an event by ID."""
        data = await self._request(
            "GET", f"/calendars/{calendar_id}/events/{event_id}"
        )
        return CalendarEvent.from_api(data, calendar_id)

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 250,
        single_events: bool = True,
        order_by: str = "startTime",
        query: Optional[str] = None,
        page_token: Optional[str] = None,
    ) -> tuple[list[CalendarEvent], Optional[str]]:
        """
        List events in a calendar.
        Returns (events, next_page_token).
        """
        params = {
            "maxResults": max_results,
            "singleEvents": str(single_events).lower(),
            "orderBy": order_by,
        }

        if time_min:
            params["timeMin"] = time_min.isoformat()
        if time_max:
            params["timeMax"] = time_max.isoformat()
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET", f"/calendars/{calendar_id}/events", params=params
        )

        events = [
            CalendarEvent.from_api(e, calendar_id)
            for e in data.get("items", [])
        ]
        next_token = data.get("nextPageToken")

        return events, next_token

    async def create_event(
        self,
        summary: str,
        start: EventDateTime,
        end: EventDateTime,
        calendar_id: str = "primary",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[EventAttendee]] = None,
        reminders: Optional[list[EventReminder]] = None,
        visibility: Visibility = Visibility.DEFAULT,
        transparency: Transparency = Transparency.OPAQUE,
        conference_data: Optional[dict[str, Any]] = None,
    ) -> CalendarEvent:
        """Create a new event."""
        event = CalendarEvent(
            id="",
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
            attendees=attendees or [],
            reminders=reminders or [],
            visibility=visibility,
            transparency=transparency,
            conference_data=conference_data,
        )

        params = {}
        if conference_data:
            params["conferenceDataVersion"] = "1"

        data = await self._request(
            "POST",
            f"/calendars/{calendar_id}/events",
            json=event.to_api(),
            params=params if params else None,
        )

        logger.info(f"Created event {data['id']}: {summary}")
        return CalendarEvent.from_api(data, calendar_id)

    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        **kwargs,
    ) -> CalendarEvent:
        """Update an existing event."""
        # Get existing event first
        existing = await self.get_event(event_id, calendar_id)

        # Build update body
        body = existing.to_api()

        # Override with provided kwargs
        if "summary" in kwargs:
            body["summary"] = kwargs["summary"]
        if "description" in kwargs:
            body["description"] = kwargs["description"]
        if "location" in kwargs:
            body["location"] = kwargs["location"]
        if "start" in kwargs:
            body["start"] = kwargs["start"].to_api()
        if "end" in kwargs:
            body["end"] = kwargs["end"].to_api()
        if "attendees" in kwargs:
            body["attendees"] = [a.to_api() for a in kwargs["attendees"]]
        if "reminders" in kwargs:
            body["reminders"] = {
                "useDefault": False,
                "overrides": [r.to_api() for r in kwargs["reminders"]],
            }
        if "visibility" in kwargs:
            body["visibility"] = kwargs["visibility"].value
        if "transparency" in kwargs:
            body["transparency"] = kwargs["transparency"].value
        if "status" in kwargs:
            body["status"] = kwargs["status"].value

        data = await self._request(
            "PUT",
            f"/calendars/{calendar_id}/events/{event_id}",
            json=body,
        )

        logger.info(f"Updated event {event_id}")
        return CalendarEvent.from_api(data, calendar_id)

    async def patch_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        **kwargs,
    ) -> CalendarEvent:
        """Patch (partial update) an event."""
        body = {}

        if "summary" in kwargs:
            body["summary"] = kwargs["summary"]
        if "description" in kwargs:
            body["description"] = kwargs["description"]
        if "location" in kwargs:
            body["location"] = kwargs["location"]
        if "start" in kwargs:
            body["start"] = kwargs["start"].to_api()
        if "end" in kwargs:
            body["end"] = kwargs["end"].to_api()
        if "attendees" in kwargs:
            body["attendees"] = [a.to_api() for a in kwargs["attendees"]]
        if "status" in kwargs:
            body["status"] = kwargs["status"].value

        data = await self._request(
            "PATCH",
            f"/calendars/{calendar_id}/events/{event_id}",
            json=body,
        )

        return CalendarEvent.from_api(data, calendar_id)

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_notifications: bool = True,
    ) -> bool:
        """Delete an event."""
        await self._request(
            "DELETE",
            f"/calendars/{calendar_id}/events/{event_id}",
            params={"sendNotifications": str(send_notifications).lower()},
        )
        logger.info(f"Deleted event {event_id}")
        return True

    async def move_event(
        self,
        event_id: str,
        destination_calendar_id: str,
        source_calendar_id: str = "primary",
    ) -> CalendarEvent:
        """Move an event to another calendar."""
        data = await self._request(
            "POST",
            f"/calendars/{source_calendar_id}/events/{event_id}/move",
            params={"destination": destination_calendar_id},
        )
        return CalendarEvent.from_api(data, destination_calendar_id)

    async def quick_add(
        self,
        text: str,
        calendar_id: str = "primary",
    ) -> CalendarEvent:
        """
        Quick add event using natural language.
        Example: "Meeting with John tomorrow at 3pm"
        """
        data = await self._request(
            "POST",
            f"/calendars/{calendar_id}/events/quickAdd",
            params={"text": text},
        )
        return CalendarEvent.from_api(data, calendar_id)

    # ==================== Recurring Events ====================

    async def get_instances(
        self,
        event_id: str,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 250,
    ) -> list[CalendarEvent]:
        """Get instances of a recurring event."""
        params = {"maxResults": max_results}

        if time_min:
            params["timeMin"] = time_min.isoformat()
        if time_max:
            params["timeMax"] = time_max.isoformat()

        data = await self._request(
            "GET",
            f"/calendars/{calendar_id}/events/{event_id}/instances",
            params=params,
        )

        return [
            CalendarEvent.from_api(e, calendar_id)
            for e in data.get("items", [])
        ]

    # ==================== Free/Busy ====================

    async def query_free_busy(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_ids: Optional[list[str]] = None,
        group_ids: Optional[list[str]] = None,
        timezone: Optional[str] = None,
    ) -> FreeBusyResponse:
        """Query free/busy information."""
        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
        }

        if timezone:
            body["timeZone"] = timezone

        items = []
        if calendar_ids:
            for cal_id in calendar_ids:
                items.append({"id": cal_id})
        else:
            items.append({"id": "primary"})

        if group_ids:
            for group_id in group_ids:
                items.append({"id": group_id, "type": "group"})

        body["items"] = items

        data = await self._request(
            "POST",
            "/freeBusy",
            json=body,
        )

        # Parse response
        calendars = {}
        for cal_id, cal_data in data.get("calendars", {}).items():
            if "busy" in cal_data:
                calendars[cal_id] = [
                    FreeBusyPeriod.from_api(p) for p in cal_data["busy"]
                ]
            else:
                calendars[cal_id] = []

        groups = {}
        for group_id, group_data in data.get("groups", {}).items():
            if "busy" in group_data:
                groups[group_id] = [
                    FreeBusyPeriod.from_api(p) for p in group_data["busy"]
                ]
            else:
                groups[group_id] = []

        return FreeBusyResponse(
            time_min=datetime.fromisoformat(data["timeMin"].replace("Z", "+00:00")),
            time_max=datetime.fromisoformat(data["timeMax"].replace("Z", "+00:00")),
            calendars=calendars,
            groups=groups,
        )

    async def is_free(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
    ) -> bool:
        """Check if a time slot is free."""
        response = await self.query_free_busy(
            time_min=start,
            time_max=end,
            calendar_ids=[calendar_id],
        )

        periods = response.calendars.get(calendar_id, [])

        for period in periods:
            # Check if there's any overlap
            if not (end <= period.start or start >= period.end):
                return False

        return True

    async def find_free_time(
        self,
        duration_minutes: int,
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = "primary",
    ) -> list[tuple[datetime, datetime]]:
        """Find free time slots of specified duration."""
        response = await self.query_free_busy(
            time_min=time_min,
            time_max=time_max,
            calendar_ids=[calendar_id],
        )

        periods = response.calendars.get(calendar_id, [])
        duration = timedelta(minutes=duration_minutes)

        free_slots = []
        current_start = time_min

        for period in sorted(periods, key=lambda p: p.start):
            if current_start + duration <= period.start:
                free_slots.append((current_start, period.start))
            current_start = max(current_start, period.end)

        # Check after last busy period
        if current_start + duration <= time_max:
            free_slots.append((current_start, time_max))

        return free_slots

    # ==================== Convenience Methods ====================

    async def create_simple_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        timezone: str = "UTC",
        **kwargs,
    ) -> CalendarEvent:
        """Create a simple timed event."""
        start_dt = EventDateTime(datetime=start, timezone=timezone)
        end_dt = EventDateTime(datetime=end, timezone=timezone)

        return await self.create_event(
            summary=summary,
            start=start_dt,
            end=end_dt,
            **kwargs,
        )

    async def create_all_day_event(
        self,
        summary: str,
        date: str,  # YYYY-MM-DD
        calendar_id: str = "primary",
        **kwargs,
    ) -> CalendarEvent:
        """Create an all-day event."""
        start_dt = EventDateTime(date=date)
        end_dt = EventDateTime(date=date)

        return await self.create_event(
            summary=summary,
            start=start_dt,
            end=end_dt,
            calendar_id=calendar_id,
            **kwargs,
        )

    async def get_upcoming_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 10,
    ) -> list[CalendarEvent]:
        """Get upcoming events."""
        events, _ = await self.list_events(
            calendar_id=calendar_id,
            time_min=datetime.now(),
            max_results=max_results,
        )
        return events

    async def get_events_for_day(
        self,
        date: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        """Get all events for a specific day."""
        time_min = date.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = time_min + timedelta(days=1)

        events, _ = await self.list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
        )
        return events

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "GoogleCalendarClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class CalendarError(Exception):
    """Calendar API error."""
    pass
