#!/usr/bin/env python3
"""Git tools - status, commit, push, pull, branch, log, diff."""
import subprocess
from .registry import tool, ToolContext, ToolResult

WORKSPACE = "~/sentience_workspace"

def _git(args: list, cwd: str = None) -> ToolResult:
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=60, cwd=cwd)
        return ToolResult(success=True, content=f"{result.stdout}\n{result.stderr}" if result.stderr else result.stdout)
    except Exception as e: return ToolResult(success=False, error=str(e))

@tool("git_status", "Show working tree status", {"dir": {"type": "string"}}, {"readOnlyHint": True})
def git_status(args: dict, ctx: ToolContext): return _git(["status", "--porcelain"], cwd=args.get("dir"))

@tool("git_log", "Show recent commit history",
      {"dir": {"type": "string"}, "num": {"type": "integer"}}, {"readOnlyHint": True})
def git_log(args: dict, ctx: ToolContext): return _git(["log", f"-{args.get('num', 10)}", "--oneline", "--graph", "--decorate"], cwd=args.get("dir"))

@tool("git_diff", "Show unstaged changes",
      {"dir": {"type": "string"}, "file": {"type": "string"}}, {"readOnlyHint": True})
def git_diff(args: dict, ctx: ToolContext): return _git(["diff"] + ([args["file"]] if args.get("file") else []), cwd=args.get("dir"))

@tool("git_branch", "List all branches, current highlighted",
      {"dir": {"type": "string"}}, {"readOnlyHint": True})
def git_branch(args: dict, ctx: ToolContext): return _git(["branch", "-a", "-vv"], cwd=args.get("dir"))

@tool("git_commit", "Commit staged changes with message",
      {"message": {"type": "string"}, "dir": {"type": "string"}}, {"destructiveHint": False})
def git_commit(args: dict, ctx: ToolContext): return _git(["commit", "-m", args["message"]], cwd=args.get("dir"))

@tool("git_push", "Push commits to remote",
      {"remote": {"type": "string"}, "branch": {"type": "string"}, "dir": {"type": "string"}}, {})
def git_push(args: dict, ctx: ToolContext): return _git(["push"] + ([args["remote"]] if args.get("remote") else []) + ([args["branch"]] if args.get("branch") else []), cwd=args.get("dir"))

@tool("git_pull", "Pull from remote",
      {"remote": {"type": "string"}, "branch": {"type": "string"}, "dir": {"type": "string"}}, {})
def git_pull(args: dict, ctx: ToolContext): return _git(["pull"] + ([args["remote"]] if args.get("remote") else []) + ([args["branch"]] if args.get("branch") else []), cwd=args.get("dir"))

@tool("git_stage", "Stage files for commit",
      {"files": {"type": "array", "items": {"type": "string"}}, "dir": {"type": "string"}}, {})
def git_stage(args: dict, ctx: ToolContext): return _git(["add"] + (args.get("files", ["."])), cwd=args.get("dir"))

@tool("git_stash", "Stash/unstash working changes",
      {"action": {"type": "string", "description": "stash, stash pop, or stash drop"}, "dir": {"type": "string"}}, {})
def git_stash(args: dict, ctx: ToolContext): return _git([args.get("action", "stash")], cwd=args.get("dir"))
