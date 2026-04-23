"""
Stealth Module for Sentience v3.0
Anti-detection features including user agent rotation, fingerprint masking, rate limiting, and human-like delays.
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    BrowserType,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)


# ==================== User Agent Management ====================

# Common user agents
USER_AGENTS = {
    "chrome_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ],
    "chrome_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ],
    "firefox_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    ],
    "firefox_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    ],
    "safari_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ],
    "edge_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ],
}

# Device profiles
DEVICE_PROFILES = {
    "desktop_windows": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "chrome_windows",
        "platform": "Win32",
        "timezone": "America/New_York",
        "locale": "en-US",
    },
    "desktop_mac": {
        "viewport": {"width": 1440, "height": 900},
        "user_agent": "chrome_mac",
        "platform": "MacIntel",
        "timezone": "America/Los_Angeles",
        "locale": "en-US",
    },
    "laptop_windows": {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": "chrome_windows",
        "platform": "Win32",
        "timezone": "America/Chicago",
        "locale": "en-US",
    },
    "laptop_mac": {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": "safari_mac",
        "platform": "MacIntel",
        "timezone": "America/Los_Angeles",
        "locale": "en-US",
    },
}


@dataclass
class UserAgentProfile:
    """User agent profile with associated properties."""
    user_agent: str
    viewport: Dict[str, int]
    platform: str
    timezone: str
    locale: str
    device_memory: int = 8
    hardware_concurrency: int = 4
    color_depth: int = 24
    device_scale_factor: float = 1.0
    touch_support: Dict[str, bool] = field(default_factory=lambda: {
        "maxTouchPoints": 0,
        "touchEvent": False,
        "touchStart": False,
    })


class UserAgentRotator:
    """
    Manages user agent rotation for stealth browsing.
    """
    
    def __init__(
        self,
        profiles_path: Optional[str] = None,
        rotation_strategy: str = "random"
    ):
        self.profiles_path = profiles_path
        self.rotation_strategy = rotation_strategy  # random, sequential, weighted
        self._profiles: List[UserAgentProfile] = []
        self._current_index = 0
        self._usage_history: Dict[str, int] = {}
        
        self._load_profiles()
        
    def _load_profiles(self) -> None:
        """Load user agent profiles."""
        # Load built-in profiles
        for device_name, config in DEVICE_PROFILES.items():
            ua_category = config["user_agent"]
            ua_list = USER_AGENTS.get(ua_category, [])
            
            if ua_list:
                profile = UserAgentProfile(
                    user_agent=random.choice(ua_list),
                    viewport=config["viewport"],
                    platform=config["platform"],
                    timezone=config["timezone"],
                    locale=config["locale"],
                )
                self._profiles.append(profile)
                
        # Load custom profiles if provided
        if self.profiles_path and os.path.exists(self.profiles_path):
            try:
                with open(self.profiles_path) as f:
                    custom = json.load(f)
                    for profile_data in custom.get("profiles", []):
                        profile = UserAgentProfile(**profile_data)
                        self._profiles.append(profile)
            except Exception as e:
                logger.error(f"Error loading custom profiles: {e}")
                
    def get_profile(self) -> UserAgentProfile:
        """Get next user agent profile based on rotation strategy."""
        if not self._profiles:
            return self._default_profile()
            
        if self.rotation_strategy == "random":
            profile = random.choice(self._profiles)
        elif self.rotation_strategy == "sequential":
            profile = self._profiles[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._profiles)
        elif self.rotation_strategy == "weighted":
            # Select least used profile
            profile = min(
                self._profiles,
                key=lambda p: self._usage_history.get(p.user_agent, 0)
            )
        else:
            profile = self._profiles[0]
            
        # Track usage
        self._usage_history[profile.user_agent] = self._usage_history.get(profile.user_agent, 0) + 1
        
        return profile
        
    def _default_profile(self) -> UserAgentProfile:
        """Return default profile."""
        return UserAgentProfile(
            user_agent=USER_AGENTS["chrome_windows"][0],
            viewport={"width": 1920, "height": 1080},
            platform="Win32",
            timezone="America/New_York",
            locale="en-US",
        )
        
    def add_profile(self, profile: UserAgentProfile) -> None:
        """Add a custom profile."""
        self._profiles.append(profile)
        
    def get_random_user_agent(self, browser: str = "chrome") -> str:
        """Get a random user agent string."""
        ua_key = f"{browser}_windows" if f"{browser}_windows" in USER_AGENTS else "chrome_windows"
        return random.choice(USER_AGENTS[ua_key])


# ==================== Fingerprint Masking ====================

FINGERPRINT_SCRIPTS = {
    # Hide webdriver property
    "webdriver": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """,
    
    # Mock plugins
    "plugins": """
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                plugins.item = (index) => plugins[index] || null;
                plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                plugins.refresh = () => {};
                return plugins;
            }
        });
    """,
    
    # Mock languages
    "languages": """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
    """,
    
    # Hide automation flags
    "automation": """
        // Remove automation indicators
        window.chrome = { runtime: {} };
        
        // Hide permissions query fingerprinting
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """,
    
    # Mock WebGL vendor and renderer
    "webgl": """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.apply(this, [parameter]);
        };
    """,
    
    # Mock hardware concurrency
    "hardware": """
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 4
        });
        
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
    """,
    
    # Mock screen properties
    "screen": """
        Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
        Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
    """,
    
    # Mock connection info
    "connection": """
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false
            })
        });
    """,
    
    # Hide automation in function prototypes
    "prototypes": """
        // Override function toString to hide modifications
        const oldToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === navigator.webdriver) {
                return 'function webdriver() { [native code] }';
            }
            return oldToString.call(this);
        };
    """,
    
    # Mock audio context fingerprint
    "audio": """
        const audioContext = window.AudioContext || window.webkitAudioContext;
        if (audioContext) {
            const originalCreateAnalyser = audioContext.prototype.createAnalyser;
            audioContext.prototype.createAnalyser = function() {
                const analyser = originalCreateAnalyser.apply(this, arguments);
                const originalGetFloatFrequencyData = analyser.getFloatFrequencyData;
                analyser.getFloatFrequencyData = function(array) {
                    originalGetFloatFrequencyData.apply(this, arguments);
                    // Add noise to prevent fingerprinting
                    for (let i = 0; i < array.length; i++) {
                        array[i] += Math.random() * 0.0001;
                    }
                };
                return analyser;
            };
        }
    """,
}


