#!/usr/bin/env python3
"""Sentience Desktop App with all features - PySide6."""
import os, sys, json, time, webbrowser
from threading import Thread
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel, QTabWidget, QListWidget, QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QDialog, QFormLayout, QComboBox, QSpinBox, QCheckBox, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QAction

class SentienceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sentience — Local AI Computer")
        self.setMinimumSize(1200, 800)
        self.agent = None
        self.conversations = {}
        self.current_conv = "default"
        self.server_thread = None
        self.init_ui()
        self.start_server()
    
    def start_server(self):
        def run():
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            import server
        self.server_thread = Thread(target=run, daemon=True)
        self.server_thread.start()
        QTimer.singleShot(2000, lambda: self.statusBar().showMessage("Sentience AI ready"))
    
    def init_ui(self):
        self.dark_palette()
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        
        # Left sidebar - conversations + tools
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("<b>Conversations</b>"))
        self.conv_list = QListWidget()
        self.conv_list.addItems(["default"])
        left_layout.addWidget(self.conv_list)
        
        tabs = QTabWidget()
        tabs.addTab(self.build_tools_tab(), "Tools")
        tabs.addTab(self.build_forms_tab(), "Forms")
        tabs.addTab(self.build_kb_tab(), "Knowledge")
        tabs.addTab(self.build_tasks_tab(), "Tasks")
        tabs.addTab(self.build_settings_tab(), "Settings")
        left_layout.addWidget(tabs)
        left.setMaximumWidth(300)
        
        # Center - chat
        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        center_layout.addWidget(self.chat_display)
        
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask anything... (Ctrl+Enter to send)")
        self.input_field.returnPressed.connect(self.send_message)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        center_layout.addLayout(input_layout)
        
        # Right sidebar - knowledge + context
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("<b>Context</b>"))
        self.context_tree = QTreeWidget()
        self.context_tree.setHeaderLabels(["Key", "Value"])
        right_layout.addWidget(self.context_tree)
        right.setMaximumWidth(300)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)
    
    def build_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("<b>Tool Categories</b>"))
        list_widget = QListWidget()
        categories = [
            "Filesystem (read_file, write_file, glob, grep)",
            "Code (write_code, run_code, debug, review)",
            "Web (fetch_page, search, download, scrape)",
            "Browser (open_url, click, type, scroll, screenshot)",
            "Data (analyze, compare, summarize, extract)",
            "Email (send_email, check_inbox, auto_reply)",
            "Calendar (create_event, list_events, check_schedule)",
            "Cloud (upload, download, sync, list_files)",
            "Remote (ssh, sftp, execute_remote)",
            "Forms (auto_fill, create_template, extract_fields)",
            "Knowledge (kb_add, kb_search, kb_update)",
            "Automation (schedule, trigger, workflow)",
        ]
        list_widget.addItems(categories)
        layout.addWidget(list_widget)
        return tab
    
    def build_forms_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("<b>Form Templates</b>"))
        self.forms_list = QListWidget()
        from forms.engine import list_available_templates
        self.forms_list.addItems(list_available_templates())
        layout.addWidget(self.forms_list)
        fill_btn = QPushButton("Auto-Fill Selected Form")
        fill_btn.clicked.connect(self.auto_fill_form)
        layout.addWidget(fill_btn)
        return tab
    
    def build_kb_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("<b>Knowledge Base</b>"))
        self.kb_search = QLineEdit()
        self.kb_search.setPlaceholderText("Search knowledge...")
        self.kb_search.returnPressed.connect(self.search_kb)
        layout.addWidget(self.kb_search)
        self.kb_results = QListWidget()
        layout.addWidget(self.kb_results)
        return tab
    
    def build_tasks_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("<b>Background Tasks</b>"))
        self.tasks_table = QTableWidget()
        self.tasks_table.setColumnCount(4)
        self.tasks_table.setHorizontalHeaderLabels(["ID", "Instruction", "Status", "Created"])
        layout.addWidget(self.tasks_table)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_tasks)
        layout.addWidget(refresh_btn)
        return tab
    
    def build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("<b>BYOK Provider Settings</b>"))
        
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["anthropic", "openai", "groq", "ollama", "lmstudio"])
        form.addRow("Provider:", self.provider_combo)
        
        self.api_key_field = QLineEdit()
        self.api_key_field.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", self.api_key_field)
        
        self.model_field = QLineEdit()
        self.model_field.setText("claude-sonnet-4")
        form.addRow("Model:", self.model_field)
        
        layout.addLayout(form)
        
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addWidget(QLabel("<b>Hosting Settings</b>"))
        hosting_layout = QHBoxLayout()
        self.port_field = QSpinBox()
        self.port_field.setValue(3132)
        self.port_field.setRange(1024, 65535)
        hosting_layout.addWidget(QLabel("Port:"))
        hosting_layout.addWidget(self.port_field)
        layout.addLayout(hosting_layout)
        
        self.cloud_enabled = QCheckBox("Enable cloud sync")
        layout.addWidget(self.cloud_enabled)
        
        self.remote_enabled = QCheckBox("Enable remote access")
        layout.addWidget(self.remote_enabled)
        
        layout.addStretch()
        return tab
    
    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.chat_display.append(f"<b>You:</b> {text}")
        self.input_field.clear()
        try:
            import requests
            resp = requests.post("http://localhost:3132/api/chat", json={"message": text, "conversation_id": self.current_conv}, timeout=60)
            result = resp.json()
            response = result.get("response", "No response")
            self.chat_display.append(f"<b>Sentience:</b> {response}")
        except Exception as e:
            self.chat_display.append(f"<b>Error:</b> {str(e)}")
    
    def auto_fill_form(self):
        current = self.forms_list.currentItem()
        if current:
            QMessageBox.information(self, "Auto-Fill", f"Form '{current.text()}' selected. Sentience will auto-fill using your reference documents.")
    
    def search_kb(self):
        from knowledge.engine import KnowledgeBase
        kb = KnowledgeBase()
        results = kb.search(self.kb_search.text())
        self.kb_results.clear()
        for r in results:
            self.kb_results.addItem(f"{r.entry.title} (score: {r.score:.1f})")
    
    def refresh_tasks(self):
        try:
            import requests
            resp = requests.get("http://localhost:3132/api/tasks", timeout=5)
            tasks = resp.json().get("tasks", [])
            self.tasks_table.setRowCount(len(tasks))
            for i, t in enumerate(tasks):
                self.tasks_table.setItem(i, 0, QTableWidgetItem(t.get("id","")[:8]))
                self.tasks_table.setItem(i, 1, QTableWidgetItem(t.get("instruction","")[:40]))
                self.tasks_table.setItem(i, 2, QTableWidgetItem(t.get("status","")))
                import datetime
                ts = t.get("created_at", 0)
                self.tasks_table.setItem(i, 3, QTableWidgetItem(datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""))
        except:
            pass
    
    def save_settings(self):
        settings = {
            "provider": self.provider_combo.currentText(),
            "api_key": self.api_key_field.text(),
            "model": self.model_field.text(),
            "port": self.port_field.value(),
            "cloud_sync": self.cloud_enabled.isChecked(),
            "remote_access": self.remote_enabled.isChecked(),
        }
        with open("sentience_settings.json", "w") as f:
            json.dump(settings, f)
        QMessageBox.information(self, "Settings", "Settings saved!")
    
    def dark_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(20, 20, 20))
        palette.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
        palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
        palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(50, 50, 50))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.Highlight, QColor(70, 130, 180))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SentienceApp()
    window.show()
    sys.exit(app.exec())
