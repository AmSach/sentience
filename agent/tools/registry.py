#!/usr/bin/env python3
"""Tool Registry - decorator-based registration for all agent tools."""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

@dataclass
class ToolResult:
    success: bool; content: str = ""; error: str = ""
    def __str__(self): return self.content if self.success else f"Error: {self.error}"

@dataclass  
class ToolContext:
    workspace_path: str; conversation_id: str; user_id: str
    memory: Any = None; integrations: Any = None
    vault: Any = None; compression: Any = None; graph: Any = None

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}
        self._handlers: Dict[str, Callable] = {}
    
    def register(self, name: str, handler: Callable, description: str, input_schema: dict, annotations: dict = None):
        self._tools[name] = {"name": name, "description": description, "input_schema": input_schema, "annotations": annotations or {}}
        self._handlers[name] = handler
    
    def execute(self, name: str, args: dict, ctx: ToolContext) -> ToolResult:
        if name not in self._handlers: return ToolResult(success=False, error=f"Unknown tool: {name}")
        try: return self._handlers[name](args, ctx)
        except Exception as e: return ToolResult(success=False, error=str(e))
    
    def list_tools(self): return list(self._tools.values())
    def get_schema(self): return [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"], "annotations": t["annotations"]} for t in self._tools.values()]

_registry = ToolRegistry()

def tool(name: str = None, description: str = "", input_schema: dict = None, annotations: dict = None):
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        schema = input_schema or {}
        if not schema and fn.__doc__:
            import re
            params = re.findall(r'(\w+):\s*(\{[^}]+\}|[\w\[\]]+)', fn.__doc__)
            for p, t in params: schema[p] = {"type": "string" if 'str' in t else "integer" if 'int' in t else "object"}
        _registry.register(tool_name, fn, description or (fn.__doc__ or "")[:200], schema, annotations)
        return fn
    return decorator

def get_registry(): return _registry
