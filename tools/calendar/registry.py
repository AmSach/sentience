"""calendar tool registry."""
import json

def execute(cmd, args, ctx):
    return json.dumps({"tool": "calendar", "cmd": cmd, "args": args})
__all__ = ["execute"]
