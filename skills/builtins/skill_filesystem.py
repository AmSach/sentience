#!/usr/bin/env python3
## Skill: filesystem
## Description: File operations - search, read, write, organize files
## Triggers: file, folder, search, find, organize
## Tools: grep, glob, read_file, write_file, edit_file

import os, json, subprocess, re

def execute(instruction, ctx):
    instruction = instruction.lower()
    if "search" in instruction or "find" in instruction or "where" in instruction:
        return json.dumps({"action": "grep", "query": instruction})
    elif "read" in instruction or "open" in instruction:
        return json.dumps({"action": "read_file", "query": instruction})
    elif "create" in instruction or "make" in instruction or "write" in instruction:
        return json.dumps({"action": "write_file", "query": instruction})
    return json.dumps({"error": "unclear instruction"})
