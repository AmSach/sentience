#!/usr/bin/env python3
"""
Sentience - Local AI Computer
A complete desktop application like Cursor/Zo for local AI assistance
"""
import sys
import os
import json
import subprocess
import threading
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Qt imports
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget,
    QListWidgetItem, QTreeWidget, QTreeWidgetItem, QTabWidget, QPlainTextEdit,
    QComboBox, QSpinBox, QCheckBox, QGroupBox, QFormLayout, QMessageBox,
    QFileDialog, QStatusBar, QToolBar, QMenuBar, QMenu, QProgressBar,
    QSystemTrayIcon, QStyle, QSizePolicy, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QProcess, QSize, QUrl
from PySide6.QtGui import QFont, QIcon, QColor, QSyntaxHighlighter, QTextCharFormat, QAction, QKeySequence, QDesktopServices

# Third-party
import requests
from dotenv import load_dotenv

load_dotenv()

# Import local modules
sys.path.insert(0, str(Path(__file__).parent))
from browser.automation import BROWSER_TOOLS, PLAYWRIGHT_AVAILABLE
from email_agent.client import EMAIL_TOOLS, init_email, execute_email_tool
from oauth_manager.manager.manager import OAUTH_TOOLS, get_oauth_manager, execute_oauth_tool
from voice.controller import VOICE_TOOLS, get_voice_controller, execute_voice_tool
from skills.registry import SKILL_TOOLS, get_skill_registry, execute_skill_tool
from hosting.server import HOSTING_TOOLS, get_hosting_server

# ============== CONFIG ==============
CONFIG_DIR = Path.home() / ".sentience"
CONFIG_DIR.mkdir(exist_ok=True)
DB_PATH = CONFIG_DIR / "sentience.db"
HISTORY_PATH = CONFIG_DIR / "history.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "provider": "groq",
    "model": "llama-3.3-70b-versatile",
    "api_key": "",
    "workspace": str(Path.home()),
    "theme": "dark",
    "font_size": 12,
    "max_tokens": 4096,
    "temperature": 0.7,
    "voice_enabled": True,
    "browser_enabled": True,
    "email_provider": "gmail"
}

# ============== PROVIDERS ==============
PROVIDERS = {
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.2-90b-vision-preview", "mixtral-8x7b-32768"],
        "free_tier": True
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "free_tier": False
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "free_tier": False
    },
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": os.getenv("OLLAMA_HOST", "http://localhost:11434/v1"),
        "models": ["llama3.2", "llama3.1", "codellama", "mistral", "qwen2.5"],
        "free_tier": True
    }
}

# ============== AI CLIENT ==============
class AIClient:
    def __init__(self, provider: str, model: str, api_key: str = ""):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.config = PROVIDERS.get(provider, PROVIDERS["groq"])
        
    def chat(self, messages: List[Dict], tools: List[Dict] = None) -> Dict:
        """Send chat request to provider"""
        if self.provider == "anthropic":
            return self._chat_anthropic(messages, tools)
        else:
            return self._chat_openai_compatible(messages, tools)
    
    def _chat_openai_compatible(self, messages: List[Dict], tools: List[Dict] = None) -> Dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.7
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        try:
            resp = requests.post(
                f"{self.config['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    def _chat_anthropic(self, messages: List[Dict], tools: List[Dict] = None) -> Dict:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        anthropic_messages = []
        system_msg = None
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append(msg)
        
        payload = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": 4096
        }
        if system_msg:
            payload["system"] = system_msg
        if tools:
            payload["tools"] = tools
        
        try:
            resp = requests.post(
                f"{self.config['base_url']}/messages",
                headers=headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

# ============== TOOLS ==============
ALL_TOOLS = [
    # File tools
    {"type": "function", "function": {"name": "read_file", "description": "Read a file from the filesystem", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to the file"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to the file"}, "content": {"type": "string", "description": "Content to write"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "List contents of a directory", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to the directory"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run a shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Command to run"}, "cwd": {"type": "string", "description": "Working directory"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "search_files", "description": "Search for files matching a pattern", "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Search pattern"}, "path": {"type": "string", "description": "Directory to search in"}}, "required": ["pattern"]}}},
    # Browser tools
    *BROWSER_TOOLS,
    # Email tools
    *EMAIL_TOOLS,
    # OAuth tools
    *OAUTH_TOOLS,
    # Voice tools
    *VOICE_TOOLS,
    # Skill tools
    *SKILL_TOOLS,
    # Hosting tools
    *HOSTING_TOOLS
]

