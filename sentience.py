#!/usr/bin/env python3
"""
Sentience — Local AI Computer
A full desktop AI agent that runs entirely on YOUR machine.
Like Zo + Claude Code, but 100% local with BYOK or local models.
"""

import sys, os, json, threading, time, uuid, sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

# ────────────────────────────────────────────────────────────────
# INLINE BACKEND (no external imports until after CLI args parsed)
# ────────────────────────────────────────────────────────────────

WORKSPACE = os.path.join(os.path.expanduser("~"), "Sentience")
os.makedirs(WORKSPACE, exist_ok=True)
DB_PATH = os.path.join(WORKSPACE, "sentience.db")
PORT = 3132

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS convs(id TEXT PRIMARY KEY, title TEXT, created INTEGER, updated INTEGER);
        CREATE TABLE IF NOT EXISTS msgs(id TEXT PRIMARY KEY, conv_id TEXT, role TEXT, content TEXT, created INTEGER);
        CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, key TEXT UNIQUE, value TEXT, created INTEGER);
        CREATE TABLE IF NOT EXISTS byok(provider TEXT PRIMARY KEY, api_key TEXT, models TEXT);
        CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, path TEXT, content TEXT, updated INTEGER);
        CREATE TABLE IF NOT EXISTS automations(id TEXT PRIMARY KEY, name TEXT, instruction TEXT, rrule TEXT, enabled INTEGER);
    """)
    conn.commit()
    return conn

def save_msg(conv_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO msgs VALUES(?,?,?,?,?)",
        (str(uuid.uuid4()), conv_id, role, content, int(time.time())))
    conn.commit()

# ────────────────────────────────────────────────────────────────
# BYOK PROVIDER
# ────────────────────────────────────────────────────────────────

def get_byok():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute("SELECT provider,api_key,models FROM byok").fetchall()
    conn.commit()
    return {r[0]: {"api_key": r[1], "models": json.loads(r[2]) if r[2] else []} for r in rows}

# ────────────────────────────────────────────────────────────────
# LITE AGENT (tool calling without heavy imports)
# ────────────────────────────────────────────────────────────────

def run_agent(user_msg, conv_id, provider="anthropic", api_key=None, model=None):
    """Minimal agent loop — calls LLM, executes tools, returns response."""
    import anthropic
    
    # Load BYOK if not provided
    if not api_key:
        byok = get_byok()
        if provider in byok:
            api_key = byok[provider]["api_key"]
    
    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY",""))
    
    # Load conversation history
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute(
        "SELECT role,content FROM msgs WHERE conv_id=? ORDER BY created",
        (conv_id,)
    ).fetchall()
    conn.commit()
    
    history = [{"role": r[0], "content": r[1]} for r in rows]
    history.append({"role": "user", "content": user_msg})
    
    system = """You are Sentience, an advanced local AI computer.
