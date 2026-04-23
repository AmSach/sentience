#!/usr/bin/env python3
"""
Sentience — Local AI Computer
Works on Windows, macOS, Linux
"""
import sys
import os
import platform
import traceback
import subprocess
import json
import sqlite3
import hashlib
import uuid
import threading
import queue
import time
import re
import glob
import shutil
import mimetypes
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
from concurrent.futures import ThreadPoolExecutor

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Graceful imports - don't crash if something is missing
FLASK_AVAILABLE = False
PYSIDE_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
ANTHROPIC_AVAILABLE = False
OPENAI_AVAILABLE = False
GROQ_AVAILABLE = False

try:
    from flask import Flask, request, jsonify, send_from_directory, send_file
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    print("Warning: Flask not available - server disabled")

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                     QTextEdit, QLineEdit, QPushButton, QLabel, QSplitter,
                                     QTabWidget, QListWidget, QSystemTrayIcon, QMenu, QFileDialog,
                                     QMessageBox, QStatusBar, QToolBar, QComboBox, QSpinBox,
                                     QProgressBar, QGroupBox, QFormLayout, QLineEdit)
    from PySide6.QtCore import Qt, QTimer, Signal, QThread, QUrl, QSize
    from PySide6.QtGui import QIcon, QFont, QPalette, QColor, QAction, QDesktopServices
    PYSIDE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: PySide6 not available - GUI disabled: {e}")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    print("Warning: Playwright not available - browser automation disabled")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    pass

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    pass

try:
    import groq
    GROQ_AVAILABLE = True
except ImportError:
    pass

# ============================================
# DATABASE
# ============================================

