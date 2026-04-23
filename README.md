# Sentience - Local AI Computer

**A real desktop application like Cursor/Zo for local AI assistance.**

## Features

### 🖥️ Desktop GUI
- File browser (tree view)
- Code editor with syntax highlighting
- AI chat panel
- Terminal output
- Settings dialog

### 🤖 AI Capabilities
- BYOK (Bring Your Own Key)
- Supports: Groq (free), OpenAI, Anthropic, Ollama
- Tool execution (read/write files, run commands)
- Conversation memory

### 🛠️ Tools
- `read_file` - Read any file
- `write_file` - Write/create files
- `list_directory` - Browse directories
- `run_command` - Execute shell commands
- `search_files` - Find files by pattern

## Install

### Windows
```cmd
install.bat
```

### Linux/Mac
```bash
chmod +x install.sh
./install.sh
```

## Run

### Windows
```cmd
run.bat
```

Or manually:
```cmd
venv\Scripts\activate
set GROQ_API_KEY=gsk_your_key_here
python src\main.py
```

### Linux/Mac
```bash
source venv/bin/activate
export GROQ_API_KEY=gsk_your_key_here
python src/main.py
```

## 100% Local (Ollama)

1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama3.2`
3. Run with: `OLLAMA_HOST=http://localhost:11434 python src/main.py`

## Get Free API Key

- **Groq** (recommended, free tier): https://console.groq.com
- **OpenAI**: https://platform.openai.com
- **Anthropic**: https://console.anthropic.com

## Usage

1. Open the app
2. Go to File → Settings
3. Select provider and enter API key
4. Set your workspace directory
5. Chat with the AI to:
   - Edit files
   - Run commands
   - Search code
   - Get help

## Requirements

- Python 3.10+
- Internet connection (for API providers)
- Or Ollama for 100% local

## License

MIT

---

**Now you have a real desktop application!**
