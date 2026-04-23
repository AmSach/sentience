#!/usr/bin/env python3
"""Google Calendar Integration - events, create, search, availability."""
import os, json, time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

try:
    import requests
    CALENDAR_AVAILABLE = True
except ImportError: CALENDAR_AVAILABLE = False

class CalendarIntegration:
    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.environ.get("GOOGLE_CALENDAR_TOKEN")
        self.headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"} if self.access_token else {}
        self.base_url = "https://www.googleapis.com/calendar/v3"
    
    def is_connected(self) -> bool: return bool(self.access_token)
    
    def connect(self, access_token: str) -> bool:
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        return self.is_connected()
    
    def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
        if not self.access_token: return {"error": "not connected"}
        try:
            import requests
            url = f"{self.base_url}/{endpoint}"
            resp = requests.request(method, url, headers=self.headers, params=params, json=data, timeout=30)
            return resp.json()
        except Exception as e: return {"error": str(e)}
    
    def list_events(self, calendar_id: str = "primary", max_results: int = 20, time_min: str = None, time_max: str = None, q: str = None) -> List[Dict]:
        params = {"calendarId": calendar_id, "maxResults": min(max_results, 250), "singleEvents": True, "orderBy": "startTime"}
        if time_min: params["timeMin"] = time_min
        if time_max: params["timeMax"] = time_max
        if q: params["q"] = q
        result = self._request("GET", "calendars/primary/events", params=params)
        if "items" in result: return result["items"]
        return []
    
    def get_event(self, event_id: str, calendar_id: str = "primary") -> Dict:
        return self._request("GET", f"calendars/{calendar_id}/events/{event_id}")
    
    def create_event(self, summary: str, start: str, end: str, description: str = "", location: str = "", attendees: List[str] = None, calendar_id: str = "primary") -> Dict:
        data = {
            "summary": summary, "location": location,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
            "description": description,
        }
        if attendees: data["attendees"] = [{"email": a} for a in attendees]
        return self._request("POST", f"calendars/{calendar_id}/events", data=data)
    
    def quick_add(self, text: str) -> Dict:
        return self._request("POST", f"calendars/primary/events?text={text}") or {"success": True}
    
    def update_event(self, event_id: str, data: dict) -> Dict:
        return self._request("PATCH", f"calendars/primary/events/{event_id}", data=data)
    
    def delete_event(self, event_id: str) -> bool:
        result = self._request("DELETE", f"calendars/primary/events/{event_id}")
        return result == {} or "error" not in result
    
    def freebusy(self, start: str, end: str, emails: List[str] = None) -> Dict:
        data = {"timeMin": start, "timeMax": end, "items": [{"id": e} for e in (emails or [os.environ.get("USER_EMAIL", "primary")])]}
        result = self._request("POST", "freeBusy", data=data)
        if "calendars" in result: return result["calendars"]
        return {}
