#!/usr/bin/env python3
"""Notion Integration - pages, databases, search via Notion API."""
import os, json, time
from typing import List, Dict, Any, Optional

try:
    from notion_client import AsyncClient
    NOTION_AVAILABLE = True
except ImportError:
    try:
        import requests
        NOTION_AVAILABLE = True
    except: NOTION_AVAILABLE = False

class NotionIntegration:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("NOTION_API_KEY")
        self.base_url = "https://api.notion.com/v1"
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"} if self.api_key else {}
        self.async_client = None
        if NOTION_AVAILABLE and self.api_key: self._init_async()
    
    def _init_async(self):
        try: self.async_client = AsyncClient(auth=self.api_key)
        except: pass
    
    def is_connected(self) -> bool: return bool(self.api_key)
    
    def connect(self, api_key: str) -> bool:
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
        self._init_async()
        return self.is_connected()
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        if not self.api_key: return {"error": "not connected"}
        try:
            import requests
            url = f"{self.base_url}/{endpoint}"
            resp = requests.request(method, url, headers=self.headers, json=data, timeout=30)
            return resp.json()
        except Exception as e: return {"error": str(e)}
    
    def search(self, query: str = "", filter_type: str = None, max_results: int = 20) -> List[Dict]:
        body = {"query": query, "page_size": min(max_results, 100)}
        if filter_type: body["filter"] = {"property": "object", "value": filter_type}
        result = self._request("POST", "search", body)
        if "results" in result: return result["results"]
        return [result] if "error" in result else []
    
    def get_page(self, page_id: str) -> Dict:
        return self._request("GET", f"pages/{page_id}")
    
    def get_block_children(self, block_id: str, max_results: int = 100) -> List[Dict]:
        result = self._request("GET", f"blocks/{block_id}/children?page_size={min(max_results, 100)}")
        if "results" in result: return result["results"]
        return [result] if "error" in result else []
    
    def create_page(self, parent_id: str, properties: dict, children: List[dict] = None) -> Dict:
        data = {"parent": {"page_id": parent_id} if len(parent_id) > 30 else {"database_id": parent_id}, "properties": properties}
        if children: data["children"] = children
        return self._request("POST", "pages", data)
    
    def update_page(self, page_id: str, properties: dict) -> Dict:
        return self._request("PATCH", f"pages/{page_id}", {"properties": properties})
    
    def create_database(self, parent_id: str, title: str, properties: dict) -> Dict:
        data = {"parent": {"page_id": parent_id}, "title": [{"text": {"content": title}}], "properties": properties}
        return self._request("POST", "databases", data)
    
    def append_block(self, block_id: str, children: List[dict]) -> Dict:
        return self._request("PATCH", f"blocks/{block_id}/children", {"children": children})
    
    def archive_page(self, page_id: str) -> Dict:
        return self._request("PATCH", f"pages/{page_id}", {"archived": True})
