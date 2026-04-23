"""
Sentience v3.0 - Embedded Terminal
Full terminal emulator with color output, command history, and tab completion
"""

import os
import sys
import re
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QCompleter, QStringListModel, QMenu,
    QSplitter, QComboBox, QApplication, QStyle
)
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QFont, QKeyEvent,
    QTextDocument, QTextFormat, QAction
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QTimer, QProcess, QProcessEnvironment,
    QSettings, QEvent, QRegularExpression, QSize
)

from .styles import ThemeColors, get_editor_font


class AnsiColor(Enum):
    """ANSI color codes"""
    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    MAGENTA = 5
    CYAN = 6
    WHITE = 7
    BRIGHT_BLACK = 8
    BRIGHT_RED = 9
    BRIGHT_GREEN = 10
    BRIGHT_YELLOW = 11
    BRIGHT_BLUE = 12
    BRIGHT_MAGENTA = 13
    BRIGHT_CYAN = 14
    BRIGHT_WHITE = 15


class TerminalColors:
    """Color palette for terminal output"""
    
    # Standard 16-color palette
    COLORS = {
        AnsiColor.BLACK: '#2e3436',
        AnsiColor.RED: '#cc0000',
        AnsiColor.GREEN: '#4e9a06',
        AnsiColor.YELLOW: '#c4a000',
        AnsiColor.BLUE: '#3465a4',
        AnsiColor.MAGENTA: '#75507b',
        AnsiColor.CYAN: '#06989a',
        AnsiColor.WHITE: '#d3d7cf',
        AnsiColor.BRIGHT_BLACK: '#555753',
        AnsiColor.BRIGHT_RED: '#ef2929',
        AnsiColor.BRIGHT_GREEN: '#8ae234',
        AnsiColor.BRIGHT_YELLOW: '#fce94f',
        AnsiColor.BRIGHT_BLUE: '#729fcf',
        AnsiColor.BRIGHT_MAGENTA: '#ad7fa8',
        AnsiColor.BRIGHT_CYAN: '#34e2e2',
        AnsiColor.BRIGHT_WHITE: '#eeeeec',
    }
    
    # Extended color mapping (256 colors)
    @classmethod
    def get_color(cls, index: int) -> QColor:
        """Get a QColor for the given ANSI color index"""
        if index in cls.COLORS:
            return QColor(cls.COLORS[index])
        
        # Default to white
        return QColor('#d3d7cf')


@dataclass
class CommandHistory:
    """Command history entry"""
    command: str
    timestamp: str
    working_dir: str
    exit_code: int = 0


