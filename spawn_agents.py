#!/usr/bin/env python3
"""
Spawn multiple parallel agents to build Sentience components
Each agent works independently on their assigned module
"""
import os
import sys
import json
import time
import concurrent.futures
import requests

API_URL = "https://api.zo.computer/zo/ask"
TOKEN = os.environ.get("ZO_CLIENT_IDENTITY_TOKEN", "")
MODEL = "vercel:zai/glm-5"

def call_agent(prompt: str, agent_name: str) -> dict:
    """Call a single agent"""
    try:
        resp = requests.post(
            API_URL,
            headers={
                "authorization": TOKEN,
                "content-type": "application/json"
            },
            json={
                "input": prompt,
                "model_name": MODEL
            },
            timeout=300
        )
        return {
            "agent": agent_name,
            "status": "success" if resp.ok else "error",
            "output": resp.json().get("output", "") if resp.ok else resp.text
        }
    except Exception as e:
        return {"agent": agent_name, "status": "error", "output": str(e)}

# Agent prompts - each gets a self-contained task
AGENTS = {
    "gui": """
Build a complete PySide6 GUI for Sentience - a local AI computer like Cursor/Zo.

Create file: /home/workspace/sentience-v2/gui/app.py

Requirements:
1. Main window with:
   - Chat panel (left) - conversation with AI
   - Code editor panel (center) - syntax highlighted
   - File tree panel (right) - workspace browser
   - Terminal panel (bottom) - command output

2. Features:
   - Tab system for multiple files
   - Syntax highlighting (use QSyntaxHighlighter)
   - Splitter panels (resizable)
   - Dark theme (use QDarkStyle or custom)
   - Status bar with model info

3. Menu bar:
   - File: New, Open, Save, Settings
   - Edit: Undo, Redo, Find
   - View: Toggle panels
   - Tools: Run code, Format

4. Settings dialog:
   - API key inputs (OpenAI, Anthropic, Groq)
   - Model selection dropdown
   - Workspace path

5. Must be importable and runnable:
   if __name__ == "__main__":
       app = QApplication(sys.argv)
       window = SentienceWindow()
       window.show()
       sys.exit(app.exec())

Write complete working code - no stubs, no placeholders.
""",

    "lsp": """
Build a Language Server Protocol (LSP) client for Sentience code completion.

Create files:
- /home/workspace/sentience-v2/lsp/client.py
- /home/workspace/sentience-v2/lsp/completion.py

Requirements:
1. LSP Client that can:
   - Connect to local LSP servers (pyright, rust-analyzer, etc.)
   - Send didOpen, didChange, didClose notifications
   - Request completion (textDocument/completion)
   - Handle completion responses

2. Completion Engine:
   - Async completion provider
   - Caching of completions
   - Fuzzy matching
   - Documentation popups

3. Integration with PySide6:
   - QCompleter-compatible output
   - Real-time suggestions as user types
   - Trigger characters (., ::, etc.)

4. Fallback when no LSP:
   - Simple autocomplete from:
     - File content
     - Python builtins
     - Common patterns

Write complete working code.
""",

    "integrations": """
Build OAuth integrations for Gmail, Notion, Google Calendar, Spotify, Linear, GitHub.

Create files:
- /home/workspace/sentience-v2/integrations/oauth.py
- /home/workspace/sentience-v2/integrations/gmail.py
- /home/workspace/sentience-v2/integrations/notion.py
- /home/workspace/sentience-v2/integrations/calendar.py
- /home/workspace/sentience-v2/integrations/spotify.py
- /home/workspace/sentience-v2/integrations/linear.py
- /home/workspace/sentience-v2/integrations/github.py

Requirements:
1. OAuth base class:
   - Device flow for CLI apps
   - Token storage (SQLite)
   - Auto refresh
   - Multi-account support

2. Each integration must have:
   - authenticate() - get tokens
   - list_items() - list emails/tasks/etc
   - create_item() - create new
   - search() - search items
   - Proper error handling

3. Gmail:
   - List emails (inbox, sent, drafts)
   - Send email
   - Search
   - Create draft

4. Notion:
   - List pages
   - Create page
   - Search
   - Append to page

5. Google Calendar:
   - List events
   - Create event
   - Quick add

6. Spotify:
   - Search tracks
   - Play/pause (via API)
   - Create playlist

7. Linear/GitHub:
   - List issues
   - Create issue
   - Comment

Write complete working code with proper OAuth flows.
""",

    "hosting": """
Build local hosting infrastructure like Zo Space.

Create files:
- /home/workspace/sentience-v2/hosting/server.py
- /home/workspace/sentience-v2/hosting/domains.py
- /home/workspace/sentience-v2/hosting/sites.py
- /home/workspace/sentience-v2/hosting/routes.py

Requirements:
1. Local HTTP Server:
   - Flask/FastAPI backend
   - Serve static files
   - SPA routing support
   - Hot reload in dev mode

2. Site Management:
   - Create site from template
   - Deploy to local port
   - List running sites
   - Stop/start sites

3. Custom Domains:
   - Edit /etc/hosts (local DNS)
   - Port-based routing
   - SSL with self-signed certs
   - Domain -> port mapping

4. Routes API:
   - Dynamic routes (like Zo Space)
   - API routes (return JSON)
   - Page routes (serve HTML)
   - Middleware support

5. Templates:
   - blank (empty)
   - blog (markdown-based)
   - dashboard (React/Vue)
   - api (FastAPI)

6. Must work without internet:
   - All templates local
   - Self-contained
   - Works offline

Write complete working code.
""",

    "automations": """
Build a full automation scheduler with rrule support.

Create files:
- /home/workspace/sentience-v2/automations/scheduler.py
- /home/workspace/sentience-v2/automations/parser.py
- /home/workspace/sentience-v2/automations/executor.py

Requirements:
1. Scheduler:
   - Parse rrule strings (RFC 5545)
   - Calculate next run times
   - Background thread execution
   - SQLite persistence
   - Handle timezone (Asia/Calcutta)

2. Automation Types:
   - scheduled (run at times)
   - triggered (run on event)
   - recurring (repeat interval)

3. Executor:
   - Run Python scripts
   - Run shell commands
   - Call APIs
   - Chain multiple actions
   - Error handling + retry
   - Logging to file

4. Built-in automations:
   - morning_briefing - summarize news
   - daily_backup - backup workspace
   - weekly_report - generate report
   - file_watch - watch for changes

5. Management:
   - create_automation(name, rrule, action)
   - list_automations()
   - enable/disable
   - delete
   - run_now()

Write complete working code using dateutil.rrule.
""",

    "skills": """
Build 70+ skills system like Zo's skill marketplace.

Create files:
- /home/workspace/sentience-v2/skills/registry.py
- /home/workspace/sentience-v2/skills/loader.py
- /home/workspace/sentience-v2/skills/builtin/*.py (70 files)

Requirements:
1. Skill Registry:
   - Load from ~/.sentience/skills/
   - Hot reload on change
   - Dependency resolution
   - Version checking

2. Skill Format (SKILL.md):
   ```markdown
   ---
   name: skill-name
   description: What it does
   triggers: [keywords]
   ---
   # Instructions
   ...
   ```

3. Built-in Skills (create these):
   - debugging-wizard
   - code-reviewer
   - fastapi-expert
   - django-expert
   - react-expert
   - vue-expert
   - angular-architect
   - nextjs-developer
   - typescript-pro
   - python-pro
   - golang-pro
   - rust-expert
   - cpp-pro
   - java-architect
   - spring-boot-engineer
   - dotnet-core-expert
   - database-optimizer
   - test-master
   - devops-engineer
   - cli-developer
   - code-documenter
   - architecture-designer
   - api-designer
   - security-reviewer
   - chaos-engineer
   - mcp-builder
   - embedded-systems
   - cloud-architect
   - feature-forge
   - sentiment-analyzer
   - data-scientist
   - ml-engineer
   - nlp-specialist
   - computer-vision
   - reinforcement-learning
   - time-series-analyst
   - bayesian-modeler
   - geospatial-analyst
   - network-analyst
   - graph-theorist
   - optimization-expert
   - game-theorist
   - crypto-economist
   - blockchain-developer
   - smart-contract-auditor
   - defi-architect
   - web3-developer
   - mobile-developer
   - flutter-expert
   - react-native-expert
   - ios-developer
   - android-developer
   - desktop-developer
   - electron-expert
   - tauri-expert
   - game-developer
   - unity-expert
   - unreal-expert
   - godot-expert
   - ar-vr-developer
   - iot-specialist
   - robotics-engineer
   - drone-developer
   - cad-engineer
   - 3d-artist
   - animation-expert
   - video-editor
   - audio-engineer
   - music-producer
   - writer-assistant
   - translator
   - tutor
   - career-coach
   - health-advisor
   - fitness-trainer
   - nutritionist
   - meditation-guide

4. Each skill must:
   - Have proper SKILL.md
   - Reference scripts/ if needed
   - Be loadable dynamically
   - Execute when triggered

Write all 70 SKILL.md files with real content.
""",

    "browser": """
Build browser automation with Playwright and auth support.

Create files:
- /home/workspace/sentience-v2/browser/engine.py
- /home/workspace/sentience-v2/browser/auth.py
- /home/workspace/sentience-v2/browser/actions.py
- /home/workspace/sentience-v2/browser/session.py

Requirements:
1. Browser Engine:
   - Playwright async context
   - Headless/headful mode
   - Multi-browser (chromium, firefox, webkit)
   - Screenshot capture
   - PDF generation

2. Authentication:
   - Store cookies in SQLite
   - Restore sessions
   - Handle logins
   - 2FA support (prompt user)

3. Actions:
   - navigate(url)
   - click(selector)
   - fill(selector, text)
   - select(selector, value)
   - scroll(direction)
   - wait(selector)
   - screenshot(path)
   - extract(selector)
   - evaluate(js_code)

4. Session Management:
   - Named sessions (gmail, notion, etc.)
   - Auto-save cookies
   - Auto-restore cookies
   - Clear session

5. Integration with agent:
   - Tool interface for AI
   - Return markdown from pages
   - Handle errors gracefully

Write complete working code.
""",

    "forms": """
Build PDF/DOCX form filling engine.

Create files:
- /home/workspace/sentience-v2/forms/pdf_filler.py
- /home/workspace/sentience-v2/forms/docx_filler.py
- /home/workspace/sentience-v2/forms/ocr.py
- /home/workspace/sentience-v2/forms/extractor.py

Requirements:
1. PDF Filler:
   - Fill AcroForm fields
   - Flatten PDF after fill
   - Handle checkboxes
   - Handle dropdowns
   - Digital signatures (basic)

2. DOCX Filler:
   - Find {{placeholder}} patterns
   - Replace with values
   - Handle tables
   - Handle images
   - Handle formatting

3. OCR Engine:
   - Extract text from scanned PDFs
   - Use pytesseract
   - Field detection
   - Label extraction

4. Field Extractor:
   - Auto-detect fields
   - Map labels to fields
   - Generate field map
   - Validate required fields

5. High-level API:
   - fill_form(pdf_path, data)
   - auto_fill(pdf_path, user_info)
   - extract_fields(pdf_path)

Write complete working code.
""",

    "learning": """
Build self-improvement and learning system.

Create files:
- /home/workspace/sentience-v2/learning/engine.py
- /home/workspace/sentience-v2/learning/patterns.py
- /home/workspace/sentience-v2/learning/preferences.py
- /home/workspace/sentience-v2/learning/feedback.py

Requirements:
1. Learning Engine:
   - Track user interactions
   - Identify patterns
   - Store learned behaviors
   - Apply learned preferences

2. Pattern Recognition:
   - Track commands used
   - Track files edited
   - Track time of day
   - Track project types
   - Predict next actions

3. Preferences:
   - Code style preferences
   - Naming conventions
   - Project structure
   - Editor settings
   - Tool preferences

4. Feedback System:
   - Positive/negative feedback
   - Implicit feedback (undo, retry)
   - Explicit feedback (thumbs up/down)
   - Weight by recency

5. Self-Improvement:
   - Analyze past mistakes
   - Generate better prompts
   - Suggest optimizations
   - Update skill prompts

Write complete working code.
""",

    "context": """
Build project-wide context engine like Cursor.

Create files:
- /home/workspace/sentience-v2/context/project.py
- /home/workspace/sentience-v2/context/indexer.py
- /home/workspace/sentience-v2/context/embeddings.py
- /home/workspace/sentience-v2/context/retriever.py

Requirements:
1. Project Analyzer:
   - Detect project type (Python, JS, Rust, etc.)
   - Find entry points
   - Map dependencies
   - Identify config files

2. Code Indexer:
   - Parse all source files
   - Extract symbols (classes, functions, vars)
   - Build call graph
   - Track imports/exports

3. Embeddings:
   - Use sentence-transformers (local)
   - Index code snippets
   - Index documentation
   - Index comments
   - Store in SQLite with vector search

4. Retriever:
   - Semantic search across project
   - Find relevant code for query
   - Build context window
   - Prioritize by relevance

5. Integration:
   - Auto-index on file change
   - Incremental updates
   - Cache embeddings
   - Context for code completion

Write complete working code using chromadb or sqlite-vss.
"""
}

def main():
    print(f"Spawning {len(AGENTS)} parallel agents...")
    print(f"Model: {MODEL}")
    print("-" * 50)
    
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(call_agent, prompt, name): name
            for name, prompt in AGENTS.items()
        }
        
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results.append(result)
                status = "✓" if result["status"] == "success" else "✗"
                print(f"{status} {name}: {result['output'][:100]}...")
            except Exception as e:
                results.append({"agent": name, "status": "error", "output": str(e)})
                print(f"✗ {name}: {e}")
    
    print("-" * 50)
    print(f"Completed: {len([r for r in results if r['status']=='success'])}/{len(results)}")
    
    # Save results
    with open("/home/workspace/sentience-v2/agent_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return results

if __name__ == "__main__":
    main()
