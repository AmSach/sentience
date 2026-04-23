"""
Sentience v3.0 - Dark Theme Styles
VS Code-inspired dark theme with syntax highlighting
"""

from PySide6.QtGui import QColor, QPalette, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtCore import Qt, QRegularExpression


class ThemeColors:
    """Centralized color definitions for the dark theme"""
    
    # Base colors
    BACKGROUND = "#1e1e1e"
    BACKGROUND_LIGHTER = "#252526"
    BACKGROUND_LIGHT = "#2d2d30"
    BACKGROUND_DARKER = "#181818"
    
    # Text colors
    FOREGROUND = "#d4d4d4"
    FOREGROUND_DIM = "#858585"
    FOREGROUND_BRIGHT = "#ffffff"
    
    # Accent colors
    ACCENT = "#007acc"
    ACCENT_HOVER = "#1c97ea"
    ACCENT_PRESSED = "#005a9e"
    
    # UI colors
    BORDER = "#3c3c3c"
    BORDER_LIGHT = "#474747"
    SELECTION = "#264f78"
    SELECTION_INACTIVE = "#3a3d41"
    
    # Status colors
    SUCCESS = "#4ec9b0"
    WARNING = "#dcdcaa"
    ERROR = "#f14c4c"
    INFO = "#3794ff"
    
    # Syntax colors (Python-inspired)
    SYNTAX_KEYWORD = "#569cd6"      # Blue
    SYNTAX_STRING = "#ce9178"       # Orange-brown
    SYNTAX_COMMENT = "#6a9955"      # Green
    SYNTAX_NUMBER = "#b5cea8"       # Light green
    SYNTAX_FUNCTION = "#dcdcaa"     # Yellow
    SYNTAX_CLASS = "#4ec9b0"        # Teal
    SYNTAX_VARIABLE = "#9cdcfe"     # Light blue
    SYNTAX_OPERATOR = "#d4d4d4"     # Default
    SYNTAX_BUILTIN = "#c586c0"      # Purple
    SYNTAX_DECORATOR = "#dcdcaa"    # Yellow


class DarkPalette(QPalette):
    """Dark palette for the application"""
    
    def __init__(self):
        super().__init__()
        
        # Window colors
        self.setColor(QPalette.Window, QColor(ThemeColors.BACKGROUND))
        self.setColor(QPalette.WindowText, QColor(ThemeColors.FOREGROUND))
        
        # Base colors (for text inputs, etc.)
        self.setColor(QPalette.Base, QColor(ThemeColors.BACKGROUND_DARKER))
        self.setColor(QPalette.AlternateBase, QColor(ThemeColors.BACKGROUND_LIGHTER))
        
        # Text colors
        self.setColor(QPalette.Text, QColor(ThemeColors.FOREGROUND))
        self.setColor(QPalette.BrightText, QColor(ThemeColors.FOREGROUND_BRIGHT))
        
        # Button colors
        self.setColor(QPalette.Button, QColor(ThemeColors.BACKGROUND_LIGHT))
        self.setColor(QPalette.ButtonText, QColor(ThemeColors.FOREGROUND))
        
        # Highlight colors
        self.setColor(QPalette.Highlight, QColor(ThemeColors.SELECTION))
        self.setColor(QPalette.HighlightedText, QColor(ThemeColors.FOREGROUND_BRIGHT))
        
        # Link colors
        self.setColor(QPalette.Link, QColor(ThemeColors.ACCENT))
        self.setColor(QPalette.LinkVisited, QColor(ThemeColors.ACCENT_HOVER))
        
        # Disabled colors
        self.setColor(QPalette.Disabled, QPalette.Text, QColor(ThemeColors.FOREGROUND_DIM))
        self.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(ThemeColors.FOREGROUND_DIM))


