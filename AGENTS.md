# Sentience - Local AI Computer

## What This Is
A complete desktop application like Cursor/Zo for local AI assistance - runs entirely on your machine.

## Architecture

```
sentience-app/
├── src/
│   ├── main.py           # Main application (GUI, AI client, tool execution)
│   ├── browser/          # Playwright-based browser automation
│   ├── email_agent/      # IMAP/SMTP email integration
│   ├── oauth_manager/    # OAuth flows for Google, GitHub, Notion, Linear
│   ├── voice/            # Speech recognition and TTS
│   ├── skills/           # Modular skill system
│   └── hosting/          # Local web server
├── skills/
│   └── senior-coder/     # Coding best practices skill
├── requirements.txt      # Python dependencies
└── README.md
```

## Tech Stack
- **GUI**: PySide6 (Qt for Python)
- **Browser**: Playwright
- **Email**: IMAP/SMTP (email library)
- **Voice**: SpeechRecognition, pyttsx3
- **AI Providers**: Groq, OpenAI, Anthropic, Ollama (BYOK)
- **Server**: aiohttp

## Features
- 21+ AI tools (file ops, browser, email, voice, skills, hosting)
- Full BYOK support (Bring Your Own API Key)
- 100% local mode with Ollama
- Desktop GUI with file browser, code editor, chat, terminal

## Known Issues
1. GUI requires display (won't run on headless servers)
2. Windows build needs GitHub Actions with workflow scope
3. Playwright browsers need manual install: `playwright install chromium`

## Install
```bash
pip install -r requirements.txt
playwright install chromium
python src/main.py
```

## Rules Applied
- `senior-coder`: All code follows production-quality practices
- `context-rag`: Always read AGENTS.md/README.md before changes
