#!/usr/bin/env python3
## Skill: email
## Description: Email management - send, read, search, auto-reply
## Triggers: email, mail, send email, inbox, reply
## Tools: gmail_send, gmail_list, gmail_search, gmail_draft

import json

def execute(instruction, ctx):
    return json.dumps({"action": "email_task", "query": instruction})
