"""
Browser Agent Tools for Sentience v3.0
Agent tools for browser automation including browse, click, fill, extract, and screenshot.
"""

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union
from urllib.parse import urlparse

from playwright.async_api import (
    Page,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

from .engine import BrowserEngine, BrowserConfig, BrowserType, BrowserSession
from .actions import BrowserActions, ActionResult, HumanBehavior
from .extractor import ContentExtractor
from .stealth import StealthCoordinator, StealthConfig
from .auth_manager import AuthManager

logger = logging.getLogger(__name__)


# ==================== Tool Decorator ====================

def browser_tool(func):
    """Decorator for browser tools."""
    func._is_browser_tool = True
    return func


# ==================== Tool Result Types ====================

@dataclass
class ToolResult:
    """Result from a browser tool."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    screenshot: Optional[str] = None  # Base64 encoded
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "screenshot": self.screenshot,
            "metadata": self.metadata,
        }


# ==================== Browser Tools ====================

class BrowserTools:
    """
    Collection of browser automation tools for agents.
    Each tool is designed to be called by an AI agent.
    """
    
    def __init__(
        self,
        engine: Optional[BrowserEngine] = None,
        config: Optional[BrowserConfig] = None,
        stealth_config: Optional[StealthConfig] = None,
        auth_manager: Optional[AuthManager] = None,
        screenshot_dir: str = "/tmp/sentience-screenshots"
    ):
        self.engine = engine or BrowserEngine(config or BrowserConfig())
        self.config = config or BrowserConfig()
        self.stealth = StealthCoordinator(stealth_config)
        self.auth_manager = auth_manager or AuthManager()
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # State
        self._current_page: Optional[Page] = None
        self._current_url: Optional[str] = None
        self._actions: Optional[BrowserActions] = None
        self._extractor: Optional[ContentExtractor] = None
        self._is_initialized = False
        
        # Tool registry
        self._tools: Dict[str, Callable] = {}
        self._register_tools()
        
    def _register_tools(self) -> None:
        """Register all available tools."""
        for name in dir(self):
            method = getattr(self, name)
            if hasattr(method, '_is_browser_tool'):
                self._tools[name] = method
                
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get JSON schemas for all tools."""
        schemas = []
        
        for name, tool in self._tools.items():
            schema = {
                "name": name,
                "description": tool.__doc__ or f"Browser tool: {name}",
                "parameters": self._get_tool_parameters(tool),
            }
            schemas.append(schema)
            
        return schemas
        
    def _get_tool_parameters(self, tool: Callable) -> Dict[str, Any]:
        """Extract parameter schema from tool."""
        # This is a simplified version - real implementation would use type hints
        import inspect
        sig = inspect.signature(tool)
        
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
                
            param_schema = {"type": "string"}
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
                
            properties[param_name] = param_schema
            
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        
    async def initialize(self) -> None:
        """Initialize browser engine."""
        if self._is_initialized:
            return
            
        await self.engine.start()
        self._is_initialized = True
        logger.info("Browser tools initialized")
        
    async def shutdown(self) -> None:
        """Shutdown browser engine."""
        if self._is_initialized:
            await self.engine.stop()
            self._is_initialized = False
            logger.info("Browser tools shutdown")
            
    async def _ensure_page(self) -> Page:
        """Ensure we have an active page."""
        if not self._is_initialized:
            await self.initialize()
            
        if not self._current_page:
            self._current_page = await self.engine.create_page()
            self._actions = BrowserActions(self._current_page)
            self._extractor = ContentExtractor(self._current_page)
            
            # Apply stealth
            context = self._current_page.context
            await self.stealth.setup_context(context, self._current_page)
            
        return self._current_page
        
    # ==================== Browse Tool ====================
    
    @browser_tool
    async def browse(
        self,
        url: str,
        wait_until: str = "load",
        timeout: int = 30000,
        take_screenshot: bool = True
    ) -> ToolResult:
        """
        Navigate to a URL and load the page.
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition (load, domcontentloaded, networkidle)
            timeout: Timeout in milliseconds
            take_screenshot: Whether to take a screenshot after loading
        """
        try:
            page = await self._ensure_page()
            
            # Rate limiting
            await self.stealth.before_request()
            
            # Navigate
            response = await self.engine.navigate(
                page,
                url,
                wait_until=wait_until,
                timeout=timeout
            )
            
            self._current_url = url
            
            # Post-navigation delay
            await self.stealth.after_navigation()
            
            # Update extractor
            self._extractor = ContentExtractor(page)
            
            result = {
                "url": page.url,
                "status": response.status if response else None,
                "title": await page.title(),
            }
            
            screenshot_b64 = None
            if take_screenshot:
                screenshot = await self.engine.screenshot(page)
                screenshot_b64 = base64.b64encode(screenshot).decode()
                
            return ToolResult(
                success=True,
                output=result,
                screenshot=screenshot_b64,
                metadata={"final_url": page.url}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Click Tool ====================
    
    @browser_tool
    async def click(
        self,
        selector: str,
        button: str = "left",
        click_count: int = 1,
        timeout: int = 30000,
        wait_after: bool = True
    ) -> ToolResult:
        """
        Click on an element.
        
        Args:
            selector: CSS selector or text to click
            button: Mouse button (left, right, middle)
            click_count: Number of clicks (1 for single, 2 for double)
            timeout: Timeout in milliseconds
            wait_after: Wait for navigation/action to complete
        """
        try:
            page = await self._ensure_page()
            
            # Pre-action stealth
            await self.stealth.before_action("click")
            
            # Determine if selector is text or CSS
            if not any(c in selector for c in ["#", ".", "[", ">", " "]):
                # Treat as text
                locator = page.get_by_text(selector)
            else:
                locator = page.locator(selector)
                
            # Perform click
            await locator.click(
                button=button,
                click_count=click_count,
                timeout=timeout
            )
            
            # Post-action delay
            await self.stealth.after_action("click")
            
            # Wait for potential navigation
            if wait_after:
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except PlaywrightTimeoutError:
                    pass
                    
            result = {
                "selector": selector,
                "button": button,
                "click_count": click_count,
                "current_url": page.url,
            }
            
            return ToolResult(
                success=True,
                output=result,
                metadata={"clicked_at": datetime.now().isoformat()}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Fill Tool ====================
    
    @browser_tool
    async def fill(
        self,
        selector: str,
        value: str,
        clear_first: bool = True,
        press_enter: bool = False,
        timeout: int = 30000
    ) -> ToolResult:
        """
        Fill an input field with a value.
        
        Args:
            selector: CSS selector for input field
            value: Value to fill
            clear_first: Clear existing content first
            press_enter: Press Enter after filling
            timeout: Timeout in milliseconds
        """
        try:
            page = await self._ensure_page()
            
            # Pre-action stealth
            await self.stealth.before_action("type")
            
            locator = page.locator(selector)
            
            # Fill
            await locator.fill(value, timeout=timeout)
            
            # Post-action delay
            await self.stealth.after_action("type")
            
            # Press enter if requested
            if press_enter:
                await page.keyboard.press("Enter")
                await self.stealth.after_action("click")
                
            result = {
                "selector": selector,
                "value": value,
                "cleared": clear_first,
            }
            
            return ToolResult(
                success=True,
                output=result,
                metadata={"filled_at": datetime.now().isoformat()}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Type Tool ====================
    
    @browser_tool
    async def type_text(
        self,
        selector: str,
        text: str,
        delay: float = 50,
        human_like: bool = True
    ) -> ToolResult:
        """
        Type text into an input field character by character.
        
        Args:
            selector: CSS selector for input field
            text: Text to type
            delay: Delay between keystrokes in ms
            human_like: Use human-like typing delays
        """
        try:
            page = await self._ensure_page()
            
            locator = page.locator(selector)
            
            if human_like:
                # Type with human-like delays
                for char in text:
                    await self.stealth.before_action("type")
                    await locator.press_sequentially(char)
                    await self.stealth.after_action("type")
            else:
                await locator.type(text, delay=delay)
                
            result = {
                "selector": selector,
                "text": text,
                "human_like": human_like,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Extract Tool ====================
    
    @browser_tool
    async def extract(
        self,
        extract_type: str = "all",
        selector: Optional[str] = None,
        include_images: bool = True,
        include_links: bool = True,
        include_tables: bool = True
    ) -> ToolResult:
        """
        Extract content from the current page.
        
        Args:
            extract_type: Type of extraction (text, links, images, tables, metadata, forms, all)
            selector: Optional CSS selector to limit extraction scope
            include_images: Include images in all extraction
            include_links: Include links in all extraction
            include_tables: Include tables in all extraction
        """
        try:
            page = await self._ensure_page()
            extractor = ContentExtractor(page)
            
            output = {}
            
            if extract_type == "text" or extract_type == "all":
                text = await extractor.extract_text(selector)
                output["text"] = {
                    "content": text.content[:5000],  # Limit size
                    "word_count": text.word_count,
                    "headings": text.headings,
                }
                
            if extract_type == "links" or extract_type == "all":
                if include_links:
                    links = await extractor.extract_links(selector)
                    output["links"] = {
                        "count": len(links),
                        "items": [
                            {"url": l.url, "text": l.text}
                            for l in links[:100]  # Limit
                        ],
                    }
                    
            if extract_type == "images" or extract_type == "all":
                if include_images:
                    images = await extractor.extract_images(selector)
                    output["images"] = {
                        "count": len(images),
                        "items": [
                            {"url": img.url, "alt": img.alt}
                            for img in images[:50]
                        ],
                    }
                    
            if extract_type == "tables" or extract_type == "all":
                if include_tables:
                    tables = await extractor.extract_tables(selector)
                    output["tables"] = {
                        "count": len(tables),
                        "items": [
                            {"headers": t.headers, "rows": t.rows[:10]}
                            for t in tables[:10]
                        ],
                    }
                    
            if extract_type == "metadata" or extract_type == "all":
                metadata = await extractor.extract_metadata()
                output["metadata"] = {
                    "title": metadata.title,
                    "description": metadata.description,
                    "keywords": metadata.keywords,
                }
                
            if extract_type == "forms":
                forms = await extractor.extract_forms(selector)
                output["forms"] = {
                    "count": len(forms),
                    "items": [
                        {"action": f.action, "inputs": f.inputs}
                        for f in forms
                    ],
                }
                
            if extract_type == "structured_data":
                structured = await extractor.extract_structured_data()
                output["structured_data"] = {
                    "count": len(structured),
                    "items": [s.data for s in structured[:10]],
                }
                
            output["current_url"] = page.url
            
            return ToolResult(
                success=True,
                output=output,
                metadata={"extract_type": extract_type}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Screenshot Tool ====================
    
    @browser_tool
    async def screenshot(
        self,
        full_page: bool = False,
        selector: Optional[str] = None,
        save_path: Optional[str] = None
    ) -> ToolResult:
        """
        Take a screenshot of the current page.
        
        Args:
            full_page: Capture the full scrollable page
            selector: CSS selector to capture specific element
            save_path: Path to save screenshot (optional)
        """
        try:
            page = await self._ensure_page()
            
            # Determine save path
            if not save_path:
                timestamp = int(time.time() * 1000)
                save_path = str(self.screenshot_dir / f"screenshot_{timestamp}.png")
                
            # Take screenshot
            screenshot_bytes = await self.engine.screenshot(
                page,
                path=save_path,
                full_page=full_page,
                selector=selector
            )
            
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
            
            result = {
                "path": save_path,
                "size_bytes": len(screenshot_bytes),
                "full_page": full_page,
            }
            
            return ToolResult(
                success=True,
                output=result,
                screenshot=screenshot_b64,
                metadata={"saved_at": datetime.now().isoformat()}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Scroll Tool ====================
    
    @browser_tool
    async def scroll(
        self,
        direction: str = "down",
        amount: int = 300,
        to_element: Optional[str] = None,
        to_percentage: Optional[float] = None
    ) -> ToolResult:
        """
        Scroll the page.
        
        Args:
            direction: Scroll direction (up, down, left, right)
            amount: Scroll amount in pixels
            to_element: CSS selector to scroll to
            to_percentage: Scroll to percentage of page (0-100)
        """
        try:
            page = await self._ensure_page()
            
            # Pre-action stealth
            await self.stealth.before_action("scroll")
            
            if to_element:
                locator = page.locator(to_element)
                await locator.scroll_into_view_if_needed()
            elif to_percentage is not None:
                script = f"""
                    const scrollHeight = document.body.scrollHeight - window.innerHeight;
                    window.scrollTo(0, scrollHeight * {to_percentage / 100});
                """
                await page.evaluate(script)
            else:
                scroll_amounts = {
                    "up": -amount,
                    "down": amount,
                    "left": -amount,
                    "right": amount,
                }
                
                if direction in ["up", "down"]:
                    await page.evaluate(f"window.scrollBy(0, {scroll_amounts[direction]})")
                else:
                    await page.evaluate(f"window.scrollBy({scroll_amounts[direction]}, 0)")
                    
            # Post-action delay
            await self.stealth.after_action("scroll")
            
            # Get current scroll position
            scroll_pos = await page.evaluate("({x: window.scrollX, y: window.scrollY})")
            
            result = {
                "direction": direction,
                "amount": amount,
                "position": scroll_pos,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Wait Tool ====================
    
    @browser_tool
    async def wait(
        self,
        wait_type: str = "selector",
        selector: Optional[str] = None,
        state: str = "visible",
        timeout: int = 30000,
        duration: Optional[float] = None
    ) -> ToolResult:
        """
        Wait for a condition.
        
        Args:
            wait_type: Type of wait (selector, load, timeout, networkidle)
            selector: CSS selector to wait for
            state: State to wait for (visible, hidden, attached, detached)
            timeout: Timeout in milliseconds
            duration: Duration in seconds (for timeout wait_type)
        """
        try:
            page = await self._ensure_page()
            
            start_time = time.time()
            
            if wait_type == "selector" and selector:
                await page.wait_for_selector(selector, state=state, timeout=timeout)
            elif wait_type == "load":
                await page.wait_for_load_state("load", timeout=timeout)
            elif wait_type == "networkidle":
                await page.wait_for_load_state("networkidle", timeout=timeout)
            elif wait_type == "timeout" and duration:
                await asyncio.sleep(duration)
            else:
                raise ValueError(f"Invalid wait configuration: {wait_type}")
                
            elapsed = time.time() - start_time
            
            result = {
                "wait_type": wait_type,
                "elapsed_seconds": elapsed,
                "success": True,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Hover Tool ====================
    
    @browser_tool
    async def hover(
        self,
        selector: str,
        timeout: int = 30000
    ) -> ToolResult:
        """
        Hover over an element.
        
        Args:
            selector: CSS selector for element
            timeout: Timeout in milliseconds
        """
        try:
            page = await self._ensure_page()
            
            await self.stealth.before_action("mouse_move")
            
            locator = page.locator(selector)
            await locator.hover(timeout=timeout)
            
            await self.stealth.after_action("mouse_move")
            
            result = {
                "selector": selector,
                "hovered": True,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Select Tool ====================
    
    @browser_tool
    async def select(
        self,
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        index: Optional[int] = None
    ) -> ToolResult:
        """
        Select an option from a dropdown.
        
        Args:
            selector: CSS selector for select element
            value: Option value to select
            label: Option label to select
            index: Option index to select
        """
        try:
            page = await self._ensure_page()
            
            locator = page.locator(selector)
            
            if value is not None:
                await locator.select_option(value=value)
            elif label is not None:
                await locator.select_option(label=label)
            elif index is not None:
                await locator.select_option(index=index)
            else:
                raise ValueError("Must provide value, label, or index")
                
            result = {
                "selector": selector,
                "selected": value or label or index,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Press Tool ====================
    
    @browser_tool
    async def press(
        self,
        key: str,
        modifiers: Optional[str] = None
    ) -> ToolResult:
        """
        Press a keyboard key.
        
        Args:
            key: Key to press (e.g., Enter, Tab, Escape, ArrowDown)
            modifiers: Modifier keys separated by + (e.g., Control+Shift)
        """
        try:
            page = await self._ensure_page()
            
            if modifiers:
                # Parse modifiers
                modifier_list = modifiers.split("+")
                for mod in modifier_list:
                    await page.keyboard.down(mod.strip())
                    
                await page.keyboard.press(key)
                
                for mod in reversed(modifier_list):
                    await page.keyboard.up(mod.strip())
            else:
                await page.keyboard.press(key)
                
            result = {
                "key": key,
                "modifiers": modifiers,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Go Back/Forward Tools ====================
    
    @browser_tool
    async def go_back(self) -> ToolResult:
        """Navigate back in browser history."""
        try:
            page = await self._ensure_page()
            
            await page.go_back()
            await self.stealth.after_navigation()
            
            result = {
                "url": page.url,
                "title": await page.title(),
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    @browser_tool
    async def go_forward(self) -> ToolResult:
        """Navigate forward in browser history."""
        try:
            page = await self._ensure_page()
            
            await page.go_forward()
            await self.stealth.after_navigation()
            
            result = {
                "url": page.url,
                "title": await page.title(),
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Reload Tool ====================
    
    @browser_tool
    async def reload(
        self,
        ignore_cache: bool = False
    ) -> ToolResult:
        """
        Reload the current page.
        
        Args:
            ignore_cache: Bypass cache when reloading
        """
        try:
            page = await self._ensure_page()
            
            await page.reload(ignore_cache=ignore_cache)
            await self.stealth.after_navigation()
            
            result = {
                "url": page.url,
                "title": await page.title(),
                "ignore_cache": ignore_cache,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Execute Script Tool ====================
    
    @browser_tool
    async def execute(
        self,
        script: str,
        arg: Optional[Any] = None
    ) -> ToolResult:
        """
        Execute JavaScript on the page.
        
        Args:
            script: JavaScript code to execute
            arg: Optional argument to pass to the script
        """
        try:
            page = await self._ensure_page()
            
            if arg is not None:
                result = await page.evaluate(script, arg)
            else:
                result = await page.evaluate(script)
                
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Upload File Tool ====================
    
    @browser_tool
    async def upload(
        self,
        selector: str,
        files: Union[str, List[str]]
    ) -> ToolResult:
        """
        Upload files to a file input.
        
        Args:
            selector: CSS selector for file input
            files: File path(s) to upload
        """
        try:
            page = await self._ensure_page()
            
            locator = page.locator(selector)
            
            if isinstance(files, str):
                files = [files]
                
            await locator.set_input_files(files)
            
            result = {
                "selector": selector,
                "files": files,
            }
            
            return ToolResult(
                success=True,
                output=result
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Login Tool ====================
    
    @browser_tool
    async def login(
        self,
        url: str,
        username: str,
        password: str,
        username_selector: Optional[str] = None,
        password_selector: Optional[str] = None,
        submit_selector: Optional[str] = None
    ) -> ToolResult:
        """
        Login to a website.
        
        Args:
            url: Login page URL
            username: Username/email
            password: Password
            username_selector: Username field selector
            password_selector: Password field selector
            submit_selector: Submit button selector
        """
        try:
            # Navigate to login page
            browse_result = await self.browse(url)
            if not browse_result.success:
                return browse_result
                
            page = await self._ensure_page()
            
            # Default selectors
            username_selector = username_selector or "input[name='username'], input[name='email'], input[type='email'], #username, #email"
            password_selector = password_selector or "input[name='password'], input[type='password'], #password"
            submit_selector = submit_selector or "button[type='submit'], input[type='submit']"
            
            # Fill credentials
            await self.fill(username_selector, username)
            await self.fill(password_selector, password)
            
            # Submit
            await self.click(submit_selector)
            
            # Wait for navigation
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass
                
            # Check for auth state
            auth_state = await self.auth_manager.detect_auth_state(page, url)
            
            result = {
                "url": page.url,
                "auth_state": auth_state.value,
                "logged_in": auth_state.value == "logged_in",
            }
            
            # Save session if logged in
            if result["logged_in"]:
                await self.auth_manager.save_session(page.context, url)
                
            return ToolResult(
                success=result["logged_in"],
                output=result,
                error=None if result["logged_in"] else f"Login failed: {auth_state.value}"
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Get Current State Tool ====================
    
    @browser_tool
    async def get_state(self) -> ToolResult:
        """Get current browser state."""
        try:
            page = await self._ensure_page()
            
            state = {
                "url": page.url,
                "title": await page.title(),
                "viewport": page.viewport_size,
                "is_initialized": self._is_initialized,
            }
            
            # Add rate limit stats
            rate_stats = self.stealth.get_rate_limit_stats()
            if rate_stats:
                state["rate_limit"] = rate_stats
                
            return ToolResult(
                success=True,
                output=state
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Close Tool ====================
    
    @browser_tool
    async def close(self) -> ToolResult:
        """Close the current page."""
        try:
            if self._current_page:
                await self._current_page.close()
                self._current_page = None
                self._actions = None
                self._extractor = None
                
            return ToolResult(
                success=True,
                output={"closed": True}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
            
    # ==================== Utility Methods ====================
    
    async def __aenter__(self):
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()


# ==================== Tool Registry ====================

def create_browser_tool_registry() -> Dict[str, Any]:
    """Create a registry of browser tools for an agent."""
    tools = BrowserTools()
    return {
        "tools": tools,
        "schemas": tools.get_tool_schemas(),
    }