def execute_tool(name: str, args: Dict, workspace: str) -> Dict:
    """Execute a tool and return result"""
    try:
        # File tools
        if name == "read_file":
            path = Path(args.get("path", ""))
            if not path.is_absolute():
                path = Path(workspace) / path
            if path.exists():
                return {"success": True, "content": path.read_text()[:10000]}
            return {"success": False, "error": "File not found"}
        
        elif name == "write_file":
            path = Path(args.get("path", ""))
            if not path.is_absolute():
                path = Path(workspace) / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.get("content", ""))
            return {"success": True, "message": f"Written to {path}"}
        
        elif name == "list_directory":
            path = Path(args.get("path", workspace))
            if not path.exists():
                return {"success": False, "error": "Directory not found"}
            items = []
            for item in sorted(path.iterdir())[:100]:
                items.append({"name": item.name, "type": "dir" if item.is_dir() else "file", "size": item.stat().st_size if item.is_file() else None})
            return {"success": True, "items": items}
        
        elif name == "run_command":
            cmd = args.get("command", "")
            cwd = args.get("cwd", workspace)
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd)
            return {"success": True, "stdout": result.stdout[:5000], "stderr": result.stderr[:5000], "exit_code": result.returncode}
        
        elif name == "search_files":
            import fnmatch
            pattern = args.get("pattern", "*")
            path = Path(args.get("path", workspace))
            matches = []
            for root, dirs, files in os.walk(path):
                for fname in files + dirs:
                    if fnmatch.fnmatch(fname, pattern):
                        matches.append(str(Path(root) / fname))
                if len(matches) > 100:
                    break
            return {"success": True, "matches": matches[:100]}
        
        # Email tools
        elif name.startswith("email_"):
            return execute_email_tool(name, args)
        
        # OAuth tools
        elif name.startswith("oauth_"):
            return execute_oauth_tool(name, args)
        
        # Voice tools
        elif name.startswith("voice_"):
            return execute_voice_tool(name, args)
        
        # Skill tools
        elif name.startswith("skill_"):
            return execute_skill_tool(name, args)
        
        return {"success": False, "error": f"Unknown tool: {name}"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============== WIDGETS ==============
class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
        self.timestamp = datetime.now()
        self.tool_calls = []
        self.tool_results = []

class CodeEditor(QPlainTextEdit):
    """Simple code editor with syntax highlighting"""
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Consolas", 11))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setStyleSheet("QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: none; }")

class FileTreeWidget(QTreeWidget):
    """File browser tree"""
    file_opened = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setHeaderLabel("Files")
        self.setStyleSheet("QTreeWidget { background-color: #252526; color: #cccccc; border: none; } QTreeWidget::item:selected { background-color: #094771; }")
        self.itemDoubleClicked.connect(self.on_double_click)
        self.path = str(Path.home())
    
    def load_directory(self, path: str):
        self.clear()
        self._add_items(self, Path(path))
        self.path = path
    
    def _add_items(self, parent, path: Path):
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith('.') or item.name == '__pycache__':
                    continue
                tree_item = QTreeWidgetItem(parent, [item.name])
                tree_item.setData(0, Qt.UserRole, str(item))
                if item.is_dir():
                    tree_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                    self._add_items(tree_item, item)
                else:
                    tree_item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
        except PermissionError:
            pass
    
    def on_double_click(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.UserRole)
        if path and Path(path).is_file():
            self.file_opened.emit(path)

