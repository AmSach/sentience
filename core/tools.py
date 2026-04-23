#!/usr/bin/env python3
"""Tool Registry - Real implementations of all tools"""
import os
import sys
import json
import subprocess
import shutil
import glob
import re
import ast
import hashlib
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import urllib.request
import urllib.parse

@dataclass
class ToolResult:
    success: bool
    output: Any
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

@dataclass  
class ToolContext:
    workspace: Path
    conversation_id: str
    config: Dict
    memory: Any  # Memory instance

class ToolRegistry:
    """Registry for all tools with schema validation"""
    
    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self._handlers: Dict[str, Callable] = {}
    
    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict,
        handler: Callable,
        annotations: Dict = None
    ) -> None:
        """Register a tool"""
        self._tools[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "annotations": annotations or {}
        }
        self._handlers[name] = handler
    
    def get_tool(self, name: str) -> Optional[Dict]:
        """Get tool definition"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[Dict]:
        """List all tools"""
        return list(self._tools.values())
    
    def execute(self, name: str, args: Dict, ctx: ToolContext) -> ToolResult:
        """Execute a tool"""
        if name not in self._handlers:
            return ToolResult(False, None, f"Unknown tool: {name}")
        
        try:
            result = self._handlers[name](args, ctx)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(True, result)
        except Exception as e:
            return ToolResult(False, None, f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")

def tool(name: str, description: str, input_schema: Dict = None, annotations: Dict = None):
    """Decorator to register a tool"""
    def decorator(func):
        func._tool_meta = {
            "name": name,
            "description": description,
            "input_schema": input_schema or {"type": "object", "properties": {}},
            "annotations": annotations or {}
        }
        return func
    return decorator

# === FILESYSTEM TOOLS ===

@tool(
    "read_file",
    "Read contents of a file. Supports text, PDF, DOCX, images.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
            "start_line": {"type": "integer", "description": "Start line (1-indexed, optional)"},
            "end_line": {"type": "integer", "description": "End line (inclusive, optional)"},
        },
        "required": ["path"]
    },
    {"readOnlyHint": True}
)
def read_file(args: Dict, ctx: ToolContext) -> ToolResult:
    path = Path(args["path"])
    if not path.is_absolute():
        path = ctx.workspace / path
    
    if not path.exists():
        return ToolResult(False, None, f"File not found: {path}")
    
    # Determine file type
    suffix = path.suffix.lower()
    
    try:
        if suffix == ".pdf":
            # PDF extraction
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                return ToolResult(True, text, metadata={"pages": len(reader.pages)})
            except ImportError:
                return ToolResult(False, None, "pypdf not installed. Run: pip install pypdf")
        
        elif suffix == ".docx":
            # DOCX extraction
            try:
                from docx import Document
                doc = Document(str(path))
                text = "\n".join(p.text for p in doc.paragraphs)
                return ToolResult(True, text)
            except ImportError:
                return ToolResult(False, None, "python-docx not installed. Run: pip install python-docx")
        
        elif suffix in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]:
            # Image - return base64 for vision models
            import base64
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            return ToolResult(True, f"[IMAGE:{path.name}]", metadata={"base64": data, "media_type": suffix[1:]})
        
        else:
            # Text file
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            start = (args.get("start_line", 1) or 1) - 1
            end = args.get("end_line") or len(lines)
            
            content = "".join(lines[start:end])
            return ToolResult(True, content, metadata={"lines": len(lines)})
    
    except Exception as e:
        return ToolResult(False, None, str(e))

@tool(
    "write_file",
    "Write content to a file. Creates directories if needed.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {"type": "string", "enum": ["write", "append"], "default": "write"},
        },
        "required": ["path", "content"]
    },
    {"destructiveHint": True}
)
def write_file(args: Dict, ctx: ToolContext) -> ToolResult:
    path = Path(args["path"])
    if not path.is_absolute():
        path = ctx.workspace / path
    
    # Create parent directories
    path.parent.mkdir(parents=True, exist_ok=True)
    
    mode = args.get("mode", "write")
    write_mode = "a" if mode == "append" else "w"
    
    try:
        with open(path, write_mode, encoding='utf-8') as f:
            f.write(args["content"])
        return ToolResult(True, f"Wrote {len(args['content'])} chars to {path}")
    except Exception as e:
        return ToolResult(False, None, str(e))

@tool(
    "edit_file",
    "Make surgical edits to a file.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "oldText": {"type": "string"},
                        "newText": {"type": "string"},
                    },
                    "required": ["oldText"]
                }
            },
        },
        "required": ["path", "edits"]
    },
    {"destructiveHint": True}
)
def edit_file(args: Dict, ctx: ToolContext) -> ToolResult:
    path = Path(args["path"])
    if not path.is_absolute():
        path = ctx.workspace / path
    
    if not path.exists():
        return ToolResult(False, None, f"File not found: {path}")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        results = []
        for edit in args["edits"]:
            old = edit["oldText"]
            new = edit.get("newText", "")
            
            if old not in content:
                results.append(f"NOT FOUND: {old[:50]}...")
                continue
            
            content = content.replace(old, new, 1)
            results.append(f"REPLACED")
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return ToolResult(True, "\n".join(results))
    except Exception as e:
        return ToolResult(False, None, str(e))

@tool(
    "list_directory",
    "List contents of a directory.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": "."},
            "recursive": {"type": "boolean", "default": False},
            "pattern": {"type": "string", "description": "Glob pattern filter"},
        },
    },
    {"readOnlyHint": True}
)
def list_directory(args: Dict, ctx: ToolContext) -> ToolResult:
    path = Path(args.get("path", "."))
    if not path.is_absolute():
        path = ctx.workspace / path
    
    if not path.exists():
        return ToolResult(False, None, f"Directory not found: {path}")
    
    try:
        pattern = args.get("pattern", "*")
        recursive = args.get("recursive", False)
        
        if recursive:
            items = list(path.rglob(pattern))
        else:
            items = list(path.glob(pattern))
        
        result = []
        for item in sorted(items)[:100]:  # Limit output
            rel = item.relative_to(path)
            if item.is_dir():
                result.append(f"📁 {rel}/")
            else:
                size = item.stat().st_size
                result.append(f"📄 {rel} ({size} bytes)")
        
        return ToolResult(True, "\n".join(result) or "(empty)")
    except Exception as e:
        return ToolResult(False, None, str(e))

@tool(
    "delete_file",
    "Delete a file or directory.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "recursive": {"type": "boolean", "default": False},
        },
        "required": ["path"]
    },
    {"destructiveHint": True}
)
def delete_file(args: Dict, ctx: ToolContext) -> ToolResult:
    path = Path(args["path"])
    if not path.is_absolute():
        path = ctx.workspace / path
    
    if not path.exists():
        return ToolResult(False, None, f"Not found: {path}")
    
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            if args.get("recursive"):
                shutil.rmtree(path)
            else:
                path.rmdir()
        return ToolResult(True, f"Deleted: {path}")
    except Exception as e:
        return ToolResult(False, None, str(e))

@tool(
    "search_files",
    "Search for files by name or content.",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Filename pattern"},
            "content": {"type": "string", "description": "Content to search for"},
            "path": {"type": "string", "default": "."},
        },
    },
    {"readOnlyHint": True}
)
def search_files(args: Dict, ctx: ToolContext) -> ToolResult:
    start_path = Path(args.get("path", "."))
    if not start_path.is_absolute():
        start_path = ctx.workspace / start_path
    
    results = []
    
    try:
        # Filename search
        if "pattern" in args:
            for match in start_path.rglob(args["pattern"]):
                if len(results) >= 50:
                    break
                results.append(str(match.relative_to(ctx.workspace)))
        
        # Content search
        if "content" in args:
            import re
            try:
                pattern = re.compile(args["content"], re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(args["content"]), re.IGNORECASE)
            
            for file in start_path.rglob("*"):
                if not file.is_file():
                    continue
                if file.suffix in ['.pyc', '.exe', '.dll', '.so', '.dylib', '.png', '.jpg', '.gif']:
                    continue
                
                try:
                    with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f, 1):
                            if pattern.search(line):
                                results.append(f"{file.relative_to(ctx.workspace)}:{i}: {line.strip()[:100]}")
                                if len(results) >= 50:
                                    break
                except:
                    pass
                if len(results) >= 50:
                    break
        
        return ToolResult(True, "\n".join(results) or "No matches found")
    except Exception as e:
        return ToolResult(False, None, str(e))

# === SHELL TOOLS ===

@tool(
    "run_command",
    "Execute a shell command.",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to run"},
            "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"},
            "cwd": {"type": "string", "description": "Working directory"},
        },
        "required": ["command"]
    },
    {"destructiveHint": True}
)
def run_command(args: Dict, ctx: ToolContext) -> ToolResult:
    cmd = args["command"]
    timeout = args.get("timeout", 30)
    cwd = args.get("cwd")
    
    if cwd and not Path(cwd).is_absolute():
        cwd = str(ctx.workspace / cwd)
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or str(ctx.workspace)
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        
        return ToolResult(
            result.returncode == 0,
            output,
            metadata={"return_code": result.returncode}
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, None, f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(False, None, str(e))

# === CODE ANALYSIS TOOLS ===

@tool(
    "analyze_code",
    "Analyze code structure, find issues, suggest improvements.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to analyze"},
            "analysis_type": {"type": "string", "enum": ["full", "lint", "complexity", "security"]},
        },
        "required": ["path"]
    },
    {"readOnlyHint": True}
)
def analyze_code(args: Dict, ctx: ToolContext) -> ToolResult:
    path = Path(args["path"])
    if not path.is_absolute():
        path = ctx.workspace / path
    
    if not path.exists():
        return ToolResult(False, None, f"File not found: {path}")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        analysis_type = args.get("analysis_type", "full")
        results = {"file": str(path), "issues": [], "metrics": {}}
        
        # Parse AST
        try:
            tree = ast.parse(code)
            results["metrics"]["lines"] = len(code.splitlines())
            results["metrics"]["functions"] = len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))])
            results["metrics"]["classes"] = len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])
        except SyntaxError as e:
            results["issues"].append({
                "type": "syntax_error",
                "line": e.lineno,
                "message": e.msg
            })
            return ToolResult(True, results)
        
        # Complexity analysis
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = sum(1 for n in ast.walk(node) if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler)))
                if complexity > 10:
                    results["issues"].append({
                        "type": "high_complexity",
                        "line": node.lineno,
                        "function": node.name,
                        "complexity": complexity,
                        "message": f"Function '{node.name}' has complexity {complexity}, consider refactoring"
                    })
        
        # Security patterns
        dangerous_patterns = [
            (r'eval\s*\(', "Use of eval() is dangerous"),
            (r'exec\s*\(', "Use of exec() is dangerous"),
            (r'__import__\s*\(', "Dynamic import can be dangerous"),
            (r'subprocess\.call.*shell=True', "shell=True can be dangerous"),
            (r'pickle\.loads?\s*\(', "Pickle can execute arbitrary code"),
        ]
        
        for pattern, msg in dangerous_patterns:
            for match in re.finditer(pattern, code):
                line = code[:match.start()].count('\n') + 1
                results["issues"].append({
                    "type": "security_warning",
                    "line": line,
                    "message": msg
                })
        
        return ToolResult(True, results)
    except Exception as e:
        return ToolResult(False, None, str(e))

# === WEB TOOLS ===

@tool(
    "web_fetch",
    "Fetch content from a URL.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
            "headers": {"type": "object"},
            "body": {"type": "string"},
        },
        "required": ["url"]
    },
    {"readOnlyHint": True}
)
def web_fetch(args: Dict, ctx: ToolContext) -> ToolResult:
    url = args["url"]
    
    try:
        req = urllib.request.Request(
            url,
            method=args.get("method", "GET"),
            headers=args.get("headers", {"User-Agent": "Sentience/2.0"})
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8', errors='replace')
            
            # Basic HTML to text
            if 'html' in response.headers.get('Content-Type', ''):
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()
            
            return ToolResult(True, content[:10000], metadata={"url": url})
    except Exception as e:
        return ToolResult(False, None, str(e))

@tool(
    "web_search",
    "Search the web using DuckDuckGo.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"]
    },
    {"readOnlyHint": True}
)
def web_search(args: Dict, ctx: ToolContext) -> ToolResult:
    query = args["query"]
    limit = args.get("limit", 5)
    
    try:
        # DuckDuckGo instant answer API
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
        
        req = urllib.request.Request(url, headers={"User-Agent": "Sentience/2.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        results = []
        
        if data.get("AbstractText"):
            results.append({
                "type": "summary",
                "text": data["AbstractText"],
                "source": data.get("AbstractURL", "")
            })
        
        for topic in (data.get("RelatedTopics") or [])[:limit]:
            if "Text" in topic:
                results.append({
                    "type": "result",
                    "text": topic["Text"],
                    "url": topic.get("FirstURL", "")
                })
        
        return ToolResult(True, results if results else [{"type": "error", "text": "No results found"}])
    except Exception as e:
        return ToolResult(False, None, str(e))

# === GIT TOOLS ===

@tool(
    "git_command",
    "Run a git command.",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Git subcommand and args"},
            "repo": {"type": "string", "description": "Repository path"},
        },
        "required": ["command"]
    },
    {"destructiveHint": True}
)
def git_command(args: Dict, ctx: ToolContext) -> ToolResult:
    cmd = args["command"]
    repo = args.get("repo", str(ctx.workspace))
    
    if not Path(repo).is_absolute():
        repo = str(ctx.workspace / repo)
    
    try:
        result = subprocess.run(
            ["git"] + cmd.split(),
            capture_output=True,
            text=True,
            cwd=repo
        )
        
        output = result.stdout or result.stderr
        return ToolResult(
            result.returncode == 0,
            output,
            metadata={"return_code": result.returncode}
        )
    except Exception as e:
        return ToolResult(False, None, str(e))

# === MEMORY TOOLS ===

@tool(
    "remember",
    "Store information in long-term memory.",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["key", "value"]
    }
)
def remember(args: Dict, ctx: ToolContext) -> ToolResult:
    key = args["key"]
    value = args["value"]
    tags = args.get("tags", [])
    
    ctx.memory.remember(key, value, tags)
    return ToolResult(True, f"Remembered: {key}")

@tool(
    "recall",
    "Retrieve information from memory.",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "query": {"type": "string", "description": "Search query if key not provided"},
        },
    }
)
def recall(args: Dict, ctx: ToolContext) -> ToolResult:
    if "key" in args:
        value = ctx.memory.recall(args["key"])
        if value:
            return ToolResult(True, value)
        return ToolResult(False, None, f"Not found: {args['key']}")
    
    if "query" in args:
        results = ctx.memory.search_memory(args["query"])
        return ToolResult(True, results)
    
    return ToolResult(False, None, "Provide either key or query")

# === REGISTER ALL ===

def create_registry() -> ToolRegistry:
    """Create and populate tool registry"""
    registry = ToolRegistry()
    
    # Find all @tool decorated functions
    import sys
    current = sys.modules[__name__]
    
    for name in dir(current):
        obj = getattr(current, name)
        if callable(obj) and hasattr(obj, '_tool_meta'):
            meta = obj._tool_meta
            registry.register(
                meta["name"],
                meta["description"],
                meta["input_schema"],
                obj,
                meta["annotations"]
            )
    
    return registry
