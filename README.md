# Sentience — Local AI Computer

**Your personal AI that runs 100% on YOUR hardware. No cloud. No data leaving your machine.**

<p align="center">
  <strong>Download: <code>Sentience-Full-Setup.zip</code> — 240MB, everything bundled, double-click to run</strong>
</p>

## What It Does

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENTIENCE CORE FEATURES                       │
├──────────────┬──────────────────────────────────────────────────┤
│ AI AGENT     │ 127 tools • multi-model • BYOK • background     │
│ FORMS        │ 8 templates • auto-fill from docs • AI assist  │
│ RESEARCH     │ Web search • deep analysis • multi-source synth │
│ ANALYSIS     │ Entity extraction • sentiment • readability     │
│ KNOWLEDGE    │ Persistent KB • search • tags • categories     │
│ EXECUTION    │ Task queue • workflows • background processing  │
│ COLLABORATION│ Rooms • file sharing • permissions • logs      │
│ FORMS & DOCS │ PDF/DOCX/XLSX process • auto-fill • templates  │
│ HOSTING      │ Local web server • domains • SSL • reverse proxy│
│ EMAIL        │ Gmail/IMAP/SMTP • auto-reply • email-to-task   │
│ REMOTE       │ SSH/SFTP to any machine • remote execution      │
│ CLOUD        │ Dropbox • Google Drive • OneDrive • S3 sync    │
│ SKILLS       │ 8 built-in • custom skill loading • npm/URL     │
│ MEMORY       │ LZ4 compression • semantic summarization        │
│ GRAPH        │ Entity graph • context understanding            │
│ MULTIMODAL   │ Images • video frames • audio transcription    │
└──────────────┴──────────────────────────────────────────────────┘
```

## Form Templates (Auto-Fill)

| Template | Use Case |
|----------|----------|
| `visa_application` | Visa applications with all fields |
| `job_application` | Job applications with resume link |
| `government_form` | Gov forms (Aadhar, PAN, etc) |
| `tax_form` | ITR and tax submissions |
| `bank_account` | Bank account opening |
| `insurance_claim` | Insurance claims |
| `leave_application` | Leave requests |
| `contract_agreement` | Legal contracts |

**Auto-fill workflow:**
1. Select a form template
2. Point to your reference documents (passport, previous forms, etc.)
3. Sentience extracts data and fills the form
4. You review and sign

## Background Execution

```
"Fill my visa application in the background while I sleep"
"Research this topic and email me when done"
"Process all documents in /uploads and summarize results"
```

## Remote Access

Access your Sentience from anywhere:
- **Email bridge**: Send an email, get AI-powered response
- **SSH tunnel**: Connect to your home machine from anywhere
- **Cloud sync**: Files accessible from any device

## Quick Start

```bash
# 1. Extract the zip
unzip Sentience-Full-Setup.zip -d ~/Sentience

# 2. Edit .env with your API keys
nano ~/Sentience/.env

# 3. Run
./Sentience.exe        # Windows
python3 Sentience.py   # Any OS

# Or run the server and use the web UI
python3 server.py      # → http://localhost:3132
```

## Skills System

```python
# Built-in skills
skills = [
    "filesystem"   # File operations
    "code"        # Code writing, review, debugging
    "web"         # Web scraping, APIs
    "data"        # Data processing, analysis
    "research"    # Research workflows
    "automation"  # Scheduling, triggers
    "collab"      # Team collaboration
    "forms"       # Form processing
]

# Load custom skills
sentience.load_skill("https://example.com/skill.json")
sentience.load_skill("github://user/repo/skill")
```

## Settings

| Setting | Description |
|---------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GROQ_API_KEY` | Groq API key (free) |
| `OLLAMA_BASE_URL` | Local Ollama server |
| `LMSTUDIO_BASE_URL` | Local LM Studio |
| `SENTIENCE_PORT` | Server port (default: 3132) |
| `WORKSPACE_PATH` | Working directory |
| `GMAIL_EMAIL` | Gmail for email bridge |
| `GMAIL_APP_PASSWORD` | Gmail app password |

## Architecture

```
sentience/
├── agent/          # AI agent + tool registry (127 tools)
├── skills/        # Skill system (built-in + custom)
├── storage/       # SQLite DB + memory
├── memory/        # Compression + graph + vault
├── forms/         # Form processing + auto-fill
├── analysis/      # Document analysis
├── research/      # Web research + synthesis
├── execution/     # Task queue + workflows
├── knowledge/     # Knowledge base
├── collab/        # Collaboration rooms
├── hosting/       # Local web hosting
├── email/         # Email integration
├── remote/        # SSH/SFTP remote control
├── cloud/         # Cloud storage sync
├── multimodal/    # Images, video, audio
├── server.py      # Flask REST API
├── sentience.py   # CLI entry point
└── Sentience.exe  # Windows desktop app
```

## License

MIT — Build on this, make it yours.