class AnsiParser:
    """Parse ANSI escape sequences and convert to QTextCharFormat"""
    
    def __init__(self):
        self.reset_state()
    
    def reset_state(self):
        """Reset the parser state"""
        self.foreground = QColor('#d3d7cf')
        self.background = QColor('#0c0c0c')
        self.bold = False
        self.italic = False
        self.underline = False
        self.strikethrough = False
        self.inverse = False
    
    def parse(self, text: str) -> List[Tuple[str, QTextCharFormat]]:
        """Parse text with ANSI codes and return formatted segments"""
        result = []
        
        # Pattern for ANSI escape sequences
        ansi_pattern = r'\x1b\[([0-9;]*)m'
        
        last_end = 0
        for match in re.finditer(ansi_pattern, text):
            # Add text before this code
            if match.start() > last_end:
                segment_text = text[last_end:match.start()]
                fmt = self._create_format()
                result.append((segment_text, fmt))
            
            # Parse the code
            params = match.group(1)
            if params:
                self._apply_code(params)
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            segment_text = text[last_end:]
            fmt = self._create_format()
            result.append((segment_text, fmt))
        
        return result
    
    def _create_format(self) -> QTextCharFormat:
        """Create a QTextCharFormat from current state"""
        fmt = QTextCharFormat()
        
        fg = self.background if self.inverse else self.foreground
        bg = self.foreground if self.inverse else self.background
        
        fmt.setForeground(fg)
        fmt.setBackground(bg)
        fmt.setFontWeight(QFont.Bold if self.bold else QFont.Normal)
        fmt.setFontItalic(self.italic)
        fmt.setFontUnderline(self.underline)
        fmt.setFontStrikeOut(self.strikethrough)
        
        return fmt
    
    def _apply_code(self, params: str):
        """Apply ANSI code parameters"""
        codes = [int(c) if c else 0 for c in params.split(';')]
        
        i = 0
        while i < len(codes):
            code = codes[i]
            
            if code == 0:
                # Reset
                self.reset_state()
            
            elif code == 1:
                # Bold
                self.bold = True
            
            elif code == 3:
                # Italic
                self.italic = True
            
            elif code == 4:
                # Underline
                self.underline = True
            
            elif code == 7:
                # Inverse
                self.inverse = True
            
            elif code == 9:
                # Strikethrough
                self.strikethrough = True
            
            elif code == 22:
                # Normal intensity
                self.bold = False
            
            elif code == 23:
                # Not italic
                self.italic = False
            
            elif code == 24:
                # Not underlined
                self.underline = False
            
            elif code == 27:
                # Not inverse
                self.inverse = False
            
            elif code == 29:
                # Not strikethrough
                self.strikethrough = False
            
            elif 30 <= code <= 37:
                # Foreground color (standard)
                self.foreground = TerminalColors.get_color(code - 30)
            
            elif code == 38:
                # Extended foreground color
                if i + 2 < len(codes) and codes[i + 1] == 5:
                    # 256-color mode
                    self.foreground = TerminalColors.get_color(codes[i + 2])
                    i += 2
                elif i + 4 < len(codes) and codes[i + 1] == 2:
                    # RGB mode
                    r, g, b = codes[i + 2:i + 5]
                    self.foreground = QColor(r, g, b)
                    i += 4
            
            elif code == 39:
                # Default foreground
                self.foreground = QColor('#d3d7cf')
            
            elif 40 <= code <= 47:
                # Background color (standard)
                self.background = TerminalColors.get_color(code - 40)
            
            elif code == 48:
                # Extended background color
                if i + 2 < len(codes) and codes[i + 1] == 5:
                    self.background = TerminalColors.get_color(codes[i + 2])
                    i += 2
                elif i + 4 < len(codes) and codes[i + 1] == 2:
                    r, g, b = codes[i + 2:i + 5]
                    self.background = QColor(r, g, b)
                    i += 4
            
            elif code == 49:
                # Default background
                self.background = QColor('#0c0c0c')
            
            elif 90 <= code <= 97:
                # Bright foreground
                self.foreground = TerminalColors.get_color(code - 90 + 8)
            
            elif 100 <= code <= 107:
                # Bright background
                self.background = TerminalColors.get_color(code - 100 + 8)
            
            i += 1


class TerminalOutput(QTextEdit):
    """Terminal output display with ANSI color support"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setReadOnly(True)
        self.setFont(get_editor_font())
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Colors
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: #0c0c0c;
                color: #d3d7cf;
                border: none;
            }}
        """)
        
        # ANSI parser
        self.ansi_parser = AnsiParser()
        
        # Buffer for incomplete ANSI sequences
        self.buffer = ''
    
    def append_colored(self, text: str):
        """Append text with ANSI color codes"""
        # Handle incomplete sequences from buffer
        text = self.buffer + text
        self.buffer = ''
        
        # Check for incomplete ANSI sequence
        last_escape = text.rfind('\x1b')
        if last_escape != -1 and last_escape < len(text) - 1:
            # Check if the sequence is complete
            after_escape = text[last_escape:]
            if not re.search(r'\x1b\[[0-9;]*m', after_escape):
                # Sequence might be incomplete
                self.buffer = text[last_escape:]
                text = text[:last_escape]
        
        # Parse and insert
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        segments = self.ansi_parser.parse(text)
        
        cursor.beginEditBlock()
        for segment_text, fmt in segments:
            cursor.insertText(segment_text, fmt)
        cursor.endEditBlock()
        
        # Scroll to bottom
        self.ensureCursorVisible()
    
    def clear_output(self):
        """Clear the terminal output"""
        self.clear()
        self.ansi_parser.reset_state()
        self.buffer = ''