class SentienceDB:
    """SQLite database for conversations, memory, automations, skills."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            app_dir = Path.home() / ".sentience"
            app_dir.mkdir(exist_ok=True)
            db_path = str(app_dir / "sentience.db")
        
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at INTEGER,
                updated_at INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                tool_results TEXT,
                created_at INTEGER,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            
            CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY,
                key TEXT UNIQUE,
                value TEXT,
                compressed INTEGER DEFAULT 0,
                created_at INTEGER,
                updated_at INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS automations (
                id TEXT PRIMARY KEY,
                name TEXT,
                instruction TEXT,
                schedule TEXT,
                enabled INTEGER DEFAULT 1,
                last_run INTEGER,
                next_run INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                content TEXT,
                enabled INTEGER DEFAULT 1
            );
            
            CREATE TABLE IF NOT EXISTS byok_keys (
                provider TEXT PRIMARY KEY,
                api_key TEXT,
                models TEXT
            );
            
            CREATE TABLE IF NOT EXISTS background_tasks (
                id TEXT PRIMARY KEY,
                instruction TEXT,
                status TEXT DEFAULT 'pending',
                result TEXT,
                created_at INTEGER,
                started_at INTEGER,
                completed_at INTEGER
            );
            
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key);
        """)
        self.conn.commit()
    
    def create_conversation(self, conv_id: str, title: str = "New Chat"):
        now = int(time.time() * 1000)
        self.conn.execute(
            "INSERT OR REPLACE INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        self.conn.commit()
    
    def add_message(self, msg_id: str, conv_id: str, role: str, content: str, tool_calls: str = None, tool_results: str = None):
        now = int(time.time() * 1000)
        self.conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, tool_calls, tool_results, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, conv_id, role, content, tool_calls, tool_results, now)
        )
        self.conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        self.conn.commit()
    
    def get_messages(self, conv_id: str, limit: int = 100):
        return self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
            (conv_id, limit)
        ).fetchall()
    
    def set_memory(self, key: str, value: str, compress: bool = False):
        now = int(time.time() * 1000)
        self.conn.execute(
            "INSERT OR REPLACE INTO memory (id, key, value, compressed, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), key, value, 1 if compress else 0, now, now)
        )
        self.conn.commit()
    
    def get_memory(self, key: str):
        row = self.conn.execute("SELECT value, compressed FROM memory WHERE key = ?", (key,)).fetchone()
        if row:
            return row['value']
        return None
    
    def list_memory(self):
        return self.conn.execute("SELECT key, value FROM memory ORDER BY key").fetchall()
    
    def save_byok(self, provider: str, api_key: str, models: str = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO byok_keys (provider, api_key, models) VALUES (?, ?, ?)",
            (provider, api_key, models)
        )
        self.conn.commit()
    
    def get_byok(self, provider: str):
        row = self.conn.execute("SELECT api_key, models FROM byok_keys WHERE provider = ?", (provider,)).fetchone()
        if row:
            return {'api_key': row['api_key'], 'models': row['models']}
        return None
    
    def add_background_task(self, task_id: str, instruction: str):
        now = int(time.time() * 1000)
        self.conn.execute(
            "INSERT INTO background_tasks (id, instruction, status, created_at) VALUES (?, ?, 'pending', ?)",
            (task_id, instruction, now)
        )
        self.conn.commit()
    
    def get_pending_tasks(self):
        return self.conn.execute(
            "SELECT * FROM background_tasks WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    
    def update_task(self, task_id: str, status: str, result: str = None):
        now = int(time.time() * 1000)
        if status == 'running':
            self.conn.execute(
                "UPDATE background_tasks SET status = ?, started_at = ? WHERE id = ?",
                (status, now, task_id)
            )
        elif status in ('completed', 'failed'):
            self.conn.execute(
                "UPDATE background_tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?",
                (status, result, now, task_id)
            )
        self.conn.commit()

# ============================================
# LLM PROVIDERS (BYOK)
# ============================================

class LLMProvider:
    """Unified interface for OpenAI, Anthropic, Groq, local models."""
    
    def __init__(self, db: SentienceDB):
        self.db = db
        self.providers = {}
        self._load_keys()
    
    def _load_keys(self):
        for provider in ['openai', 'anthropic', 'groq', 'openrouter', 'ollama']:
            key_data = self.db.get_byok(provider)
            if key_data:
                self.providers[provider] = key_data['api_key']
    
    def set_key(self, provider: str, api_key: str):
        self.providers[provider] = api_key
        self.db.save_byok(provider, api_key)
    
    def chat(self, messages: List[Dict], model: str = None, provider: str = None) -> str:
        """Send chat completion request."""
        # Determine provider from model or explicit setting
        if provider is None:
            if model and model.startswith('gpt'):
                provider = 'openai'
            elif model and model.startswith('claude'):
                provider = 'anthropic'
            elif model and model.startswith('llama'):
                provider = 'groq'
            else:
                provider = list(self.providers.keys())[0] if self.providers else 'openai'
        
        api_key = self.providers.get(provider)
        if not api_key:
            return f"Error: No API key for {provider}. Set via Settings."
        
        try:
            if provider == 'openai' and OPENAI_AVAILABLE:
                client = openai.OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model or "gpt-4",
                    messages=messages
                )
                return response.choices[0].message.content
            
            elif provider == 'anthropic' and ANTHROPIC_AVAILABLE:
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model=model or "claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    messages=messages
                )
                return response.content[0].text
            
            elif provider == 'groq' and GROQ_AVAILABLE:
                client = groq.Groq(api_key=api_key)
                response = client.chat.completions.create(
                    model=model or "llama-3.3-70b-versatile",
                    messages=messages
                )
                return response.choices[0].message.content
            
            else:
                return f"Error: Provider {provider} not available or no API key set"
        
        except Exception as e:
            return f"Error: {str(e)}"

# ============================================
# TOOLS
# ============================================