class ChatWidget(QWidget):
    """Chat interface"""
    message_sent = Signal(str)
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("QTextEdit { background-color: #1e1e1e; color: #e0e0e0; border: none; font-size: 13px; }")
        layout.addWidget(self.chat_display)
        
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #ffffff; border: 1px solid #555; padding: 8px; border-radius: 4px; }")
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setStyleSheet("QPushButton { background-color: #0e639c; color: white; border: none; padding: 8px 16px; border-radius: 4px; } QPushButton:hover { background-color: #1177bb; }")
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)
        
        self.messages: List[ChatMessage] = []
    
    def send_message(self):
        text = self.input_field.text().strip()
        if text:
            self.input_field.clear()
            self.message_sent.emit(text)
    
    def add_message(self, role: str, content: str):
        msg = ChatMessage(role, content)
        self.messages.append(msg)
        self._render_messages()
    
    def _render_messages(self):
        html = ""
        for msg in self.messages:
            if msg.role == "user":
                html += f'<div style="margin: 10px 0; padding: 10px; background: #2d2d2d; border-radius: 8px;"><b style="color: #4fc3f7;">You:</b><br>{msg.content}</div>'
            else:
                html += f'<div style="margin: 10px 0; padding: 10px; background: #1a1a2e; border-radius: 8px;"><b style="color: #81c784;">Assistant:</b><br><pre style="white-space: pre-wrap;">{msg.content}</pre></div>'
        self.chat_display.setHtml(html)
        self.chat_display.verticalScrollBar().setValue(self.chat_display.verticalScrollBar().maximum())

class SettingsDialog(QDialog):
    """Settings dialog"""
    settings_changed = Signal(dict)
    
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.settings = current_settings.copy()
        
        layout = QVBoxLayout(self)
        
        # AI Provider settings
        ai_group = QGroupBox("AI Provider")
        ai_layout = QFormLayout(ai_group)
        
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(list(PROVIDERS.keys()))
        self.provider_combo.setCurrentText(current_settings.get("provider", "groq"))
        self.provider_combo.currentTextChanged.connect(self._update_models)
        ai_layout.addRow("Provider:", self.provider_combo)
        
        self.model_combo = QComboBox()
        self._update_models()
        ai_layout.addRow("Model:", self.model_combo)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setText(current_settings.get("api_key", ""))
        ai_layout.addRow("API Key:", self.api_key_input)
        
        layout.addWidget(ai_group)
        
        # Workspace settings
        workspace_group = QGroupBox("Workspace")
        workspace_layout = QHBoxLayout(workspace_group)
        
        self.workspace_input = QLineEdit()
        self.workspace_input.setText(current_settings.get("workspace", str(Path.home())))
        workspace_layout.addWidget(self.workspace_input)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_workspace)
        workspace_layout.addWidget(browse_btn)
        
        layout.addWidget(workspace_group)
        
        # Feature toggles
        features_group = QGroupBox("Features")
        features_layout = QFormLayout(features_group)
        
        self.voice_checkbox = QCheckBox()
        self.voice_checkbox.setChecked(current_settings.get("voice_enabled", True))
        features_layout.addRow("Voice Control:", self.voice_checkbox)
        
        self.browser_checkbox = QCheckBox()
        self.browser_checkbox.setChecked(current_settings.get("browser_enabled", True))
        features_layout.addRow("Browser Automation:", self.browser_checkbox)
        
        layout.addWidget(features_group)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _update_models(self):
        provider = self.provider_combo.currentText()
        models = PROVIDERS.get(provider, {}).get("models", [])
        self.model_combo.clear()
        self.model_combo.addItems(models)
    
    def _browse_workspace(self):
        path = QFileDialog.getExistingDirectory(self, "Select Workspace")
        if path:
            self.workspace_input.setText(path)
    
    def _save(self):
        self.settings = {
            "provider": self.provider_combo.currentText(),
            "model": self.model_combo.currentText(),
            "api_key": self.api_key_input.text(),
            "workspace": self.workspace_input.text(),
            "voice_enabled": self.voice_checkbox.isChecked(),
            "browser_enabled": self.browser_checkbox.isChecked()
        }
        self.settings_changed.emit(self.settings)
        self.accept()

