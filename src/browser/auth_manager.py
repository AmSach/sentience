"""
Browser Authentication Manager for Sentience v3.0
Handles session persistence, cookie storage, credential management, and login detection.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urljoin

from playwright.async_api import (
    BrowserContext,
    Page,
    Cookie,
    StorageState,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)


class AuthState(Enum):
    UNKNOWN = "unknown"
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    SESSION_EXPIRED = "session_expired"
    REQUIRES_2FA = "requires_2fa"
    REQUIRES_CAPTCHA = "requires_captcha"
    RATE_LIMITED = "rate_limited"


@dataclass
class Credential:
    """Stored credential for authentication."""
    site: str
    username: str
    password: str
    email: Optional[str] = None
    extra_fields: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "site": self.site,
            "username": self.username,
            "password": self.password,
            "email": self.email,
            "extra_fields": self.extra_fields,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Credential":
        return cls(
            site=data["site"],
            username=data["username"],
            password=data["password"],
            email=data.get("email"),
            extra_fields=data.get("extra_fields", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AuthSession:
    """Persisted authentication session."""
    site: str
    storage_state: Dict[str, Any]
    cookies: List[Dict[str, Any]]
    local_storage: Dict[str, str]
    session_storage: Dict[str, str]
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "site": self.site,
            "storage_state": self.storage_state,
            "cookies": self.cookies,
            "local_storage": self.local_storage,
            "session_storage": self.session_storage,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_valid": self.is_valid,
            "metadata": self.metadata,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthSession":
        return cls(
            site=data["site"],
            storage_state=data["storage_state"],
            cookies=data["cookies"],
            local_storage=data["local_storage"],
            session_storage=data["session_storage"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_used=datetime.fromisoformat(data["last_used"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            is_valid=data.get("is_valid", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LoginDetector:
    """Configuration for detecting login state."""
    logged_in_indicators: List[str] = field(default_factory=list)
    logged_out_indicators: List[str] = field(default_factory=list)
    login_url_patterns: List[str] = field(default_factory=list)
    success_url_patterns: List[str] = field(default_factory=list)
    cookie_names: List[str] = field(default_factory=list)
    local_storage_keys: List[str] = field(default_factory=list)
    session_timeout_hours: int = 24


class AuthManager:
    """
    Manages browser authentication including session persistence,
    cookie storage, credential management, and login detection.
    """
    
    def __init__(
        self,
        storage_path: str = "/home/workspace/sentience-v3/data/auth",
        encryption_key: Optional[str] = None
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._encryption_key = encryption_key or os.environ.get("SENTIENCE_AUTH_KEY", "")
        
        # Storage directories
        self._credentials_path = self.storage_path / "credentials"
        self._sessions_path = self.storage_path / "sessions"
        self._cookies_path = self.storage_path / "cookies"
        
        for path in [self._credentials_path, self._sessions_path, self._cookies_path]:
            path.mkdir(exist_ok=True)
            
        # In-memory caches
        self._credentials: Dict[str, Credential] = {}
        self._sessions: Dict[str, AuthSession] = {}
        self._login_detectors: Dict[str, LoginDetector] = {}
        
        # Load existing data
        self._load_credentials()
        self._load_sessions()
        
    def _encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        if not self._encryption_key:
            return base64.b64encode(data.encode()).decode()
            
        key = self._encryption_key.encode()
        message = data.encode()
        
        # Simple XOR encryption with HMAC
        hmac_digest = hmac.new(key, message, hashlib.sha256).digest()
        encrypted = bytes(a ^ b for a, b in zip(message, hmac_digest * (len(message) // 32 + 1)))
        
        return base64.b64encode(encrypted + hmac_digest[:16]).decode()
        
    def _decrypt(self, data: str) -> str:
        """Decrypt sensitive data."""
        if not self._encryption_key:
            return base64.b64decode(data.encode()).decode()
            
        key = self._encryption_key.encode()
        raw = base64.b64decode(data)
        
        encrypted = raw[:-16]
        stored_hmac = raw[-16:]
        
        # Decrypt
        hmac_key = hmac.new(key, encrypted, hashlib.sha256).digest()
        decrypted = bytes(a ^ b for a, b in zip(encrypted, hmac_key * (len(encrypted) // 32 + 1)))
        
        return decrypted.decode()
        
    def _get_site_key(self, url: str) -> str:
        """Get normalized site key from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
        
    # ==================== Credential Management ====================
    
    def add_credential(
        self,
        site: str,
        username: str,
        password: str,
        email: Optional[str] = None,
        **extra_fields
    ) -> Credential:
        """
        Store a credential.
        
        Args:
            site: Site URL or domain
            username: Username
            password: Password
            email: Email (optional)
            **extra_fields: Additional fields (e.g., security_question, api_key)
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        credential = Credential(
            site=site_key,
            username=username,
            password=password,
            email=email,
            extra_fields=extra_fields,
        )
        
        self._credentials[site_key] = credential
        self._save_credential(credential)
        
        logger.info(f"Credential stored for: {site_key}")
        return credential
        
    def get_credential(self, site: str) -> Optional[Credential]:
        """
        Retrieve a credential.
        
        Args:
            site: Site URL or domain
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        return self._credentials.get(site_key)
        
    def update_credential(
        self,
        site: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields
    ) -> Optional[Credential]:
        """Update an existing credential."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        if site_key not in self._credentials:
            return None
            
        credential = self._credentials[site_key]
        
        if username:
            credential.username = username
        if password:
            credential.password = password
        credential.extra_fields.update(extra_fields)
        credential.updated_at = datetime.now()
        
        self._save_credential(credential)
        
        return credential
        
    def delete_credential(self, site: str) -> bool:
        """Delete a credential."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        if site_key in self._credentials:
            del self._credentials[site_key]
            
            cred_file = self._credentials_path / f"{site_key}.json.enc"
            if cred_file.exists():
                cred_file.unlink()
                
            logger.info(f"Credential deleted for: {site_key}")
            return True
            
        return False
        
    def list_credentials(self) -> List[str]:
        """List all stored credential sites."""
        return list(self._credentials.keys())
        
    def _save_credential(self, credential: Credential) -> None:
        """Save credential to disk."""
        data = credential.to_dict()
        encrypted = self._encrypt(json.dumps(data))
        
        path = self._credentials_path / f"{credential.site}.json.enc"
        path.write_text(encrypted)
        
    def _load_credentials(self) -> None:
        """Load all credentials from disk."""
        for cred_file in self._credentials_path.glob("*.json.enc"):
            try:
                encrypted = cred_file.read_text()
                data = json.loads(self._decrypt(encrypted))
                credential = Credential.from_dict(data)
                self._credentials[credential.site] = credential
            except Exception as e:
                logger.error(f"Error loading credential {cred_file}: {e}")
                
    # ==================== Session Management ====================
    
    async def save_session(
        self,
        context: BrowserContext,
        site: str,
        expires_hours: Optional[int] = None
    ) -> AuthSession:
        """
        Save browser session state.
        
        Args:
            context: Browser context to save
            site: Site identifier
            expires_hours: Hours until session expires
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        # Get storage state
        storage_state = await context.storage_state()
        
        # Extract cookies
        cookies = storage_state.get("cookies", [])
        
        # Extract localStorage and sessionStorage from origins
        local_storage = {}
        session_storage = {}
        
        for origin_data in storage_state.get("origins", []):
            origin = origin_data.get("origin", "")
            
            for item in origin_data.get("localStorage", []):
                key = f"{origin}:{item['name']}"
                local_storage[key] = item["value"]
                
            for item in origin_data.get("sessionStorage", []):
                key = f"{origin}:{item['name']}"
                session_storage[key] = item["value"]
                
        expires_at = None
        if expires_hours:
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
        session = AuthSession(
            site=site_key,
            storage_state=storage_state,
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
            expires_at=expires_at,
        )
        
        self._sessions[site_key] = session
        self._save_session(session)
        
        logger.info(f"Session saved for: {site_key}")
        return session
        
    async def load_session(
        self,
        context: BrowserContext,
        site: str
    ) -> bool:
        """
        Load browser session state.
        
        Args:
            context: Browser context to load into
            site: Site identifier
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        if site_key not in self._sessions:
            logger.warning(f"No session found for: {site_key}")
            return False
            
        session = self._sessions[site_key]
        
        # Check expiration
        if session.expires_at and datetime.now() > session.expires_at:
            session.is_valid = False
            logger.warning(f"Session expired for: {site_key}")
            return False
            
        # Add cookies to context
        await context.add_cookies(session.cookies)
        
        # Update last used
        session.last_used = datetime.now()
        self._save_session(session)
        
        logger.info(f"Session loaded for: {site_key}")
        return True
        
    async def restore_session(
        self,
        page: Page,
        site: str
    ) -> bool:
        """
        Restore session data to a page.
        
        Args:
            page: Page to restore to
            site: Site identifier
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        if site_key not in self._sessions:
            return False
            
        session = self._sessions[site_key]
        
        # Restore localStorage and sessionStorage
        for key, value in session.local_storage.items():
            try:
                origin, item_key = key.split(":", 1)
                await page.evaluate(
                    f"localStorage.setItem('{item_key}', '{value}')"
                )
            except Exception:
                pass
                
        for key, value in session.session_storage.items():
            try:
                origin, item_key = key.split(":", 1)
                await page.evaluate(
                    f"sessionStorage.setItem('{item_key}', '{value}')"
                )
            except Exception:
                pass
                
        return True
        
    def get_session(self, site: str) -> Optional[AuthSession]:
        """Get stored session for site."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        return self._sessions.get(site_key)
        
    def delete_session(self, site: str) -> bool:
        """Delete a session."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        if site_key in self._sessions:
            del self._sessions[site_key]
            
            session_file = self._sessions_path / f"{site_key}.json.enc"
            if session_file.exists():
                session_file.unlink()
                
            logger.info(f"Session deleted for: {site_key}")
            return True
            
        return False
        
    def list_sessions(self) -> List[str]:
        """List all stored session sites."""
        return list(self._sessions.keys())
        
    def is_session_valid(self, site: str) -> bool:
        """Check if session is valid and not expired."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        if site_key not in self._sessions:
            return False
            
        session = self._sessions[site_key]
        
        if not session.is_valid:
            return False
            
        if session.expires_at and datetime.now() > session.expires_at:
            return False
            
        return True
        
    def _save_session(self, session: AuthSession) -> None:
        """Save session to disk."""
        data = session.to_dict()
        encrypted = self._encrypt(json.dumps(data))
        
        path = self._sessions_path / f"{session.site}.json.enc"
        path.write_text(encrypted)
        
    def _load_sessions(self) -> None:
        """Load all sessions from disk."""
        for session_file in self._sessions_path.glob("*.json.enc"):
            try:
                encrypted = session_file.read_text()
                data = json.loads(self._decrypt(encrypted))
                session = AuthSession.from_dict(data)
                self._sessions[session.site] = session
            except Exception as e:
                logger.error(f"Error loading session {session_file}: {e}")
                
    # ==================== Cookie Management ====================
    
    async def get_cookies(
        self,
        context: BrowserContext,
        domains: Optional[List[str]] = None
    ) -> List[Cookie]:
        """
        Get cookies from context.
        
        Args:
            context: Browser context
            domains: Filter by domains (optional)
        """
        cookies = await context.cookies()
        
        if domains:
            cookies = [
                c for c in cookies
                if any(domain in c.get("domain", "") for domain in domains)
            ]
            
        return cookies
        
    async def set_cookies(
        self,
        context: BrowserContext,
        cookies: List[Dict[str, Any]]
    ) -> None:
        """Set cookies in context."""
        await context.add_cookies(cookies)
        logger.info(f"Set {len(cookies)} cookies")
        
    async def clear_cookies(
        self,
        context: BrowserContext,
        domains: Optional[List[str]] = None
    ) -> None:
        """Clear cookies from context."""
        await context.clear_cookies()
        logger.info("Cookies cleared")
        
    async def save_cookies(
        self,
        context: BrowserContext,
        site: str
    ) -> None:
        """Save cookies for a site."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        cookies = await context.cookies()
        
        data = {
            "site": site_key,
            "cookies": cookies,
            "saved_at": datetime.now().isoformat(),
        }
        
        encrypted = self._encrypt(json.dumps(data))
        path = self._cookies_path / f"{site_key}.json.enc"
        path.write_text(encrypted)
        
        logger.info(f"Cookies saved for: {site_key}")
        
    async def load_cookies(
        self,
        context: BrowserContext,
        site: str
    ) -> bool:
        """Load cookies for a site."""
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        path = self._cookies_path / f"{site_key}.json.enc"
        if not path.exists():
            return False
            
        try:
            encrypted = path.read_text()
            data = json.loads(self._decrypt(encrypted))
            cookies = data.get("cookies", [])
            
            await context.add_cookies(cookies)
            logger.info(f"Cookies loaded for: {site_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")
            return False
            
    # ==================== Login Detection ====================
    
    def configure_login_detector(
        self,
        site: str,
        logged_in_indicators: Optional[List[str]] = None,
        logged_out_indicators: Optional[List[str]] = None,
        login_url_patterns: Optional[List[str]] = None,
        success_url_patterns: Optional[List[str]] = None,
        cookie_names: Optional[List[str]] = None,
        local_storage_keys: Optional[List[str]] = None,
        session_timeout_hours: int = 24
    ) -> None:
        """
        Configure login detection for a site.
        
        Args:
            site: Site URL or domain
            logged_in_indicators: Selectors/text indicating logged in state
            logged_out_indicators: Selectors/text indicating logged out state
            login_url_patterns: URL patterns for login pages
            success_url_patterns: URL patterns for successful login
            cookie_names: Cookie names that indicate auth
            local_storage_keys: localStorage keys that indicate auth
            session_timeout_hours: Hours before session expires
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        detector = LoginDetector(
            logged_in_indicators=logged_in_indicators or [],
            logged_out_indicators=logged_out_indicators or [],
            login_url_patterns=login_url_patterns or [],
            success_url_patterns=success_url_patterns or [],
            cookie_names=cookie_names or [],
            local_storage_keys=local_storage_keys or [],
            session_timeout_hours=session_timeout_hours,
        )
        
        self._login_detectors[site_key] = detector
        logger.info(f"Login detector configured for: {site_key}")
        
    async def detect_auth_state(
        self,
        page: Page,
        site: str
    ) -> AuthState:
        """
        Detect current authentication state.
        
        Args:
            page: Browser page
            site: Site identifier
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        detector = self._login_detectors.get(site_key)
        
        # Check URL patterns
        current_url = page.url
        
        if detector:
            # Check for login page
            for pattern in detector.login_url_patterns:
                if pattern in current_url:
                    return AuthState.LOGGED_OUT
                    
            # Check for success URL
            for pattern in detector.success_url_patterns:
                if pattern in current_url:
                    return AuthState.LOGGED_IN
                    
        # Check for logged in indicators
        if detector and detector.logged_in_indicators:
            for indicator in detector.logged_in_indicators:
                try:
                    if await page.locator(indicator).count() > 0:
                        return AuthState.LOGGED_IN
                    if await page.locator(f"text={indicator}").count() > 0:
                        return AuthState.LOGGED_IN
                except Exception:
                    pass
                    
        # Check for logged out indicators
        if detector and detector.logged_out_indicators:
            for indicator in detector.logged_out_indicators:
                try:
                    if await page.locator(indicator).count() > 0:
                        return AuthState.LOGGED_OUT
                    if await page.locator(f"text={indicator}").count() > 0:
                        return AuthState.LOGGED_OUT
                except Exception:
                    pass
                    
        # Check for 2FA
        try:
            if await page.locator("input[name*='otp'], input[name*='code'], input[name*='totp']").count() > 0:
                return AuthState.REQUIRES_2FA
        except Exception:
            pass
            
        # Check for CAPTCHA
        try:
            if await page.locator("iframe[src*='captcha'], .g-recaptcha, .h-captcha").count() > 0:
                return AuthState.REQUIRES_CAPTCHA
        except Exception:
            pass
            
        # Check for rate limiting
        content = await page.content()
        rate_limit_texts = ["too many", "rate limit", "try again later", "blocked"]
        for text in rate_limit_texts:
            if text in content.lower():
                return AuthState.RATE_LIMITED
                
        return AuthState.UNKNOWN
        
    async def wait_for_login(
        self,
        page: Page,
        site: str,
        timeout: int = 60000,
        check_interval: int = 1000
    ) -> AuthState:
        """
        Wait for login to complete.
        
        Args:
            page: Browser page
            site: Site identifier
            timeout: Max wait time in ms
            check_interval: Check interval in ms
        """
        start_time = time.time()
        
        while (time.time() * 1000 - start_time * 1000) < timeout:
            state = await self.detect_auth_state(page, site)
            
            if state == AuthState.LOGGED_IN:
                return state
            if state in [AuthState.REQUIRES_2FA, AuthState.REQUIRES_CAPTCHA, AuthState.RATE_LIMITED]:
                return state
                
            await asyncio.sleep(check_interval / 1000)
            
        return AuthState.SESSION_EXPIRED
        
    # ==================== Auto Login ====================
    
    async def auto_login(
        self,
        page: Page,
        site: str,
        username_selectors: Optional[List[str]] = None,
        password_selectors: Optional[List[str]] = None,
        submit_selectors: Optional[List[str]] = None
    ) -> AuthState:
        """
        Attempt automatic login.
        
        Args:
            page: Browser page
            site: Site identifier
            username_selectors: Possible username field selectors
            password_selectors: Possible password field selectors
            submit_selectors: Possible submit button selectors
        """
        site_key = self._get_site_key(site) if site.startswith("http") else site.lower()
        
        credential = self.get_credential(site_key)
        if not credential:
            logger.warning(f"No credential found for: {site_key}")
            return AuthState.LOGGED_OUT
            
        # Default selectors
        username_selectors = username_selectors or [
            "input[name='username']",
            "input[name='email']",
            "input[type='email']",
            "input[type='text'][name*='user']",
            "#username",
            "#email",
        ]
        
        password_selectors = password_selectors or [
            "input[name='password']",
            "input[type='password']",
            "#password",
        ]
        
        submit_selectors = submit_selectors or [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "button:has-text('Login')",
        ]
        
        # Find and fill username
        for selector in username_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.fill(selector, credential.username)
                    break
            except Exception:
                continue
                
        # Find and fill password
        for selector in password_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.fill(selector, credential.password)
                    break
            except Exception:
                continue
                
        # Click submit
        for selector in submit_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    break
            except Exception:
                continue
                
        # Wait for login result
        await asyncio.sleep(2)
        
        return await self.detect_auth_state(page, site)
        
    # ==================== Utility Methods ====================
    
    def export_all(self, path: str) -> None:
        """Export all credentials and sessions to a backup file."""
        data = {
            "credentials": {k: v.to_dict() for k, v in self._credentials.items()},
            "sessions": {k: v.to_dict() for k, v in self._sessions.items()},
            "exported_at": datetime.now().isoformat(),
        }
        
        encrypted = self._encrypt(json.dumps(data))
        Path(path).write_text(encrypted)
        
        logger.info(f"Exported all auth data to: {path}")
        
    def import_all(self, path: str) -> None:
        """Import credentials and sessions from a backup file."""
        encrypted = Path(path).read_text()
        data = json.loads(self._decrypt(encrypted))
        
        for site, cred_data in data.get("credentials", {}).items():
            credential = Credential.from_dict(cred_data)
            self._credentials[site] = credential
            self._save_credential(credential)
            
        for site, session_data in data.get("sessions", {}).items():
            session = AuthSession.from_dict(session_data)
            self._sessions[site] = session
            self._save_session(session)
            
        logger.info(f"Imported all auth data from: {path}")
