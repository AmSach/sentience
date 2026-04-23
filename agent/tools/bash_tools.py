#!/usr/bin/env python3
"""Bash tools - execute shell commands."""
import subprocess, shlex
from .registry import tool, ToolContext, ToolResult

@tool("bash", "Execute a shell command and return output",
      {"command": {"type": "string", "description": "Shell command to execute"}},
      {"destructiveHint": False})
def bash(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        result = subprocess.run(args["command"], shell=True, capture_output=True, text=True, timeout=300, cwd=ctx.workspace_path)
        output = f"STDOUT:\n{result.stdout[:30000]}\n\nSTDERR:\n{result.stderr[:5000]}\n\nExit: {result.returncode}"
        return ToolResult(success=True, content=output)
    except subprocess.TimeoutExpired: return ToolResult(success=False, error="Command timed out after 300s")
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("bash_script", "Run a multi-line bash script via temp file",
      {"script": {"type": "string"}},
      {"destructiveHint": False})
def bash_script(args: dict, ctx: ToolContext) -> ToolResult:
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(args["script"]); path = f.name
        result = subprocess.run(["bash", path], capture_output=True, text=True, timeout=300, cwd=ctx.workspace_path)
        subprocess.run(["rm", "-f", path])
        return ToolResult(success=True, content=f"STDOUT:\n{result.stdout[:30000]}\n\nSTDERR:\n{result.stderr[:5000]}\n\nExit: {result.returncode}")
    except Exception as e: return ToolResult(success=False, error=str(e))