# Main stylesheet for the application
MAIN_STYLESHEET = f"""
/* Global Styles */
QWidget {{
    background-color: {ThemeColors.BACKGROUND};
    color: {ThemeColors.FOREGROUND};
    font-family: "Segoe UI", "SF Pro Display", -apple-system, BlinkMacSystemFont;
    font-size: 13px;
}}

/* Main Window */
QMainWindow {{
    background-color: {ThemeColors.BACKGROUND};
}}

/* Menu Bar */
QMenuBar {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border-bottom: 1px solid {ThemeColors.BORDER};
    padding: 2px 4px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 4px 8px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
}}

QMenuBar::item:pressed {{
    background-color: {ThemeColors.ACCENT};
}}

/* Menu */
QMenu {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 6px;
    padding: 4px 0px;
}}

QMenu::item {{
    padding: 6px 32px 6px 16px;
    border-radius: 4px;
    margin: 0px 4px;
}}

QMenu::item:selected {{
    background-color: {ThemeColors.ACCENT};
}}

QMenu::separator {{
    height: 1px;
    background: {ThemeColors.BORDER};
    margin: 4px 8px;
}}

/* Toolbar */
QToolBar {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: none;
    padding: 4px;
    spacing: 4px;
}}

QToolBar::separator {{
    width: 1px;
    background: {ThemeColors.BORDER};
    margin: 4px 8px;
}}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 6px;
}}

QToolButton:hover {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
}}

QToolButton:pressed {{
    background-color: {ThemeColors.BACKGROUND_LIGHT};
}}

QToolButton:checked {{
    background-color: {ThemeColors.ACCENT};
}}

/* Status Bar */
QStatusBar {{
    background-color: {ThemeColors.ACCENT};
    color: {ThemeColors.FOREGROUND_BRIGHT};
    font-size: 12px;
    padding: 2px 8px;
}}

QStatusBar::item {{
    border: none;
}}

QStatusBar QLabel {{
    color: {ThemeColors.FOREGROUND_BRIGHT};
    padding: 0px 8px;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {ThemeColors.BORDER};
    background-color: {ThemeColors.BACKGROUND};
}}

QTabBar::tab {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    color: {ThemeColors.FOREGROUND_DIM};
    padding: 8px 16px;
    margin-right: 1px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}

QTabBar::tab:selected {{
    background-color: {ThemeColors.BACKGROUND};
    color: {ThemeColors.FOREGROUND};
}}

QTabBar::tab:hover:!selected {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
}}

/* Tab Bar (for editor tabs) */
QTabBar {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
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

/* Splitter */
QSplitter::handle {{
    background-color: {ThemeColors.BORDER};
}}

QSplitter::handle:hover {{
    background-color: {ThemeColors.ACCENT};
}}

/* Tree View / List View */
QTreeView, QListView {{
    background-color: {ThemeColors.BACKGROUND};
    border: none;
    outline: none;
}}

QTreeView::item, QListView::item {{
    padding: 4px 8px;
    border-radius: 4px;
}}

QTreeView::item:selected, QListView::item:selected {{
    background-color: {ThemeColors.SELECTION};
}}

QTreeView::item:hover, QListView::item:hover {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
}}

QTreeView::branch {{
    background-color: transparent;
}}

/* Line Edit */
QLineEdit {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    selection-background-color: {ThemeColors.SELECTION};
}}

QLineEdit:focus {{
    border-color: {ThemeColors.ACCENT};
}}

QLineEdit:disabled {{
    background-color: {ThemeColors.BACKGROUND};
    color: {ThemeColors.FOREGROUND_DIM};
}}

/* Text Edit */
QTextEdit, QPlainTextEdit {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: none;
    selection-background-color: {ThemeColors.SELECTION};
    font-family: "Fira Code", "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-size: 14px;
    line-height: 1.5;
}}

/* Scroll Bar */
QScrollBar:vertical {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    width: 10px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border-radius: 5px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {ThemeColors.BORDER_LIGHT};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    height: 10px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border-radius: 5px;
    min-width: 30px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {ThemeColors.BORDER_LIGHT};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* Push Button */
QPushButton {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 4px;
    padding: 6px 16px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {ThemeColors.BACKGROUND_LIGHT};
    border-color: {ThemeColors.BORDER_LIGHT};
}}

QPushButton:pressed {{
    background-color: {ThemeColors.ACCENT_PRESSED};
}}

QPushButton:default {{
    background-color: {ThemeColors.ACCENT};
    border-color: {ThemeColors.ACCENT};
}}

QPushButton:default:hover {{
    background-color: {ThemeColors.ACCENT_HOVER};
}}

/* Combo Box */
QComboBox {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 4px;
    padding: 6px 10px;
}}

QComboBox:hover {{
    border-color: {ThemeColors.BORDER_LIGHT};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
}}

QComboBox QAbstractItemView {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border: 1px solid {ThemeColors.BORDER};
    selection-background-color: {ThemeColors.SELECTION};
}}

/* Spin Box */
QSpinBox, QDoubleSpinBox {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 4px;
    padding: 4px 10px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ThemeColors.ACCENT};
}}

/* Check Box */
QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {ThemeColors.BORDER};
    background-color: {ThemeColors.BACKGROUND_DARKER};
}}

QCheckBox::indicator:checked {{
    background-color: {ThemeColors.ACCENT};
    border-color: {ThemeColors.ACCENT};
}}

QCheckBox::indicator:hover {{
    border-color: {ThemeColors.ACCENT};
}}

/* Radio Button */
QRadioButton {{
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid {ThemeColors.BORDER};
    background-color: {ThemeColors.BACKGROUND_DARKER};
}}

QRadioButton::indicator:checked {{
    background-color: {ThemeColors.ACCENT};
    border-color: {ThemeColors.ACCENT};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: none;
    border-radius: 4px;
    text-align: center;
    height: 8px;
}}

QProgressBar::chunk {{
    background-color: {ThemeColors.ACCENT};
    border-radius: 4px;
}}

/* Slider */
QSlider::groove:horizontal {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {ThemeColors.ACCENT};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {ThemeColors.ACCENT_HOVER};
}}

/* Group Box */
QGroupBox {{
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: {ThemeColors.BACKGROUND};
}}

/* Dock Widget */
QDockWidget {{
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    padding: 8px;
    text-align: left;
}}

/* Frame */
QFrame {{
    border: none;
}}

QFrame[frameShape="4"] {{
    background-color: {ThemeColors.BORDER};
}}

/* Label */
QLabel {{
    background: transparent;
}}

/* Tooltip */
QToolTip {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    color: {ThemeColors.FOREGROUND};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* Custom Classes */
SidebarFrame {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border-right: 1px solid {ThemeColors.BORDER};
}}

PanelHeader {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border-bottom: 1px solid {ThemeColors.BORDER};
    padding: 8px;
    font-weight: bold;
}}

TerminalWidget {{
    background-color: #0c0c0c;
    color: #cccccc;
    font-family: "Cascadia Code", "Fira Code", Consolas, monospace;
}}

ChatMessage {{
    background-color: {ThemeColors.BACKGROUND_LIGHTER};
    border-radius: 8px;
    padding: 12px;
    margin: 4px;
}}

ChatMessage[user="true"] {{
    background-color: {ThemeColors.ACCENT};
}}

CodeBlock {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    border: 1px solid {ThemeColors.BORDER};
    border-radius: 4px;
    font-family: "Fira Code", Consolas, monospace;
}}

EditorLineNumber {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
    color: {ThemeColors.FOREGROUND_DIM};
}}

MinimapWidget {{
    background-color: {ThemeColors.BACKGROUND_DARKER};
}}
"""


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Python code"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.highlighting_rules = []
        
        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(ThemeColors.SYNTAX_KEYWORD))
        keyword_format.setFontWeight(QFont.Bold)
        
        keywords = [
            "and", "as", "assert", "async", "await", "break", "class",
            "continue", "def", "del", "elif", "else", "except", "False",
            "finally", "for", "from", "global", "if", "import", "in",
            "is", "lambda", "None", "nonlocal", "not", "or", "pass",
            "raise", "return", "True", "try", "while", "with", "yield"
        ]
        
        for word in keywords:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self.highlighting_rules.append((pattern, keyword_format))
        
        # Built-in functions
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor(ThemeColors.SYNTAX_BUILTIN))
        
        builtins = [
            "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr",
            "classmethod", "compile", "complex", "delattr", "dict", "dir",
            "divmod", "enumerate", "eval", "exec", "filter", "float", "format",
            "frozenset", "getattr", "globals", "hasattr", "hash", "help", "hex",
            "id", "input", "int", "isinstance", "issubclass", "iter", "len",
            "list", "locals", "map", "max", "memoryview", "min", "next", "object",
            "oct", "open", "ord", "pow", "print", "property", "range", "repr",
            "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod",
            "str", "sum", "super", "tuple", "type", "vars", "zip"
        ]
        
        for word in builtins:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self.highlighting_rules.append((pattern, builtin_format))
        
        # Decorators
        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor(ThemeColors.SYNTAX_DECORATOR))
        pattern = QRegularExpression(r"@\w+")
        self.highlighting_rules.append((pattern, decorator_format))
        
        # Class names
        class_format = QTextCharFormat()
        class_format.setForeground(QColor(ThemeColors.SYNTAX_CLASS))
        pattern = QRegularExpression(r"\bclass\s+(\w+)")
        self.highlighting_rules.append((pattern, class_format))
        
        # Function names
        function_format = QTextCharFormat()
        function_format.setForeground(QColor(ThemeColors.SYNTAX_FUNCTION))
        pattern = QRegularExpression(r"\bdef\s+(\w+)")
        self.highlighting_rules.append((pattern, function_format))
        
        # Function calls
        call_format = QTextCharFormat()
        call_format.setForeground(QColor(ThemeColors.SYNTAX_FUNCTION))
        pattern = QRegularExpression(r"\b(\w+)(?=\s*\()")
        self.highlighting_rules.append((pattern, call_format))
        
        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(ThemeColors.SYNTAX_NUMBER))
        patterns = [
            r"\b[0-9]+\b",
            r"\b0x[0-9A-Fa-f]+\b",
            r"\b0b[01]+\b",
            r"\b0o[0-7]+\b",
            r"\b[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?\b"
        ]
        for p in patterns:
            pattern = QRegularExpression(p)
            self.highlighting_rules.append((pattern, number_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(ThemeColors.SYNTAX_STRING))
        
        # Single quoted strings
        pattern = QRegularExpression(r"'[^']*'")
        self.highlighting_rules.append((pattern, string_format))
        
        # Double quoted strings
        pattern = QRegularExpression(r'"[^"]*"')
        self.highlighting_rules.append((pattern, string_format))
        
        # Triple quoted strings (single line for simplicity)
        pattern = QRegularExpression(r"'''[^']*'''")
        self.highlighting_rules.append((pattern, string_format))
        
        pattern = QRegularExpression(r'"""[^"]*"""')
        self.highlighting_rules.append((pattern, string_format))
        
        # F-strings
        pattern = QRegularExpression(r'f"[^"]*"')
        self.highlighting_rules.append((pattern, string_format))
        
        pattern = QRegularExpression(r"f'[^']*'")
        self.highlighting_rules.append((pattern, string_format))
        
        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(ThemeColors.SYNTAX_COMMENT))
        pattern = QRegularExpression(r"#[^\n]*")
        self.highlighting_rules.append((pattern, comment_format))
        
        # Operators
        operator_format = QTextCharFormat()
        operator_format.setForeground(QColor(ThemeColors.SYNTAX_OPERATOR))
        operators = [r"\+", r"-", r"\*", r"/", r"%", r"=", r"==", r"!=", r"<", r">", r"<=", r">=", r"and", r"or", r"not"]
        for op in operators:
            pattern = QRegularExpression(op)
            self.highlighting_rules.append((pattern, operator_format))
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)


class JavaScriptSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for JavaScript/TypeScript code"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.highlighting_rules = []
        
        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(ThemeColors.SYNTAX_KEYWORD))
        keyword_format.setFontWeight(QFont.Bold)
        
        keywords = [
            "break", "case", "catch", "class", "const", "continue", "debugger",
            "default", "delete", "do", "else", "export", "extends", "finally",
            "for", "function", "if", "import", "in", "instanceof", "let", "new",
            "return", "super", "switch", "this", "throw", "try", "typeof", "var",
            "void", "while", "with", "yield", "async", "await", "static", "get",
            "set", "of", "as", "interface", "type", "enum", "implements", "private",
            "protected", "public", "readonly", "abstract", "declare", "namespace",
            "module", "require", "from", "true", "false", "null", "undefined"
        ]
        
        for word in keywords:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self.highlighting_rules.append((pattern, keyword_format))
        
        # Built-in objects
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor(ThemeColors.SYNTAX_BUILTIN))
        
        builtins = [
            "Array", "Boolean", "Date", "Error", "Function", "JSON", "Map", "Math",
            "Number", "Object", "Promise", "Proxy", "Reflect", "RegExp", "Set",
            "String", "Symbol", "ArrayBuffer", "DataView", "Float32Array",
            "Float64Array", "Int8Array", "Int16Array", "Int32Array", "Uint8Array",
            "Uint16Array", "Uint32Array", "console", "document", "window", "fetch"
        ]
        
        for word in builtins:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self.highlighting_rules.append((pattern, builtin_format))
        
        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(ThemeColors.SYNTAX_NUMBER))
        pattern = QRegularExpression(r"\b[0-9]+(\.[0-9]+)?\b")
        self.highlighting_rules.append((pattern, number_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(ThemeColors.SYNTAX_STRING))
        pattern = QRegularExpression(r'"[^"]*"')
        self.highlighting_rules.append((pattern, string_format))
        
        pattern = QRegularExpression(r"'[^']*'")
        self.highlighting_rules.append((pattern, string_format))
        
        # Template literals
        pattern = QRegularExpression(r"`[^`]*`")
        self.highlighting_rules.append((pattern, string_format))
        
        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(ThemeColors.SYNTAX_COMMENT))
        
        # Single line comments
        pattern = QRegularExpression(r"//[^\n]*")
        self.highlighting_rules.append((pattern, comment_format))
        
        # Multi-line comments (simplified)
        pattern = QRegularExpression(r"/\*[^*]*\*/")
        self.highlighting_rules.append((pattern, comment_format))
        
        # Function calls
        function_format = QTextCharFormat()
        function_format.setForeground(QColor(ThemeColors.SYNTAX_FUNCTION))
        pattern = QRegularExpression(r"\b(\w+)(?=\s*\()")
        self.highlighting_rules.append((pattern, function_format))
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)


def get_syntax_highlighter(file_extension: str) -> type:
    """Get the appropriate syntax highlighter for a file extension"""
    highlighters = {
        '.py': PythonSyntaxHighlighter,
        '.pyw': PythonSyntaxHighlighter,
        '.js': JavaScriptSyntaxHighlighter,
        '.jsx': JavaScriptSyntaxHighlighter,
        '.ts': JavaScriptSyntaxHighlighter,
        '.tsx': JavaScriptSyntaxHighlighter,
        '.mjs': JavaScriptSyntaxHighlighter,
        '.cjs': JavaScriptSyntaxHighlighter,
    }
    
    return highlighters.get(file_extension.lower(), None)


def apply_dark_theme(app):
    """Apply the dark theme to a QApplication instance"""
    app.setPalette(DarkPalette())
    app.setStyleSheet(MAIN_STYLESHEET)


def get_editor_font():
    """Get the recommended font for code editing"""
    font = QFont("Fira Code", 14)
    font.setStyleHint(QFont.Monospace)
    font.setFixedPitch(True)
    return font


def get_ui_font():
    """Get the recommended font for UI elements"""
    font = QFont("Segoe UI", 13)
    font.setStyleHint(QFont.SansSerif)
    return font
