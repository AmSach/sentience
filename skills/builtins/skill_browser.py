#!/usr/bin/env python3
## Skill: browser
## Description: Web surfing, browsing, form filling, scraping
## Triggers: browse, surf, scrape, fill form, website
## Tools: browser_open, browser_click, browser_type, browser_screenshot

import json

def execute(instruction, ctx):
    return json.dumps({"action": "browser_task", "query": instruction})
