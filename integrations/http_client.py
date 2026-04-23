"""HTTP Integration - generic API connector for any REST API."""
import urllib.request, json, os, hashlib, time
from typing import Dict, Any, Optional
# removed

class HTTPIntegration:
    def __init__(self, config):
        self.config = config
        self.base_url = config.secrets.get("base_url", "")
        self.headers = config.secrets.get("headers", {})
        self.api_key = config.secrets.get("api_key", "")
    
    def connect(self) -> bool:
        if self.api_key or self.base_url:
            return True
        return False
    
    def request(self, method: str, path: str, data: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        headers = {**self.headers}
        if self.api_key:
            auth_type = self.config.secrets.get("auth_type", "Bearer")
            headers["Authorization"] = f"{auth_type} {self.api_key}"
        headers["Content-Type"] = "application/json"
        
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return {"status": resp.status, "data": json.loads(resp.read())}
        except Exception as e:
            return {"error": str(e)}
    
    def get(self, path: str):
        return self.request("GET", path)
    
    def post(self, path: str, data: dict):
        return self.request("POST", path, data)
    
    def put(self, path: str, data: dict):
        return self.request("PUT", path, data)
    
    def delete(self, path: str):
        return self.request("DELETE", path)
