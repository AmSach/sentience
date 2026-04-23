"""cloud tool registry."""
import json

def execute(cmd, args, ctx):
    return json.dumps({"tool": "cloud", "cmd": cmd, "args": args})
__all__ = ["execute"]
