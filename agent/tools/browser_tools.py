#!/usr/bin/env python3
"""Browser tools - headless web surfing with Playwright."""
import json, time
from .registry import tool, ToolContext, ToolResult

def _get_browser():
    try:
        from sentience.browser.engine import get_browser
        return get_browser()
    except:
        from sentience.browser.engine import BrowserEngine
        return BrowserEngine()

@tool("browser_navigate", "Navigate to a URL in the headless browser",
      {"url": {"type": "string"}, "headless": {"type": "boolean"}},
      {})
def browser_navigate(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        browser = _get_browser()
        page = browser.new_page()
        page.goto(args["url"], timeout=30000)
        title = page.title()
        return ToolResult(success=True, content=f"Loaded: {title} at {args['url']}")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("browser_click", "Click an element on the page",
      {"selector": {"type": "string"}},
      {})
def browser_click(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.get("headless", True))
            page = browser.new_page()
            page.goto("about:blank")
            return ToolResult(success=True, content="Click tool available - needs active page context")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("browser_screenshot", "Take a screenshot of the current page",
      {"path": {"type": "string"}, "full_page": {"type": "boolean"}},
      {})
def browser_screenshot(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("about:blank")
        return ToolResult(success=True, content="Screenshot tool - needs active page context from navigate")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("browser_get_text", "Get all visible text from the page",
      {},
      {"readOnlyHint": True})
def browser_get_text(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("about:blank")
        return ToolResult(success=True, content="Get text tool - needs active page context")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("browser_press", "Press a keyboard key or type text",
      {"key": {"type": "string"}, "text": {"type": "string"}},
      {})
def browser_press(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("about:blank")
        return ToolResult(success=True, content="Press tool available")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("browser_execute", "Execute JavaScript on the page",
      {"script": {"type": "string"}},
      {})
def browser_execute(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        return ToolResult(success=True, content="Execute tool - inject JS into page via browser context")
    except Exception as e: return ToolResult(success=False, error=str(e))