class FingerprintMasker:
    """
    Masks browser fingerprint to avoid detection.
    """
    
    def __init__(
        self,
        enabled_scripts: Optional[List[str]] = None,
        custom_scripts: Optional[Dict[str, str]] = None
    ):
        self.enabled_scripts = enabled_scripts or list(FINGERPRINT_SCRIPTS.keys())
        self.custom_scripts = custom_scripts or {}
        
    async def apply_mask(self, page: Page) -> None:
        """Apply all fingerprint masking scripts."""
        combined_script = self._combine_scripts()
        
        try:
            await page.add_init_script(combined_script)
            logger.info("Fingerprint mask applied")
        except Exception as e:
            logger.error(f"Error applying fingerprint mask: {e}")
            
    async def apply_script(self, page: Page, script_name: str) -> None:
        """Apply a specific fingerprint script."""
        script = FINGERPRINT_SCRIPTS.get(script_name) or self.custom_scripts.get(script_name)
        
        if script:
            try:
                await page.add_init_script(script)
            except Exception as e:
                logger.error(f"Error applying script {script_name}: {e}")
        else:
            logger.warning(f"Script not found: {script_name}")
            
    def _combine_scripts(self) -> str:
        """Combine all enabled scripts into one."""
        scripts = []
        
        for name in self.enabled_scripts:
            script = FINGERPRINT_SCRIPTS.get(name) or self.custom_scripts.get(name)
            if script:
                scripts.append(f"// {name}\n{script}")
                
        return "\n\n".join(scripts)
        
    def add_custom_script(self, name: str, script: str) -> None:
        """Add a custom fingerprint script."""
        self.custom_scripts[name] = script
        
    async def generate_consistent_fingerprint(
        self,
        seed: str
    ) -> Dict[str, Any]:
        """
        Generate a consistent fingerprint based on a seed.
        Useful for maintaining the same identity across sessions.
        """
        # Use seed to generate deterministic values
        hash_obj = hashlib.md5(seed.encode())
        hash_int = int.from_bytes(hash_obj.digest(), byteorder='big')
        
        # Generate consistent values
        random.seed(hash_int)
        
        fingerprint = {
            "webgl_vendor": random.choice([
                "Intel Inc.",
                "NVIDIA Corporation",
                "AMD",
            ]),
            "webgl_renderer": random.choice([
                "Intel Iris OpenGL Engine",
                "NVIDIA GeForce GTX 1060",
                "AMD Radeon RX 580",
            ]),
            "audio_fingerprint": random.uniform(124.0, 125.0),
            "canvas_noise": [random.random() for _ in range(10)],
            "font_fingerprint": sorted(random.sample(range(100), 10)),
        }
        
        random.seed()  # Reset random seed
        return fingerprint