class TerminalInput(QLineEdit):
    """Terminal input with history and completion"""
    
    command_submitted = Signal(str)
    history_up = Signal()
    history_down = Signal()
    tab_completion = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setFont(get_editor_font())
        self.setPlaceholderText("Enter command...")
        
        # Styling
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: #0c0c0c;
                color: #d3d7cf;
                border: none;
                border-top: 1px solid {ThemeColors.BORDER};
                padding: 8px;
                font-family: "Fira Code", "Cascadia Code", Consolas, monospace;
            }}
        """)
        
        # Completer
        self.completer = QCompleter(self)
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.InlineCompletion)
        
        # Current completion prefix
        self.completion_prefix = ''
    
    def set_completions(self, completions: List[str]):
        """Set the completion list"""
        self.completer_model.setStringList(completions)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events"""
        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            # Submit command
            text = self.text().strip()
            if text:
                self.command_submitted.emit(text)
                self.clear()
            return
        
        elif key == Qt.Key_Up:
            self.history_up.emit()
            return
        
        elif key == Qt.Key_Down:
            self.history_down.emit()
            return
        
        elif key == Qt.Key_Tab:
            self.tab_completion.emit()
            return
        
        elif key == Qt.Key_C and modifiers == Qt.ControlModifier:
            # Send Ctrl+C to cancel current input
            self.clear()
            return
        
        elif key == Qt.Key_L and modifiers == Qt.ControlModifier:
            # Clear screen (emit clear signal)
            self.clear()
            return
        
        super().keyPressEvent(event)
    
    def apply_completion(self, completion: str):
        """Apply a completion to the current text"""
        self.setText(completion)
        self.setCursorPosition(len(completion))


