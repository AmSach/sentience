#!/usr/bin/env python3
## Skill: code
## Description: Code writing, debugging, review, and deployment
## Triggers: code, debug, fix, write, refactor, deploy, build
## Tools: write_code, run_command, git_commit, test, lint

import json

def execute(instruction, ctx):
    return json.dumps({"action": "code_task", "query": instruction})