# ==================== Rate Limiting ====================

@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_second: float = 2.0
    requests_per_minute: int = 60
    requests_per_hour: int = 500
    burst_size: int = 5
    cooldown_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_backoff: float = 60.0


class RateLimiter:
    """
    Rate limiting for browser requests.
    Implements token bucket algorithm with burst support.
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        
        # Token bucket
        self._tokens = self.config.burst_size
        self._last_refill = time.time()
        self._refill_rate = self.config.requests_per_second
        
        # Tracking
        self._request_times: List[float] = []
        self._blocked_count = 0
        self._total_requests = 0
        
        # Backoff state
        self._backoff_until: Optional[float] = None
        self._current_backoff: float = 0.0
        
    async def acquire(self) -> bool:
        """Acquire permission to make a request."""
        now = time.time()
        
        # Check if in backoff
        if self._backoff_until and now < self._backoff_until:
            wait_time = self._backoff_until - now
            logger.debug(f"Rate limited: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            
        # Refill tokens
        self._refill_tokens(now)
        
        # Check minute/hour limits
        self._cleanup_old_requests(now)
        
        minute_requests = len([t for t in self._request_times if now - t < 60])
        hour_requests = len([t for t in self._request_times if now - t < 3600])
        
        if minute_requests >= self.config.requests_per_minute:
            await self._trigger_backoff()
            return False
            
        if hour_requests >= self.config.requests_per_hour:
            await self._trigger_backoff()
            return False
            
        # Check token availability
        if self._tokens < 1:
            wait_time = (1 - self._tokens) / self._refill_rate
            await asyncio.sleep(wait_time + self.config.cooldown_seconds)
            self._tokens = 0
            
        # Consume token
        self._tokens -= 1
        self._request_times.append(now)
        self._total_requests += 1
        
        return True
        
    def _refill_tokens(self, now: float) -> None:
        """Refill tokens based on time elapsed."""
        elapsed = now - self._last_refill
        self._tokens = min(
            self.config.burst_size,
            self._tokens + elapsed * self._refill_rate
        )
        self._last_refill = now
        
    def _cleanup_old_requests(self, now: float) -> None:
        """Remove old request timestamps."""
        self._request_times = [t for t in self._request_times if now - t < 3600]
        
    async def _trigger_backoff(self) -> None:
        """Trigger exponential backoff."""
        self._blocked_count += 1
        self._current_backoff = min(
            self.config.max_backoff,
            self._current_backoff * self.config.backoff_factor or 1.0
        )
        self._backoff_until = time.time() + self._current_backoff
        
        logger.warning(f"Rate limit triggered, backoff for {self._current_backoff:.2f}s")
        
    def reset(self) -> None:
        """Reset rate limiter state."""
        self._tokens = self.config.burst_size
        self._last_refill = time.time()
        self._request_times.clear()
        self._backoff_until = None
        self._current_backoff = 0.0
        
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "tokens_available": self._tokens,
            "total_requests": self._total_requests,
            "blocked_count": self._blocked_count,
            "current_backoff": self._current_backoff,
            "requests_last_minute": len([t for t in self._request_times if time.time() - t < 60]),
            "requests_last_hour": len(self._request_times),
        }


# ==================== Human-like Delays ====================

@dataclass
class DelayConfig:
    """Configuration for human-like delays."""
    min_action_delay: float = 0.1
    max_action_delay: float = 0.5
    min_scroll_delay: float = 0.05
    max_scroll_delay: float = 0.2
    min_type_delay: float = 0.05
    max_type_delay: float = 0.15
    min_page_load_delay: float = 1.0
    max_page_load_delay: float = 3.0
    min_mouse_move_delay: float = 0.01
    max_mouse_move_delay: float = 0.05
    think_time_min: float = 0.5
    think_time_max: float = 2.0


class HumanDelay:
    """
    Generates human-like delays for actions.
    Uses various distributions to mimic human behavior.
    """
    
    def __init__(self, config: Optional[DelayConfig] = None):
        self.config = config or DelayConfig()
        
    def action_delay(self) -> float:
        """Get delay for a general action."""
        return random.uniform(
            self.config.min_action_delay,
            self.config.max_action_delay
        )
        
    def scroll_delay(self) -> float:
        """Get delay for scroll actions."""
        return random.uniform(
            self.config.min_scroll_delay,
            self.config.max_scroll_delay
        )
        
    def type_delay(self) -> float:
        """Get delay between keystrokes."""
        # Use a distribution closer to human typing
        base = random.uniform(
            self.config.min_type_delay,
            self.config.max_type_delay
        )
        # Occasionally add longer pauses
        if random.random() < 0.1:
            base += random.uniform(0.1, 0.3)
        return base
        
    def page_load_delay(self) -> float:
        """Get delay after page load."""
        return random.uniform(
            self.config.min_page_load_delay,
            self.config.max_page_load_delay
        )
        
    def mouse_move_delay(self) -> float:
        """Get delay for mouse movement."""
        return random.uniform(
            self.config.min_mouse_move_delay,
            self.config.max_mouse_move_delay
        )
        
    def think_time(self) -> float:
        """Get 'thinking' delay for complex actions."""
        return random.uniform(
            self.config.min_think_time,
            self.config.max_think_time
        )
        
    async def wait_action(self) -> None:
        """Wait for action delay."""
        await asyncio.sleep(self.action_delay())
        
    async def wait_scroll(self) -> None:
        """Wait for scroll delay."""
        await asyncio.sleep(self.scroll_delay())
        
    async def wait_type(self) -> None:
        """Wait for type delay."""
        await asyncio.sleep(self.type_delay())
        
    async def wait_page_load(self) -> None:
        """Wait for page load delay."""
        await asyncio.sleep(self.page_load_delay())
        
    async def wait_mouse_move(self) -> None:
        """Wait for mouse move delay."""
        await asyncio.sleep(self.mouse_move_delay())
        
    async def wait_think(self) -> None:
        """Wait for think time."""
        await asyncio.sleep(self.think_time())


# ==================== Stealth Coordinator ====================

@dataclass
class StealthConfig:
    """Configuration for stealth mode."""
    enabled: bool = True
    user_agent_rotation: bool = True
    fingerprint_masking: bool = True
    rate_limiting: bool = True
    human_delays: bool = True
    random_viewport: bool = False
    random_timezone: bool = False
    
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    delay: DelayConfig = field(default_factory=DelayConfig)


class StealthCoordinator:
    """
    Coordinates all stealth features.
    """
    
    def __init__(
        self,
        config: Optional[StealthConfig] = None,
        seed: Optional[str] = None
    ):
        self.config = config or StealthConfig()
        self.seed = seed
        
        # Initialize components
        self.ua_rotator = UserAgentRotator() if self.config.user_agent_rotation else None
        self.fingerprint_masker = FingerprintMasker() if self.config.fingerprint_masking else None
        self.rate_limiter = RateLimiter(self.config.rate_limit) if self.config.rate_limiting else None
        self.human_delay = HumanDelay(self.config.delay) if self.config.human_delays else None
        
        # Current profile
        self._current_profile: Optional[UserAgentProfile] = None
        
    async def setup_context(
        self,
        context: BrowserContext,
        page: Page
    ) -> Dict[str, Any]:
        """
        Setup a context with all stealth features.
        
        Returns:
            Applied settings for verification
        """
        settings = {}
        
        # Apply user agent and viewport
        if self.ua_rotator and self.config.user_agent_rotation:
            self._current_profile = self.ua_rotator.get_profile()
            
            await context.set_extra_http_headers({
                "User-Agent": self._current_profile.user_agent,
            })
            
            settings["user_agent"] = self._current_profile.user_agent
            settings["viewport"] = self._current_profile.viewport
            
        # Apply fingerprint masking
        if self.fingerprint_masker and self.config.fingerprint_masking:
            await self.fingerprint_masker.apply_mask(page)
            settings["fingerprint_masked"] = True
            
        # Apply consistent fingerprint if seed provided
        if self.seed and self.fingerprint_masker:
            fingerprint = await self.fingerprint_masker.generate_consistent_fingerprint(self.seed)
            settings["consistent_fingerprint"] = fingerprint
            
        settings["stealth_enabled"] = self.config.enabled
        
        logger.info("Stealth context setup complete")
        return settings
        
    async def before_request(self) -> None:
        """Call before making a request."""
        if self.rate_limiter:
            await self.rate_limiter.acquire()
            
        if self.human_delay:
            await self.human_delay.wait_action()
            
    async def after_navigation(self) -> None:
        """Call after navigation."""
        if self.human_delay:
            await self.human_delay.wait_page_load()
            
    async def before_action(self, action_type: str = "general") -> None:
        """Call before an action with type-specific delay."""
        if not self.human_delay:
            return
            
        if action_type == "scroll":
            await self.human_delay.wait_scroll()
        elif action_type == "type":
            await self.human_delay.wait_type()
        elif action_type == "click":
            await self.human_delay.wait_action()
        elif action_type == "mouse_move":
            await self.human_delay.wait_mouse_move()
        else:
            await self.human_delay.wait_action()
            
    async def after_action(self, action_type: str = "general") -> None:
        """Call after an action."""
        await self.before_action(action_type)  # Same delays apply
        
    def get_current_profile(self) -> Optional[UserAgentProfile]:
        """Get current user agent profile."""
        return self._current_profile
        
    def get_rate_limit_stats(self) -> Optional[Dict[str, Any]]:
        """Get rate limiter statistics."""
        if self.rate_limiter:
            return self.rate_limiter.get_stats()
        return None
        
    def rotate_user_agent(self) -> UserAgentProfile:
        """Force rotate to a new user agent."""
        if self.ua_rotator:
            self._current_profile = self.ua_rotator.get_profile()
        return self._current_profile
        
    def reset_rate_limiter(self) -> None:
        """Reset the rate limiter."""
        if self.rate_limiter:
            self.rate_limiter.reset()


# ==================== Utility Functions ====================

def get_random_viewport() -> Dict[str, int]:
    """Get a random common viewport size."""
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1440, "height": 900},
        {"width": 1366, "height": 768},
        {"width": 1280, "height": 720},
        {"width": 1536, "height": 864},
        {"width": 2560, "height": 1440},
    ]
    return random.choice(viewports)


def get_random_timezone() -> str:
    """Get a random timezone."""
    timezones = [
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Paris",
        "Asia/Tokyo",
    ]
    return random.choice(timezones)


def get_random_locale() -> str:
    """Get a random locale."""
    locales = [
        "en-US",
        "en-GB",
        "en-CA",
        "fr-FR",
        "de-DE",
        "es-ES",
    ]
    return random.choice(locales)


async def apply_stealth_to_page(
    page: Page,
    user_agent: Optional[str] = None,
    viewport: Optional[Dict[str, int]] = None
) -> None:
    """
    Quick function to apply basic stealth to a page.
    """
    masker = FingerprintMasker()
    await masker.apply_mask(page)
    
    if user_agent:
        await page.set_extra_http_headers({"User-Agent": user_agent})
