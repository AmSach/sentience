# Sentience v2.0 — Local AI Computer

**Like Cursor + Claude Code + Zo, but runs 100% on your machine.**

## Features

### 🤖 Multi-LLM Support (BYOK)
- **OpenAI** — GPT-4o, GPT-4-turbo, GPT-3.5-turbo
- **Anthropic** — Claude Sonnet, Claude Opus
- **Groq** — Llama 3.3 70B, Mixtral (FREE tier available)
- **Ollama** — Run completely offline with local models

### 🛠️ 15+ Real Tools
| Tool | What it does |
|------|--------------|
| `read_file` | Read any file (text, PDF, DOCX, images) |
| `write_file` | Create/overwrite files |
| `edit_file` | Surgical edits |
| `list_directory` | Browse folders |
| `search_files` | Find by name or content |
| `delete_file` | Remove files/folders |
| `run_command` | Execute shell commands |
| `analyze_code` | AST analysis, complexity, security |
| `git_command` | Git operations |
| `web_fetch` | HTTP requests |
| `web_search` | DuckDuckGo search |
| `remember` | Store in long-term memory |
| `recall` | Retrieve from memory |

### 💾 Persistent Storage
- SQLite database (~/.sentience/sentience.db)
- Conversations, messages, memory
- LZ4 compression for large content
- Knowledge graph for entities

### 🔧 Skills System
- Load custom Python skills
- Persistent across sessions
- Auto-registration

### ⚡ Automations
- Schedule background tasks
- Run autonomous workflows

## Quick Start

### Windows

1. **Download** `Sentience-v2.zip` from [Releases](https://github.com/AmSach/sentience/releases)
2. **Extract** to any folder
3. **Run** `install.bat` as Administrator
4. **Launch**: Open terminal and run `sentience`

Or manually:
```cmd
pip install -r requirements.txt
python cli.py
```

### Linux/Mac

```bash
pip install -r requirements.txt
python cli.py
```

## Configuration

First run will ask for your API key, or set via environment:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# Groq (FREE tier at console.groq.com)
export GROQ_API_KEY=gsk_...
```

## Usage

```
Sentience v2.0 - Local AI Computer

You: read the file src/main.py and explain what it does

Sentience: I'll read the file and analyze it...
[uses read_file tool]

You: refactor it to use async

Sentience: [uses edit_file tool]

You: commit the changes

Sentience: [uses git_command tool]
```

## Commands

| Command | Description |
|---------|-------------|
| `help` | Show all commands |
| `new` | Start new conversation |
| `list` | List conversations |
| `load <id>` | Load conversation |
| `provider` | List available providers |
| `use <p> [m]` | Switch provider/model |
| `tools` | List all tools |
| `config` | Show configuration |
| `quit` | Exit |

## Examples

### Code Analysis
```
You: analyze the code in src/api.py for security issues

Sentience: I'll analyze the code...
[uses analyze_code tool]
Found 3 security warnings:
- Line 45: Use of eval() is dangerous
- Line 78: shell=True can be dangerous
- Line 102: Pickle can execute arbitrary code
```

### File Operations
```
You: create a new React component called Dashboard in src/components/

Sentience: I'll create the file...
[uses write_file tool]
Created src/components/Dashboard.jsx
```

### Web Search
```
You: what's the latest news about AI agents?

Sentience: [uses web_search tool]
Here are the latest results:
1. "OpenAI releases new agent framework..."
2. "Anthropic announces Claude agent capabilities..."
```

## Architecture

```
sentience-v2/
├── core/
│   ├── engine.py      # Main agent loop
│   ├── config.py      # Configuration & BYOK
│   ├── memory.py      # SQLite + compression + graph
│   └── tools.py       # 15+ real tool implementations
├── cli.py             # Terminal interface
├── requirements.txt   # Dependencies
├── install.bat        # Windows installer
└── README.md
```

## vs Others

| Feature | Sentience | Cursor | Claude Code | Zo |
|---------|-----------|--------|-------------|-----|
| **100% Local** | ✅ | ❌ | ❌ | ❌ |
| **BYOK** | ✅ | ❌ | ❌ | ✅ |
| **Offline** | ✅ | ❌ | ❌ | ❌ |
| **Free Tier** | ✅ (Groq) | ❌ | ❌ | ❌ |
| **Open Source** | ✅ | ❌ | ❌ | ❌ |
| **Shell Access** | ✅ | ❌ | ✅ | ✅ |
| **Memory** | ✅ | ❌ | ❌ | ✅ |
| **Knowledge Graph** | ✅ | ❌ | ❌ | ✅ |

## Requirements

- Python 3.11+
- 4GB RAM minimum
- Internet for API calls (or use Ollama for offline)

## License

MIT

## Credits

Inspired by:
- [Zo Computer](https://zo.computer) — architecture
- [Claude Code](https://claude.ai/code) — tool calling
- [Cursor](https://cursor.sh) — coding assistant
