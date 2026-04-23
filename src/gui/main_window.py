"""
Sentience v3.0 - Main IDE Window
Complete IDE window with editor, sidebars, terminal, and all panels
"""

import os
import sys
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QTabBar, QMenuBar, QMenu, QToolBar,
    QStatusBar, QLabel, QPushButton, QFileDialog, QMessageBox,
    QProgressDialog, QComboBox, QFrame, QShortcut, QSizePolicy,
    QDockWidget, QListWidget, QListWidgetItem, QScrollArea,
    QTextEdit, QLineEdit, QDialog, QDialogButtonBox
)
from PySide6.QtGui import (
    QAction, QActionGroup, QIcon, QKeySequence, QFont, QColor,
    QPalette, QCursor, QTextDocument, QTextCursor
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QTimer, QSize, QSettings, QEvent,
    QFileSystemWatcher, QThread
)

from .styles import (
    ThemeColors, DarkPalette, apply_dark_theme, MAIN_STYLESHEET,
    get_editor_font, get_ui_font
)
from .editor import CodeEditor
from .sidebar import LeftSidebar, RightSidebar
from .terminal import TerminalPanel
from .chat_panel import AIChatPanel, ChatMessage, MessageRole


class EditorTabWidget(QTabWidget):
    """Custom tab widget for editor tabs"""
    
    tab_close_requested = Signal(int)
    tab_reordered = Signal(int, int)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setElideMode(Qt.ElideMiddle)
        
        # Custom tab bar
        self.tab_bar = QTabBar()
        self.setTabBar(self.tab_bar)
        
        # Styling
        self.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {ThemeColors.BACKGROUND};
            }}
            
            QTabBar::tab {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                color: {ThemeColors.FOREGROUND_DIM};
                padding: 8px 16px;
                margin-right: 1px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                min-width: 100px;
                max-width: 200px;
            }}
            
            QTabBar::tab:selected {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.FOREGROUND};
            }}
            
            QTabBar::tab:hover:!selected {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
            }}
            
            QTabBar::close-button {{
                image: none;
                subcontrol-position: right;
                margin-right: 4px;
            }}
            
            QTabBar::close-button:hover {{
                background-color: {ThemeColors.ERROR};
                border-radius: 2px;
            }}
        """)
        
        # Connect signals
        self.tabCloseRequested.connect(self._on_tab_close)
    
    def _on_tab_close(self, index: int):
        """Handle tab close request"""
        self.tab_close_requested.emit(index)


class ProblemsPanel(QWidget):
    """Panel showing problems and errors"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the problems panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        title = QLabel("PROBLEMS")
        title.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        header_layout.addWidget(title)
        
        # Problem counts
        self.errors_label = QLabel("0 Errors")
        self.errors_label.setStyleSheet("color: #f14c4c; font-size: 11px;")
        header_layout.addWidget(self.errors_label)
        
        self.warnings_label = QLabel("0 Warnings")
        self.warnings_label.setStyleSheet("color: #cca700; font-size: 11px;")
        header_layout.addWidget(self.warnings_label)
        
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Problems list
        self.problems_list = QListWidget()
        self.problems_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                color: {ThemeColors.FOREGROUND};
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
            QListWidget::item:selected {{
                background-color: {ThemeColors.SELECTION};
            }}
        """)
        layout.addWidget(self.problems_list)
    
    def add_problem(self, file: str, line: int, message: str, severity: str = "error"):
        """Add a problem to the list"""
        icon = "❌" if severity == "error" else "⚠️"
        item = QListWidgetItem(f"{icon} {file}:{line} - {message}")
        item.setData(Qt.UserRole, {'file': file, 'line': line, 'message': message, 'severity': severity})
        self.problems_list.addItem(item)
        
        self._update_counts()
    
    def clear_problems(self):
        """Clear all problems"""
        self.problems_list.clear()
        self._update_counts()
    
    def _update_counts(self):
        """Update problem counts"""
        errors = 0
        warnings = 0
        
        for i in range(self.problems_list.count()):
            item = self.problems_list.item(i)
            data = item.data(Qt.UserRole)
            if data['severity'] == 'error':
                errors += 1
            else:
                warnings += 1
        
        self.errors_label.setText(f"{errors} Errors")
        self.warnings_label.setText(f"{warnings} Warnings")


class OutputPanel(QWidget):
    """Panel showing output from various sources"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the output panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with tabs
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        # Output source selector
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Output", "Debug", "Build", "Test"])
        self.source_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
                color: {ThemeColors.FOREGROUND};
                border: none;
                padding: 4px 8px;
            }}
        """)
        header_layout.addWidget(self.source_combo)
        
        header_layout.addStretch()
        
        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #858585;
                border: none;
            }}
            QPushButton:hover {{
                color: {ThemeColors.FOREGROUND};
            }}
        """)
        clear_btn.clicked.connect(self._clear_output)
        header_layout.addWidget(clear_btn)
        
        layout.addWidget(header)
        
        # Output text
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(get_editor_font())
        self.output_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #0c0c0c;
                color: #d3d7cf;
                border: none;
            }}
        """)
        layout.addWidget(self.output_text)
    
    def append_output(self, text: str, source: str = "Output"):
        """Append text to output"""
        self.output_text.append(text)
    
    def _clear_output(self):
        """Clear the output"""
        self.output_text.clear()


class FindReplaceDialog(QDialog):
    """Find and replace dialog"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setWindowTitle("Find and Replace")
        self.setMinimumWidth(400)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Find input
        find_label = QLabel("Find:")
        layout.addWidget(find_label)
        
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Search text...")
        layout.addWidget(self.find_input)
        
        # Replace input
        replace_label = QLabel("Replace:")
        layout.addWidget(replace_label)
        
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with...")
        layout.addWidget(self.replace_input)
        
        # Options
        options = QWidget()
        options_layout = QHBoxLayout(options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        self.case_sensitive = QCheckBox("Case Sensitive")
        options_layout.addWidget(self.case_sensitive)
        
        self.whole_word = QCheckBox("Whole Word")
        options_layout.addWidget(self.whole_word)
        
        self.regex = QCheckBox("Regex")
        options_layout.addWidget(self.regex)
        
        layout.addWidget(options)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Find | 
            QDialogButtonBox.Replace | 
            QDialogButtonBox.ReplaceAll |
            QDialogButtonBox.Close
        )
        
        button_box.button(QDialogButtonBox.Find).clicked.connect(self._find)
        button_box.button(QDialogButtonBox.Replace).clicked.connect(self._replace)
        button_box.button(QDialogButtonBox.ReplaceAll).clicked.connect(self._replace_all)
        button_box.button(QDialogButtonBox.Close).clicked.connect(self.close)
        
        layout.addWidget(button_box)
    
    def _find(self):
        """Find next occurrence"""
        # Signal to parent window
        pass
    
    def _replace(self):
        """Replace current occurrence"""
        pass
    
    def _replace_all(self):
        """Replace all occurrences"""
        pass


