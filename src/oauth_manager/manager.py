#!/usr/bin/env python3
"""OAuth Integration Module - Handle OAuth flows for external services"""
import json
import secrets
import hashlib
import base64
import urllib.parse
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime, timedelta
import webbrowser
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler

# OAuth configurations for common services
OAUTH_PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["repo", "user", "read:org"]
    },
    "notion": {
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes": []
    },
    "linear": {
        "auth_url": "https://linear.app/oauth/authorize",
        "token_url": "https://api.linear.app/oauth/token",
        "scopes": ["read", "write"]
    }
}

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback"""
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                <h1>Authentication successful!</h1>
                <p>You can close this window now.</p>
                <script>setTimeout(() => window.close(), 2000);</script>
                </body>
                </html>
            """)
        elif "error" in params:
            self.server.auth_error = params["error"][0]
            self.send_response(400)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logging


class OAuthManager:
    """Manage OAuth flows and tokens"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = Path(storage_path or (Path.home() / ".sentience" / "oauth_tokens.json"))
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.tokens = self._load_tokens()
    
    def _load_tokens(self) -> Dict:
        """Load stored tokens"""
        if self.storage_path.exists():
            try:
                return json.loads(self.storage_path.read_text())
            except:
                pass
        return {}
    
    def _save_tokens(self):
        """Save tokens to storage"""
        self.storage_path.write_text(json.dumps(self.tokens, indent=2))
    
    def generate_pkce(self) -> Dict[str, str]:
        """Generate PKCE code verifier and challenge"""
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")
        
        return {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge
        }
    
    def generate_state(self) -> str:
        """Generate random state for CSRF protection"""
        return secrets.token_urlsafe(16)
    
    def get_auth_url(self, provider: str, client_id: str, redirect_uri: str,
                     scopes: List[str] = None, pkce: bool = True) -> Dict:
        """Generate authorization URL"""
        config = OAUTH_PROVIDERS.get(provider)
        if not config:
            return {"success": False, "error": f"Unknown provider: {provider}"}
        
        state = self.generate_state()
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": " ".join(scopes or config["scopes"])
        }
        
        pkce_data = None
        if pkce:
            pkce_data = self.generate_pkce()
            params["code_challenge"] = pkce_data["code_challenge"]
            params["code_challenge_method"] = "S256"
        
        # Store state for verification
        self.tokens[f"{provider}_state"] = {
            "state": state,
            "pkce": pkce_data,
            "redirect_uri": redirect_uri,
            "client_id": client_id
        }
        self._save_tokens()
        
        auth_url = f"{config['auth_url']}?{urllib.parse.urlencode(params)}"
        
        return {
            "success": True,
            "auth_url": auth_url,
            "state": state
        }
    
    def wait_for_callback(self, port: int = 8765, timeout: int = 300) -> Dict:
        """Wait for OAuth callback on local port"""
        try:
            server = HTTPServer(("localhost", port), OAuthCallbackHandler)
            server.auth_code = None
            server.auth_error = None
            server.timeout = timeout
            
            # Handle one request
            server.handle_request()
            
            if server.auth_code:
                return {"success": True, "code": server.auth_code}
            elif server.auth_error:
                return {"success": False, "error": server.auth_error}
            else:
                return {"success": False, "error": "Timeout waiting for callback"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def exchange_code(self, provider: str, code: str, client_id: str, 
                      client_secret: str, redirect_uri: str) -> Dict:
        """Exchange authorization code for access token"""
        import requests
        
        config = OAUTH_PROVIDERS.get(provider)
        if not config:
            return {"success": False, "error": f"Unknown provider: {provider}"}
        
        # Get stored PKCE data if available
        state_data = self.tokens.get(f"{provider}_state", {})
        pkce_data = state_data.get("pkce")
        
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        if pkce_data:
            data["code_verifier"] = pkce_data["code_verifier"]
        
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.post(config["token_url"], data=data, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            
            # Store tokens
            self.tokens[provider] = {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in"),
                "token_type": token_data.get("token_type", "Bearer"),
                "obtained_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat()
            }
            self._save_tokens()
            
            return {"success": True, "tokens": self.tokens[provider]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def refresh_token(self, provider: str, client_id: str, client_secret: str) -> Dict:
        """Refresh access token using refresh token"""
        import requests
        
        config = OAUTH_PROVIDERS.get(provider)
        if not config:
            return {"success": False, "error": f"Unknown provider: {provider}"}
        
        token_data = self.tokens.get(provider)
        if not token_data or not token_data.get("refresh_token"):
            return {"success": False, "error": "No refresh token available"}
        
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": token_data["refresh_token"],
            "grant_type": "refresh_token"
        }
        
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.post(config["token_url"], data=data, headers=headers)
            response.raise_for_status()
            new_token_data = response.json()
            
            # Update stored tokens
            self.tokens[provider].update({
                "access_token": new_token_data.get("access_token"),
                "refresh_token": new_token_data.get("refresh_token") or token_data["refresh_token"],
                "expires_in": new_token_data.get("expires_in"),
                "obtained_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=new_token_data.get("expires_in", 3600))).isoformat()
            })
            self._save_tokens()
            
            return {"success": True, "tokens": self.tokens[provider]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_token(self, provider: str) -> Optional[str]:
        """Get valid access token for provider"""
        token_data = self.tokens.get(provider)
        if not token_data:
            return None
        
        # Check if expired
        expires_at = datetime.fromisoformat(token_data.get("expires_at", "9999-12-31"))
        if datetime.now() >= expires_at - timedelta(minutes=5):
            return None  # Token expired or about to expire
        
        return token_data.get("access_token")
    
    def revoke_token(self, provider: str) -> Dict:
        """Revoke tokens for provider"""
        if provider in self.tokens:
            del self.tokens[provider]
            self._save_tokens()
        return {"success": True, "message": f"Tokens revoked for {provider}"}
    
    def start_auth_flow(self, provider: str, client_id: str, client_secret: str,
                        port: int = 8765) -> Dict:
        """Complete OAuth flow with local callback"""
        redirect_uri = f"http://localhost:{port}/callback"
        
        # Generate auth URL
        auth_result = self.get_auth_url(provider, client_id, redirect_uri)
        if not auth_result["success"]:
            return auth_result
        
        # Open browser
        webbrowser.open(auth_result["auth_url"])
        
        # Wait for callback
        callback_result = self.wait_for_callback(port)
        if not callback_result["success"]:
            return callback_result
        
        # Exchange code
        return self.exchange_code(
            provider, callback_result["code"], 
            client_id, client_secret, redirect_uri
        )


# Tool definitions for AI
OAUTH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "oauth_connect",
            "description": "Connect to OAuth provider",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Provider name (google, github, notion, linear)"},
                    "client_id": {"type": "string", "description": "OAuth client ID"},
                    "client_secret": {"type": "string", "description": "OAuth client secret"}
                },
                "required": ["provider", "client_id", "client_secret"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "oauth_get_token",
            "description": "Get access token for provider",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Provider name"}
                },
                "required": ["provider"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "oauth_disconnect",
            "description": "Disconnect from OAuth provider",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Provider name"}
                },
                "required": ["provider"]
            }
        }
    }
]

# Singleton
_oauth_manager: Optional[OAuthManager] = None

def get_oauth_manager() -> OAuthManager:
    """Get or create OAuth manager"""
    global _oauth_manager
    if _oauth_manager is None:
        _oauth_manager = OAuthManager()
    return _oauth_manager

def execute_oauth_tool(name: str, args: Dict) -> Dict:
    """Execute OAuth tool by name"""
    manager = get_oauth_manager()
    
    if name == "oauth_connect":
        return manager.start_auth_flow(
            provider=args.get("provider"),
            client_id=args.get("client_id"),
            client_secret=args.get("client_secret")
        )
    elif name == "oauth_get_token":
        token = manager.get_token(args.get("provider"))
        if token:
            return {"success": True, "token": token}
        return {"success": False, "error": "No valid token available"}
    elif name == "oauth_disconnect":
        return manager.revoke_token(args.get("provider"))
    else:
        return {"success": False, "error": f"Unknown OAuth tool: {name}"}