class ToolRegistry:
    """Registry for all tools the agent can use."""
    
    def __init__(self):
        self.tools = {}
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        # Filesystem tools
        self.register("read_file", self._read_file, "Read a file from disk")
        self.register("write_file", self._write_file, "Write content to a file")
        self.register("list_dir", self._list_dir, "List directory contents")
        self.register("delete_file", self._delete_file, "Delete a file")
        self.register("search_files", self._search_files, "Search for files by pattern")
        
        # Shell tools
        self.register("run_command", self._run_command, "Execute a shell command")
        
        # Web tools
        self.register("fetch_url", self._fetch_url, "Fetch content from URL")
        self.register("web_search", self._web_search, "Search the web")
        
        # Memory tools
        self.register("remember", self._remember, "Store something in memory")
        self.register("recall", self._recall, "Retrieve from memory")
        self.register("list_memory", self._list_memory, "List all memory entries")
        
        # Browser tools
        if PLAYWRIGHT_AVAILABLE:
            self.register("browse", self._browse, "Browse a webpage with Playwright")
        
        # Code tools
        self.register("execute_python", self._execute_python, "Execute Python code")
        self.register("analyze_code", self._analyze_code, "Analyze code file")
    
    def register(self, name: str, func: Callable, description: str):
        self.tools[name] = {'func': func, 'description': description}
    
    def list_tools(self) -> List[Dict]:
        return [{'name': k, 'description': v['description']} for k, v in self.tools.items()]
    
    def execute(self, name: str, **kwargs) -> Any:
        if name not in self.tools:
            return f"Error: Tool '{name}' not found"
        try:
            return self.tools[name]['func'](**kwargs)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"
    
    # Tool implementations
    def _read_file(self, path: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    def _write_file(self, path: str, content: str) -> str:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"
    
    def _list_dir(self, path: str = ".") -> str:
        try:
            items = list(Path(path).iterdir())
            result = []
            for item in items[:50]:  # Limit output
                result.append(f"{'[DIR] ' if item.is_dir() else '[FILE]'} {item.name}")
            return "\n".join(result)
        except Exception as e:
            return f"Error listing directory: {str(e)}"
    
    def _delete_file(self, path: str) -> str:
        try:
            Path(path).unlink()
            return f"Deleted {path}"
        except Exception as e:
            return f"Error deleting file: {str(e)}"
    
    def _search_files(self, pattern: str, path: str = ".") -> str:
        try:
            matches = list(Path(path).rglob(pattern))[:20]
            return "\n".join(str(m) for m in matches)
        except Exception as e:
            return f"Error searching: {str(e)}"
    
    def _run_command(self, command: str, cwd: str = None) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=cwd
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
            return output[:5000]  # Limit output
        except subprocess.TimeoutExpired:
            return "Command timed out after 60 seconds"
        except Exception as e:
            return f"Error running command: {str(e)}"
    
    def _fetch_url(self, url: str) -> str:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8', errors='replace')[:10000]
        except Exception as e:
            return f"Error fetching URL: {str(e)}"
    
    def _web_search(self, query: str) -> str:
        # Use DuckDuckGo HTML for simple search
        url = f"https://html.duckduckgo.com/html/?q={query}"
        return self._fetch_url(url)
    
    def _remember(self, key: str, value: str, db: SentienceDB = None) -> str:
        if db:
            db.set_memory(key, value)
            return f"Remembered: {key}"
        return "Error: Database not available"
    
    def _recall(self, key: str, db: SentienceDB = None) -> str:
        if db:
            value = db.get_memory(key)
            return value if value else f"No memory found for key: {key}"
        return "Error: Database not available"
    
    def _list_memory(self, db: SentienceDB = None) -> str:
        if db:
            rows = db.list_memory()
            return "\n".join(f"{r['key']}: {r['value'][:100]}..." for r in rows)
        return "Error: Database not available"
    
    def _browse(self, url: str) -> str:
        if not PLAYWRIGHT_AVAILABLE:
            return "Playwright not available"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                content = page.content()[:10000]
                browser.close()
                return content
        except Exception as e:
            return f"Error browsing: {str(e)}"
    
    def _execute_python(self, code: str) -> str:
        try:
            # Safe execution with limited globals
            globals_dict = {'__builtins__': __builtins__}
            locals_dict = {}
            exec(code, globals_dict, locals_dict)
            return str(locals_dict.get('result', 'Code executed successfully'))
        except Exception as e:
            return f"Error executing code: {str(e)}"
    
    def _analyze_code(self, path: str) -> str:
        try:
            code = self._read_file(path)
            lines = code.split('\n')
            return f"File: {path}\nLines: {len(lines)}\nCharacters: {len(code)}\n\nFirst 50 lines:\n" + "\n".join(lines[:50])
        except Exception as e:
            return f"Error analyzing: {str(e)}"

# ============================================
# SERVER
# ============================================

class SentienceServer:
    """Flask server for API and web UI."""
    
    def __init__(self, db: SentienceDB, tools: ToolRegistry, llm: LLMProvider):
        self.db = db
        self.tools = tools
        self.llm = llm
        self.app = None
        self.server_thread = None
    
    def create_app(self):
        if not FLASK_AVAILABLE:
            return None
        
        app = Flask(__name__, static_folder='ui', static_url_path='')
        CORS(app)
        
        @app.route('/')
        def index():
            return send_from_directory('ui', 'index.html')
        
        @app.route('/api/health')
        def health():
            return jsonify({'status': 'ok', 'platform': platform.system()})
        
        @app.route('/api/tools')
        def list_tools():
            return jsonify({'tools': self.tools.list_tools()})
        
        @app.route('/api/chat', methods=['POST'])
        def chat():
            data = request.json
            messages = data.get('messages', [])
            model = data.get('model')
            provider = data.get('provider')
            response = self.llm.chat(messages, model, provider)
            return jsonify({'response': response})
        
        @app.route('/api/tools/<name>', methods=['POST'])
        def execute_tool(name):
            data = request.json or {}
            # Pass db for memory tools
            if name in ['remember', 'recall', 'list_memory']:
                data['db'] = self.db
            result = self.tools.execute(name, **data)
            return jsonify({'result': result})
        
        @app.route('/api/conversations', methods=['GET'])
        def list_conversations():
            convs = self.db.conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 50"
            ).fetchall()
            return jsonify({'conversations': [dict(c) for c in convs]})
        
        @app.route('/api/conversations/<conv_id>/messages', methods=['GET'])
        def get_messages(conv_id):
            msgs = self.db.get_messages(conv_id)
            return jsonify({'messages': [dict(m) for m in msgs]})
        
        @app.route('/api/settings/byok', methods=['POST'])
        def set_byok():
            data = request.json
            self.llm.set_key(data['provider'], data['api_key'])
            return jsonify({'status': 'ok'})
        
        @app.route('/api/settings/byok', methods=['GET'])
        def list_byok():
            providers = []
            for p in ['openai', 'anthropic', 'groq', 'openrouter', 'ollama']:
                key_data = self.db.get_byok(p)
                providers.append({
                    'provider': p,
                    'configured': bool(key_data)
                })
            return jsonify({'providers': providers})
        
        @app.route('/api/tasks', methods=['GET'])
        def list_tasks():
            tasks = self.db.conn.execute(
                "SELECT * FROM background_tasks ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            return jsonify({'tasks': [dict(t) for t in tasks]})
        
        @app.route('/api/tasks', methods=['POST'])
        def create_task():
            data = request.json
            task_id = str(uuid.uuid4())
            self.db.add_background_task(task_id, data['instruction'])
            return jsonify({'task_id': task_id})
        
        self.app = app
        return app
    
    def run(self, host: str = '127.0.0.1', port: int = 3131):
        if self.app:
            self.app.run(host=host, port=port, threaded=True, use_reloader=False)

# ============================================
# DESKTOP GUI
# ============================================

class SentienceWindow(QMainWindow if PYSIDE_AVAILABLE else object):
    """Main desktop window."""
    
    def __init__(self, db: SentienceDB, tools: ToolRegistry, llm: LLMProvider, server: SentienceServer):
        if not PYSIDE_AVAILABLE:
            return
        
        super().__init__()
        self.db = db
        self.tools = tools
        self.llm = llm
        self.server = server
        self.current_conversation = str(uuid.uuid4())
        
        self.setWindowTitle("Sentience — Local AI Computer")
        self.setMinimumSize(1000, 700)
        
        # Dark theme
        self._apply_dark_theme()
        
        # Create UI
        self._create_menu()
        self._create_central_widget()
        self._create_status_bar()
        
        # Initialize conversation
        self.db.create_conversation(self.current_conversation, "New Chat")
        
        # Start server in background
        if self.server and self.server.app:
            import threading
            server_thread = threading.Thread(target=self.server.run, daemon=True)
            server_thread.start()
            self.status.showMessage("Server running on http://127.0.0.1:3131")
    
    def _apply_dark_theme(self):
        app = QApplication.instance()
        app.setStyle('Fusion')
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        app.setPalette(palette)
    
    def _create_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        new_action = QAction("New Conversation", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_conversation)
        file_menu.addAction(new_action)
        
        open_action = QAction("Open Workspace", self)
        open_action.triggered.connect(self._open_workspace)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menubar.addMenu("Settings")
        
        byok_action = QAction("BYOK Keys", self)
        byok_action.triggered.connect(self._show_byok_dialog)
        settings_menu.addAction(byok_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _create_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        
        # Left panel - conversation list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Conversations"))
        
        self.conv_list = QListWidget()
        self.conv_list.itemClicked.connect(self._switch_conversation)
        left_layout.addWidget(self.conv_list)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_conversations)
        left_layout.addWidget(refresh_btn)
        
        # Right panel - chat
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.chat_display, stretch=3)
        
        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.returnPressed.connect(self._send_message)
        
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_message)
        
        # Tool selector
        self.tool_combo = QComboBox()
        self.tool_combo.addItem("Chat")
        for tool in self.tools.list_tools():
            self.tool_combo.addItem(f"Tool: {tool['name']}")
        
        input_layout.addWidget(self.input_field, stretch=3)
        input_layout.addWidget(self.tool_combo)
        input_layout.addWidget(send_btn)
        
        right_layout.addLayout(input_layout)
        
        # Add panels to splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 800])
        
        layout.addWidget(splitter)
        
        # Load conversations
        self._load_conversations()
    
    def _create_status_bar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(f"Ready | Platform: {platform.system()}")
    
    def _load_conversations(self):
        self.conv_list.clear()
        convs = self.db.conn.execute(
            "SELECT id, title FROM conversations ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
        for c in convs:
            self.conv_list.addItem(f"{c['title']} ({c['id'][:8]})")
    
    def _switch_conversation(self, item):
        # Extract conversation ID from item text
        text = item.text()
        # Format: "Title (id)"
        match = re.search(r'\(([a-f0-9-]{8})\)', text)
        if match:
            conv_id_short = match.group(1)
            convs = self.db.conn.execute(
                "SELECT id FROM conversations WHERE id LIKE ?", (f"{conv_id_short}%",)
            ).fetchone()
            if convs:
                self.current_conversation = convs['id']
                self._load_messages()
    
    def _load_messages(self):
        self.chat_display.clear()
        msgs = self.db.get_messages(self.current_conversation)
        for m in msgs:
            role = m['role'].upper()
            content = m['content']
            self.chat_display.append(f"<b>{role}:</b> {content}\n")
    
    def _new_conversation(self):
        self.current_conversation = str(uuid.uuid4())
        self.db.create_conversation(self.current_conversation, "New Chat")
        self.chat_display.clear()
        self._load_conversations()
    
    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        
        self.input_field.clear()
        
        # Save user message
        self.db.add_message(str(uuid.uuid4()), self.current_conversation, "user", text)
        self.chat_display.append(f"<b>YOU:</b> {text}")
        
        # Check if using a tool
        tool_name = self.tool_combo.currentText()
        if tool_name.startswith("Tool: "):
            tool = tool_name[6:]
            result = self.tools.execute(tool, path=text, db=self.db)
            self.chat_display.append(f"<b>TOOL ({tool}):</b> {result}")
            self.db.add_message(str(uuid.uuid4()), self.current_conversation, "assistant", f"[Tool: {tool}]\n{result}")
        else:
            # Chat with LLM
            messages = []
            for m in self.db.get_messages(self.current_conversation, limit=10):
                messages.append({'role': m['role'], 'content': m['content']})
            
            response = self.llm.chat(messages)
            self.chat_display.append(f"<b>AI:</b> {response}")
            self.db.add_message(str(uuid.uuid4()), self.current_conversation, "assistant", response)
    
    def _open_workspace(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Workspace")
        if folder:
            self.status.showMessage(f"Workspace: {folder}")
            self.db.set_memory('workspace', folder)
    
    def _show_byok_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("BYOK - Bring Your Own Keys")
        dialog.setMinimumWidth(400)
        
        layout = QFormLayout(dialog)
        
        openai_edit = QLineEdit()
        openai_edit.setEchoMode(QLineEdit.Password)
        openai_edit.setText(self.db.get_byok('openai')['api_key'] if self.db.get_byok('openai') else '')
        layout.addRow("OpenAI API Key:", openai_edit)
        
        anthropic_edit = QLineEdit()
        anthropic_edit.setEchoMode(QLineEdit.Password)
        anthropic_edit.setText(self.db.get_byok('anthropic')['api_key'] if self.db.get_byok('anthropic') else '')
        layout.addRow("Anthropic API Key:", anthropic_edit)
        
        groq_edit = QLineEdit()
        groq_edit.setEchoMode(QLineEdit.Password)
        groq_edit.setText(self.db.get_byok('groq')['api_key'] if self.db.get_byok('groq') else '')
        layout.addRow("Groq API Key:", groq_edit)
        
        def save_keys():
            if openai_edit.text():
                self.llm.set_key('openai', openai_edit.text())
            if anthropic_edit.text():
                self.llm.set_key('anthropic', anthropic_edit.text())
            if groq_edit.text():
                self.llm.set_key('groq', groq_edit.text())
            dialog.accept()
            QMessageBox.information(self, "Saved", "API keys saved locally.")
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(save_keys)
        layout.addRow(save_btn)
        
        dialog.exec()
    
    def _show_about(self):
        QMessageBox.about(
            self,
            "About Sentience",
            "<h2>Sentience v2.0</h2>"
            "<p>Local AI Computer - Like Zo + Claude Code</p>"
            "<p>100% runs on your machine.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>BYOK (OpenAI, Anthropic, Groq, Local)</li>"
            "<li>100+ Tools</li>"
            "<li>Local Memory (SQLite)</li>"
            "<li>Self-improving Agent</li>"
            "</ul>"
            "<p>Platform: " + platform.system() + "</p>"
        )

# ============================================
# CLI MODE
# ============================================

def run_cli(db: SentienceDB, tools: ToolRegistry, llm: LLMProvider):
    """Run in CLI mode when GUI not available."""
    print("\n" + "="*50)
    print("  Sentience CLI Mode")
    print("  Type 'help' for commands, 'quit' to exit")
    print("="*50 + "\n")
    
    current_conv = str(uuid.uuid4())
    db.create_conversation(current_conv, "CLI Session")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if user_input.lower() == 'help':
                print("""
Commands:
  help          - Show this help
  tools         - List available tools
  use <tool>    - Use a tool
  remember X=Y  - Store in memory
  recall X      - Retrieve from memory
  clear         - Clear conversation
  quit          - Exit
""")
                continue
            
            if user_input.lower() == 'tools':
                for t in tools.list_tools():
                    print(f"  - {t['name']}: {t['description']}")
                continue
            
            if user_input.lower() == 'clear':
                current_conv = str(uuid.uuid4())
                db.create_conversation(current_conv, "CLI Session")
                print("Conversation cleared.")
                continue
            
            if user_input.lower().startswith('remember '):
                try:
                    key, value = user_input[9:].split('=', 1)
                    db.set_memory(key.strip(), value.strip())
                    print(f"Remembered: {key}")
                except:
                    print("Usage: remember key=value")
                continue
            
            if user_input.lower().startswith('recall '):
                key = user_input[7:].strip()
                value = db.get_memory(key)
                print(value if value else f"No memory for: {key}")
                continue
            
            if user_input.lower().startswith('use '):
                parts = user_input[4:].split(None, 1)
                tool_name = parts[0]
                tool_arg = parts[1] if len(parts) > 1 else ""
                result = tools.execute(tool_name, path=tool_arg, db=db)
                print(f"Result: {result}")
                continue
            
            # Chat with LLM
            db.add_message(str(uuid.uuid4()), current_conv, "user", user_input)
            messages = [{'role': m['role'], 'content': m['content']} 
                       for m in db.get_messages(current_conv, limit=10)]
            response = llm.chat(messages)
            print(f"\nAI: {response}\n")
            db.add_message(str(uuid.uuid4()), current_conv, "assistant", response)
        
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

# ============================================
# MAIN
# ============================================

def main():
    print(f"Sentience v2.0 starting on {platform.system()}")
    print(f"Python: {sys.version}")
    print(f"Flask: {'available' if FLASK_AVAILABLE else 'not available'}")
    print(f"PySide6: {'available' if PYSIDE_AVAILABLE else 'not available'}")
    print(f"Playwright: {'available' if PLAYWRIGHT_AVAILABLE else 'not available'}")
    
    # Initialize core components
    db = SentienceDB()
    tools = ToolRegistry()
    llm = LLMProvider(db)
    server = SentienceServer(db, tools, llm)
    
    # Create server app
    server.create_app()
    
    # Decide mode
    if PYSIDE_AVAILABLE and '--cli' not in sys.argv:
        # GUI mode
        app = QApplication(sys.argv)
        app.setApplicationName("Sentience")
        app.setApplicationDisplayName("Sentience - Local AI Computer")
        
        window = SentienceWindow(db, tools, llm, server)
        window.show()
        
        sys.exit(app.exec())
    else:
        # CLI mode
        run_cli(db, tools, llm)

if __name__ == "__main__":
    main()
