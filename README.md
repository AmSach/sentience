# Sentience — Local AI Computer

**Like Zo + Claude Code, but 100% on your machine.**

## Quick Start (Windows)

### Option 1: With Python installed
1. Install Python 3.11+ from [python.org](https://python.org) — **Check "Add Python to PATH" during install!**
2. Download `Sentience-Windows-Setup.zip` from [Releases](https://github.com/AmSach/sentience/releases)
3. Extract to any folder (e.g., `C:\Sentience`)
4. Run `install-windows.bat` as Administrator
5. Launch via Desktop shortcut or `run.bat`

### Option 2: Direct run (if Python already installed)
```cmd
pip install flask flask-cors anthropic openai groq python-dotenv pyyaml pyside6 playwright pypdf reportlab python-docx openpyxl lz4 requests
playwright install chromium
python sentience_app.py
```

## Features

### BYOK (Bring Your Own Keys)
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude 3.5 Sonnet, Claude Opus)
- Groq (Llama 3.3 70B, Mixtral)
- Local models (Ollama support)

### Tools (40+ built-in)
- **Filesystem**: read_file, write_file, list_dir, search_files, delete_file
- **Shell**: run_command, execute_code
- **Web**: fetch_url, web_search, browse (Playwright)
- **Memory**: remember, recall, list_memory
- **Code**: analyze_code, execute_python
- **Analysis**: PDF, DOCX, XLSX parsing
- **Integrations**: Gmail, Notion, Calendar, Spotify, Drive, Dropbox, Linear

### Local Storage
- SQLite database (~/.sentience/sentience.db)
- Conversations, messages, memory, automations
- API keys encrypted locally

### UI Modes
- **GUI**: Desktop window with PySide6
- **CLI**: Terminal mode (use `--cli` flag)
- **Web**: Browser UI at http://127.0.0.1:3131

### Automation
- Scheduled tasks
- Background job processing
- Self-improving agent capabilities

## Architecture

```
sentience/
├── sentience_app.py      # Main entry point
├── storage/
│   └── db.py             # SQLite database
├── agent/
│   ├── engine.py         # Agent loop
│   └── tools/            # Tool implementations
├── integrations/         # Gmail, Notion, etc.
├── memory/               # Obsidian-like memory
├── forms/                # Form filling
├── analysis/             # Document analysis
├── research/             # Web research
├── hosting/              # Local web server
├── browser/              # Playwright automation
├── email/                # Email listener
├── remote/               # SSH/SFTP
├── cloud/                # Cloud sync
├── skills/               # Skill registry
├── automation/           # Task scheduler
├── ui/
│   └── index.html        # Web UI
├── install-windows.bat   # Windows installer
├── run.bat               # CLI launcher
└── run-ui.bat            # GUI launcher
```

## First Time Setup

1. **Launch Sentience**
2. **Go to Settings → BYOK Keys**
3. **Add your API keys**:
   - OpenAI: `sk-...` (GPT-4 access)
   - Anthropic: `sk-ant-...` (Claude access)
   - Groq: `gsk_...` (Free tier available)
4. **Start chatting!**

## Troubleshooting

### "Python not found"
- Install Python 3.11+ from python.org
- Make sure to check "Add Python to PATH"

### "Module not found"
```cmd
pip install -r requirements.txt
```

### "Playwright not working"
```cmd
playwright install chromium
```

### GUI doesn't open
- Run `run.bat` for CLI mode
- Or check if PySide6 is installed: `pip install pyside6`

## Comparison

| Feature | Zo | Claude Code | Sentience |
|---------|-----|-------------|-----------|
| Local execution | ❌ | ✅ | ✅ |
| BYOK | ❌ | ✅ | ✅ |
| Local memory | ❌ | ❌ | ✅ |
| GUI | ✅ | ❌ | ✅ |
| CLI | ❌ | ✅ | ✅ |
| Self-hosted | ❌ | ❌ | ✅ |
| Free tier | ❌ | ❌ | ✅ (BYOK) |
| Works offline | ❌ | ❌ | ✅ (with local model) |

## License

MIT — Use it, fork it, improve it.

---

Built with ❤️ for local-first AI computing.
