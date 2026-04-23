# Sentience — Local AI Computer

**Double-click `Sentience.exe` → Full AI computer on your desktop.**

## What's Built

- **127MB standalone .exe** — no Python, no pip, no install needed
- **Desktop GUI** — chat, file browser, code editor, terminal
- **Web UI** — http://localhost:3132  
- **40+ AI tools** — file operations, bash, git, web search, browser automation
- **BYOK** — Anthropic, OpenAI, Groq, or local Ollama
- **Memory** — Obsidian-like vault with backlinks, entity graph, semantic search
- **Compression** — LZ4 real-time context compression
- **Integrations** — Gmail, Notion, Spotify, Calendar, Drive, Dropbox, Linear

## Quick Start

1. Unzip Sentience-Full-Setup.zip
2. Double-click `Sentience.exe`
3. In the app, click **BYOK Setup** (bottom left)
4. Paste your Anthropic API key
5. Start chatting!

## Configure API Keys

**Option A — In-app (easiest):**
- Click "BYOK Setup" button
- Select provider (Anthropic/OpenAI/Groq)
- Paste your API key

**Option B — Environment file:**
```bash
# Create .env in the Sentience folder
ANTHROPIC_API_KEY=sk-ant-your-key
OPENAI_API_KEY=sk-your-key
```

**Option C — Set directly:**
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key
./Sentience
```

## Using Local Models (Fully Offline)

1. Install [Ollama](https://ollama.ai/)
2. Pull a model: `ollama pull llama3`
3. In Sentience, set provider to "ollama"
4. All AI runs locally, no internet needed

## Features In Depth

### Chat Interface
- Conversation history (saved automatically)
- File operations (read, write, edit, search)
- Run shell commands
- Git operations (commit, push, pull, branch)
- Web search and browsing
- Code writing and execution

### Memory System
- **Short-term**: Remembers current conversation
- **Long-term**: Saved across sessions in `~/.Sentience/`
- **Vault**: Obsidian-like markdown notes with `[[backlinks]]`
- **Graph**: Entity relationships (people, places, topics)
- **Semantic Search**: Find anything by meaning, not just keywords

### Compression Engine
Automatically compresses context to fit more in the AI window:
- LZ4: 5GB/s compression, 50GB/s decompression
- Delta encoding for file versions
- RLE for repetitive patterns
- Semantic deduplication

### Browser Automation
Sentience can control a real browser:
- Navigate to any URL
- Click buttons, fill forms
- Screenshot pages
- Extract data from web pages

## Keyboard Shortcuts

- `Ctrl+Enter` — Send message
- `Ctrl+N` — New conversation
- `Ctrl+F` — Search files
- `Ctrl+,` — Settings

## File Locations

- Database: `~/.Sentience/sentience.db`
- Vault: `~/.Sentience/vault/`
- Logs: `~/.Sentience/logs/`
- Config: `~/.Sentience/config.json`

## Troubleshooting

**"ANTHROPIC_API_KEY not set"**
→ Click BYOK Setup and add your key

**Browser doesn't open**
→ Install Chromium: `playwright install chromium`

**Slow responses**
→ Switch to a faster model or use Groq (free tier)

**Out of memory**
→ Use a smaller model or reduce context window

## Tech Stack

- PyInstaller (standalone binary)
- PySide6 (Qt desktop UI)
- SQLite (local database)
- LZ4 (compression)
- Playwright (browser automation)
- Anthropic/OpenAI/Groq SDKs
