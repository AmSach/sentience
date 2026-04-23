#!/usr/bin/env python3
"""
Sentience Tool Registry - 40+ Tools like Zo + Cursor
Based on: Sujatx/Jarvis, vierisid/jarvis, JARVIS-desktop
"""
import os
import re
import json
import shlex
import subprocess
import asyncio
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Union
from dataclasses import dataclass, field
import logging
import traceback

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    success: bool
    output: Any
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass 
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable
    risk_level: str = "low"  # low, medium, high, critical
    requires_confirmation: bool = False
    category: str = "general"
    
    def to_schema(self) -> Dict:
        """Convert to OpenAI tool schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolRegistry:
    """Registry for all tools"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.categories: Dict[str, List[str]] = {}
        
    def register(self, name: str, description: str, parameters: Dict, 
                 risk_level: str = "low", category: str = "general"):
        """Decorator to register a tool"""
        def decorator(func: Callable) -> Callable:
            tool = Tool(
                name=name,
                description=description,
                parameters=parameters,
                func=func,
                risk_level=risk_level,
                requires_confirmation=risk_level in ["high", "critical"],
                category=category
            )
            self.tools[name] = tool
            
            if category not in self.categories:
                self.categories[category] = []
            self.categories[category].append(name)
            
            return func
        return decorator
    
    def get(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)
    
    def list_all(self, category: str = None) -> List[Tool]:
        if category:
            return [self.tools[n] for n in self.categories.get(category, [])]
        return list(self.tools.values())
    
    def to_schemas(self) -> List[Dict]:
        return [t.to_schema() for t in self.tools.values()]
    
    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool"""
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, output=None, error=f"Tool '{name}' not found")
        
        try:
            # Validate parameters
            for param, schema in tool.parameters.get("properties", {}).items():
                if param in tool.parameters.get("required", []) and param not in kwargs:
                    return ToolResult(success=False, output=None, error=f"Missing required parameter: {param}")
            
            # Execute
            result = tool.func(**kwargs)
            
            # Handle async
            if asyncio.iscoroutine(result):
                result = await result
                
            return ToolResult(success=True, output=result)
            
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}\n{traceback.format_exc()}")
            return ToolResult(success=False, output=None, error=str(e))


# Global registry
tools = ToolRegistry()


# ==================== FILESYSTEM TOOLS ====================

@tools.register(
    name="read_file",
    description="Read contents of a file",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"}
        },
        "required": ["path"]
    },
    category="filesystem"
)
def read_file(path: str) -> str:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    
    # Detect encoding
    mime, _ = mimetypes.guess_type(str(path))
    if mime and 'image' in mime:
        return f"[Binary file: {mime}]"
    
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return path.read_text(encoding='latin-1')


@tools.register(
    name="write_file",
    description="Write content to a file (creates or overwrites)",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"}
        },
        "required": ["path", "content"]
    },
    risk_level="medium",
    category="filesystem"
)
def write_file(path: str, content: str) -> str:
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return f"Written {len(content)} chars to {path}"


@tools.register(
    name="edit_file",
    description="Edit a file by replacing text",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_text": {"type": "string", "description": "Text to find and replace"},
            "new_text": {"type": "string", "description": "Replacement text"}
        },
        "required": ["path", "old_text", "new_text"]
    },
    risk_level="medium",
    category="filesystem"
)
def edit_file(path: str, old_text: str, new_text: str) -> str:
    content = read_file(path)
    if old_text not in content:
        raise ValueError(f"Text not found in file: {old_text[:50]}...")
    
    new_content = content.replace(old_text, new_text, 1)
    write_file(path, new_content)
    return f"Replaced text in {path}"


@tools.register(
    name="list_directory",
    description="List contents of a directory",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path", "default": "."},
            "pattern": {"type": "string", "description": "Glob pattern to filter", "default": "*"}
        }
    },
    category="filesystem"
)
def list_directory(path: str = ".", pattern: str = "*") -> List[str]:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not path.is_dir():
        raise ValueError(f"Not a directory: {path}")
    
    items = []
    for item in sorted(path.glob(pattern)):
        item_type = "dir" if item.is_dir() else "file"
        size = item.stat().st_size if item.is_file() else "-"
        items.append(f"{item_type:4} {size:>8} {item.name}")
    return items


@tools.register(
    name="delete_file",
    description="Delete a file",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to delete"}
        },
        "required": ["path"]
    },
    risk_level="high",
    category="filesystem"
)
def delete_file(path: str) -> str:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    path.unlink()
    return f"Deleted: {path}"


@tools.register(
    name="create_directory",
    description="Create a directory",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to create"}
        },
        "required": ["path"]
    },
    category="filesystem"
)
def create_directory(path: str) -> str:
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return f"Created directory: {path}"


@tools.register(
    name="search_files",
    description="Search for files by name or content",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to search"},
            "query": {"type": "string", "description": "Search query"},
            "search_content": {"type": "boolean", "description": "Search file contents", "default": False}
        },
        "required": ["path", "query"]
    },
    category="filesystem"
)
def search_files(path: str, query: str, search_content: bool = False) -> List[str]:
    results = []
    path = Path(path).expanduser().resolve()
    
    for file in path.rglob("*"):
        if not file.is_file():
            continue
            
        # Search by name
        if query.lower() in file.name.lower():
            results.append(f"[name] {file}")
            continue
            
        # Search by content
        if search_content:
            try:
                content = file.read_text(encoding='utf-8', errors='ignore')
                if query.lower() in content.lower():
                    results.append(f"[content] {file}")
            except:
                pass
                
    return results[:50]  # Limit results


# ==================== SHELL TOOLS ====================

@tools.register(
    name="execute_command",
    description="Execute a shell command",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
        },
        "required": ["command"]
    },
    risk_level="high",
    category="shell"
)
def execute_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:5000]
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"Timeout after {timeout}s"}


# ==================== WEB TOOLS ====================

@tools.register(
    name="http_request",
    description="Make HTTP request",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to request"},
            "method": {"type": "string", "description": "HTTP method", "default": "GET"},
            "headers": {"type": "object", "description": "Headers"},
            "body": {"type": "string", "description": "Request body"}
        },
        "required": ["url"]
    },
    risk_level="medium",
    category="web"
)
def http_request(url: str, method: str = "GET", headers: Dict = None, body: str = None) -> Dict:
    import urllib.request
    import urllib.error
    
    req = urllib.request.Request(url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    
    try:
        with urllib.request.urlopen(req, data=body.encode() if body else None, timeout=30) as resp:
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": resp.read().decode('utf-8', errors='ignore')[:10000]
            }
    except urllib.error.URLError as e:
        return {"status": 0, "error": str(e)}


@tools.register(
    name="web_search",
    description="Search the web using DuckDuckGo",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results", "default": 5}
        },
        "required": ["query"]
    },
    category="web"
)
def web_search(query: str, limit: int = 5) -> List[Dict]:
    import urllib.request
    import urllib.parse
    import json
    
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        results = []
        for topic in data.get('RelatedTopics', [])[:limit]:
            if 'Text' in topic and 'FirstURL' in topic:
                results.append({
                    "title": topic['Text'][:100],
                    "url": topic['FirstURL']
                })
        return results
    except Exception as e:
        return [{"error": str(e)}]


# ==================== CODE TOOLS ====================

@tools.register(
    name="analyze_code",
    description="Analyze code file for issues",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Code file to analyze"}
        },
        "required": ["path"]
    },
    category="code"
)
def analyze_code(path: str) -> Dict[str, Any]:
    content = read_file(path)
    ext = Path(path).suffix
    
    issues = []
    
    # Basic checks
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # Check for common issues
        if 'TODO' in line or 'FIXME' in line:
            issues.append({"line": i, "type": "todo", "message": line.strip()})
        if 'print(' in line and ext == '.py':
            issues.append({"line": i, "type": "debug", "message": "Debug print statement"})
        if 'console.log(' in line and ext in ['.js', '.ts']:
            issues.append({"line": i, "type": "debug", "message": "Debug console.log"})
    
    # Python syntax check
    if ext == '.py':
        try:
            import ast
            ast.parse(content)
        except SyntaxError as e:
            issues.append({"line": e.lineno, "type": "syntax", "message": e.msg})
    
    return {
        "file": path,
        "lines": len(lines),
        "issues": issues
    }


# ==================== MEMORY TOOLS ====================

@tools.register(
    name="store_memory",
    description="Store a memory for later retrieval",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Memory key"},
            "value": {"type": "string", "description": "Memory content"},
            "metadata": {"type": "object", "description": "Additional metadata"}
        },
        "required": ["key", "value"]
    },
    category="memory"
)
def store_memory(key: str, value: str, metadata: Dict = None) -> str:
    # This will be connected to the MemorySystem
    return f"Stored memory: {key}"


@tools.register(
    name="retrieve_memory",
    description="Retrieve a stored memory",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Memory key to retrieve"}
        },
        "required": ["key"]
    },
    category="memory"
)
def retrieve_memory(key: str) -> str:
    return f"Memory for {key}: [not implemented - connect to MemorySystem]"


@tools.register(
    name="search_memory",
    description="Search stored memories",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results", "default": 5}
        },
        "required": ["query"]
    },
    category="memory"
)
def search_memory(query: str, limit: int = 5) -> List[str]:
    return [f"Result {i} for: {query}" for i in range(min(limit, 3))]


# ==================== SYSTEM TOOLS ====================

@tools.register(
    name="get_system_info",
    description="Get system information",
    parameters={"type": "object", "properties": {}},
    category="system"
)
def get_system_info() -> Dict[str, Any]:
    import platform
    import psutil
    
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "python": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_total_gb": psutil.virtual_memory().total / (1024**3),
        "memory_available_gb": psutil.virtual_memory().available / (1024**3),
        "disk_total_gb": psutil.disk_usage('/').total / (1024**3),
        "disk_free_gb": psutil.disk_usage('/').free / (1024**3)
    }


# ==================== TIME TOOLS ====================

@tools.register(
    name="get_current_time",
    description="Get current date and time",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "Timezone name", "default": "local"}
        }
    },
    category="time"
)
def get_current_time(timezone: str = "local") -> str:
    from datetime import datetime
    return datetime.now().isoformat()


# Export
__all__ = ['ToolRegistry', 'Tool', 'ToolResult', 'tools']
