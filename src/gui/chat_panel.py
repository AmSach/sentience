"""
Sentience v3.0 - AI Chat Panel
AI chat interface with message list, markdown support, and code block rendering
"""

import re
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QScrollArea, QFrame, QSplitter,
    QComboBox, QApplication, QSizePolicy, QMenu
)
from PySide6.QtGui import (
    QTextDocument, QTextCursor, QTextCharFormat, QColor, QFont,
    QKeySequence, QShortcut, QTextBlockFormat, QTextImageFormat
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QTimer, QSize, QEvent, QPropertyAnimation,
    QEasingCurve, Property, QThread
)

from .styles import ThemeColors, get_editor_font


class MessageRole(Enum):
    """Role of a message"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ChatMessage:
    """Represents a chat message"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'role': self.role.value,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
            'tool_calls': self.tool_calls,
            'tool_results': self.tool_results
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create from dictionary"""
        return cls(
            role=MessageRole(data['role']),
            content=data['content'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            metadata=data.get('metadata', {}),
            tool_calls=data.get('tool_calls', []),
            tool_results=data.get('tool_results', [])
        )


@dataclass
class ToolCall:
    """Represents a tool call"""
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    status: str = "pending"  # pending, running, success, error


class MarkdownRenderer:
    """Renders markdown to QTextDocument"""
    
    def __init__(self):
        self.code_block_pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
        self.inline_code_pattern = re.compile(r'`([^`]+)`')
        self.bold_pattern = re.compile(r'\*\*([^*]+)\*\*')
        self.italic_pattern = re.compile(r'\*([^*]+)\*')
        self.link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        self.header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.list_pattern = re.compile(r'^[\*\-\+]\s+(.+)$', re.MULTILINE)
        self.numbered_list_pattern = re.compile(r'^\d+\.\s+(.+)$', re.MULTILINE)
    
    def render(self, text: str, document: QTextDocument) -> None:
        """Render markdown text to a QTextDocument"""
        cursor = QTextCursor(document)
        
        # Process code blocks first
        parts = self._split_code_blocks(text)
        
        for is_code, content in parts:
            if is_code:
                self._render_code_block(cursor, content)
            else:
                self._render_markdown(cursor, content)
    
    def _split_code_blocks(self, text: str) -> List[tuple]:
        """Split text into code blocks and regular text"""
        parts = []
        last_end = 0
        
        for match in self.code_block_pattern.finditer(text):
            # Add text before code block
            if match.start() > last_end:
                parts.append((False, text[last_end:match.start()]))
            
            # Add code block
            language = match.group(1)
            code = match.group(2)
            parts.append((True, (language, code)))
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            parts.append((False, text[last_end:]))
        
        return parts
    
    def _render_code_block(self, cursor: QTextCursor, content: tuple) -> None:
        """Render a code block"""
        language, code = content
        
        # Format for code block
        fmt = QTextCharFormat()
        fmt.setFont(QFont("Fira Code", 10))
        fmt.setBackground(QColor(ThemeColors.BACKGROUND_DARKER))
        fmt.setForeground(QColor(ThemeColors.FOREGROUND))
        
        # Add language header
        if language:
            header_fmt = QTextCharFormat()
            header_fmt.setForeground(QColor(ThemeColors.ACCENT))
            header_fmt.setFontWeight(QFont.Bold)
            cursor.insertText(f"[{language}]\n", header_fmt)
        
        # Insert code
        cursor.insertText(code, fmt)
        cursor.insertText("\n\n")
    
    def _render_markdown(self, cursor: QTextCursor, text: str) -> None:
        """Render markdown text"""
        # Split into lines for processing
        lines = text.split('\n')
        
        for line in lines:
            if not line:
                cursor.insertText("\n")
                continue
            
            # Check for headers
            header_match = self.header_pattern.match(line)
            if header_match:
                level = len(header_match.group(1))
                text_content = header_match.group(2)
                
                fmt = QTextCharFormat()
                fmt.setFontWeight(QFont.Bold)
                
                if level == 1:
                    fmt.setFontPointSize(24)
                elif level == 2:
                    fmt.setFontPointSize(20)
                elif level == 3:
                    fmt.setFontPointSize(16)
                else:
                    fmt.setFontPointSize(14)
                
                cursor.insertText(text_content + "\n", fmt)
                continue
            
            # Check for list items
            list_match = self.list_pattern.match(line)
            if list_match:
                cursor.insertText("• ")
                self._render_inline(cursor, list_match.group(1))
                cursor.insertText("\n")
                continue
            
            numbered_match = self.numbered_list_pattern.match(line)
            if numbered_match:
                # Extract number from line
                cursor.insertText(line[:line.index('.')+1] + " ")
                self._render_inline(cursor, numbered_match.group(1))
                cursor.insertText("\n")
                continue
            
            # Regular text with inline formatting
            self._render_inline(cursor, line)
            cursor.insertText("\n")
    
    def _render_inline(self, cursor: QTextCursor, text: str) -> None:
        """Render inline markdown elements"""
        i = 0
        while i < len(text):
            # Check for inline code
            if text[i] == '`':
                end = text.find('`', i + 1)
                if end != -1:
                    code = text[i+1:end]
                    
                    fmt = QTextCharFormat()
                    fmt.setFont(QFont("Fira Code", 10))
                    fmt.setBackground(QColor(ThemeColors.BACKGROUND_LIGHTER))
                    fmt.setForeground(QColor(ThemeColors.SYNTAX_STRING))
                    
                    cursor.insertText(code, fmt)
                    i = end + 1
                    continue
            
            # Check for bold
            if text[i:i+2] == '**':
                end = text.find('**', i + 2)
                if end != -1:
                    bold_text = text[i+2:end]
                    
                    fmt = QTextCharFormat()
                    fmt.setFontWeight(QFont.Bold)
                    
                    cursor.insertText(bold_text, fmt)
                    i = end + 2
                    continue
            
            # Check for italic
            if text[i] == '*' and (i == 0 or text[i-1] != '*'):
                end = text.find('*', i + 1)
                if end != -1 and text[end+1:end+2] != '*':
                    italic_text = text[i+1:end]
                    
                    fmt = QTextCharFormat()
                    fmt.setFontItalic(True)
                    
                    cursor.insertText(italic_text, fmt)
                    i = end + 1
                    continue
            
            # Check for links
            if text[i] == '[':
                end_bracket = text.find(']', i)
                if end_bracket != -1 and text[end_bracket+1] == '(':
                    end_paren = text.find(')', end_bracket + 2)
                    if end_paren != -1:
                        link_text = text[i+1:end_bracket]
                        link_url = text[end_bracket+2:end_paren]
                        
                        fmt = QTextCharFormat()
                        fmt.setForeground(QColor(ThemeColors.ACCENT))
                        fmt.setAnchor(True)
                        fmt.setAnchorHref(link_url)
                        fmt.setFontUnderline(True)
                        
                        cursor.insertText(link_text, fmt)
                        i = end_paren + 1
                        continue
            
            # Regular character
            cursor.insertText(text[i])
            i += 1


class MessageWidget(QFrame):
    """Widget for displaying a single message"""
    
    def __init__(self, message: ChatMessage, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.message = message
        self.markdown_renderer = MarkdownRenderer()
        
        self._setup_ui()
        self._apply_styles()
    
    def _setup_ui(self):
        """Setup the message widget UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Role icon/label
        role_label = QLabel(self.message.role.value.upper())
        role_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 4px;
            }}
        """)
        
        if self.message.role == MessageRole.USER:
            role_label.setStyleSheet(role_label.styleSheet() + f"background-color: {ThemeColors.ACCENT}; color: white;")
        elif self.message.role == MessageRole.ASSISTANT:
            role_label.setStyleSheet(role_label.styleSheet() + f"background-color: {ThemeColors.SUCCESS}; color: white;")
        elif self.message.role == MessageRole.SYSTEM:
            role_label.setStyleSheet(role_label.styleSheet() + f"background-color: {ThemeColors.WARNING}; color: black;")
        elif self.message.role == MessageRole.TOOL:
            role_label.setStyleSheet(role_label.styleSheet() + f"background-color: {ThemeColors.INFO}; color: white;")
        
        header_layout.addWidget(role_label)
        
        # Timestamp
        time_label = QLabel(self.message.timestamp.strftime("%H:%M"))
        time_label.setStyleSheet("color: #858585; font-size: 10px;")
        header_layout.addWidget(time_label)
        
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Content
        self.content_text = QTextEdit()
        self.content_text.setReadOnly(True)
        self.content_text.setFrameStyle(QFrame.NoFrame)
        self.content_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.content_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: {ThemeColors.FOREGROUND};
                border: none;
            }}
        """)
        
        # Render markdown content
        self.markdown_renderer.render(self.message.content, self.content_text.document())
        
        # Adjust height to content
        self.content_text.document().documentLayout().documentSizeChanged.connect(
            lambda: self.content_text.setFixedHeight(int(self.content_text.document().size().height() + 10))
        )
        
        layout.addWidget(self.content_text)
        
        # Tool calls
        if self.message.tool_calls:
            self._render_tool_calls(layout)
        
        # Tool results
        if self.message.tool_results:
            self._render_tool_results(layout)
    
    def _render_tool_calls(self, layout: QVBoxLayout):
        """Render tool calls section"""
        tools_label = QLabel("Tool Calls:")
        tools_label.setStyleSheet("font-weight: bold; color: #858585; margin-top: 8px;")
        layout.addWidget(tools_label)
        
        for tool_call in self.message.tool_calls:
            tool_widget = QFrame()
            tool_widget.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeColors.BACKGROUND_DARKER};
                    border: 1px solid {ThemeColors.BORDER};
                    border-radius: 4px;
                    padding: 8px;
                    margin: 4px 0;
                }}
            """)
            
            tool_layout = QVBoxLayout(tool_widget)
            tool_layout.setContentsMargins(8, 8, 8, 8)
            
            # Tool name
            name_label = QLabel(f"🔧 {tool_call.get('name', 'Unknown')}")
            name_label.setStyleSheet("font-weight: bold;")
            tool_layout.addWidget(name_label)
            
            # Arguments (collapsed by default)
            args_text = json.dumps(tool_call.get('arguments', {}), indent=2)
            args_label = QLabel(args_text)
            args_label.setStyleSheet(f"font-family: 'Fira Code'; font-size: 10px; color: {ThemeColors.FOREGROUND_DIM};")
            args_label.setWordWrap(True)
            tool_layout.addWidget(args_label)
            
            layout.addWidget(tool_widget)
    
    def _render_tool_results(self, layout: QVBoxLayout):
        """Render tool results section"""
        results_label = QLabel("Tool Results:")
        results_label.setStyleSheet("font-weight: bold; color: #858585; margin-top: 8px;")
        layout.addWidget(results_label)
        
        for result in self.message.tool_results:
            result_widget = QFrame()
            result_widget.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeColors.BACKGROUND_DARKER};
                    border: 1px solid {ThemeColors.BORDER};
                    border-radius: 4px;
                    padding: 8px;
                    margin: 4px 0;
                }}
            """)
            
            result_layout = QVBoxLayout(result_widget)
            result_layout.setContentsMargins(8, 8, 8, 8)
            
            # Result content
            content_label = QLabel(result.get('content', 'No result'))
            content_label.setStyleSheet(f"font-family: 'Fira Code'; font-size: 10px;")
            content_label.setWordWrap(True)
            result_layout.addWidget(content_label)
            
            layout.addWidget(result_widget)
    
    def _apply_styles(self):
        """Apply styles based on role"""
        if self.message.role == MessageRole.USER:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeColors.ACCENT + "20"};
                    border-radius: 8px;
                    margin: 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeColors.BACKGROUND_LIGHTER};
                    border-radius: 8px;
                    margin: 4px;
                }}
            """)


class ChatInputWidget(QWidget):
    """Chat input widget with markdown preview"""
    
    message_submitted = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
        self._setup_connections()
    
    def _setup_ui(self):
        """Setup the chat input UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Input area
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Type your message... (Markdown supported)")
        self.input_text.setMaximumHeight(150)
        self.input_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                color: {ThemeColors.FOREGROUND};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.input_text)
        
        # Action bar
        action_bar = QWidget()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        
        # Model selector
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "GPT-4o",
            "GPT-4o-mini",
            "Claude 3.5 Sonnet",
            "Claude 3 Opus",
            "Gemini 1.5 Pro",
            "Gemini 1.5 Flash",
            "Llama 3.1 70B",
            "Llama 3.1 8B"
        ])
        self.model_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                color: {ThemeColors.FOREGROUND};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        action_layout.addWidget(self.model_combo)
        
        action_layout.addStretch()
        
        # Send button
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ThemeColors.ACCENT_PRESSED};
            }}
        """)
        action_layout.addWidget(self.send_btn)
        
        layout.addWidget(action_bar)
    
    def _setup_connections(self):
        """Setup signal connections"""
        self.send_btn.clicked.connect(self._on_send)
        
        # Ctrl+Enter to send
        shortcut = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Return), self)
        shortcut.activated.connect(self._on_send)
    
    def _on_send(self):
        """Handle send button click"""
        text = self.input_text.toPlainText().strip()
        
        if text:
            self.message_submitted.emit(text)
            self.input_text.clear()
    
    def set_enabled(self, enabled: bool):
        """Enable or disable the input"""
        self.input_text.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)


class AIChatPanel(QWidget):
    """AI chat panel with message history and input"""
    
    message_sent = Signal(str, str)  # message, model
    clear_requested = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.messages: List[ChatMessage] = []
        self.message_widgets: List[MessageWidget] = []
        self.is_loading = False
        
        self._setup_ui()
        self._setup_connections()
        self._add_welcome_message()
    
    def _setup_ui(self):
        """Setup the AI chat panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        title = QLabel("AI ASSISTANT")
        title.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #858585;
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
            }}
        """)
        clear_btn.clicked.connect(self._clear_chat)
        header_layout.addWidget(clear_btn)
        
        layout.addWidget(header)
        
        # Messages scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
            }}
        """)
        
        # Messages container
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(8, 8, 8, 8)
        self.messages_layout.setSpacing(4)
        self.messages_layout.addStretch()
        
        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area)
        
        # Loading indicator
        self.loading_widget = QLabel("Thinking...")
        self.loading_widget.setAlignment(Qt.AlignCenter)
        self.loading_widget.setStyleSheet(f"""
            QLabel {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
                color: {ThemeColors.ACCENT};
                padding: 8px;
                border-radius: 8px;
            }}
        """)
        self.loading_widget.hide()
        
        # Add loading widget to layout
        loading_container = QWidget()
        loading_layout = QVBoxLayout(loading_container)
        loading_layout.setContentsMargins(8, 0, 8, 8)
        loading_layout.addWidget(self.loading_widget, alignment=Qt.AlignCenter)
        layout.addWidget(loading_container)
        
        # Input widget
        self.input_widget = ChatInputWidget()
        layout.addWidget(self.input_widget)
    
    def _setup_connections(self):
        """Setup signal connections"""
        self.input_widget.message_submitted.connect(self._on_message_submitted)
    
    def _add_welcome_message(self):
        """Add welcome message"""
        welcome = ChatMessage(
            role=MessageRole.SYSTEM,
            content="Welcome to Sentience AI Assistant! I'm here to help you with coding, debugging, and any questions you might have. How can I assist you today?"
        )
        self.add_message(welcome)
    
    def _on_message_submitted(self, text: str):
        """Handle message submission"""
        # Create user message
        message = ChatMessage(
            role=MessageRole.USER,
            content=text
        )
        self.add_message(message)
        
        # Get selected model
        model = self.input_widget.model_combo.currentText()
        
        # Emit signal
        self.message_sent.emit(text, model)
        
        # Show loading
        self.set_loading(True)
    
    def add_message(self, message: ChatMessage):
        """Add a message to the chat"""
        self.messages.append(message)
        
        # Create message widget
        message_widget = MessageWidget(message)
        self.message_widgets.append(message_widget)
        
        # Add to layout before stretch
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, message_widget)
        
        # Store reference
        message_widget.message_widget = message_widget
        
        # Scroll to bottom
        QTimer.singleShot(100, self._scroll_to_bottom)
    
    def add_assistant_message(self, content: str, tool_calls: List[Dict] = None):
        """Add an assistant message"""
        self.set_loading(False)
        
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls or []
        )
        self.add_message(message)
    
    def add_tool_result(self, tool_id: str, tool_name: str, result: str):
        """Add a tool result message"""
        message = ChatMessage(
            role=MessageRole.TOOL,
            content=result,
            metadata={'tool_id': tool_id, 'tool_name': tool_name}
        )
        self.add_message(message)
    
    def set_loading(self, loading: bool):
        """Set loading state"""
        self.is_loading = loading
        self.loading_widget.setVisible(loading)
        self.input_widget.set_enabled(not loading)
        
        if loading:
            self._scroll_to_bottom()
    
    def _scroll_to_bottom(self):
        """Scroll to the bottom of the chat"""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _clear_chat(self):
        """Clear the chat history"""
        self.messages.clear()
        self.message_widgets.clear()
        
        # Clear widgets from layout
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._add_welcome_message()
        self.clear_requested.emit()
    
    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """Get messages formatted for API call"""
        return [
            {'role': msg.role.value, 'content': msg.content}
            for msg in self.messages
            if msg.role != MessageRole.SYSTEM
        ]
    
    def save_history(self, filepath: str):
        """Save chat history to file"""
        data = {
            'messages': [msg.to_dict() for msg in self.messages]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_history(self, filepath: str):
        """Load chat history from file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self._clear_chat()
            
            for msg_data in data.get('messages', []):
                message = ChatMessage.from_dict(msg_data)
                self.add_message(message)
        
        except Exception as e:
            print(f"Error loading chat history: {e}")
    
    def contextMenuEvent(self, event):
        """Show context menu"""
        menu = QMenu(self)
        
        copy_action = menu.addAction("Copy Conversation")
        copy_action.triggered.connect(self._copy_conversation)
        
        export_action = menu.addAction("Export to File")
        export_action.triggered.connect(self._export_to_file)
        
        menu.addSeparator()
        
        clear_action = menu.addAction("Clear Conversation")
        clear_action.triggered.connect(self._clear_chat)
        
        menu.exec(event.globalPos())
    
    def _copy_conversation(self):
        """Copy conversation to clipboard"""
        text = "\n\n".join([
            f"[{msg.role.value.upper()}]: {msg.content}"
            for msg in self.messages
        ])
        QApplication.clipboard().setText(text)
    
    def _export_to_file(self):
        """Export conversation to markdown file"""
        from datetime import datetime
        filename = f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        self.save_history(filename)


class StreamingChatWorker(QThread):
    """Worker for streaming chat responses"""
    
    chunk_received = Signal(str)
    completed = Signal(str)
    error = Signal(str)
    
    def __init__(self, messages: List[Dict], model: str, api_key: str = None):
        super().__init__()
        
        self.messages = messages
        self.model = model
        self.api_key = api_key
        self.is_cancelled = False
    
    def run(self):
        """Run the streaming request"""
        try:
            # This is a placeholder for actual API integration
            # In a real implementation, this would connect to an LLM API
            
            # Simulate streaming response
            response = "This is a simulated AI response. In a real implementation, "
            response += "this would connect to an LLM API (OpenAI, Anthropic, etc.) "
            response += "and stream the response back to the UI."
            
            # Stream in chunks
            words = response.split()
            full_response = ""
            
            for word in words:
                if self.is_cancelled:
                    break
                
                chunk = word + " "
                full_response += chunk
                self.chunk_received.emit(chunk)
                self.msleep(50)  # Simulate network delay
            
            self.completed.emit(full_response)
        
        except Exception as e:
            self.error.emit(str(e))
    
    def cancel(self):
        """Cancel the streaming"""
        self.is_cancelled = True
