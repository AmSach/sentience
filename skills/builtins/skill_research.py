#!/usr/bin/env python3
## Skill: research
## Description: Deep research on any topic - web search, summarize, fact-check
## Triggers: research, search, investigate, look up, find information
## Tools: web_search, read_webpage, summarize, fact_check

import json

def execute(instruction, ctx):
    return json.dumps({"action": "research", "query": instruction, "depth": "deep"})
