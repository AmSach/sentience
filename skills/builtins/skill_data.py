#!/usr/bin/env python3
## Skill: data
## Description: Data analysis, CSV, database queries, visualization
## Triggers: analyze, data, csv, database, query, chart
## Tools: query_db, read_csv, generate_chart, statistics

import json

def execute(instruction, ctx):
    return json.dumps({"action": "data_task", "query": instruction})
