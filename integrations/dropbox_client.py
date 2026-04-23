#!/usr/bin/env python3
"""Dropbox Integration - files, folders, search, upload, download."""
import os, json
from typing import List, Dict

try:
    import requests
    DROPBOX_AVAILABLE = True
except ImportError: DROPBOX_AVAILABLE = False

class DropboxIntegration:
    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.environ.get("DROPBOX_TOKEN")
        self.headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"} if self.access_token else {}
        self.content_headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}
    
    def is_connected(self) -> bool: return bool(self.access_token)
    def connect(self, token: str) -> bool:
        self.access_token = token
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.content_headers = {"Authorization": f"Bearer {token}"}
        return self.is_connected()
    
    def _request(self, endpoint: str, data: dict = None) -> dict:
        if not self.access_token: return {"error": "not connected"}
        try:
            import requests
            resp = requests.post(f"https://api.dropboxapi.com/2/{endpoint}", headers=self.headers, json=data, timeout=30)
            return resp.json()
        except Exception as e: return {"error": str(e)}
    
    def list_folder(self, path: str = "") -> List[Dict]:
        result = self._request("files/list_folder", {"path": path, "include_media_info": True})
        if "entries" in result: return result["entries"]
        return []
    
    def search(self, query: str, max_results: int = 20) -> List[Dict]:
        result = self._request("files/search_v2", {"query": query, "options": {"max_results": min(max_results, 300)}})
        if "matches" in result: return [m["metadata"]["metadata"] for m in result["matches"]]
        return []
    
    def upload_file(self, path: str, content: bytes) -> Dict:
        if not self.access_token: return {"error": "not connected"}
        try:
            import requests
            resp = requests.post("https://content.dropboxapi.com/2/files/upload",
                headers={"Authorization": f"Bearer {self.access_token}", "Dropbox-API-Arg": json.dumps({"path": path, "mode": "add", "autorename": True}), "Content-Type": "application/octet-stream"},
                data=content, timeout=60)
            return resp.json()
        except Exception as e: return {"error": str(e)}
    
    def download_file(self, path: str) -> bytes:
        if not self.access_token: return b""
        try:
            import requests
            resp = requests.post("https://content.dropboxapi.com/2/files/download",
                headers={"Authorization": f"Bearer {self.access_token}", "Dropbox-API-Arg": json.dumps({"path": path})}, timeout=60)
            return resp.content
        except: return b""