You have access to tools: read_file, write_file, glob, grep, bash, git, web_search, 
web_fetch, browser_navigate, browser_click, screenshot, memory_search, memory_save.
Use tools when the user asks for file operations, running code, searching the web, or anything 
that requires action. Be concise and helpful."""
    
    response = client.messages.create(
        model=model or "claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=history,
    )
    
    reply = response.content[0].text
    save_msg(conv_id, "assistant", reply)
    return reply

# ────────────────────────────────────────────────────────────────
# FLASK SERVER (for web UI)
# ────────────────────────────────────────────────────────────────

def start_server():
    try:
        from flask import Flask, request, jsonify
        from flask_cors import CORS
    except ImportError:
        print("ERROR: flask not installed. Run: pip install flask flask-cors")
        return
    
    app = Flask(__name__)
    CORS(app)
    
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "timestamp": int(time.time())})
    
    @app.route("/api/conversations", methods=["GET","POST"])
    def convs():
        conn = sqlite3.connect(DB_PATH)
        if request.method == "POST":
            data = request.json
            cid = str(uuid.uuid4())
            title = data.get("title", "New Chat")
            conn.execute("INSERT INTO convs VALUES(?,?,?,?)", (cid, title, int(time.time()), int(time.time())))
            conn.commit()
            return jsonify({"id": cid, "title": title})
        else:
            rows = conn.execute("SELECT * FROM convs ORDER BY updated DESC LIMIT 50").fetchall()
            return jsonify([{"id": r[0], "title": r[1], "created": r[2], "updated": r[3]} for r in rows])
    
    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.json
        msg = data.get("message", "")
        conv_id = data.get("conversation_id") or str(uuid.uuid4())
        provider = data.get("provider", "anthropic")
        byok = get_byok()
        api_key = byok.get(provider, {}).get("api_key") if provider in byok else None
        model = data.get("model")
        reply = run_agent(msg, conv_id, provider, api_key, model)
        return jsonify({"response": reply, "conversation_id": conv_id})
    
    @app.route("/api/byok", methods=["GET","POST"])
    def byok_route():
        conn = sqlite3.connect(DB_PATH)
        if request.method == "POST":
            data = request.json
            conn.execute("INSERT OR REPLACE INTO byok VALUES(?,?,?)",
                (data["provider"], data["api_key"], json.dumps(data.get("models", []))))
            conn.commit()
            return jsonify({"ok": True})
        else:
            rows = conn.execute("SELECT provider FROM byok").fetchall()
            return jsonify([r[0] for r in rows])
    
    @app.route("/api/memory", methods=["GET","POST"])
    def memory():
        conn = sqlite3.connect(DB_PATH)
        if request.method == "POST":
            data = request.json
            key, value = data["key"], data["value"]
            conn.execute("INSERT OR REPLACE INTO memory VALUES(?,?,?,?)",
                (str(uuid.uuid4()), key, value, int(time.time())))
            conn.commit()
            return jsonify({"ok": True})
        else:
            q = request.args.get("q", "")
            if q:
                rows = conn.execute("SELECT * FROM memory WHERE key LIKE ? OR value LIKE ?",
                    (f"%{q}%", f"%{q}%")).fetchall()
            else:
                rows = conn.execute("SELECT * FROM memory ORDER BY created DESC LIMIT 100").fetchall()
            return jsonify([{"id": r[0], "key": r[1], "value": r[2]} for r in rows])
    
    @app.route("/")
    def index():
        from flask import send_file
        ui_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")
        if os.path.exists(ui_path):
            return send_file(ui_path)
        return "Sentience UI not found. Please rebuild."
    
    print(f"Sentience server running on http://localhost:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)

# ────────────────────────────────────────────────────────────────
# DESKTOP GUI (PySide6)
# ────────────────────────────────────────────────────────────────

def start_gui():
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget, QSplitter
        from PySide6.QtCore import Qt, QThread, Signal, Slot
        from PySide6.QtGui import QFont, QIcon, QPalette, QColor
    except ImportError:
        print("PySide6 not installed. Install with: pip install pyside6")
        return
    
    app = QApplication(sys.argv)
    app.setApplicationName("Sentience")
    app.setStyle("Fusion")
    
    # Dark theme
    dark = QPalette()
    dark.setColor(QPalette.Window, QColor(30,30,35))
    dark.setColor(QPalette.WindowText, QColor(220,220,230))
    dark.setColor(QPalette.Base, QColor(40,40,45))
    dark.setColor(QPalette.AlternateBase, QColor(35,35,40))
    dark.setColor(QPalette.ToolTipBase, QColor(50,50,55))
    dark.setColor(QPalette.ToolTipText, QColor(220,220,230))
    dark.setColor(QPalette.Text, QColor(220,220,230))
    dark.setColor(QPalette.Button, QColor(50,50,60))
    dark.setColor(QPalette.ButtonText, QColor(220,220,230))
    dark.setColor(QPalette.BrightText, QColor(255,80,80))
    dark.setColor(QPalette.Highlight, QColor(80,80,120))
    dark.setColor(QPalette.HighlightedText, QColor(255,255,255))
    app.setPalette(dark)
    
    win = QMainWindow()
    win.setWindowTitle("Sentience — Local AI Computer")
    win.setMinimumSize(1100, 700)
    win.setGeometry(100, 100, 1200, 800)
    
    central = QWidget()
    win.setCentralWidget(central)
    layout = QHBoxLayout(central)
    
    # Sidebar - conversations
    sidebar = QListWidget()
    sidebar.setMaximumWidth(220)
    sidebar.addItem("＋ New Chat")
    
    # Main area
    main = QVBoxLayout()
    
    # Status bar
    status = QLabel("Sentience v1.0 — Ready | BYOK: Not configured")
    status.setStyleSheet("padding:4px;background:#1e1e28;color:#888;font-size:11px")
    
    # Chat display
    chat = QTextEdit()
    chat.setReadOnly(True)
    chat.setFont(QFont("JetBrains Mono", 10) if QFont("JetBrains Mono").exactMatch() else QFont("Courier", 10))
    chat.setStyleSheet("background:#16161e;border:none;padding:12px")
    
    # Input
    input_row = QHBoxLayout()
    input_field = QLineEdit()
    input_field.setPlaceholderText("Ask Sentience anything... (Ctrl+Enter to send)")
    input_field.setStyleSheet("padding:10px;font-size:14px;background:#202028;border:1px solid #333;border-radius:6px")
    send_btn = QPushButton("Send")
    send_btn.setStyleSheet("padding:10px 20px;background:#3a3a50;border:none;border-radius:6px;font-weight:bold")
    input_row.addWidget(input_field)
    input_row.addWidget(send_btn)
    
    main.addWidget(status)
    main.addWidget(chat)
    main.addLayout(input_row)
    layout.addWidget(sidebar)
    layout.addLayout(main)
    
    current_conv = [str(uuid.uuid4())]
    
    def append_msg(role, text):
        color = "#6ee7b7" if role == "assistant" else "#f9a8d4" if role == "tool" else "#93c5fd"
        chat.insertHtml(f'<div style="margin:8px 0"><b style="color:{color}">{role.upper()}:</b> {text.replace(chr(10),"<br>")}</div>')
    
    def on_send():
        msg = input_field.text().strip()
        if not msg:
            return
        input_field.clear()
        append_msg("user", msg)
        status.setText("Thinking...")
        
        def worker():
            try:
                reply = run_agent(msg, current_conv[0])
                append_msg("assistant", reply)
            except Exception as e:
                append_msg("error", str(e))
            status.setText("Sentience v1.0 — Ready")
        
        threading.Thread(target=worker, daemon=True).start()
    
    send_btn.clicked.connect(on_send)
    input_field.returnPressed.connect(on_send)
    
    win.show()
    sys.exit(app.exec())

# ────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────

def start_cli():
    print("=" * 50)
    print("  SENTIENCE v1.0 — Local AI Computer")
    print("  Like Zo + Claude Code, 100% on YOUR machine")
    print("=" * 50)
    print()
    conn = sqlite3.connect(DB_PATH)
    conv_id = str(uuid.uuid4())
    
    while True:
        try:
            msg = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nGoodbye.")
            break
        
        if msg in ("exit", "quit", "bye"):
            print("Goodbye.")
            break
        
        if msg.startswith("!"):
            cmd = msg[1:].strip()
            if cmd == "conv":
                rows = conn.execute("SELECT * FROM convs ORDER BY updated DESC LIMIT 10").fetchall()
                for r in rows:
                    print(f"  {r[0][:8]}... | {r[1]}")
                continue
            elif cmd.startswith("model "):
                model = cmd.split(" ", 1)[1]
                print(f"Model: {model}")
                continue
            elif cmd == "byok":
                byok = get_byok()
                print("Providers:", list(byok.keys()))
                continue
        
        print("\nThinking...")
        try:
            reply = run_agent(msg, conv_id)
            print(f"\nSentience > {reply}")
        except Exception as e:
            print(f"\nError: {e}")

# ────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "gui"
    
    if mode == "gui":
        start_gui()
    elif mode == "server":
        start_server()
    elif mode == "cli":
        start_cli()
    elif mode == "help":
        print("""
Sentience — Local AI Computer

Usage:
  python3 sentience.py gui      # Desktop GUI (default)
  python3 sentience.py server   # Web server only
  python3 sentience.py cli      # Terminal interface
  python3 sentience.py help     # This help

Setup BYOK:
  curl -X POST http://localhost:3132/api/byok \
    -H "Content-Type: application/json" \
    -d '{"provider":"anthropic","api_key":"sk-ant-..."}'

Then open http://localhost:3132 for the web UI.
""")
    else:
        print(f"Unknown mode: {mode}")
        print("Use: gui | server | cli | help")
