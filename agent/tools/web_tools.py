#!/usr/bin/env python3
"""Web tools - fetch pages, download files, HTTP requests."""
import urllib.request, urllib.error, json, os, hashlib
from .registry import tool, ToolContext, ToolResult

@tool("web_fetch", "Fetch a web page and extract content",
      {"url": {"type": "string"}, "prompt": {"type": "string"}},
      {"readOnlyHint": True})
def web_fetch(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        req = urllib.request.Request(args["url"], headers={"User-Agent": "Mozilla/5.0 Sentience/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read().decode("utf-8", errors="replace")[:100000]
        return ToolResult(success=True, content=content)
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("download_file", "Download a file from a URL to local filesystem",
      {"url": {"type": "string"}, "dest": {"type": "string"}},
      {})
def download_file(args: dict, ctx: ToolContext) -> ToolResult:
    dest = args.get("dest") or os.path.join(ctx.workspace_path or os.expanduser("~/sentience_workspace"), os.path.basename(args["url"]))
    try:
        req = urllib.request.Request(args["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(dest, "wb") as f: f.write(r.read())
        return ToolResult(success=True, content=f"Downloaded to {dest}")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("http_request", "Make HTTP requests (GET, POST, PUT, DELETE)",
      {"method": {"type": "string"}, "url": {"type": "string"}, "headers": {"type": "object"}, "body": {"type": "string"}},
      {})
def http_request(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        data = args.get("body", "").encode() if args.get("body") else None
        req = urllib.request.Request(args["url"], data=data, method=args.get("method", "GET"),
            headers=args.get("headers", {"User-Agent": "Sentience/1.0"}))
        with urllib.request.urlopen(req, timeout=30) as r:
            return ToolResult(success=True, content=f"Status: {r.status}\n{r.read().decode('utf-8', errors='replace')[:20000]}")
    except Exception as e: return ToolResult(success=False, error=str(e))
