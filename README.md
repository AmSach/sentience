# Sentience v4.0 — Local AI Computer

**Like Zo + Cursor + Jarvis — Runs 100% Locally**

## Features

### Core
- **BYOK System**: OpenAI, Anthropic, Groq, Ollama
- **Memory System**: SQLite + LZ4 compression
- **Knowledge Graph**: Obsidian-like vault with wikilinks
- **RAG Engine**: Hybrid search (vector + BM25)
- **16+ Tools**: Files, shell, web, code, memory

### RAG (Retrieval Augmented Generation)
- Chunking with overlap
- Vector embeddings (sentence-transformers)
- BM25 keyword search
- Hybrid search combining both
- SQLite or ChromaDB storage

### Memory
- Compressed storage (LZ4 or zlib)
- Knowledge graph with edges
- Conversation persistence
- Markdown vault files

## Install

### Quick Start (Windows)
```cmd
pip install -r requirements.txt
python sentience.py
```

### Quick Start (Linux/Mac)
```bash
pip install -r requirements.txt
python3 sentience.py
```

### With Ollama (100% Local)
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.2

# Run Sentience
OLLAMA_HOST=http://localhost:11434 python3 sentience.py
```

### With Groq (Free Cloud)
1. Get free API key at https://console.groq.com
2. Set environment: `set GROQ_API_KEY=gsk_...` (Windows) or `export GROQ_API_KEY=gsk_...` (Linux/Mac)
3. Run `python sentience.py`

## Usage

### CLI Mode
```bash
python sentience.py --cli
```

### Index Files for RAG
```bash
python sentience.py --index ./my-docs
```

## API Keys

| Provider | Get Key | Env Variable |
|----------|---------|--------------|
| Groq (free) | console.groq.com | GROQ_API_KEY |
| OpenAI | platform.openai.com | OPENAI_API_KEY |
| Anthropic | console.anthropic.com | ANTHROPIC_API_KEY |
| Ollama | localhost | OLLAMA_HOST |

## Tools Available

| Tool | Description |
|------|-------------|
| read_file | Read file contents |
| write_file | Write to file |
| edit_file | Replace text in file |
| list_directory | List dir contents |
| delete_file | Delete file |
| create_directory | Create directory |
| search_files | Search by name/content |
| execute_command | Run shell command |
| http_request | Make HTTP request |
| web_search | DuckDuckGo search |
| analyze_code | Analyze code for issues |
| store_memory | Store long-term memory |
| retrieve_memory | Get stored memory |
| search_memory | Search memories |
| get_system_info | System stats |
| get_current_time | Date/time |

## File Structure

```
sentience-v4/
├── src/
│   ├── core/
│   │   ├── config.py      # BYOK configuration
│   │   ├── memory.py      # SQLite + compression
│   │   ├── tools.py       # Tool registry (16+ tools)
│   │   └── engine.py      # Main AI engine
│   └── rag/
│       └── engine.py      # RAG system
├── data/
│   ├── vault/             # Obsidian-like notes
│   └── models/            # Local models
├── requirements.txt
└── sentience.py           # Entry point
```

## What's Different from Zo

| Feature | Zo | Sentience |
|---------|-----|-----------|
| Runs locally | ❌ | ✅ |
| BYOK | ❌ | ✅ |
| Obsidian vault | ❌ | ✅ |
| RAG built-in | ❌ | ✅ |
| Knowledge graph | ❌ | ✅ |
| Cloud dependency | ✅ | ❌ |

## Roadmap

- [ ] Full GUI (PySide6)
- [ ] Browser automation (Playwright)
- [ ] Email integration
- [ ] OAuth for services
- [ ] Voice control
- [ ] Skills system
- [ ] Hosting server

## License

MIT

## Credits

Inspired by:
- Zo Computer (zo.computer)
- Cursor (cursor.sh)
- OpenAI/Claude Code
- Obsidian (obsidian.md)
- UltraRAG, RagClaw (GitHub)
- JARVIS-desktop, OpenJarvis (GitHub)
