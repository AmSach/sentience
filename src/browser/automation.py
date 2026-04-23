#!/usr/bin/env python3
"""Browser Automation Module - Playwright-based web automation"""
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class BrowserAutomation:
    """Playwright-based browser automation for web tasks"""
    
    def __init__(self, headless: bool = True, downloads_path: str = None):
        self.headless = headless
        self.downloads_path = downloads_path or str(Path.home() / "Downloads" / "sentience")
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        
    async def start(self) -> bool:
        """Start browser instance"""
        if not PLAYWRIGHT_AVAILABLE:
            return False
            
        try:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless,
                downloads_path=self.downloads_path
            )
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            self.page = await self.context.new_page()
            return True
        except Exception as e:
            print(f"Browser start error: {e}")
            return False
    
    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def navigate(self, url: str, wait_until: str = "load") -> Dict:
        """Navigate to URL"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            response = await self.page.goto(url, wait_until=wait_until, timeout=30000)
            return {
                "success": True,
                "url": self.page.url,
                "title": await self.page.title(),
                "status": response.status if response else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def screenshot(self, path: str = None, full_page: bool = False) -> Dict:
        """Take screenshot"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            path = path or str(Path(self.downloads_path) / f"screenshot_{asyncio.get_event_loop().time():.0f}.png")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=path, full_page=full_page)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_text(self, selector: str = "body") -> Dict:
        """Get text content from selector"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.inner_text()
                return {"success": True, "text": text}
            return {"success": False, "error": "Element not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_html(self) -> Dict:
        """Get page HTML"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            html = await self.page.content()
            return {"success": True, "html": html[:50000]}  # Limit size
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def click(self, selector: str, timeout: int = 10000) -> Dict:
        """Click element"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            await self.page.click(selector, timeout=timeout)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def fill(self, selector: str, value: str) -> Dict:
        """Fill input field"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            await self.page.fill(selector, value)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def type(self, selector: str, text: str, delay: int = 50) -> Dict:
        """Type text into element"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            await self.page.type(selector, text, delay=delay)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> Dict:
        """Wait for element to appear"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, script: str) -> Dict:
        """Execute JavaScript"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            result = await self.page.evaluate(script)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def scroll(self, direction: str = "down", amount: int = 500) -> Dict:
        """Scroll page"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            if direction == "down":
                await self.page.evaluate(f"window.scrollBy(0, {amount})")
            else:
                await self.page.evaluate(f"window.scrollBy(0, -{amount})")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_links(self) -> Dict:
        """Get all links on page"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            links = await self.page.evaluate("""
                Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.innerText,
                    href: a.href
                }))
            """)
            return {"success": True, "links": links[:100]}  # Limit
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def download(self, url: str, save_path: str = None) -> Dict:
        """Download file from URL"""
        if not self.page:
            return {"success": False, "error": "Browser not started"}
        
        try:
            save_path = save_path or str(Path(self.downloads_path) / "download")
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            
            async with self.page.expect_download() as download_info:
                await self.page.goto(url)
            download = await download_info.value
            await download.save_as(save_path)
            
            return {"success": True, "path": save_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Tool definitions for AI
BROWSER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate browser to URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click element by CSS selector",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Fill input field",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "value": {"type": "string", "description": "Value to fill"}
                },
                "required": ["selector", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_text",
            "description": "Get text content from page",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector (default: body)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take screenshot of current page",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Save path"},
                    "full_page": {"type": "boolean", "description": "Capture full page"}
                }
            }
        }
    }
]

# Singleton instance
_browser_instance: Optional[BrowserAutomation] = None

async def get_browser() -> BrowserAutomation:
    """Get or create browser instance"""
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = BrowserAutomation()
        await _browser_instance.start()
    return _browser_instance

async def execute_browser_tool(name: str, args: Dict) -> Dict:
    """Execute browser tool by name"""
    browser = await get_browser()
    
    if name == "browser_navigate":
        return await browser.navigate(args.get("url", ""))
    elif name == "browser_click":
        return await browser.click(args.get("selector", ""))
    elif name == "browser_fill":
        return await browser.fill(args.get("selector", ""), args.get("value", ""))
    elif name == "browser_get_text":
        return await browser.get_text(args.get("selector", "body"))
    elif name == "browser_screenshot":
        return await browser.screenshot(args.get("path"), args.get("full_page", False))
    else:
        return {"success": False, "error": f"Unknown browser tool: {name}"}
