"""
OAuth Flow Skill
Implement OAuth 2.0 authentication flows.
"""

import base64
import hashlib
import json
import os
import secrets
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

METADATA = {
    "name": "oauth-flow",
    "description": "Implement OAuth 2.0 authentication flows for API integration",
    "category": "web",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["oauth", "authentication", "authorize", "token"],
    "dependencies": [],
    "tags": ["oauth", "authentication", "authorization", "api"]
}

SKILL_NAME = "oauth-flow"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "web"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    redirect_uri: str
    scope: str = ""
    additional_params: Dict[str, str] = None


@dataclass
class TokenInfo:
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str]
    scope: str
    expires_at: datetime
    
    def is_expired(self) -> bool:
        return datetime.now() >= self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "expires_at": self.expires_at.isoformat(),
            "is_expired": self.is_expired()
        }


class OAuthFlow:
    """OAuth 2.0 authentication flow implementation."""
    
    def __init__(self, config: OAuthConfig):
        self.config = config
        self.state: Optional[str] = None
        self.code_verifier: Optional[str] = None
        self.token_info: Optional[TokenInfo] = None
    
    def generate_state(self) -> str:
        """Generate random state for CSRF protection."""
        self.state = secrets.token_urlsafe(32)
        return self.state
    
    def generate_pkce_verifier(self) -> str:
        """Generate PKCE code verifier."""
        self.code_verifier = secrets.token_urlsafe(32)
        return self.code_verifier
    
    def generate_pkce_challenge(self, method: str = "S256") -> str:
        """Generate PKCE code challenge."""
        if not self.code_verifier:
            self.generate_pkce_verifier()
        
        if method == "S256":
            digest = hashlib.sha256(self.code_verifier.encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
            return challenge
        elif method == "plain":
            return self.code_verifier
        
        raise ValueError(f"Unsupported challenge method: {method}")
    
    def get_authorization_url(self, response_type: str = "code",
                              use_pkce: bool = False,
                              additional_params: Dict = None) -> str:
        """Generate authorization URL for redirect."""
        if not self.state:
            self.generate_state()
        
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": response_type,
            "state": self.state
        }
        
        if self.config.scope:
            params["scope"] = self.config.scope
        
        if use_pkce:
            params["code_challenge"] = self.generate_pkce_challenge()
            params["code_challenge_method"] = "S256"
        
        if additional_params:
            params.update(additional_params)
        
        if self.config.additional_params:
            params.update(self.config.additional_params)
        
        query = urllib.parse.urlencode(params)
        return f"{self.config.authorization_url}?{query}"
    
    def validate_state(self, received_state: str) -> bool:
        """Validate received state matches generated state."""
        return received_state == self.state
    
    def exchange_code_for_token(self, code: str, use_pkce: bool = False) -> TokenInfo:
        """Exchange authorization code for access token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        if use_pkce and self.code_verifier:
            data["code_verifier"] = self.code_verifier
        
        return self._request_token(data)
    
    def refresh_access_token(self, refresh_token: str) -> TokenInfo:
        """Refresh access token using refresh token."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        return self._request_token(data)
    
    def client_credentials_flow(self, scope: str = None) -> TokenInfo:
        """Perform client credentials flow for server-to-server auth."""
        data = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        if scope:
            data["scope"] = scope
        elif self.config.scope:
            data["scope"] = self.config.scope
        
        return self._request_token(data)
    
    def resource_owner_password_flow(self, username: str, password: str,
                                      scope: str = None) -> TokenInfo:
        """Perform resource owner password credentials flow."""
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        if scope:
            data["scope"] = scope
        elif self.config.scope:
            data["scope"] = self.config.scope
        
        return self._request_token(data)
    
    def device_authorization_flow(self) -> Dict[str, Any]:
        """Start device authorization flow."""
        # Request device code
        data = {
            "client_id": self.config.client_id,
            "scope": self.config.scope
        }
        
        encoded_data = urllib.parse.urlencode(data).encode()
        
        request = urllib.request.Request(
            self.config.token_url.replace("token", "device/code"),
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        try:
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode())
                
                return {
                    "device_code": result.get("device_code"),
                    "user_code": result.get("user_code"),
                    "verification_url": result.get("verification_uri"),
                    "expires_in": result.get("expires_in"),
                    "interval": result.get("interval", 5)
                }
        except Exception as e:
            raise Exception(f"Device authorization failed: {e}")
    
    def poll_device_token(self, device_code: str) -> Optional[TokenInfo]:
        """Poll for device authorization token."""
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": self.config.client_id
        }
        
        try:
            return self._request_token(data)
        except Exception as e:
            if "authorization_pending" in str(e).lower():
                return None
            raise
    
    def _request_token(self, data: Dict) -> TokenInfo:
        """Make token request to OAuth server."""
        encoded_data = urllib.parse.urlencode(data).encode()
        
        request = urllib.request.Request(
            self.config.token_url,
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        try:
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            try:
                error_info = json.loads(error_body)
                raise Exception(f"OAuth error: {error_info.get('error_description', error_info.get('error'))}")
            except json.JSONDecodeError:
                raise Exception(f"OAuth error: {error_body}")
        
        # Calculate expiration
        expires_in = result.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        self.token_info = TokenInfo(
            access_token=result.get("access_token"),
            token_type=result.get("token_type", "Bearer"),
            expires_in=expires_in,
            refresh_token=result.get("refresh_token"),
            scope=result.get("scope", ""),
            expires_at=expires_at
        )
        
        return self.token_info
    
    def revoke_token(self, token: str, token_type_hint: str = "access_token",
                     revocation_url: str = None) -> bool:
        """Revoke a token."""
        url = revocation_url or self.config.token_url.replace("token", "revoke")
        
        data = {
            "token": token,
            "token_type_hint": token_type_hint,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        encoded_data = urllib.parse.urlencode(data).encode()
        
        request = urllib.request.Request(
            url,
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        try:
            with urllib.request.urlopen(request) as response:
                return response.status == 200
        except:
            return False
    
    def introspect_token(self, token: str, introspection_url: str = None) -> Dict[str, Any]:
        """Introspect a token to get its status and claims."""
        url = introspection_url or self.config.token_url.replace("token", "introspect")
        
        data = {
            "token": token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        encoded_data = urllib.parse.urlencode(data).encode()
        
        request = urllib.request.Request(
            url,
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            return {"active": False, "error": str(e)}
    
    def get_auth_header(self) -> Optional[str]:
        """Get Authorization header value."""
        if self.token_info and not self.token_info.is_expired():
            return f"{self.token_info.token_type} {self.token_info.access_token}"
        return None


# Common OAuth provider configurations
OAUTH_PROVIDERS = {
    "google": {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile"
    },
    "github": {
        "authorization_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scope": "user repo"
    },
    "microsoft": {
        "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "openid profile email"
    },
    "slack": {
        "authorization_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scope": "chat:write channels:read"
    }
}


def execute(
    provider: str = None,
    client_id: str = None,
    client_secret: str = None,
    redirect_uri: str = None,
    authorization_url: str = None,
    token_url: str = None,
    scope: str = None,
    operation: str = "auth_url",
    code: str = None,
    refresh_token: str = None,
    use_pkce: bool = False,
    state: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    OAuth 2.0 flow operations.
    
    Args:
        provider: Predefined provider (google/github/microsoft/slack)
        client_id: OAuth client ID
        client_secret: OAuth client secret
        redirect_uri: Redirect URI
        authorization_url: Authorization endpoint URL
        token_url: Token endpoint URL
        scope: OAuth scopes
        operation: Operation (auth_url/exchange/refresh/client_credentials/introspect)
        code: Authorization code
        refresh_token: Refresh token
        use_pkce: Use PKCE flow
        state: State to validate
    
    Returns:
        OAuth operation result
    """
    # Build config
    if provider and provider in OAUTH_PROVIDERS:
        provider_config = OAUTH_PROVIDERS[provider]
        authorization_url = authorization_url or provider_config["authorization_url"]
        token_url = token_url or provider_config["token_url"]
        scope = scope or provider_config["scope"]
    
    if not all([client_id, client_secret, redirect_uri]):
        return {"success": False, "error": "client_id, client_secret, and redirect_uri required"}
    
    config = OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        authorization_url=authorization_url or "",
        token_url=token_url or "",
        redirect_uri=redirect_uri,
        scope=scope or "",
        additional_params=kwargs.get("additional_params")
    )
    
    oauth = OAuthFlow(config)
    
    if operation == "auth_url":
        url = oauth.get_authorization_url(
            response_type=kwargs.get("response_type", "code"),
            use_pkce=use_pkce,
            additional_params=kwargs.get("additional_params")
        )
        
        return {
            "success": True,
            "authorization_url": url,
            "state": oauth.state,
            "code_verifier": oauth.code_verifier if use_pkce else None
        }
    
    elif operation == "validate_state":
        if not state:
            return {"success": False, "error": "state required"}
        
        valid = oauth.validate_state(state)
        return {
            "success": True,
            "valid": valid
        }
    
    elif operation == "exchange":
        if not code:
            return {"success": False, "error": "code required"}
        
        try:
            token_info = oauth.exchange_code_for_token(code, use_pkce)
            return {
                "success": True,
                "token": token_info.to_dict()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif operation == "refresh":
        if not refresh_token:
            return {"success": False, "error": "refresh_token required"}
        
        try:
            token_info = oauth.refresh_access_token(refresh_token)
            return {
                "success": True,
                "token": token_info.to_dict()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif operation == "client_credentials":
        try:
            token_info = oauth.client_credentials_flow(kwargs.get("scope_override"))
            return {
                "success": True,
                "token": token_info.to_dict()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif operation == "password":
        username = kwargs.get("username")
        password = kwargs.get("password")
        
        if not username or not password:
            return {"success": False, "error": "username and password required"}
        
        try:
            token_info = oauth.resource_owner_password_flow(username, password, kwargs.get("scope_override"))
            return {
                "success": True,
                "token": token_info.to_dict()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif operation == "introspect":
        token = kwargs.get("token")
        if not token:
            return {"success": False, "error": "token required"}
        
        result = oauth.introspect_token(token)
        return {
            "success": True,
            "introspection": result
        }
    
    elif operation == "revoke":
        token = kwargs.get("token")
        if not token:
            return {"success": False, "error": "token required"}
        
        revoked = oauth.revoke_token(token, kwargs.get("token_type_hint", "access_token"))
        return {
            "success": revoked,
            "revoked": revoked
        }
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
