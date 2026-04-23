#!/usr/bin/env python3
"""Tool Registry"""
from typing import Dict, Callable, Any

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        
    def register(self, name: str):
        """Decorator to register a tool"""
        def decorator(func):
            self.tools[name] = func
            return func
        return decorator
        
    def get(self, name: str) -> Callable:
        """Get tool by name"""
        return self.tools.get(name)
        
    def list_tools(self) -> Dict[str, str]:
        """List all tools with descriptions"""
        return {name: func.__doc__ or "" for name, func in self.tools.items()}