# ============== MAIN WINDOW ==============
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sentience - Local AI Computer")
        self.setMinimumSize(1400, 900)
        
        self.settings = self._load_settings()
        self.messages: List[Dict] = []
        self.ai_client = None
        self.current_file = None
        
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_statusbar()
        self._init_ai()
        self._apply_dark_theme()
    
    def _load_settings(self) -> dict:
        if SETTINGS_PATH.exists():
            try:
                return json.loads(SETTINGS_PATH.read_text())
            except:
                pass
        return DEFAULT_SETTINGS.copy()
    
    def _save_settings(self, settings: dict):
        self.settings.update(settings)
        SETTINGS_PATH.write_text(json.dumps(self.settings, indent=2))
        self._init_ai()
        self.statusBar().showMessage("Settings saved", 3000)
    
    def _init_ai(self):
        provider = self.settings.get("provider", "groq")
        model = self.settings.get("model", "llama-3.3-70b-versatile")
        api_key = self.settings.get("api_key", "") or os.getenv(f"{provider.upper()}_API_KEY", "")
        self.ai_client = AIClient(provider, model, api_key)
    
    def _setup_menubar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        new_action = QAction("New File", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_file)
        file_menu.addAction(new_action)
        
        open_action = QAction("Open File", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        browser_action = QAction("Browser Automation", self)
        browser_action.triggered.connect(self._show_browser_status)
        tools_menu.addAction(browser_action)
        
        email_action = QAction("Email Setup", self)
        email_action.triggered.connect(self._setup_email)
        tools_menu.addAction(email_action)
        
        voice_action = QAction("Voice Control", self)
        voice_action.triggered.connect(self._toggle_voice)
        tools_menu.addAction(voice_action)
        
        server_action = QAction("Start Local Server", self)
        server_action.triggered.connect(self._start_server)
        tools_menu.addAction(server_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        
        toolbar.addAction("New", self._new_file)
        toolbar.addAction("Open", self._open_file)
        toolbar.addAction("Save", self._save_file)
        toolbar.addSeparator()
        toolbar.addAction("Settings", self._open_settings)
        toolbar.addAction("Voice", self._toggle_voice)
    
    def _setup_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - File tree
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.file_tree = FileTreeWidget()
        self.file_tree.file_opened.connect(self._open_file_path)
        self.file_tree.load_directory(self.settings.get("workspace", str(Path.home())))
        left_layout.addWidget(self.file_tree)
        
        splitter.addWidget(left_panel)
        
        # Middle panel - Editor/Terminal tabs
        middle_panel = QTabWidget()
        
        self.code_editor = CodeEditor()
        middle_panel.addTab(self.code_editor, "Editor")
        
        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setFont(QFont("Consolas", 10))
        self.terminal_output.setStyleSheet("background: #1e1e1e; color: #ffffff;")
        middle_panel.addTab(self.terminal_output, "Terminal")
        
        splitter.addWidget(middle_panel)
        
        # Right panel - Chat
        self.chat_widget = ChatWidget()
        self.chat_widget.message_sent.connect(self._handle_chat)
        splitter.addWidget(self.chat_widget)
        
        splitter.setSizes([250, 550, 500])
        layout.addWidget(splitter)
    
    def _setup_statusbar(self):
        status = self.statusBar()
        status.showMessage("Ready")
        
        self.provider_label = QLabel(f"Provider: {self.settings.get('provider', 'groq')}")
        status.addPermanentWidget(self.provider_label)
        
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: green;")
        status.addPermanentWidget(self.status_indicator)
    
    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QMenuBar { background-color: #2d2d2d; color: #ffffff; }
            QMenuBar::item:selected { background-color: #094771; }
            QMenu { background-color: #2d2d2d; color: #ffffff; }
            QMenu::item:selected { background-color: #094771; }
            QToolBar { background-color: #2d2d2d; color: #ffffff; border: none; padding: 4px; }
            QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #ffffff; padding: 8px 16px; border: 1px solid #3c3c3c; }
            QTabBar::tab:selected { background: #1e1e1e; border-bottom: none; }
            QStatusBar { background-color: #007acc; color: #ffffff; }
        """)
    
    # Actions
    def _new_file(self):
        self.code_editor.clear()
        self.current_file = None
    
    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File")
        if path:
            self._open_file_path(path)
    
    def _open_file_path(self, path: str):
        try:
            content = Path(path).read_text()
            self.code_editor.setPlainText(content)
            self.current_file = path
            self.statusBar().showMessage(f"Opened: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file: {e}")
    
    def _save_file(self):
        if self.current_file:
            Path(self.current_file).write_text(self.code_editor.toPlainText())
            self.statusBar().showMessage(f"Saved: {self.current_file}", 3000)
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Save File")
            if path:
                Path(path).write_text(self.code_editor.toPlainText())
                self.current_file = path
                self.statusBar().showMessage(f"Saved: {path}", 3000)
    
    def _open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.settings_changed.connect(self._save_settings)
        dialog.exec()
    
    def _show_browser_status(self):
        if PLAYWRIGHT_AVAILABLE:
            QMessageBox.information(self, "Browser", "Browser automation is available!\n\nUse commands like:\n- browser_navigate\n- browser_click\n- browser_screenshot")
        else:
            QMessageBox.warning(self, "Browser", "Browser automation not available.\n\nInstall: pip install playwright\nThen run: playwright install chromium")
    
    def _setup_email(self):
        email, ok = QInputDialog.getText(self, "Email Setup", "Enter your email address:")
        if ok and email:
            password, ok = QInputDialog.getText(self, "Email Setup", "Enter app password:", QLineEdit.Password)
            if ok:
                result = init_email(self.settings.get("email_provider", "gmail"), email, password)
                if result["success"]:
                    QMessageBox.information(self, "Email", "Email connected successfully!")
                else:
                    QMessageBox.warning(self, "Email", f"Failed to connect: {result}")
    
    def _toggle_voice(self):
        vc = get_voice_controller()
        if vc.is_listening:
            vc.stop_listening()
            self.statusBar().showMessage("Voice control stopped")
        else:
            vc.listen_continuous(lambda text: self._handle_chat(text))
            self.statusBar().showMessage("Listening for voice commands...")
    
    def _start_server(self):
        server = get_hosting_server()
        if server.is_running:
            asyncio.run(server.stop())
            self.statusBar().showMessage("Server stopped")
        else:
            result = asyncio.run(server.start())
            if result["success"]:
                self.statusBar().showMessage(f"Server running at {result['url']}")
            else:
                QMessageBox.warning(self, "Server", f"Failed to start: {result}")
    
    def _show_about(self):
        QMessageBox.about(self, "About Sentience",
            "<h2>Sentience v1.0</h2>"
            "<p>Local AI Computer - Like Cursor/Zo for your machine</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>BYOK - Bring your own API key</li>"
            "<li>Browser automation (Playwright)</li>"
            "<li>Email integration (IMAP/SMTP)</li>"
            "<li>Voice control</li>"
            "<li>Skills system</li>"
            "<li>Local hosting server</li>"
            "<li>File editing with AI assistance</li>"
            "<li>Shell command execution</li>"
            "<li>100% local with Ollama</li>"
            "</ul>"
        )
    
    def _handle_chat(self, text: str):
        """Handle chat message"""
        self.chat_widget.add_message("user", text)
        self.messages.append({"role": "user", "content": text})
        self._process_ai(text)
    
    def _process_ai(self, user_input: str):
        """Process user input with AI"""
        if not self.ai_client:
            self.chat_widget.add_message("assistant", "Error: AI client not configured. Check settings.")
            return
        
        system_msg = {
            "role": "system",
            "content": f"""You are Sentience, a helpful AI assistant with access to tools.
You can read files, write files, list directories, run commands, search files, browse the web, send emails, and more.
Current workspace: {self.settings.get('workspace', Path.home())}
Help the user accomplish their tasks. Use tools when needed.
Be concise and helpful."""
        }
        
        messages = [system_msg] + self.messages[-10:]
        
        self.statusBar().showMessage("Thinking...")
        
        try:
            response = self.ai_client.chat(messages, ALL_TOOLS)
            
            if "error" in response:
                self.chat_widget.add_message("assistant", f"Error: {response['error']}")
                return
            
            if "choices" in response:
                msg = response["choices"][0]["message"]
            else:
                msg = response.get("content", [{}])[0]
                if isinstance(msg, dict):
                    msg = {"content": msg.get("text", "")}
            
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            
            if tool_calls:
                tool_results = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args = json.loads(fn.get("arguments", "{}"))
                    
                    result = execute_tool(name, args, self.settings.get("workspace", str(Path.home())))
                    tool_results.append({"tool_call_id": tc.get("id"), "role": "tool", "content": json.dumps(result)})
                    
                    self.chat_widget.add_message("assistant", f"🔧 Executed: {name}\nResult: {json.dumps(result, indent=2)[:500]}")
                
                messages.append(msg)
                messages.extend(tool_results)
                
                response = self.ai_client.chat(messages, ALL_TOOLS)
                if "choices" in response:
                    content = response["choices"][0]["message"].get("content", "")
            
            if content:
                self.chat_widget.add_message("assistant", content)
                self.messages.append({"role": "assistant", "content": content})
        
        except Exception as e:
            self.chat_widget.add_message("assistant", f"Error: {str(e)}")
        
        self.statusBar().showMessage("Ready")

# ============== MAIN ==============
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