class TerminalWidget(QWidget):
    """Main terminal widget with shell process"""
    
    # Signals
    command_executed = Signal(str, int)  # command, exit_code
    directory_changed = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None, shell: Optional[str] = None):
        super().__init__(parent)
        
        # Shell configuration
        self.shell = shell or os.environ.get('SHELL', '/bin/bash')
        self.working_directory = os.getcwd()
        
        # Process
        self.process: Optional[QProcess] = None
        self.is_process_running = False
        
        # Command history
        self.command_history: List[CommandHistory] = []
        self.history_index = -1
        self.max_history = 1000
        
        # Load history from settings
        self.settings = QSettings('Sentience', 'Terminal')
        self._load_history()
        
        # Tab completion data
        self.completion_data: List[str] = []
        
        # Setup UI
        self._setup_ui()
        self._setup_process()
        self._setup_connections()
        
        # Start shell
        self._start_shell()
    
    def _setup_ui(self):
        """Setup the terminal UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Terminal header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        # Terminal name
        self.terminal_name = QLabel("Terminal")
        self.terminal_name.setStyleSheet("font-weight: bold; color: #d3d7cf;")
        header_layout.addWidget(self.terminal_name)
        
        # Working directory
        self.dir_label = QLabel(self.working_directory)
        self.dir_label.setStyleSheet("color: #729fcf; font-size: 11px;")
        header_layout.addWidget(self.dir_label)
        
        header_layout.addStretch()
        
        # Terminal controls
        self.new_terminal_btn = QPushButton("+")
        self.new_terminal_btn.setFixedSize(24, 24)
        self.new_terminal_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #d3d7cf;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #2d2d30;
            }
        """)
        header_layout.addWidget(self.new_terminal_btn)
        
        self.split_terminal_btn = QPushButton("▭")
        self.split_terminal_btn.setFixedSize(24, 24)
        self.split_terminal_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #d3d7cf;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2d2d30;
            }
        """)
        header_layout.addWidget(self.split_terminal_btn)
        
        self.kill_terminal_btn = QPushButton("×")
        self.kill_terminal_btn.setFixedSize(24, 24)
        self.kill_terminal_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #ef2929;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #ef2929;
                color: white;
            }
        """)
        header_layout.addWidget(self.kill_terminal_btn)
        
        layout.addWidget(header)
        
        # Output area
        self.output = TerminalOutput()
        layout.addWidget(self.output)
        
        # Input area
        self.input = TerminalInput()
        layout.addWidget(self.input)
        
        # Set focus policy
        self.setFocusPolicy(Qt.StrongFocus)
    
    def _setup_process(self):
        """Setup the shell process"""
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        
        # Set environment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "xterm-256color")
        env.insert("COLORTERM", "truecolor")
        self.process.setProcessEnvironment(env)
        
        # Set working directory
        self.process.setWorkingDirectory(self.working_directory)
    
    def _setup_connections(self):
        """Setup signal connections"""
        # Process signals
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_process_finished)
        self.process.started.connect(self._on_process_started)
        
        # Input signals
        self.input.command_submitted.connect(self._execute_command)
        self.input.history_up.connect(self._history_up)
        self.input.history_down.connect(self._history_down)
        self.input.tab_completion.connect(self._tab_completion)
        
        # Button signals
        self.kill_terminal_btn.clicked.connect(self._kill_shell)
    
    def _start_shell(self):
        """Start the shell process"""
        if self.is_process_running:
            return
        
        # Clear output
        self.output.clear_output()
        
        # Start the shell
        self.process.start(self.shell, [])
    
    def _kill_shell(self):
        """Kill the shell process"""
        if self.process and self.is_process_running:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
    
    def _restart_shell(self):
        """Restart the shell process"""
        self._kill_shell()
        self._start_shell()
    
    def _on_process_started(self):
        """Handle process started"""
        self.is_process_running = True
        self.terminal_name.setText(f"Terminal ({os.path.basename(self.shell)})")
    
    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        """Handle process finished"""
        self.is_process_running = False
        
        if exit_status == QProcess.CrashExit:
            self.output.append_colored(f"\n\x1b[1;31mProcess crashed with exit code {exit_code}\x1b[0m\n")
        else:
            self.output.append_colored(f"\n\x1b[1;33mProcess exited with code {exit_code}\x1b[0m\n")
        
        # Prompt to restart
        self.output.append_colored("\x1b[1;34mPress Enter to start a new shell...\x1b[0m\n")
    
    def _on_stdout(self):
        """Handle stdout from process"""
        data = self.process.readAllStandardOutput().data()
        try:
            text = data.decode('utf-8', errors='replace')
            self.output.append_colored(text)
        except Exception as e:
            print(f"Error decoding stdout: {e}")
    
    def _on_stderr(self):
        """Handle stderr from process"""
        data = self.process.readAllStandardError().data()
        try:
            text = data.decode('utf-8', errors='replace')
            self.output.append_colored(f"\x1b[31m{text}\x1b[0m")
        except Exception as e:
            print(f"Error decoding stderr: {e}")
    
    def _execute_command(self, command: str):
        """Execute a command in the shell"""
        if not self.is_process_running:
            self._start_shell()
        
        # Write command to process
        self.process.write((command + '\n').encode('utf-8'))
        
        # Add to history
        from datetime import datetime
        entry = CommandHistory(
            command=command,
            timestamp=datetime.now().isoformat(),
            working_dir=self.working_directory
        )
        self.command_history.append(entry)
        self.history_index = len(self.command_history)
        
        # Save history
        self._save_history()
        
        # Update completion data
        self._update_completion_data(command)
    
    def _history_up(self):
        """Navigate up in command history"""
        if not self.command_history:
            return
        
        if self.history_index > 0:
            self.history_index -= 1
            self.input.setText(self.command_history[self.history_index].command)
    
    def _history_down(self):
        """Navigate down in command history"""
        if not self.command_history:
            return
        
        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.input.setText(self.command_history[self.history_index].command)
        else:
            self.history_index = len(self.command_history)
            self.input.clear()
    
    def _tab_completion(self):
        """Handle tab completion"""
        text = self.input.text()
        
        if not text:
            return
        
        # Get completions from shell
        # For now, use a simple file/directory completion
        
        parts = text.split()
        if len(parts) == 0:
            return
        
        # Complete the last part
        last_part = parts[-1]
        
        # Check if it's a path
        if '/' in last_part:
            base_dir = os.path.dirname(last_part)
            prefix = os.path.basename(last_part)
            search_dir = os.path.join(self.working_directory, base_dir) if not os.path.isabs(base_dir) else base_dir
        else:
            search_dir = self.working_directory
            prefix = last_part
        
        try:
            entries = os.listdir(search_dir)
            matches = [e for e in entries if e.startswith(prefix)]
            
            if len(matches) == 1:
                # Single match - complete
                if '/' in last_part:
                    new_text = ' '.join(parts[:-1] + [os.path.join(base_dir, matches[0])])
                else:
                    new_text = ' '.join(parts[:-1] + [matches[0]])
                self.input.setText(new_text + ' ')
            elif len(matches) > 1:
                # Multiple matches - show options
                self.output.append_colored(f"\n\x1b[1;36m{'  '.join(matches)}\x1b[0m\n")
        except Exception:
            pass
    
    def _update_completion_data(self, command: str):
        """Update completion data based on command"""
        # Add command to completions
        parts = command.split()
        if parts and parts[0] not in self.completion_data:
            self.completion_data.append(parts[0])
            self.input.set_completions(self.completion_data)
    
    def _load_history(self):
        """Load command history from settings"""
        history_data = self.settings.value('command_history', [])
        
        for entry in history_data:
            if isinstance(entry, dict):
                self.command_history.append(CommandHistory(**entry))
        
        self.history_index = len(self.command_history)
    
    def _save_history(self):
        """Save command history to settings"""
        # Keep only last N entries
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]
        
        # Convert to dict for storage
        history_data = [
            {
                'command': entry.command,
                'timestamp': entry.timestamp,
                'working_dir': entry.working_dir,
                'exit_code': entry.exit_code
            }
            for entry in self.command_history
        ]
        
        self.settings.setValue('command_history', history_data)
    
    def set_working_directory(self, path: str):
        """Set the working directory"""
        if os.path.isdir(path):
            self.working_directory = path
            self.process.setWorkingDirectory(path)
            self.dir_label.setText(path)
            self.directory_changed.emit(path)
            
            # Execute cd command in shell
            if self.is_process_running:
                self.process.write(f'cd "{path}"\n'.encode('utf-8'))
    
    def send_command(self, command: str):
        """Send a command to the terminal"""
        self._execute_command(command)
    
    def clear(self):
        """Clear the terminal output"""
        self.output.clear_output()
        self.process.write('clear\n'.encode('utf-8'))
    
    def focusInEvent(self, event: QEvent):
        """Handle focus in event"""
        self.input.setFocus()
        super().focusInEvent(event)
    
    def contextMenuEvent(self, event):
        """Show context menu"""
        menu = QMenu(self)
        
        menu.addAction("Copy", self.output.copy, QKeySequence.StandardKey.Copy)
        menu.addAction("Clear", self.clear)
        menu.addSeparator()
        menu.addAction("Restart Shell", self._restart_shell)
        
        menu.exec(event.globalPos())
    
    def sizeHint(self) -> QSize:
        """Return size hint"""
        return QSize(600, 400)


