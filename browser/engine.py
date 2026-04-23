#!/usr/bin/env python3
"""Browser Engine - Playwright-based headless browser with session management."""
import os, json, time
from typing import Optional, Dict, Any

class BrowserEngine:
    """Persistent headless browser for web surfing - like Perplexity."""
    _instance: Optional["BrowserEngine"] = None
    _playwright = None
    _browser = None
    _page = None
    _session_id = None
    
    def __init__(self):
        self.history = []
        self.cookies = {}
        self._init_playwright()
    
    def _init_playwright(self):
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"])
            self._page = self._browser.new_page()
            self._session_id = str(time.time())
        except Exception as e:
            print(f"Browser init failed: {e}")
            self._playwright = None
    
    def is_ready(self) -> bool:
        return self._page is not None
    
    def navigate(self, url: str, timeout: int = 30000) -> Dict[str, Any]:
        if not self._page: return {"success": False, "error": "Browser not initialized"}
        try:
            response = self._page.goto(url, timeout=timeout)
            self.history.append(url)
            title = self._page.title()
            return {"success": True, "url": url, "title": title, "status": response.status if response else 200}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def click(self, selector: str, timeout: int = 10000) -> Dict[str, Any]:
        if not self._page: return {"success": False, "error": "No page"}
        try:
            self._page.click(selector, timeout=timeout)
            return {"success": True, "action": f"clicked {selector}"}
        except Exception as e: return {"success": False, "error": str(e)}
    
    def fill(self, selector: str, text: str) -> Dict[str, Any]:
        if not self._page: return {"success": False, "error": "No page"}
        try:
            self._page.fill(selector, text)
            return {"success": True, "action": f"filled {selector}"}
        except Exception as e: return {"success": False, "error": str(e)}
    
    def type_text(self, selector: str, text: str, delay: int = 100) -> Dict[str, Any]:
        if not self._page: return {"success": False, "error": "No page"}
        try:
            self._page.type(selector, text, delay=delay)
            return {"success": True, "action": f"typed into {selector}"}
        except Exception as e: return {"success": False, "error": str(e)}
    
    def get_text(self, selector: str = None) -> str:
        if not self._page: return ""
        try:
            if selector: return self._page.locator(selector).inner_text(timeout=5000)
            return self._page.inner_text("body")
        except: return ""
    
    def get_html(self) -> str:
        if not self._page: return ""
        return self._page.content()
    
    def screenshot(self, path: str = None, full_page: bool = False) -> bytes:
        if not self._page: return b""
        p = path or f"/tmp/screenshot_{int(time.time())}.png"
        try:
            self._page.screenshot(path=p, full_page=full_page)
            with open(p, "rb") as f: return f.read()
        except: return b""
    
    def find_elements(self, selector: str) -> list:
        if not self._page: return []
        try: return self._page.locator(selector).all()
        except: return []
    
    def press(self, key: str) -> Dict[str, Any]:
        if not self._page: return {"success": False}
        try:
            self._page.keyboard.press(key)
            return {"success": True, "action": f"pressed {key}"}
        except Exception as e: return {"success": False, "error": str(e)}
    
    def scroll(self, direction: str = "down", amount: int = 1) -> Dict[str, Any]:
        if not self._page: return {"success": False}
        try:
            for _ in range(amount):
                if direction == "down": self._page.evaluate("window.scrollBy(0, window.innerHeight)")
                else: self._page.evaluate("window.scrollBy(0, -window.innerHeight)")
                time.sleep(0.3)
            return {"success": True, "action": f"scrolled {direction}"}
        except Exception as e: return {"success": False, "error": str(e)}
    
    def wait(self, selector: str = None, timeout: int = 5000) -> Dict[str, Any]:
        if not self._page: return {"success": False}
        try:
            if selector: self._page.wait_for_selector(selector, timeout=timeout)
            else: time.sleep(timeout / 1000)
            return {"success": True}
        except: return {"success": True, "timeout": True}
    
    def execute_js(self, script: str) -> Any:
        if not self._page: return None
        try: return self._page.evaluate(script)
        except: return None
    
    def get_cookies(self) -> Dict[str, str]:
        if not self._page: return {}
        return {c["name"]: c["value"] for c in self._page.context.cookies()}
    
    def set_cookies(self, cookies: Dict[str, str]) -> None:
        if not self._page: return
        for name, value in cookies.items():
            self._page.context.add_cookies([{"name": name, "value": value, "domain": ".any.com"}])
    
    def close(self):
        if self._page: self._page.close()
        if self._browser: self._browser.close()
        if self._playwright: self._playwright.stop()
        self._page = None; self._browser = None; self._playwright = None

_browser_instance: Optional[BrowserEngine] = None

def get_browser() -> BrowserEngine:
    global _browser_instance
    if _browser_instance is None or not _browser_instance.is_ready():
        if _browser_instance: _browser_instance.close()
        _browser_instance = BrowserEngine()
    return _browser_instance

def close_browser():
    global _browser_instance
    if _browser_instance:
        _browser_instance.close()
        _browser_instance = None
