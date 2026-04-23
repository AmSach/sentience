#!/usr/bin/env python3
"""Search tools - DuckDuckGo search and instant answers."""
import urllib.request, urllib.parse, json
from .registry import tool, ToolContext, ToolResult

@tool("web_search", "Search the web using DuckDuckGo",
      {"query": {"type": "string"}, "num_results": {"type": "integer"}},
      {"readOnlyHint": True})
def web_search(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        q = urllib.parse.quote(args["query"])
        url = f"https://api.duckduckgo.com/?q={q}&format=json&t=Sentience"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Sentience/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        results = []
        for topic in data.get("RelatedTopics", [])[:args.get("num_results", 10)]:
            if "Text" in topic:
                results.append(f"- {topic.get('Text','')} [{topic.get('FirstURL','')}]")
        return ToolResult(success=True, content=f"Query: {args['query']}\n\n" + "\n".join(results) + (f"\n\nAbstract: {data.get('AbstractText','')}" if data.get('AbstractText') else ""))
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("ddg_instant_answer", "Get instant answer from DuckDuckGo",
      {"query": {"type": "string"}},
      {"readOnlyHint": True})
def ddg_instant_answer(args: dict, ctx: ToolContext) -> ToolResult:
    return web_search({"query": args["query"], "num_results": 3}, ctx)