class TerminalPanel(QWidget):
    """Panel containing multiple terminal tabs"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.terminals: List[TerminalWidget] = []
        
        self._setup_ui()
        self._add_terminal()
    
    def _setup_ui(self):
        """Setup the panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Tab bar for multiple terminals
        self.tab_bar = QWidget()
        tab_layout = QHBoxLayout(self.tab_bar)
        tab_layout.setContentsMargins(4, 0, 4, 0)
        tab_layout.setSpacing(2)
        
        self.tab_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        tab_layout.addStretch()
        
        # Add terminal button
        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #d3d7cf;
            }
            QPushButton:hover {
                background-color: #2d2d30;
            }
        """)
        add_btn.clicked.connect(self._add_terminal)
        tab_layout.addWidget(add_btn)
        
        layout.addWidget(self.tab_bar)
        
        # Stack for terminals
        self.stack = QWidget()
        self.stack_layout = QVBoxLayout(self.stack)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(self.stack)
    
    def _add_terminal(self):
        """Add a new terminal"""
        terminal = TerminalWidget()
        self.terminals.append(terminal)
        
        # Add to stack
        self.stack_layout.addWidget(terminal)
        
        # Add tab button
        tab_btn = QPushButton(f"Terminal {len(self.terminals)}")
        tab_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                border: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: #d3d7cf;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #3d3d40;
            }
        """)
        
        # Store reference
        tab_btn.terminal = terminal
        
        # Add before the add button
        tab_layout = self.tab_bar.layout()
        tab_layout.insertWidget(tab_layout.count() - 1, tab_btn)
        
        # Connect button to switch terminal
        tab_btn.clicked.connect(lambda checked, t=terminal: self._switch_terminal(t))
        
        # Show terminal
        self._switch_terminal(terminal)
    
    def _switch_terminal(self, terminal: TerminalWidget):
        """Switch to the specified terminal"""
        for i in range(self.stack_layout.count()):
            widget = self.stack_layout.itemAt(i).widget()
            if widget:
                widget.setVisible(widget == terminal)
        
        terminal.setFocus()
    
    def get_active_terminal(self) -> Optional[TerminalWidget]:
        """Get the currently visible terminal"""
        for i in range(self.stack_layout.count()):
            widget = self.stack_layout.itemAt(i).widget()
            if widget and widget.isVisible():
                return widget
        return None
