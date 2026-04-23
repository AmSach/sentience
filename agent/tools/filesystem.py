#!/usr/bin/env python3
"""Filesystem tools - read_file, write_file, glob, grep, edit, etc."""
import os, re, glob as g, hashlib
from pathlib import Path
from .registry import tool, ToolContext, ToolResult

WORKSPACE = os.environ.get("SENTIENCE_WORKSPACE", os.path.expanduser("~/sentience_workspace"))

def _resolve(path: str, ctx: ToolContext) -> str:
    if os.path.isabs(path): return path
    return os.path.join(ctx.workspace_path or WORKSPACE, path)

@tool("read_file", "Read a file from the filesystem",
      {"file_path": {"type": "string", "description": "Absolute or relative path to the file"}},
      {"readOnlyHint": True})
def read_file(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["file_path"], ctx)
    if not os.path.exists(path): return ToolResult(success=False, error=f"File not found: {path}")
    try:
        with open(path, "r", errors="replace") as f: content = f.read()
        if ctx.vault: ctx.vault.create_note(title=f"file:{path}", content=content[:5000])
        return ToolResult(success=True, content=content[:50000])
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("read_multiple_files", "Read multiple files at once",
      {"file_paths": {"type": "array", "items": {"type": "string"}, "description": "List of file paths"}},
      {"readOnlyHint": True})
def read_multiple_files(args: dict, ctx: ToolContext) -> ToolResult:
    results = []
    for fp in args["file_paths"][:20]:
        path = _resolve(fp, ctx)
        try:
            with open(path, "r", errors="replace") as f: results.append(f"=== {fp} ===\n{f.read()[:5000]}")
        except: results.append(f"=== {fp} ===\n[NOT FOUND]")
    return ToolResult(success=True, content="\n".join(results)[:100000])

@tool("write_file", "Write content to a file (creates or overwrites)",
      {"file_path": {"type": "string"}, "content": {"type": "string"}},
      {"idempotentHint": True})
def write_file(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["file_path"], ctx)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w") as f: f.write(args["content"])
        return ToolResult(success=True, content=f"Wrote {len(args['content'])} bytes to {path}")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("create_directory", "Create a directory and all parent directories",
      {"dir_path": {"type": "string"}})
def create_directory(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["dir_path"], ctx)
    try: os.makedirs(path, exist_ok=True); return ToolResult(success=True, content=f"Created: {path}")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("list_directory", "List contents of a directory",
      {"dir_path": {"type": "string"}},
      {"readOnlyHint": True})
def list_directory(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["dir_path"], ctx)
    try:
        items = os.listdir(path)
        return ToolResult(success=True, content="\n".join(sorted(items))[:10000])
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("glob", "Find files matching a glob pattern",
      {"pattern": {"type": "string", "description": "Glob pattern (e.g. **/*.py)"}, "dir": {"type": "string", "description": "Root directory (optional)"}},
      {"readOnlyHint": True})
def glob(args: dict, ctx: ToolContext) -> ToolResult:
    root = _resolve(args.get("dir", ""), ctx) or ctx.workspace_path or WORKSPACE
    try:
        matches = g.glob(args["pattern"], root_dir=root, recursive=True)
        return ToolResult(success=True, content="\n".join(matches[:500])[:50000])
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("grep", "Search for text within files",
      {"pattern": {"type": "string"}, "path": {"type": "string"}, "case_sensitive": {"type": "boolean"}, "include": {"type": "string"}},
      {"readOnlyHint": True})
def grep(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["path"], ctx)
    cs = args.get("case_sensitive", True)
    pat = re.compile(args["pattern"], 0 if cs else re.I)
    matches, count = [], 0
    try:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for fn in files:
                    if args.get("include") and not fn.endswith(args["include"]): continue
                    fp = os.path.join(root, fn)
                    try:
                        with open(fp, "r", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if pat.search(line):
                                    matches.append(f"{fp}:{i}: {line.rstrip()}")
                                    count += 1
                                    if count > 500: break
                    except: pass
                if count > 500: break
        else:
            with open(path, "r", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if pat.search(line): matches.append(f"{path}:{i}: {line.rstrip()}"); count += 1
        return ToolResult(success=True, content="\n".join(matches[:500])[:50000])
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("file_info", "Get file metadata (size, modified, type)",
      {"file_path": {"type": "string"}},
      {"readOnlyHint": True})
def file_info(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["file_path"], ctx)
    try:
        s = os.stat(path)
        return ToolResult(success=True, content=f"Size: {s.st_size} bytes\nModified: {s.st_mtime}\nIs file: {os.path.isfile(path)}\nIs dir: {os.path.isdir(path)}")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("edit_file", "Make targeted edits to a file using diff/patch format",
      {"file_path": {"type": "string"}, "operations": {"type": "array", "description": "List of edit operations (replace_block, insert_after, delete_block, append_line)"}},
      {"idempotentHint": True})
def edit_file(args: dict, ctx: ToolContext) -> ToolResult:
    path = _resolve(args["file_path"], ctx)
    if not os.path.exists(path): return ToolResult(success=False, error=f"File not found: {path}")
    try:
        with open(path, "r") as f: lines = f.readlines()
        for op in args.get("operations", []):
            if op.get("type") == "replace_block" and "old_text" in op:
                idxs = [i for i, l in enumerate(lines) if op["old_text"] in l]
                if idxs: lines[idxs[0]] = op.get("new_text", op["old_text"]) + "\n"
            elif op.get("type") == "append_line": lines.append(op.get("text", "") + "\n")
        with open(path, "w") as f: f.writelines(lines)
        return ToolResult(success=True, content=f"Edits applied to {path}")
    except Exception as e: return ToolResult(success=False, error=str(e))
