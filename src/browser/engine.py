"""
Playwright Browser Engine for Sentience v3.0
Core browser automation with multi-browser support, context management, and network interception.
"""

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
from urllib.parse import urlparse

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Request,
    Response,
    Route,
    Download,
    FileChooser,
    Dialog,
    Video,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)


class BrowserType(Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass
class BrowserConfig:
    """Configuration for browser instance."""
    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    slow_mo: int = 0
    timeout: int = 30000
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    user_agent: Optional[str] = None
    locale: str = "en-US"
    timezone: str = "America/New_York"
    geolocation: Optional[Dict[str, float]] = None
    permissions: List[str] = field(default_factory=lambda: ["geolocation"])
    proxy: Optional[Dict[str, str]] = None
    downloads_path: str = "/tmp/sentience-downloads"
    record_video: bool = False
    video_path: str = "/tmp/sentience-videos"
    ignore_https_errors: bool = True
    args: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        os.makedirs(self.downloads_path, exist_ok=True)
        if self.record_video:
            os.makedirs(self.video_path, exist_ok=True)


@dataclass
class NetworkEvent:
    """Captured network event."""
    timestamp: float
    method: str
    url: str
    status: Optional[int] = None
    request_headers: Dict[str, str] = field(default_factory=dict)
    response_headers: Dict[str, str] = field(default_factory=dict)
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    resource_type: str = ""
    time: float = 0.0


@dataclass
class InterceptRule:
    """Rule for network interception."""
    pattern: str
    handler: Callable[[Route], Awaitable[None]]
    methods: List[str] = field(default_factory=list)
    resource_types: List[str] = field(default_factory=list)


class BrowserEngine:
    """
    Core Playwright browser engine for Sentience v3.0.
    Handles browser lifecycle, context management, and page operations.
    """
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}
        self._pages: Dict[str, Page] = {}
        self._network_events: List[NetworkEvent] = []
        self._intercept_rules: List[InterceptRule] = []
        self._downloads: Dict[str, Download] = {}
        self._is_running = False
        
    async def start(self) -> None:
        """Start the browser engine."""
        if self._is_running:
            logger.warning("Browser engine already running")
            return
            
        logger.info(f"Starting {self.config.browser_type.value} browser...")
        
        self._playwright = await async_playwright().start()
        
        browser_launcher = {
            BrowserType.CHROMIUM: self._playwright.chromium,
            BrowserType.FIREFOX: self._playwright.firefox,
            BrowserType.WEBKIT: self._playwright.webkit,
        }
        
        launcher = browser_launcher[self.config.browser_type]
        
        launch_options = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
            "args": self.config.args,
            "ignore_https_errors": self.config.ignore_https_errors,
        }
        
        if self.config.proxy:
            launch_options["proxy"] = self.config.proxy
            
        self._browser = await launcher.launch(**launch_options)
        self._is_running = True
        logger.info("Browser engine started successfully")
        
    async def stop(self) -> None:
        """Stop the browser engine and cleanup resources."""
        if not self._is_running:
            return
            
        logger.info("Stopping browser engine...")
        
        # Close all contexts
        for name, context in self._contexts.items():
            try:
                await context.close()
            except Exception as e:
                logger.error(f"Error closing context {name}: {e}")
                
        # Close browser
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
                
        # Stop playwright
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")
                
        self._contexts.clear()
        self._pages.clear()
        self._network_events.clear()
        self._is_running = False
        logger.info("Browser engine stopped")
        
    async def create_context(
        self,
        name: str,
        storage_state: Optional[str] = None,
        **kwargs
    ) -> BrowserContext:
        """
        Create a new browser context.
        
        Args:
            name: Unique identifier for the context
            storage_state: Path to load saved auth state
            **kwargs: Additional context options
        """
        if name in self._contexts:
            logger.warning(f"Context '{name}' already exists, returning existing")
            return self._contexts[name]
            
        context_options = {
            "viewport": self.config.viewport,
            "locale": self.config.locale,
            "timezone_id": self.config.timezone,
            "accept_downloads": True,
        }
        
        if self.config.user_agent:
            context_options["user_agent"] = self.config.user_agent
            
        if self.config.geolocation:
            context_options["geolocation"] = self.config.geolocation
            
        if self.config.permissions:
            context_options["permissions"] = self.config.permissions
            
        if storage_state and os.path.exists(storage_state):
            context_options["storage_state"] = storage_state
            
        context_options.update(kwargs)
        
        if self.config.record_video:
            context_options["record_video_dir"] = self.config.video_path
            
        context = await self._browser.new_context(**context_options)
        
        # Set default timeout
        context.set_default_timeout(self.config.timeout)
        
        # Setup network monitoring
        context.on("request", self._on_request)
        context.on("response", self._on_response)
        
        self._contexts[name] = context
        logger.info(f"Created context: {name}")
        
        return context
        
    async def get_context(self, name: str) -> Optional[BrowserContext]:
        """Get an existing context by name."""
        return self._contexts.get(name)
        
    async def close_context(self, name: str) -> None:
        """Close and remove a context."""
        if name in self._contexts:
            await self._contexts[name].close()
            del self._contexts[name]
            logger.info(f"Closed context: {name}")
            
    async def create_page(
        self,
        context_name: str = "default",
        page_name: Optional[str] = None
    ) -> Page:
        """
        Create a new page in a context.
        
        Args:
            context_name: Name of context to create page in
            page_name: Optional unique identifier for the page
        """
        if context_name not in self._contexts:
            await self.create_context(context_name)
            
        context = self._contexts[context_name]
        page = await context.new_page()
        
        # Setup page event handlers
        page.on("download", self._on_download)
        page.on("filechooser", self._on_filechooser)
        page.on("dialog", self._on_dialog)
        
        # Apply interception rules
        for rule in self._intercept_rules:
            await page.route(rule.pattern, rule.handler)
            
        page_id = page_name or f"page_{len(self._pages) + 1}"
        self._pages[page_id] = page
        
        logger.info(f"Created page: {page_id}")
        return page
        
    async def get_page(self, page_id: str) -> Optional[Page]:
        """Get an existing page by ID."""
        return self._pages.get(page_id)
        
    async def close_page(self, page_id: str) -> None:
        """Close and remove a page."""
        if page_id in self._pages:
            await self._pages[page_id].close()
            del self._pages[page_id]
            logger.info(f"Closed page: {page_id}")
            
    async def navigate(
        self,
        page: Page,
        url: str,
        wait_until: str = "load",
        timeout: Optional[int] = None
    ) -> Response:
        """
        Navigate to a URL.
        
        Args:
            page: Page instance
            url: Target URL
            wait_until: Wait condition (load, domcontentloaded, networkidle)
            timeout: Override default timeout
        """
        logger.info(f"Navigating to: {url}")
        
        options = {"wait_until": wait_until}
        if timeout:
            options["timeout"] = timeout
            
        response = await page.goto(url, **options)
        
        if response:
            logger.info(f"Navigation complete: {response.status}")
            
        return response
        
    async def screenshot(
        self,
        page: Page,
        path: Optional[str] = None,
        full_page: bool = False,
        selector: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Take a screenshot.
        
        Args:
            page: Page instance
            path: Save path (optional)
            full_page: Capture full scrollable page
            selector: CSS selector for element screenshot
            **kwargs: Additional screenshot options
        """
        options = {
            "full_page": full_page,
            "animations": "disabled",
            **kwargs
        }
        
        if path:
            options["path"] = path
            
        if selector:
            element = await page.query_selector(selector)
            if element:
                return await element.screenshot(**options)
            else:
                logger.warning(f"Element not found for screenshot: {selector}")
                
        screenshot_bytes = await page.screenshot(**options)
        logger.info(f"Screenshot captured: {len(screenshot_bytes)} bytes")
        
        return screenshot_bytes
        
    async def pdf(
        self,
        page: Page,
        path: Optional[str] = None,
        format: str = "A4",
        print_background: bool = True,
        margin: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> bytes:
        """
        Generate PDF of page.
        
        Args:
            page: Page instance
            path: Save path (optional)
            format: Paper format (A4, Letter, etc.)
            print_background: Include background graphics
            margin: Page margins
            **kwargs: Additional PDF options
        """
        options = {
            "format": format,
            "print_background": print_background,
            **kwargs
        }
        
        if path:
            options["path"] = path
            
        if margin:
            options["margin"] = margin
            
        pdf_bytes = await page.pdf(**options)
        logger.info(f"PDF generated: {len(pdf_bytes)} bytes")
        
        return pdf_bytes
        
    async def add_intercept_rule(
        self,
        pattern: str,
        handler: Callable[[Route], Awaitable[None]],
        methods: Optional[List[str]] = None,
        resource_types: Optional[List[str]] = None
    ) -> None:
        """
        Add a network interception rule.
        
        Args:
            pattern: URL pattern to intercept (glob or regex)
            handler: Async function to handle intercepted requests
            methods: HTTP methods to intercept (empty = all)
            resource_types: Resource types to intercept (empty = all)
        """
        rule = InterceptRule(
            pattern=pattern,
            handler=handler,
            methods=methods or [],
            resource_types=resource_types or []
        )
        
        self._intercept_rules.append(rule)
        
        # Apply to all existing pages
        for page in self._pages.values():
            await page.route(pattern, handler)
            
        logger.info(f"Added intercept rule: {pattern}")
        
    async def remove_intercept_rule(self, pattern: str) -> None:
        """Remove an interception rule."""
        self._intercept_rules = [
            rule for rule in self._intercept_rules if rule.pattern != pattern
        ]
        
        # Unroute from all pages
        for page in self._pages.values():
            await page.unroute(pattern)
            
        logger.info(f"Removed intercept rule: {pattern}")
        
    async def block_resources(
        self,
        resource_types: List[str] = None
    ) -> None:
        """
        Block specified resource types.
        
        Args:
            resource_types: Types to block (e.g., ['image', 'font', 'stylesheet'])
        """
        if resource_types is None:
            resource_types = ['image', 'font', 'media']
            
        async def block_handler(route: Route):
            if route.request.resource_type in resource_types:
                await route.abort()
            else:
                await route.continue_()
                
        await self.add_intercept_rule(
            "**/*",
            block_handler,
            resource_types=resource_types
        )
        
        logger.info(f"Blocking resources: {resource_types}")
        
    async def mock_response(
        self,
        url_pattern: str,
        response_body: Any,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Mock responses for matching URLs.
        
        Args:
            url_pattern: URL pattern to match
            response_body: Response body (string, dict, or bytes)
            status: HTTP status code
            headers: Response headers
        """
        async def mock_handler(route: Route):
            body = response_body
            if isinstance(body, dict):
                body = json.dumps(body)
                
            await route.fulfill(
                status=status,
                body=body,
                headers=headers or {"content-type": "application/json"}
            )
            
        await self.add_intercept_rule(url_pattern, mock_handler)
        
        logger.info(f"Mocking response for: {url_pattern}")
        
    def get_network_events(
        self,
        url_filter: Optional[str] = None,
        method_filter: Optional[str] = None,
        status_filter: Optional[int] = None
    ) -> List[NetworkEvent]:
        """
        Get captured network events with optional filters.
        
        Args:
            url_filter: Filter by URL substring
            method_filter: Filter by HTTP method
            status_filter: Filter by status code
        """
        events = self._network_events
        
        if url_filter:
            events = [e for e in events if url_filter in e.url]
            
        if method_filter:
            events = [e for e in events if e.method.upper() == method_filter.upper()]
            
        if status_filter:
            events = [e for e in events if e.status == status_filter]
            
        return events
        
    def clear_network_events(self) -> None:
        """Clear captured network events."""
        self._network_events.clear()
        logger.info("Network events cleared")
        
    async def get_download(self, download_id: str) -> Optional[Download]:
        """Get a download by ID."""
        return self._downloads.get(download_id)
        
    async def save_download(
        self,
        download: Download,
        path: Optional[str] = None
    ) -> str:
        """
        Save a download to disk.
        
        Args:
            download: Download instance
            path: Save path (optional, uses suggested name if not provided)
        """
        if path is None:
            path = os.path.join(
                self.config.downloads_path,
                download.suggested_filename
            )
            
        await download.save_as(path)
        logger.info(f"Download saved: {path}")
        
        return path
        
    async def _on_request(self, request: Request) -> None:
        """Handle request event."""
        event = NetworkEvent(
            timestamp=time.time(),
            method=request.method,
            url=request.url,
            request_headers=dict(request.headers),
            resource_type=request.resource_type,
        )
        
        if request.post_data:
            event.request_body = request.post_data
            
        self._network_events.append(event)
        
    async def _on_response(self, response: Response) -> None:
        """Handle response event."""
        # Find matching request event
        for event in reversed(self._network_events):
            if event.url == response.url and event.method == response.request.method:
                event.status = response.status
                event.response_headers = dict(response.headers)
                event.time = time.time() - event.timestamp
                
                # Capture response body for certain types
                if response.ok and response.request.resource_type in ["document", "xhr", "fetch"]:
                    try:
                        body = await response.text()
                        event.response_body = body[:10000]  # Limit size
                    except Exception:
                        pass
                break
                
    async def _on_download(self, download: Download) -> None:
        """Handle download event."""
        download_id = f"dl_{int(time.time() * 1000)}"
        self._downloads[download_id] = download
        logger.info(f"Download started: {download.suggested_filename} ({download_id})")
        
    async def _on_filechooser(self, file_chooser: FileChooser) -> None:
        """Handle file chooser event."""
        logger.info(f"File chooser opened: {file_chooser.element}")
        
    async def _on_dialog(self, dialog: Dialog) -> None:
        """Handle dialog event."""
        logger.info(f"Dialog appeared: {dialog.type} - {dialog.message}")
        # Auto-dismiss dialogs
        await dialog.dismiss()
        
    @property
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._is_running
        
    @property
    def contexts(self) -> Dict[str, BrowserContext]:
        """Get all contexts."""
        return self._contexts.copy()
        
    @property
    def pages(self) -> Dict[str, Page]:
        """Get all pages."""
        return self._pages.copy()
        
    @property
    def browser_version(self) -> Optional[str]:
        """Get browser version."""
        if self._browser:
            return self._browser.version
        return None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


class BrowserSession:
    """
    High-level browser session manager.
    Simplifies common browser operations.
    """
    
    def __init__(self, engine: BrowserEngine):
        self.engine = engine
        self._current_page: Optional[Page] = None
        self._current_context: str = "default"
        
    async def start(self) -> None:
        """Start the session."""
        await self.engine.start()
        
    async def stop(self) -> None:
        """Stop the session."""
        await self.engine.stop()
        
    async def open(self, url: str, **kwargs) -> Page:
        """
        Open a URL in a new page.
        
        Args:
            url: Target URL
            **kwargs: Navigation options
        """
        page = await self.engine.create_page(self._current_context)
        await self.engine.navigate(page, url, **kwargs)
        self._current_page = page
        return page
        
    async def current_page(self) -> Optional[Page]:
        """Get the current page."""
        return self._current_page
        
    async def new_tab(self) -> Page:
        """Open a new tab."""
        page = await self.engine.create_page(self._current_context)
        return page
        
    async def switch_tab(self, page_id: str) -> Page:
        """Switch to a different tab."""
        page = await self.engine.get_page(page_id)
        if page:
            self._current_page = page
        return page
        
    async def close_tab(self, page_id: Optional[str] = None) -> None:
        """Close current or specified tab."""
        if page_id:
            await self.engine.close_page(page_id)
        elif self._current_page:
            # Find page ID for current page
            for pid, page in self.engine.pages.items():
                if page == self._current_page:
                    await self.engine.close_page(pid)
                    self._current_page = None
                    break
                    
    async def screenshot(self, **kwargs) -> bytes:
        """Take screenshot of current page."""
        if self._current_page:
            return await self.engine.screenshot(self._current_page, **kwargs)
        raise RuntimeError("No active page")
        
    async def pdf(self, **kwargs) -> bytes:
        """Generate PDF of current page."""
        if self._current_page:
            return await self.engine.pdf(self._current_page, **kwargs)
        raise RuntimeError("No active page")
        
    async def save_state(self, path: str) -> None:
        """Save browser state (cookies, localStorage)."""
        context = await self.engine.get_context(self._current_context)
        if context:
            await context.storage_state(path=path)
            logger.info(f"State saved to: {path}")
            
    async def load_state(self, path: str) -> None:
        """Load browser state."""
        self._current_context = f"loaded_{int(time.time())}"
        await self.engine.create_context(
            self._current_context,
            storage_state=path
        )
        logger.info(f"State loaded from: {path}")
        
    async def __aenter__(self):
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
