#!/usr/bin/env python3
"""Google Drive Integration - files, search, upload, download."""
import os, json
from typing import List, Dict, Optional

try:
    import requests
    DRIVE_AVAILABLE = True
except ImportError: DRIVE_AVAILABLE = False

class DriveIntegration:
    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.environ.get("GOOGLE_DRIVE_TOKEN")
        self.headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}
        self.base_url = "https://www.googleapis.com/drive/v3"
    
    def is_connected(self) -> bool: return bool(self.access_token)
    def connect(self, token: str) -> bool:
        self.access_token = token; self.headers = {"Authorization": f"Bearer {token}"}; return self.is_connected()
    
    def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None, files: dict = None) -> dict:
        if not self.access_token: return {"error": "not connected"}
        try:
            import requests
            url = f"{self.base_url}/{endpoint}"
            resp = requests.request(method, url, headers=self.headers, params=params, json=data, files=files, timeout=60)
            return resp.json()
        except Exception as e: return {"error": str(e)}
    
    def list_files(self, folder_id: str = None, mime_type: str = None, max_results: int = 100) -> List[Dict]:
        q_parts = ["trashed=false"]
        if folder_id: q_parts.append(f"'{folder_id}' in parents")
        if mime_type: q_parts.append(f"mimeType='{mime_type}'")
        result = self._request("GET", "files", {"q": " and ".join(q_parts), "pageSize": min(max_results, 200), "fields": "files(id,name,mimeType,modifiedTime,size,parents)"})
        if "files" in result: return result["files"]
        return []
    
    def search(self, query: str, max_results: int = 20) -> List[Dict]:
        result = self._request("GET", "files", {"q": query, "pageSize": min(max_results, 100), "fields": "files(id,name,mimeType,modifiedTime)"})
        if "files" in result: return result["files"]
        return []
    
    def get_file(self, file_id: str) -> Dict:
        return self._request("GET", f"files/{file_id}", {"fields": "id,name,mimeType,modifiedTime,size,description,parents"})
    
    def download_file(self, file_id: str, dest_path: str) -> bool:
        if not self.access_token: return False
        try:
            import requests
            resp = requests.get(f"{self.base_url}/files/{file_id}?alt=media", headers=self.headers, timeout=60)
            if resp.status_code == 200:
                with open(dest_path, "wb") as f: f.write(resp.content)
                return True
        except: pass
        return False
    
    def upload_file(self, name: str, parent_id: str = None, content: bytes = None, mime_type: str = "text/plain") -> Dict:
        metadata = {"name": name, "mimeType": mime_type}
        if parent_id: metadata["parents"] = [parent_id]
        if content is None: content = b""
        try:
            import requests
            from io import BytesIO
            resp = requests.post(f"{self.base_url}/upload/files",
                headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "multipart/related"},
                data={"metadata": json.dumps(metadata)},
                files={"file": (name, BytesIO(content), mime_type)}, timeout=60)
            return resp.json()
        except Exception as e: return {"error": str(e)}
    
    def create_folder(self, name: str, parent_id: str = None) -> Dict:
        data = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id: data["parents"] = [parent_id]
        return self._request("POST", "files", data=data)