class MainWindow(QMainWindow):
    """Main IDE window"""
    
    # Signals
    file_opened = Signal(str)
    file_saved = Signal(str)
    project_opened = Signal(str)
    
    def __init__(self, project_path: Optional[str] = None):
        super().__init__()
        
        # Window properties
        self.setWindowTitle("Sentience v3.0")
        self.setMinimumSize(1200, 800)
        
        # State
        self.open_files: Dict[str, CodeEditor] = {}
        self.current_file: Optional[str] = None
        self.project_path: Optional[str] = project_path
        self.recent_files: List[str] = []
        self.recent_projects: List[str] = []
        self.settings = QSettings('Sentience', 'IDE')
        
        # AI state
        self.ai_connected = False
        self.ai_model = "GPT-4o"
        
        # Setup
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_statusbar()
        self._setup_docks()
        self._setup_shortcuts()
        self._setup_watcher()
        self._load_settings()
        
        # Open project if provided
        if project_path and os.path.isdir(project_path):
            self.open_project(project_path)
    
    def _setup_menubar(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_action = QAction("&New File", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)
        
        open_action = QAction("&Open File...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        open_folder_action = QAction("Open &Folder...", self)
        open_folder_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_K, Qt.CTRL | Qt.Key_O))
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)
        
        file_menu.addSeparator()
        
        self.recent_menu = file_menu.addMenu("Recent Files")
        
        file_menu.addSeparator()
        
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_current_file)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)
        
        save_all_action = QAction("Save All", self)
        save_all_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_S))
        save_all_action.triggered.connect(self.save_all_files)
        file_menu.addAction(save_all_action)
        
        file_menu.addSeparator()
        
        close_action = QAction("&Close", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close_current_tab)
        file_menu.addAction(close_action)
        
        close_all_action = QAction("Close All", self)
        close_all_action.triggered.connect(self.close_all_tabs)
        file_menu.addAction(close_all_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._editor_action('undo'))
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._editor_action('redo'))
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        cut_action.triggered.connect(self._editor_action('cut'))
        edit_menu.addAction(cut_action)
        
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self._editor_action('copy'))
        edit_menu.addAction(copy_action)
        
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(self._editor_action('paste'))
        edit_menu.addAction(paste_action)
        
        edit_menu.addSeparator()
        
        find_action = QAction("&Find...", self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.show_find_dialog)
        edit_menu.addAction(find_action)
        
        replace_action = QAction("&Replace...", self)
        replace_action.setShortcut(QKeySequence.StandardKey.Replace)
        replace_action.triggered.connect(self.show_replace_dialog)
        edit_menu.addAction(replace_action)
        
        edit_menu.addSeparator()
        
        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self._editor_action('selectAll'))
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        toggle_comment_action = QAction("Toggle Comment", self)
        toggle_comment_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_Slash))
        toggle_comment_action.triggered.connect(self._editor_action('toggle_comment'))
        edit_menu.addAction(toggle_comment_action)
        
        duplicate_line_action = QAction("Duplicate Line", self)
        duplicate_line_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_D))
        duplicate_line_action.triggered.connect(self._editor_action('duplicate_line'))
        edit_menu.addAction(duplicate_line_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        # Toggle sidebars
        toggle_left_action = QAction("Toggle Left Sidebar", self)
        toggle_left_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_B))
        toggle_left_action.triggered.connect(lambda: self.left_sidebar.setVisible(not self.left_sidebar.isVisible()))
        view_menu.addAction(toggle_left_action)
        
        toggle_right_action = QAction("Toggle Right Sidebar", self)
        toggle_right_action.triggered.connect(lambda: self.right_sidebar.setVisible(not self.right_sidebar.isVisible()))
        view_menu.addAction(toggle_right_action)
        
        toggle_terminal_action = QAction("Toggle Terminal", self)
        toggle_terminal_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_`))
        toggle_terminal_action.triggered.connect(self._toggle_terminal)
        view_menu.addAction(toggle_terminal_action)
        
        view_menu.addSeparator()
        
        # Zoom
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)
        
        reset_zoom_action = QAction("Reset Zoom", self)
        reset_zoom_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_0))
        reset_zoom_action.triggered.connect(self.reset_zoom)
        view_menu.addAction(reset_zoom_action)
        
        view_menu.addSeparator()
        
        full_screen_action = QAction("Full Screen", self)
        full_screen_action.setShortcut(QKeySequence(Qt.Key_F11))
        full_screen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(full_screen_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        run_action = QAction("&Run", self)
        run_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_F5))
        run_action.triggered.connect(self.run_file)
        tools_menu.addAction(run_action)
        
        build_action = QAction("&Build", self)
        build_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_B))
        build_action.triggered.connect(self.build_project)
        tools_menu.addAction(build_action)
        
        tools_menu.addSeparator()
        
        lint_action = QAction("Lint", self)
        lint_action.setShortcut(QKeySequence(Qt.ALT | Qt.SHIFT | Qt.Key_L))
        lint_action.triggered.connect(self.lint_files)
        tools_menu.addAction(lint_action)
        
        format_action = QAction("Format Document", self)
        format_action.setShortcut(QKeySequence(Qt.ALT | Qt.SHIFT | Qt.Key_F))
        format_action.triggered.connect(self.format_document)
        tools_menu.addAction(format_action)
        
        tools_menu.addSeparator()
        
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self.show_settings)
        tools_menu.addAction(settings_action)
        
        # AI menu
        ai_menu = menubar.addMenu("&AI")
        
        chat_action = QAction("Open AI Chat", self)
        chat_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_C))
        chat_action.triggered.connect(self._focus_ai_chat)
        ai_menu.addAction(chat_action)
        
        ai_menu.addSeparator()
        
        explain_action = QAction("Explain Code", self)
        explain_action.setShortcut(QKeySequence(Qt.CTRL | Qt.ALT | Qt.Key_E))
        explain_action.triggered.connect(self.ai_explain_code)
        ai_menu.addAction(explain_action)
        
        refactor_action = QAction("Refactor Code", self)
        refactor_action.setShortcut(QKeySequence(Qt.CTRL | Qt.ALT | Qt.Key_R))
        refactor_action.triggered.connect(self.ai_refactor_code)
        ai_menu.addAction(refactor_action)
        
        fix_action = QAction("Fix Issues", self)
        fix_action.setShortcut(QKeySequence(Qt.CTRL | Qt.ALT | Qt.Key_F))
        fix_action.triggered.connect(self.ai_fix_issues)
        ai_menu.addAction(fix_action)
        
        ai_menu.addSeparator()
        
        model_menu = ai_menu.addMenu("Model")
        
        model_group = QActionGroup(self)
        models = ["GPT-4o", "GPT-4o-mini", "Claude 3.5 Sonnet", "Claude 3 Opus", "Gemini 1.5 Pro"]
        for model in models:
            action = QAction(model, self, checkable=True)
            action.setChecked(model == self.ai_model)
            action.triggered.connect(lambda checked, m=model: self.set_ai_model(m))
            model_group.addAction(action)
            model_menu.addAction(action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        docs_action = QAction("&Documentation", self)
        docs_action.setShortcut(QKeySequence(Qt.Key_F1))
        docs_action.triggered.connect(self.show_docs)
        help_menu.addAction(docs_action)
        
        help_menu.addSeparator()
        
        report_action = QAction("Report Issue", self)
        report_action.triggered.connect(self.report_issue)
        help_menu.addAction(report_action)
    
    def _setup_toolbar(self):
        """Setup the toolbar"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)
        
        # File actions
        toolbar.addAction(QAction("📄", self, toolTip="New File", triggered=self.new_file))
        toolbar.addAction(QAction("📂", self, toolTip="Open File", triggered=self.open_file))
        toolbar.addAction(QAction("💾", self, toolTip="Save", triggered=self.save_current_file))
        
        toolbar.addSeparator()
        
        # Edit actions
        toolbar.addAction(QAction("↩", self, toolTip="Undo", triggered=self._editor_action('undo')))
        toolbar.addAction(QAction("↪", self, toolTip="Redo", triggered=self._editor_action('redo')))
        
        toolbar.addSeparator()
        
        # Run actions
        toolbar.addAction(QAction("▶", self, toolTip="Run", triggered=self.run_file))
        toolbar.addAction(QAction("⏹", self, toolTip="Stop", triggered=self.stop_running))
        toolbar.addAction(QAction("🔨", self, toolTip="Build", triggered=self.build_project))
        
        toolbar.addSeparator()
        
        # Git actions
        toolbar.addAction(QAction("🔀", self, toolTip="Git", triggered=self.show_git_panel))
        
        toolbar.addSeparator()
        
        # AI actions
        toolbar.addAction(QAction("🤖", self, toolTip="AI Assistant", triggered=self._focus_ai_chat))
        
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        
        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                color: {ThemeColors.FOREGROUND};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        self.search_input.returnPressed.connect(self._search_files)
        toolbar.addWidget(self.search_input)
    
    def _setup_central_widget(self):
        """Setup the central widget"""
        # Main splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.main_splitter)
        
        # Left sidebar
        self.left_sidebar = LeftSidebar()
        self.main_splitter.addWidget(self.left_sidebar)
        
        # Center area
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        # Editor tabs
        self.editor_tabs = EditorTabWidget()
        self.editor_tabs.tab_close_requested.connect(self.close_tab)
        center_layout.addWidget(self.editor_tabs)
        
        # Bottom panel
        self.bottom_splitter = QSplitter(Qt.Vertical)
        self.bottom_splitter.setSizes([1, 0])  # Collapsed by default
        
        # Problems panel
        self.problems_panel = ProblemsPanel()
        self.bottom_splitter.addWidget(self.problems_panel)
        
        # Terminal panel
        self.terminal_panel = TerminalPanel()
        self.bottom_splitter.addWidget(self.terminal_panel)
        
        # Output panel
        self.output_panel = OutputPanel()
        self.bottom_splitter.addWidget(self.output_panel)
        
        center_layout.addWidget(self.bottom_splitter)
        
        self.main_splitter.addWidget(center_widget)
        
        # Right sidebar
        self.right_sidebar = RightSidebar()
        self.main_splitter.addWidget(self.right_sidebar)
        
        # Set splitter sizes
        self.main_splitter.setSizes([250, 800, 250])
        
        # Connect signals
        self.left_sidebar.file_opened.connect(self.open_file)
        self.right_sidebar.outline_item_clicked.connect(self._goto_line)
    
    def _setup_statusbar(self):
        """Setup the status bar"""
        statusbar = self.statusBar()
        
        # Git branch
        self.branch_label = QLabel("main")
        self.branch_label.setStyleSheet("padding: 0 8px;")
        statusbar.addWidget(self.branch_label)
        
        statusbar.addWidget(QLabel("|"))
        
        # Cursor position
        self.cursor_label = QLabel("Ln 1, Col 1")
        self.cursor_label.setStyleSheet("padding: 0 8px;")
        statusbar.addWidget(self.cursor_label)
        
        statusbar.addWidget(QLabel("|"))
        
        # File encoding
        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setStyleSheet("padding: 0 8px;")
        statusbar.addWidget(self.encoding_label)
        
        statusbar.addWidget(QLabel("|"))
        
        # Line ending
        self.line_ending_label = QLabel("LF")
        self.line_ending_label.setStyleSheet("padding: 0 8px;")
        statusbar.addWidget(self.line_ending_label)
        
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        statusbar.addWidget(spacer)
        
        # AI status
        self.ai_status_label = QLabel("AI: Connected")
        self.ai_status_label.setStyleSheet(f"color: {ThemeColors.SUCCESS}; padding: 0 8px;")
        statusbar.addPermanentWidget(self.ai_status_label)
        
        # Language
        self.language_label = QLabel("Python")
        self.language_label.setStyleSheet("padding: 0 8px;")
        statusbar.addPermanentWidget(self.language_label)
    
    def _setup_docks(self):
        """Setup dock widgets"""
        # Terminal dock (alternative to embedded terminal)
        terminal_dock = QDockWidget("Terminal", self)
        terminal_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        terminal_dock.hide()  # Use embedded terminal by default
        self.addDockWidget(Qt.BottomDockWidgetArea, terminal_dock)
    
    def _setup_shortcuts(self):
        """Setup global shortcuts"""
        # Quick open
        quick_open = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_P), self)
        quick_open.activated.connect(self.show_quick_open)
        
        # Command palette
        command_palette = QShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_P), self)
        command_palette.activated.connect(self.show_command_palette)
        
        # Go to line
        goto_line = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_G), self)
        goto_line.activated.connect(self.show_goto_line)
        
        # Save all
        save_all = QShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_S), self)
        save_all.activated.connect(self.save_all_files)
    
    def _setup_watcher(self):
        """Setup file system watcher"""
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
    
    def _load_settings(self):
        """Load settings from previous session"""
        # Recent files
        self.recent_files = self.settings.value('recent_files', [])
        self.recent_projects = self.settings.value('recent_projects', [])
        
        # Window geometry
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        
        state = self.settings.value('window_state')
        if state:
            self.restoreState(state)
        
        # Update recent files menu
        self._update_recent_menu()
    
    def _save_settings(self):
        """Save settings for next session"""
        self.settings.setValue('recent_files', self.recent_files)
        self.settings.setValue('recent_projects', self.recent_projects)
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
    
    def _update_recent_menu(self):
        """Update the recent files menu"""
        self.recent_menu.clear()
        
        for filepath in self.recent_files[:10]:
            action = QAction(os.path.basename(filepath), self)
            action.setData(filepath)
            action.triggered.connect(lambda checked, f=filepath: self.open_file(f))
            self.recent_menu.addAction(action)
    
    def _add_to_recent(self, filepath: str):
        """Add a file to recent files"""
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)
        
        self.recent_files.insert(0, filepath)
        self.recent_files = self.recent_files[:20]
        
        self._update_recent_menu()
    
    # ========================================================================
    # File Operations
    # ========================================================================
    
    def new_file(self):
        """Create a new untitled file"""
        editor = CodeEditor()
        index = self.editor_tabs.addTab(editor, "Untitled")
        self.editor_tabs.setCurrentIndex(index)
        
        # Connect editor signals
        editor.cursor_position_changed.connect(self._update_cursor_position)
        editor.file_modified.connect(lambda m: self._update_tab_title(index, m))
        editor.save_requested.connect(self.save_current_file)
    
    def open_file(self, filepath: Optional[str] = None):
        """Open a file"""
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Open File", "",
                "All Files (*);;Python Files (*.py);;JavaScript Files (*.js);;HTML Files (*.html)"
            )
        
        if not filepath:
            return
        
        # Check if already open
        if filepath in self.open_files:
            editor = self.open_files[filepath]
            index = self.editor_tabs.indexOf(editor)
            self.editor_tabs.setCurrentIndex(index)
            return
        
        # Create editor and load file
        editor = CodeEditor(filepath=filepath)
        if not editor.load_file(filepath):
            QMessageBox.warning(self, "Error", f"Could not open file: {filepath}")
            return
        
        # Add tab
        filename = os.path.basename(filepath)
        index = self.editor_tabs.addTab(editor, filename)
        self.editor_tabs.setCurrentIndex(index)
        
        # Store reference
        self.open_files[filepath] = editor
        self.current_file = filepath
        
        # Watch file for changes
        self.watcher.addPath(filepath)
        
        # Connect signals
        editor.cursor_position_changed.connect(self._update_cursor_position)
        editor.file_modified.connect(lambda m: self._update_tab_title(index, m))
        editor.save_requested.connect(self.save_current_file)
        editor.find_requested.connect(self.show_find_dialog)
        editor.replace_requested.connect(self.show_replace_dialog)
        
        # Update recent files
        self._add_to_recent(filepath)
        
        # Update UI
        self._update_statusbar()
        
        # Parse for outline
        self._update_outline(editor)
        
        # Emit signal
        self.file_opened.emit(filepath)
    
    def open_folder(self, folder_path: Optional[str] = None):
        """Open a folder as a project"""
        if folder_path is None:
            folder_path = QFileDialog.getExistingDirectory(self, "Open Folder")
        
        if not folder_path:
            return
        
        self.project_path = folder_path
        self.setWindowTitle(f"Sentience v3.0 - {os.path.basename(folder_path)}")
        
        # Update sidebars
        self.left_sidebar.set_root_path(folder_path)
        
        # Add to recent projects
        if folder_path in self.recent_projects:
            self.recent_projects.remove(folder_path)
        self.recent_projects.insert(0, folder_path)
        self.recent_projects = self.recent_projects[:10]
        
        # Emit signal
        self.project_opened.emit(folder_path)
    
    def open_project(self, project_path: str):
        """Open a project"""
        self.open_folder(project_path)
    
    def save_current_file(self):
        """Save the current file"""
        editor = self._current_editor()
        if not editor:
            return
        
        if not editor.filepath:
            self.save_file_as()
            return
        
        if editor.save_file():
            index = self.editor_tabs.currentIndex()
            self._update_tab_title(index, False)
            self._add_to_recent(editor.filepath)
            self.file_saved.emit(editor.filepath)
        else:
            QMessageBox.warning(self, "Error", f"Could not save file: {editor.filepath}")
    
    def save_file_as(self):
        """Save file with a new name"""
        editor = self._current_editor()
        if not editor:
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save File As", "",
            "All Files (*);;Python Files (*.py);;JavaScript Files (*.js)"
        )
        
        if not filepath:
            return
        
        if editor.save_file(filepath):
            # Update tab and references
            index = self.editor_tabs.currentIndex()
            self.editor_tabs.setTabText(index, os.path.basename(filepath))
            
            if editor.filepath and editor.filepath in self.open_files:
                del self.open_files[editor.filepath]
            
            self.open_files[filepath] = editor
            self.current_file = filepath
            
            self._add_to_recent(filepath)
            self.file_saved.emit(filepath)
    
    def save_all_files(self):
        """Save all open files"""
        for filepath, editor in self.open_files.items():
            if editor.file_modified_flag:
                editor.save_file()
    
    def close_tab(self, index: int):
        """Close a tab"""
        editor = self.editor_tabs.widget(index)
        if not editor:
            return
        
        # Check for unsaved changes
        if editor.file_modified_flag:
            reply = QMessageBox.question(
                self, "Save Changes?",
                f"Save changes to {editor.filepath or 'Untitled'}?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Save:
                if not editor.filepath:
                    self.save_file_as()
                    if editor.file_modified_flag:  # Save was cancelled
                        return
                else:
                    editor.save_file()
            elif reply == QMessageBox.Cancel:
                return
        
        # Remove from tracking
        if editor.filepath and editor.filepath in self.open_files:
            del self.open_files[editor.filepath]
            if editor.filepath in self.watcher.files():
                self.watcher.removePath(editor.filepath)
        
        # Remove tab
        self.editor_tabs.removeTab(index)
    
    def close_current_tab(self):
        """Close the current tab"""
        self.close_tab(self.editor_tabs.currentIndex())
    
    def close_all_tabs(self):
        """Close all tabs"""
        while self.editor_tabs.count() > 0:
            self.close_tab(0)
    
    # ========================================================================
    # Editor Actions
    # ========================================================================
    
    def _current_editor(self) -> Optional[CodeEditor]:
        """Get the current editor"""
        return self.editor_tabs.currentWidget()
    
    def _editor_action(self, action: str):
        """Return a function that calls an editor action"""
        def execute():
            editor = self._current_editor()
            if editor:
                getattr(editor, action)()
        return execute
    
    def _update_tab_title(self, index: int, modified: bool):
        """Update tab title to show modified state"""
        editor = self.editor_tabs.widget(index)
        if not editor:
            return
        
        filename = os.path.basename(editor.filepath) if editor.filepath else "Untitled"
        title = f"● {filename}" if modified else filename
        self.editor_tabs.setTabText(index, title)
    
    def _update_cursor_position(self, line: int, column: int):
        """Update cursor position in status bar"""
        self.cursor_label.setText(f"Ln {line}, Col {column}")
    
    def _update_statusbar(self):
        """Update status bar for current file"""
        editor = self._current_editor()
        if not editor:
            return
        
        # Update encoding
        self.encoding_label.setText(editor.encoding)
        
        # Update line ending
        self.line_ending_label.setText(editor.line_ending)
        
        # Update language
        self.language_label.setText(editor._detect_language())
    
    def _update_outline(self, editor: CodeEditor):
        """Update outline panel with editor content"""
        content = editor.toPlainText()
        language = editor._detect_language()
        
        # Find outline panel
        self.right_sidebar.outline_panel.parse_document(content, language.lower())
    
    def _goto_line(self, line: int):
        """Go to a specific line in the editor"""
        editor = self._current_editor()
        if editor:
            editor.goto_line(line)
    
    # ========================================================================
    # UI Actions
    # ========================================================================
    
    def show_find_dialog(self):
        """Show find dialog"""
        dialog = FindReplaceDialog(self)
        dialog.find_input.setFocus()
        dialog.exec()
    
    def show_replace_dialog(self):
        """Show replace dialog"""
        dialog = FindReplaceDialog(self)
        dialog.find_input.setFocus()
        dialog.exec()
    
    def show_quick_open(self):
        """Show quick open dialog"""
        # Placeholder for quick open functionality
        pass
    
    def show_command_palette(self):
        """Show command palette"""
        # Placeholder for command palette
        pass
    
    def show_goto_line(self):
        """Show go to line dialog"""
        editor = self._current_editor()
        if not editor:
            return
        
        # Simple input dialog for now
        from PySide6.QtWidgets import QInputDialog
        line, ok = QInputDialog.getInt(
            self, "Go to Line", "Line number:",
            min=1, max=editor.blockCount()
        )
        
        if ok:
            editor.goto_line(line)
    
    def _toggle_terminal(self):
        """Toggle terminal visibility"""
        sizes = self.bottom_splitter.sizes()
        if sizes[1] == 0:
            self.bottom_splitter.setSizes([400, 200])
        else:
            self.bottom_splitter.setSizes([600, 0])
    
    def zoom_in(self):
        """Zoom in on editor"""
        editor = self._current_editor()
        if editor:
            font = editor.font()
            font.setPointSize(min(font.pointSize() + 1, 32))
            editor.setFont(font)
    
    def zoom_out(self):
        """Zoom out on editor"""
        editor = self._current_editor()
        if editor:
            font = editor.font()
            font.setPointSize(max(font.pointSize() - 1, 6))
            editor.setFont(font)
    
    def reset_zoom(self):
        """Reset editor zoom"""
        editor = self._current_editor()
        if editor:
            editor.setFont(get_editor_font())
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    # ========================================================================
    # Run and Build
    # ========================================================================
    
    def run_file(self):
        """Run the current file"""
        editor = self._current_editor()
        if not editor or not editor.filepath:
            return
        
        # Make terminal visible
        self._toggle_terminal()
        
        # Get terminal and run file
        terminal = self.terminal_panel.get_active_terminal()
        if terminal:
            if editor.filepath.endswith('.py'):
                terminal.send_command(f'python "{editor.filepath}"')
            elif editor.filepath.endswith('.js'):
                terminal.send_command(f'node "{editor.filepath}"')
            elif editor.filepath.endswith('.sh'):
                terminal.send_command(f'bash "{editor.filepath}"')
    
    def stop_running(self):
        """Stop running process"""
        terminal = self.terminal_panel.get_active_terminal()
        if terminal and terminal.process:
            terminal.process.terminate()
    
    def build_project(self):
        """Build the project"""
        if not self.project_path:
            return
        
        # Make terminal visible
        self._toggle_terminal()
        
        terminal = self.terminal_panel.get_active_terminal()
        if terminal:
            terminal.set_working_directory(self.project_path)
            terminal.send_command('python -m build')  # Or npm run build, etc.
    
    def lint_files(self):
        """Lint project files"""
        editor = self._current_editor()
        if editor and editor.filepath.endswith('.py'):
            # Run pylint
            self.output_panel.append_output(f"Linting {editor.filepath}...")
    
    def format_document(self):
        """Format the current document"""
        editor = self._current_editor()
        if editor:
            # Apply simple formatting
            pass
    
    # ========================================================================
    # AI Actions
    # ========================================================================
    
    def _focus_ai_chat(self):
        """Focus the AI chat panel"""
        self.right_sidebar._show_ai_chat()
        self.right_sidebar.ai_chat.input_widget.input_text.setFocus()
    
    def set_ai_model(self, model: str):
        """Set the AI model"""
        self.ai_model = model
        self.ai_status_label.setText(f"AI: {model}")
    
    def ai_explain_code(self):
        """Ask AI to explain current code"""
        editor = self._current_editor()
        if not editor:
            return
        
        # Get selected text or current line
        cursor = editor.textCursor()
        if cursor.hasSelection():
            code = cursor.selectedText()
        else:
            code = editor.toPlainText()
        
        # Send to AI
        self._focus_ai_chat()
        self.right_sidebar.ai_chat.input_widget.input_text.setText(f"Explain this code:\n\n```\n{code}\n```")
    
    def ai_refactor_code(self):
        """Ask AI to refactor current code"""
        editor = self._current_editor()
        if not editor:
            return
        
        cursor = editor.textCursor()
        if cursor.hasSelection():
            code = cursor.selectedText()
        else:
            code = editor.toPlainText()
        
        self._focus_ai_chat()
        self.right_sidebar.ai_chat.input_widget.input_text.setText(f"Refactor this code:\n\n```\n{code}\n```")
    
    def ai_fix_issues(self):
        """Ask AI to fix issues in current code"""
        editor = self._current_editor()
        if not editor:
            return
        
        code = editor.toPlainText()
        
        self._focus_ai_chat()
        self.right_sidebar.ai_chat.input_widget.input_text.setText(f"Fix issues in this code:\n\n```\n{code}\n```")
    
    # ========================================================================
    # Help Actions
    # ========================================================================
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "About Sentience v3.0",
            """<h2>Sentience v3.0</h2>
            <p>A modern IDE with AI-powered features</p>
            <p>Version: 3.0.0</p>
            <p>Built with PySide6</p>
            """
        )
    
    def show_docs(self):
        """Show documentation"""
        # Open documentation in browser or internal viewer
        pass
    
    def report_issue(self):
        """Report an issue"""
        # Open issue tracker
        pass
    
    def show_settings(self):
        """Show settings dialog"""
        # Placeholder for settings dialog
        pass
    
    def show_git_panel(self):
        """Show git panel"""
        self.left_sidebar._show_git()
    
    def _search_files(self):
        """Search for files"""
        query = self.search_input.text()
        if query:
            self.left_sidebar._show_search()
            self.left_sidebar.search_panel.search_input.setText(query)
            self.left_sidebar.search_panel._search()
    
    # ========================================================================
    # Event Handlers
    # ========================================================================
    
    def _on_file_changed(self, filepath: str):
        """Handle file changed on disk"""
        if filepath not in self.open_files:
            return
        
        editor = self.open_files[filepath]
        
        if not editor.file_modified_flag:
            # File was modified externally, prompt to reload
            reply = QMessageBox.question(
                self, "File Changed",
                f"{filepath} was modified on disk. Reload?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                editor.load_file(filepath)
    
    def closeEvent(self, event):
        """Handle window close"""
        # Check for unsaved files
        for filepath, editor in self.open_files.items():
            if editor.file_modified_flag:
                reply = QMessageBox.question(
                    self, "Save Changes?",
                    f"Save changes to {filepath}?",
                    QMessageBox.SaveAll | QMessageBox.DiscardAll | QMessageBox.Cancel
                )
                
                if reply == QMessageBox.SaveAll:
                    self.save_all_files()
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    return
                else:
                    break
        
        # Save settings
        self._save_settings()
        
        event.accept()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    
    # Apply dark theme
    apply_dark_theme(app)
    
    # Create main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
