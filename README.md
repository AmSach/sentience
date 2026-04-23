# Sentience - Local AI Computer

A complete desktop application like Cursor/Zo for local AI assistance.

## Features

| Module | Tools | Description |
|--------|-------|-------------|
| **Core** | 6 | File ops, shell commands |
| **Browser** | 5 | Playwright automation |
| **Email** | 3 | IMAP read, SMTP send |
| **OAuth** | 3 | Google, GitHub, Notion, Linear |
| **Voice** | 3 | Speech recognition, TTS |
| **Skills** | 3 | Modular skill system |
| **Hosting** | 4 | Local web server |
| **Total** | **27** | AI tools available |

## Install

### Windows
```cmd
pip install PySide6 playwright aiohttp SpeechRecognition pyttsx3
playwright install chromium
python src/main.py
```

### Linux/Mac
```bash
pip install -r requirements.txt
playwright install chromium
python src/main.py
```

### 100% Local Mode
```bash
ollama pull llama3.2
OLLAMA_HOST=http://localhost:11434 python src/main.py
```

## BYOK (Bring Your Own Key)

Set environment variable for your provider:
```bash
export GROQ_API_KEY=your_key        # Groq (free tier)
export OPENAI_API_KEY=your_key      # OpenAI
export ANTHROPIC_API_KEY=your_key   # Claude
# Ollama requires no key
```

## GUI Features

- **File Browser**: Navigate and edit files
- **Code Editor**: Syntax highlighting
- **Chat Interface**: AI assistant
- **Terminal**: Run commands
- **Settings**: Configure providers

## Architecture

```
src/
├── main.py         # Main application
├── browser/        # Browser automation
├── email_agent/    # Email integration
├── oauth_manager/  # OAuth flows
├── voice/          # Voice control
├── skills/         # Skill system
└── hosting/        # Web server
```

## License

MIT
