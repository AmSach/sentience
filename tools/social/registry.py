"""social tool registry."""
import json

def execute(cmd, args, ctx):
    return json.dumps({"tool": "social", "cmd": cmd, "args": args})
__all__ = ["execute"]
