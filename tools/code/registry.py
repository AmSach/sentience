"""code tool registry."""
import json

def execute(cmd, args, ctx):
    return json.dumps({"tool": "code", "cmd": cmd, "args": args})
__all__ = ["execute"]
