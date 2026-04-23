"""Cloud integrations - Dropbox, Google Drive, OneDrive, S3."""
import os, json, base64, hashlib, time

class CloudStorage:
    def __init__(self, provider="dropbox"):
        self.provider = provider
        self.token = None
        self.client_id = None
        self.client_secret = None

    def configure(self, token=None, client_id=None, client_secret=None):
        self.token = token
        self.client_id = client_id
        self.client_secret = client_secret

    def upload(self, local_path, remote_path):
        if self.provider == "dropbox" and self.token:
            import urllib.request
            url = "https://content.dropboxapi.com/2/files/upload"
            headers = {"Authorization": f"Bearer {self.token}", "Dropbox-API-Arg": json.dumps({"path": remote_path, "mode": "add", "autorename": True})}
            with open(local_path, "rb") as f:
                data = f.read()
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                resp = urllib.request.urlopen(req)
                return {"status": "uploaded", "path": remote_path, "size": len(data)}
            except Exception as e:
                return {"error": str(e)}
        return {"error": "provider not configured"}

    def download(self, remote_path, local_path):
        if self.provider == "dropbox" and self.token:
            import urllib.request
            url = "https://content.dropboxapi.com/2/files/download"
            headers = {"Authorization": f"Bearer {self.token}", "Dropbox-API-Arg": json.dumps({"path": remote_path})}
            req = urllib.request.Request(url, headers=headers, method="POST")
            try:
                resp = urllib.request.urlopen(req)
                data = resp.read()
                with open(local_path, "wb") as f:
                    f.write(data)
                return {"status": "downloaded", "path": local_path, "size": len(data)}
            except Exception as e:
                return {"error": str(e)}
        return {"error": "provider not configured"}

    def list_files(self, path=""):
        if self.provider == "dropbox" and self.token:
            import urllib.request
            url = "https://api.dropboxapi.com/2/files/list_folder"
            headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
            data = json.dumps({"path": path or ""}).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                resp = urllib.request.urlopen(req)
                result = json.loads(resp.read())
                return [f["name"] for f in result.get("entries", [])]
            except Exception as e:
                return {"error": str(e)}
        return []

    def create_share_link(self, path):
        if self.provider == "dropbox" and self.token:
            import urllib.request
            url = "https://api.dropboxapi.com/2/sharing/create_shared_link"
            headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
            data = json.dumps({"path": path, "settings": {"requested_visibility": "public"}}).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                resp = json.loads(urllib.request.urlopen(req).read())
                return resp.get("url", resp.get("shared_folder_url", ""))
            except: pass
        return ""

_dropbox = CloudStorage("dropbox")
_onedrive = CloudStorage("onedrive")
_google_drive = CloudStorage("google_drive")

def get_cloud(provider): return {"dropbox": _dropbox, "onedrive": _onedrive, "google_drive": _google_drive}.get(provider, _dropbox)
