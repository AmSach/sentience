#!/usr/bin/env python3
"""OAuth Manager - Handle OAuth flows for multiple providers"""
import json
import secrets
import hashlib
import base64
import urllib.parse
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import http.server
import socketserver
import threading
import webbrowser
from pathlib import Path

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    redirect_uri: str = "http://localhost:8888/callback"
    scopes: list = None
    use_pkce: bool = False

# Provider configurations
PROVIDERS = {
    "google": OAuthConfig(
        client_id="",  # Set by user
        client_secret="",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        redirect_uri="http://localhost:8888/callback",
        scopes=["https://www.googleapis.com/auth/gmail.modify", 
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive"]
    ),
    "github": OAuthConfig(
        client_id="",
        client_secret="",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        redirect_uri="http://localhost:8888/callback",
        scopes=["repo", "user", "read:org"]
    ),
    "notion": OAuthConfig(
        client_id="",
        client_secret="",
        auth_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        redirect_uri="http://localhost:8888/callback",
        scopes=[]
    ),
    "slack": OAuthConfig(
        client_id="",
        client_secret="",
        auth_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        redirect_uri="http://localhost:8888/callback",
        scopes=["chat:write", "channels:read", "files:write"]
    ),
    "spotify": OAuthConfig(
        client_id="",
        client_secret="",
        auth_url="https://accounts.spotify.com/authorize",
        token_url="https://accounts.spotify.com/api/token",
        redirect_uri="http://localhost:8888/callback",
        scopes=["user-read-email", "user-library-read", "playlist-modify-public"],
        use_pkce=True
    )
}

class OAuthManager:
    """Manage OAuth flows for multiple providers"""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = Path(storage_dir or Path.home() / ".sentience" / "oauth")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tokens: Dict[str, dict] = {}
        self._load_tokens()
        
    def _load_tokens(self):
        """Load stored tokens"""
        token_file = self.storage_dir / "tokens.json"
        if token_file.exists():
            with open(token_file) as f:
                self.tokens = json.load(f)
                
    def _save_tokens(self):
        """Save tokens to disk"""
        token_file = self.storage_dir / "tokens.json"
        with open(token_file, 'w') as f:
            json.dump(self.tokens, f, indent=2)
            
    def _generate_pkce(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge"""
        verifier = secrets.token_urlsafe(64)[:128]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip('=')
        return verifier, challenge
        
    def _generate_state(self) -> str:
        """Generate state parameter for CSRF protection"""
        return secrets.token_urlsafe(16)
        
    def get_auth_url(self, provider: str, custom_config: OAuthConfig = None) -> Tuple[str, str]:
        """Get authorization URL for provider"""
        config = custom_config or PROVIDERS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")
            
        state = self._generate_state()
        params = {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "state": state
        }
        
        if config.scopes:
            params["scope"] = " ".join(config.scopes)
            
        if config.use_pkce:
            verifier, challenge = self._generate_pkce()
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
            # Store verifier for later
            self.tokens[f"{provider}_verifier"] = verifier
            self._save_tokens()
            
        auth_url = f"{config.auth_url}?{urllib.parse.urlencode(params)}"
        return auth_url, state
        
    def exchange_code(self, provider: str, code: str, custom_config: OAuthConfig = None) -> dict:
        """Exchange authorization code for access token"""
        import requests
        
        config = custom_config or PROVIDERS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")
            
        data = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "redirect_uri": config.redirect_uri,
            "grant_type": "authorization_code"
        }
        
        headers = {"Accept": "application/json"}
        
        # Add PKCE verifier if used
        if config.use_pkce:
            verifier = self.tokens.get(f"{provider}_verifier")
            if verifier:
                data["code_verifier"] = verifier
                
        resp = requests.post(config.token_url, data=data, headers=headers)
        token_data = resp.json()
        
        if "access_token" in token_data:
            self.tokens[provider] = token_data
            self._save_tokens()
            
        return token_data
        
    def refresh_token(self, provider: str, custom_config: OAuthConfig = None) -> dict:
        """Refresh access token"""
        import requests
        
        config = custom_config or PROVIDERS.get(provider)
        token_data = self.tokens.get(provider)
        
        if not token_data or not token_data.get("refresh_token"):
            raise ValueError("No refresh token available")
            
        data = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": token_data["refresh_token"],
            "grant_type": "refresh_token"
        }
        
        resp = requests.post(config.token_url, data=data)
        new_token = resp.json()
        
        if "access_token" in new_token:
            # Preserve refresh token if not returned
            if "refresh_token" not in new_token:
                new_token["refresh_token"] = token_data["refresh_token"]
            self.tokens[provider] = new_token
            self._save_tokens()
            
        return new_token
        
    def get_token(self, provider: str) -> Optional[str]:
        """Get access token for provider"""
        token_data = self.tokens.get(provider)
        if token_data:
            return token_data.get("access_token")
        return None
        
    def has_valid_token(self, provider: str) -> bool:
        """Check if we have a valid token"""
        return bool(self.tokens.get(provider, {}).get("access_token"))
        
    def revoke_token(self, provider: str):
        """Revoke token for provider"""
        if provider in self.tokens:
            del self.tokens[provider]
            self._save_tokens()
            
    def authenticate(self, provider: str, custom_config: OAuthConfig = None) -> bool:
        """Full OAuth flow with browser"""
        config = custom_config or PROVIDERS.get(provider)
        auth_url, state = self.get_auth_url(provider, custom_config)
        
        # Start callback server
        auth_code = [None]
        auth_state = [None]
        
        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/callback":
                    params = urllib.parse.parse_qs(parsed.query)
                    auth_code[0] = params.get("code", [None])[0]
                    auth_state[0] = params.get("state", [None])[0]
                    
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>Success!</h1><p>You can close this window.</p>")
                    
            def log_message(self, format, *args):
                pass  # Suppress logs
                
        with socketserver.TCPServer(("", 8888), CallbackHandler) as httpd:
            # Open browser
            webbrowser.open(auth_url)
            
            # Wait for callback
            httpd.handle_request()
            
        if auth_code[0] and auth_state[0] == state:
            token = self.exchange_code(provider, auth_code[0], custom_config)
            return "access_token" in token
        return False


class GmailClient:
    """Gmail API client"""
    
    def __init__(self, oauth: OAuthManager):
        self.oauth = oauth
        
    def _get_headers(self) -> dict:
        token = self.oauth.get_token("google")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
    def send_email(self, to: str, subject: str, body: str, html: bool = False) -> dict:
        """Send an email"""
        import requests
        import base64
        
        message = f"From: me\nTo: {to}\nSubject: {subject}\n\n{body}"
        raw = base64.urlsafe_b64encode(message.encode()).decode()
        
        resp = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers=self._get_headers(),
            json={"raw": raw}
        )
        return resp.json()
        
    def list_messages(self, query: str = "", max_results: int = 10) -> list:
        """List messages"""
        import requests
        
        resp = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=self._get_headers(),
            params={"q": query, "maxResults": max_results}
        )
        return resp.json().get("messages", [])
        
    def get_message(self, message_id: str) -> dict:
        """Get message details"""
        import requests
        
        resp = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            headers=self._get_headers()
        )
        return resp.json()


class NotionClient:
    """Notion API client"""
    
    def __init__(self, oauth: OAuthManager):
        self.oauth = oauth
        self.base_url = "https://api.notion.com/v1"
        
    def _get_headers(self) -> dict:
        token = self.oauth.get_token("notion")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
    def list_pages(self) -> list:
        """List pages"""
        import requests
        
        resp = requests.post(
            f"{self.base_url}/search",
            headers=self._get_headers(),
            json={"filter": {"property": "object", "value": "page"}}
        )
        return resp.json().get("results", [])
        
    def create_page(self, parent_id: str, title: str, content: str = "") -> dict:
        """Create a page"""
        import requests
        
        resp = requests.post(
            f"{self.base_url}/pages",
            headers=self._get_headers(),
            json={
                "parent": {"page_id": parent_id},
                "properties": {
                    "title": [{"text": {"content": title}}]
                }
            }
        )
        return resp.json()


class SlackClient:
    """Slack API client"""
    
    def __init__(self, oauth: OAuthManager):
        self.oauth = oauth
        self.base_url = "https://slack.com/api"
        
    def _get_headers(self) -> dict:
        token = self.oauth.get_token("slack")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
    def post_message(self, channel: str, text: str) -> dict:
        """Post a message"""
        import requests
        
        resp = requests.post(
            f"{self.base_url}/chat.postMessage",
            headers=self._get_headers(),
            json={"channel": channel, "text": text}
        )
        return resp.json()
        
    def list_channels(self) -> list:
        """List channels"""
        import requests
        
        resp = requests.get(
            f"{self.base_url}/conversations.list",
            headers=self._get_headers()
        )
        return resp.json().get("channels", [])
