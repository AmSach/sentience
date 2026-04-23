# Sentience v3.0 — Local AI Computer

**The most advanced local AI assistant. Like Cursor + Zo + Jarvis combined.**

## Features

### 🖥️ Full IDE Workspace
- Multi-tab code editor with syntax highlighting
- File explorer, search panel, git integration
- Embedded terminal
- AI chat panel
- Problems and output panels

### 🤖 AI Capabilities
- **BYOK** (Bring Your Own Key) - OpenAI, Anthropic, Groq, Ollama
- **Local models** - Works offline with Ollama
- **Code completion** - LSP integration for Python, TypeScript, Go, Rust
- **Code analysis** - Complexity, security, patterns
- **Test generation** - Auto-generate unit tests
- **Documentation** - Auto-generate docs

### 🔧 70+ Built-in Skills
- Code analysis and security scanning
- Dependency checking
- Test generation
- Documentation generation
- Refactoring
- CSV/JSON/XML processing
- Web scraping
- API calls
- Email integration
- Slack integration
- Process management
- Backup automation

### 🔌 Integrations
- **Gmail** - Read, send, search emails
- **Notion** - Create pages, search
- **Google Calendar** - Create events, check schedule
- **Slack** - Send messages, manage channels
- **GitHub** - Repos, PRs, Issues
- **Spotify** - Playback control
- **Linear** - Issue management

### 🌐 Hosting
- Local web server (FastAPI)
- Custom domains
- SSL certificates
- Ngrok tunnels
- Static sites

### ⏰ Automations
- APScheduler-based scheduler
- Cron, interval, date triggers
- Webhook triggers
- Persistent job storage
- Execution history

### 🌐 Browser Automation
- Playwright-based
- Auth persistence
- Form filling
- Content extraction
- Screenshots

### 📄 Form Filling
- PDF form detection and filling
- DOCX template filling
- Mail merge
- Auto-fill from reference

### 🧠 Memory & Learning
- Obsidian-like vault
- Knowledge graph
- Learning system
- Interaction logging
- Preference learning

### 📊 Context Awareness
- Project structure analysis
- Symbol indexing
- Reference tracking
- LSP integration
- Smart context windows

## Installation

### Quick Install (Windows)

1. Download `Sentience-Setup.exe`
2. Run the installer
3. Set your API key:

```bash
set OPENAI_API_KEY=sk-...
# or
set GROQ_API_KEY=gsk_...
# or
set ANTHROPIC_API_KEY=sk-ant-...
```

4. Run Sentience:
```bash
sentience
```

### Manual Install (All platforms)

```bash
# Clone
git clone https://github.com/AmSach/sentience.git
cd sentience

# Install
pip install -r requirements.txt

# Run CLI
python sentience.py --cli

# Run GUI
python sentience.py --gui
```

### With Local Models (Ollama)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3

# Run Sentience
python sentience.py --provider ollama --model llama3
```

## Usage

### CLI Mode

```
Sentience v3.0 - Local AI Computer
==================================

You: Analyze the code in src/main.py

Sentience: I'll analyze that file...

You: Create a test for the parse function

Sentience: Generated test file test_parse.py...

You: Schedule a daily backup

Sentience: Created automation "Daily Backup" - runs at 9 AM

You: Fill out this PDF form with my info

Sentience: Detected 15 fields, filled with your profile data...
```

### GUI Mode

Launch with `sentience --gui` or run the executable.

Full IDE with:
- Code editor (tabs, syntax highlighting)
- AI chat panel
- Terminal
- File explorer
- Git integration

## Configuration

Config stored in `~/.sentience/config.json`:

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "api_key": "...",
  "workspace": "/path/to/workspace"
}
```

## Tools Available

| Category | Tools |
|----------|-------|
| Files | read_file, write_file, list_dir, search_files |
| Code | analyze_code, generate_tests, generate_docs, refactor |
| Web | browse, search_web, scrape, api_call |
| Memory | remember, recall, create_note, search_notes |
| Forms | fill_form, detect_fields, fill_pdf, fill_docx |
| Integrations | send_email, search_notion, create_event, slack_message |
| Automations | schedule_task, list_automations, run_automation |
| Hosting | create_site, deploy_site, create_api |
| Shell | run_command, run_script |

## Skills

70+ skills organized by category:

- **Analysis**: code-analyzer, security-scanner, dependency-checker, performance-profiler
- **Development**: code-generator, test-generator, doc-generator, refactor-engine
- **Data**: csv-processor, json-handler, xml-parser, yaml-manager
- **Web**: scraper, api-client, graphql-client, oauth-flow
- **File**: file-organizer, duplicate-finder, batch-renamer, archive-manager
- **System**: process-manager, service-monitor, log-analyzer, backup-tool
- **Communication**: email-skill, slack-skill, discord-skill, telegram-skill

## Comparison

| Feature | Sentience | Cursor | Zo | Claude Code |
|---------|-----------|--------|-----|-------------|
| Local Models | ✅ | ❌ | ❌ | ❌ |
| BYOK | ✅ | ✅ | ❌ | ❌ |
| Offline | ✅ | ❌ | ❌ | ❌ |
| Skills System | ✅ 70+ | ❌ | ✅ 70+ | ❌ |
| Hosting | ✅ | ❌ | ✅ | ❌ |
| Automations | ✅ | ❌ | ✅ | ❌ |
| Integrations | ✅ 10+ | ❌ | ✅ 10+ | ❌ |
| Browser | ✅ | ❌ | ✅ | ❌ |
| Form Filling | ✅ | ❌ | ✅ | ❌ |
| Learning | ✅ | ❌ | ❌ | ❌ |
| Open Source | ✅ | ❌ | ❌ | ❌ |

## Development

```bash
# Test
python -m pytest tests/

# Build
pyinstaller sentience.py --onefile --windowed

# Create release
python scripts/build_release.py
```

## License

MIT

## Contributing

PRs welcome! See CONTRIBUTING.md.

## Credits

Built with:
- PySide6 (Qt)
- FastAPI
- APScheduler
- Playwright
- pypdf & python-docx
- OpenAI/Anthropic/Groq APIs

---

**Made with ❤️ by the Sentience team**
