"""
Sentience v3.0 - Code Editor
Full-featured code editor with syntax highlighting, line numbers, minimap, and more
"""

import os
import re
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextEdit,
    QScrollBar, QSizePolicy, QLabel, QMenu, QToolTip, QApplication
)
from PySide6.QtGui import (
    QPainter, QColor, QFont, QTextFormat, QTextCursor, QTextBlock,
    QTextCharFormat, QPen, QBrush, QKeySequence, QShortcut, QSyntaxHighlighter,
    QFontMetrics, QTextDocument, QTextOption
)
from PySide6.QtCore import (
    Qt, QRect, QSize, QPoint, Signal, Slot, QTimer, QEvent,
    QRegularExpression
)

from .styles import (
    ThemeColors, get_syntax_highlighter, get_editor_font,
    PythonSyntaxHighlighter, JavaScriptSyntaxHighlighter
)


@dataclass
class BracketPair:
    """Represents a matching bracket pair"""
    opening: str
    closing: str
    opening_pos: int
    closing_pos: int


class LineNumberArea(QWidget):
    """Widget for displaying line numbers in the editor"""
    
    def __init__(self, editor: 'CodeEditor'):
        super().__init__(editor)
        self.editor = editor
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedWidth(self.calculate_width())
        
        # Connect to editor signals
        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_area)
        
        # Styling
        self.line_number_color = QColor(ThemeColors.FOREGROUND_DIM)
        self.current_line_color = QColor(ThemeColors.FOREGROUND)
        self.background_color = QColor(ThemeColors.BACKGROUND_DARKER)
    
    def calculate_width(self) -> int:
        """Calculate the width needed for line numbers"""
        digits = len(str(max(1, self.editor.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def update_width(self, new_block_count: int):
        """Update the width when block count changes"""
        self.setFixedWidth(self.calculate_width())
    
    def update_area(self, rect: QRect, dy: int):
        """Update the line number area when the editor scrolls"""
        if dy:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())
        
        if rect.contains(self.editor.viewport().rect()):
            self.update_width(0)
    
    def paintEvent(self, event):
        """Paint the line numbers"""
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.background_color)
        
        # Get the current viewport offset
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
        bottom = top + self.editor.blockBoundingRect(block).height()
        
        font = self.editor.font()
        painter.setFont(font)
        
        current_block_number = self.editor.textCursor().blockNumber()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = block_number + 1
                
                # Highlight current line
                if block_number == current_block_number:
                    painter.setPen(self.current_line_color)
                    painter.setFont(QFont(font.family(), font.pointSize(), QFont.Bold))
                else:
                    painter.setPen(self.line_number_color)
                    painter.setFont(font)
                
                # Draw the line number
                painter.drawText(
                    0, int(top),
                    self.width() - 5, self.editor.fontMetrics().height(),
                    Qt.AlignRight | Qt.AlignVCenter,
                    str(number)
                )
            
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1
        
        painter.end()
    
    def sizeHint(self) -> QSize:
        """Return the size hint for the widget"""
        return QSize(self.calculate_width(), 0)


class MinimapWidget(QWidget):
    """Minimap widget showing a scaled-down view of the code"""
    
    def __init__(self, editor: 'CodeEditor'):
        super().__init__(editor)
        self.editor = editor
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setMinimumWidth(80)
        self.setMaximumWidth(120)
        self.setFixedWidth(100)
        
        # Connect to editor signals
        self.editor.textChanged.connect(self.update)
        self.editor.verticalScrollBar().valueChanged.connect(self.update_viewport)
        
        self.scale = 0.15
        self.viewport_ratio = 0.0
        self.background_color = QColor(ThemeColors.BACKGROUND_DARKER)
        self.viewport_color = QColor(ThemeColors.ACCENT + "40")  # Semi-transparent
        self.line_color = QColor(ThemeColors.FOREGROUND_DIM + "60")
    
    def update_viewport(self, value: int):
        """Update the viewport indicator position"""
        scrollbar = self.editor.verticalScrollBar()
        if scrollbar.maximum() > 0:
            self.viewport_ratio = value / scrollbar.maximum()
        self.update()
    
    def paintEvent(self, event):
        """Paint the minimap content"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        
        # Draw background
        painter.fillRect(event.rect(), self.background_color)
        
        # Get document content
        document = self.editor.document()
        block = document.begin()
        
        y = 0
        font_metrics = QFontMetrics(QFont("Consolas", 2))
        line_height = font_metrics.height()
        
        # Draw lines (simplified representation)
        while block.isValid():
            text = block.text()
            if text.strip():  # Skip empty lines
                # Calculate color based on content
                if text.strip().startswith('#'):
                    color = QColor(ThemeColors.SYNTAX_COMMENT + "80")
                elif text.strip().startswith('def ') or text.strip().startswith('class '):
                    color = QColor(ThemeColors.SYNTAX_FUNCTION + "80")
                else:
                    color = QColor(ThemeColors.FOREGROUND + "40")
                
                # Draw line representation
                width = min(len(text) * 2, self.width() - 5)
                painter.fillRect(5, y, width, max(1, line_height), color)
            
            y += line_height
            block = block.next()
            
            if y > self.height():
                break
        
        # Draw viewport indicator
        viewport_height = max(10, self.height() * 0.1)
        viewport_y = self.viewport_ratio * (self.height() - viewport_height)
        painter.fillRect(0, int(viewport_y), self.width(), int(viewport_height), self.viewport_color)
        
        painter.end()
    
    def sizeHint(self) -> QSize:
        """Return the size hint for the widget"""
        return QSize(100, 0)


class CodeEditor(QPlainTextEdit):
    """Advanced code editor with syntax highlighting, line numbers, and more"""
    
    # Signals
    cursor_position_changed = Signal(int, int)  # line, column
    file_modified = Signal(bool)
    save_requested = Signal()
    find_requested = Signal()
    replace_requested = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None, filepath: Optional[str] = None):
        super().__init__(parent)
        
        self.filepath = filepath
        self.file_modified_flag = False
        self.encoding = 'utf-8'
        self.line_ending = 'LF'
        
        # Editor settings
        self.tab_width = 4
        self.indent_with_spaces = True
        self.auto_indent = True
        self.auto_brackets = True
        self.auto_save = False
        self.word_wrap = False
        self.show_whitespace = False
        self.show_minimap = True
        
        # Bracket matching
        self.bracket_pairs = {
            '(': ')', '[': ']', '{': '}',
            ')': '(', ']': '[', '}': '{'
        }
        self.matched_brackets: Optional[BracketPair] = None
        
        # Code folding
        self.foldable_blocks: Dict[int, bool] = {}
        
        # Undo/Redo stack
        self.undo_stack: List[str] = []
        self.redo_stack: List[str] = []
        self.max_undo_depth = 100
        
        # Setup UI
        self._setup_editor()
        self._setup_line_numbers()
        self._setup_minimap()
        self._setup_syntax_highlighter()
        self._setup_shortcuts()
        self._setup_timer()
        
        # Connect signals
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)
    
    def _setup_editor(self):
        """Setup basic editor configuration"""
        # Font
        self.font = get_editor_font()
        self.setFont(self.font)
        
        # Document options
        self.setLineWrapMode(QPlainTextEdit.NoWrap if not self.word_wrap else QPlainTextEdit.WidgetWidth)
        self.setTabStopDistance(self.tab_width * self.fontMetrics().horizontalAdvance(' '))
        self.setUndoRedoEnabled(True)
        
        # Cursor
        self.setCursorWidth(2)
        self.setCursor(Qt.IBeamCursor)
        
        # Scrollbar policy
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Frame
        self.setFrameStyle(QPlainTextEdit.NoFrame)
        
        # Colors
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                color: {ThemeColors.FOREGROUND};
                selection-background-color: {ThemeColors.SELECTION};
            }}
        """)
        
        # Viewport margins (will be updated for line numbers)
        self.setViewportMargins(60, 0, 0, 0)
    
    def _setup_line_numbers(self):
        """Setup line number area"""
        self.line_number_area = LineNumberArea(self)
    
    def _setup_minimap(self):
        """Setup minimap widget"""
        self.minimap = MinimapWidget(self)
        self.minimap.setVisible(self.show_minimap)
    
    def _setup_syntax_highlighter(self):
        """Setup syntax highlighting based on file type"""
        self.highlighter: Optional[QSyntaxHighlighter] = None
        self._update_syntax_highlighter()
    
    def _update_syntax_highlighter(self):
        """Update the syntax highlighter based on file extension"""
        if self.filepath:
            _, ext = os.path.splitext(self.filepath)
            highlighter_class = get_syntax_highlighter(ext)
            if highlighter_class:
                self.highlighter = highlighter_class(self.document())
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Save
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.save_requested.emit)
        
        # Find
        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.activated.connect(self.find_requested.emit)
        
        # Replace
        replace_shortcut = QShortcut(QKeySequence.StandardKey.Replace, self)
        replace_shortcut.activated.connect(self.replace_requested.emit)
        
        # Duplicate line
        dup_shortcut = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_D), self)
        dup_shortcut.activated.connect(self.duplicate_line)
        
        # Move line up
        up_shortcut = QShortcut(QKeySequence(Qt.ALT | Qt.Key_Up), self)
        up_shortcut.activated.connect(lambda: self.move_line(-1))
        
        # Move line down
        down_shortcut = QShortcut(QKeySequence(Qt.ALT | Qt.Key_Down), self)
        down_shortcut.activated.connect(lambda: self.move_line(1))
        
        # Toggle comment
        comment_shortcut = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Slash), self)
        comment_shortcut.activated.connect(self.toggle_comment)
    
    def _setup_timer(self):
        """Setup auto-save and other timers"""
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._auto_save)
        if self.auto_save:
            self.auto_save_timer.start(30000)  # Save every 30 seconds
    
    def _on_text_changed(self):
        """Handle text changed event"""
        self.file_modified_flag = True
        self.file_modified.emit(True)
        
        # Update bracket matching
        self._update_bracket_matching()
    
    def _on_cursor_position_changed(self):
        """Handle cursor position changed event"""
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.positionInBlock() + 1
        self.cursor_position_changed.emit(line, column)
        
        # Highlight current line
        self._highlight_current_line()
    
    def _highlight_current_line(self):
        """Highlight the current line"""
        extra_selections = []
        
        # Current line highlight
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(ThemeColors.BACKGROUND_LIGHTER))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        extra_selections.append(selection)
        
        # Bracket highlight
        if self.matched_brackets:
            for pos in [self.matched_brackets.opening_pos, self.matched_brackets.closing_pos]:
                cursor = QTextCursor(self.document())
                cursor.setPosition(pos)
                cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
                
                bracket_selection = QTextEdit.ExtraSelection()
                bracket_selection.format.setBackground(QColor(ThemeColors.SELECTION))
                bracket_selection.cursor = cursor
                extra_selections.append(bracket_selection)
        
        self.setExtraSelections(extra_selections)
    
    def _update_bracket_matching(self):
        """Find and highlight matching brackets"""
        cursor = self.textCursor()
        pos = cursor.position()
        
        # Check character before cursor
        if pos > 0:
            char_before = self.document().characterAt(pos - 1)
            if char_before in self.bracket_pairs:
                self._find_matching_bracket(pos - 1, char_before)
                return
        
        # Check character at cursor
        char_at = self.document().characterAt(pos)
        if char_at in self.bracket_pairs:
            self._find_matching_bracket(pos, char_at)
            return
        
        self.matched_brackets = None
    
    def _find_matching_bracket(self, pos: int, char: str):
        """Find the matching bracket for the character at pos"""
        if char in '([{':
            # Find closing bracket
            target = self.bracket_pairs[char]
            depth = 1
            current_pos = pos + 1
            
            while current_pos < self.document().characterCount() and depth > 0:
                current_char = self.document().characterAt(current_pos)
                if current_char == char:
                    depth += 1
                elif current_char == target:
                    depth -= 1
                current_pos += 1
            
            if depth == 0:
                self.matched_brackets = BracketPair(char, target, pos, current_pos - 1)
        
        elif char in ')]}':
            # Find opening bracket
            target = self.bracket_pairs[char]
            depth = 1
            current_pos = pos - 1
            
            while current_pos >= 0 and depth > 0:
                current_char = self.document().characterAt(current_pos)
                if current_char == char:
                    depth += 1
                elif current_char == target:
                    depth -= 1
                current_pos -= 1
            
            if depth == 0:
                self.matched_brackets = BracketPair(target, char, current_pos + 1, pos)
    
    def _auto_save(self):
        """Auto-save the file if modified"""
        if self.file_modified_flag and self.filepath:
            self.save_file()
    
    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        
        # Resize line number area
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area.width(), cr.height())
        )
        
        # Resize minimap
        if self.show_minimap:
            self.minimap.setGeometry(
                QRect(cr.right() - self.minimap.width(), cr.top(), 
                      self.minimap.width(), cr.height())
            )
            self.setViewportMargins(
                self.line_number_area.width(), 0,
                self.minimap.width(), 0
            )
        else:
            self.setViewportMargins(self.line_number_area.width(), 0, 0, 0)
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()
        
        # Handle Tab
        if key == Qt.Key_Tab:
            self._handle_tab()
            return
        
        # Handle Backspace
        if key == Qt.Key_Backspace:
            self._handle_backspace()
            return
        
        # Handle Return/Enter
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._handle_return()
            return
        
        # Auto-close brackets
        if self.auto_brackets and text in '([{\'"':
            self._handle_auto_bracket(text)
            return
        
        # Auto-close for closing brackets (just move cursor if matching)
        if self.auto_brackets and text in ')]}':
            cursor = self.textCursor()
            if cursor.position() < self.document().characterCount():
                next_char = self.document().characterAt(cursor.position())
                if next_char == text:
                    cursor.movePosition(QTextCursor.NextCharacter)
                    self.setTextCursor(cursor)
                    return
        
        super().keyPressEvent(event)
    
    def _handle_tab(self):
        """Handle Tab key press"""
        cursor = self.textCursor()
        
        if cursor.hasSelection():
            # Indent selection
            self.indent_selection()
        else:
            # Insert tab or spaces
            if self.indent_with_spaces:
                cursor.insertText(' ' * self.tab_width)
            else:
                cursor.insertText('\t')
    
    def _handle_backspace(self):
        """Handle Backspace key press"""
        cursor = self.textCursor()
        
        # Check for unindent opportunity
        if not cursor.hasSelection():
            line_text = cursor.block().text()
            column = cursor.positionInBlock()
            
            # If at start of indentation, unindent
            if column > 0 and column <= len(line_text):
                if line_text[:column].strip() == '':
                    # Unindent to previous tab stop
                    new_column = (column // self.tab_width) * self.tab_width
                    if new_column == column:
                        new_column = max(0, column - self.tab_width)
                    
                    cursor.movePosition(QTextCursor.StartOfBlock)
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, column)
                    cursor.removeSelectedText()
                    
                    if new_column > 0:
                        cursor.insertText(' ' * new_column)
                    return
        
        super().keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier))
    
    def _handle_return(self):
        """Handle Return/Enter key press"""
        cursor = self.textCursor()
        current_block = cursor.block()
        line_text = current_block.text()
        
        # Calculate indentation
        indent = ''
        for char in line_text:
            if char in ' \t':
                indent += char
            else:
                break
        
        # Check for bracket at end of line
        if line_text.rstrip().endswith((':', '(', '[', '{')):
            indent += ' ' * self.tab_width if self.indent_with_spaces else '\t'
        
        # Check for colon (Python)
        elif line_text.rstrip().endswith(':'):
            indent += ' ' * self.tab_width if self.indent_with_spaces else '\t'
        
        cursor.insertText('\n' + indent)
    
    def _handle_auto_bracket(self, bracket: str):
        """Handle auto-closing of brackets"""
        cursor = self.textCursor()
        
        # Determine closing bracket
        closing = {
            '(': ')', '[': ']', '{': '}',
            '"': '"', "'": "'"
        }.get(bracket)
        
        if closing:
            # Check if we should auto-close
            if bracket in '\'"':
                # Only auto-close if there's no selection or it's at the start of text
                pos = cursor.position()
                if pos > 0:
                    prev_char = self.document().characterAt(pos - 1)
                    if prev_char.isalnum() or prev_char == '_':
                        cursor.insertText(bracket)
                        return
                
                cursor.insertText(bracket + closing)
                cursor.movePosition(QTextCursor.Left)
                self.setTextCursor(cursor)
            else:
                cursor.insertText(bracket + closing)
                cursor.movePosition(QTextCursor.Left)
                self.setTextCursor(cursor)
    
    def duplicate_line(self):
        """Duplicate the current line or selection"""
        cursor = self.textCursor()
        
        if cursor.hasSelection():
            # Duplicate selection
            selected_text = cursor.selectedText()
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.EndOfLine)
            cursor.insertText('\n' + selected_text)
        else:
            # Duplicate line
            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.MoveAnchor)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            line_text = cursor.selectedText()
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.EndOfLine)
            cursor.insertText('\n' + line_text)
    
    def move_line(self, direction: int):
        """Move the current line up or down"""
        cursor = self.textCursor()
        current_block = cursor.block()
        
        if direction < 0:  # Move up
            prev_block = current_block.previous()
            if not prev_block.isValid():
                return
            
            # Swap lines
            current_text = current_block.text()
            prev_text = prev_block.text()
            
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.StartOfLine)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
            cursor.insertText(prev_text + '\n')
            cursor.movePosition(QTextCursor.Up)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            cursor.insertText(current_text)
            cursor.endEditBlock()
        
        else:  # Move down
            next_block = current_block.next()
            if not next_block.isValid():
                return
            
            # Swap lines
            current_text = current_block.text()
            next_text = next_block.text()
            
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.EndOfLine)
            cursor.insertText('\n' + next_text)
            cursor.movePosition(QTextCursor.Up)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            cursor.insertText(current_text)
            cursor.endEditBlock()
    
    def toggle_comment(self):
        """Toggle comment on the current line or selection"""
        cursor = self.textCursor()
        
        if cursor.hasSelection():
            # Toggle comment on selection
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            
            cursor.beginEditBlock()
            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.StartOfLine)
            
            while cursor.position() <= end:
                line_text = cursor.block().text()
                
                cursor.movePosition(QTextCursor.StartOfLine)
                cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
                
                if line_text.strip().startswith('#'):
                    # Uncomment
                    text = cursor.selectedText()
                    new_text = text.replace('#', '', 1)
                    cursor.insertText(new_text)
                else:
                    # Comment
                    cursor.insertText('#' + cursor.selectedText())
                
                cursor.movePosition(QTextCursor.Down)
                if cursor.atEnd():
                    break
            
            cursor.endEditBlock()
        else:
            # Toggle comment on current line
            cursor.movePosition(QTextCursor.StartOfLine)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            line_text = cursor.selectedText()
            
            if line_text.strip().startswith('#'):
                # Uncomment
                new_text = line_text.replace('#', '', 1)
                cursor.insertText(new_text)
            else:
                # Comment
                cursor.insertText('#' + line_text)
    
    def indent_selection(self):
        """Indent the selected text"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        
        indent_str = ' ' * self.tab_width if self.indent_with_spaces else '\t'
        
        while cursor.position() <= end:
            cursor.insertText(indent_str)
            cursor.movePosition(QTextCursor.Down)
            if cursor.atEnd():
                break
        
        cursor.endEditBlock()
    
    def unindent_selection(self):
        """Unindent the selected text"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        
        while cursor.position() <= end:
            line_text = cursor.block().text()
            
            if line_text.startswith('\t'):
                cursor.deleteChar()
            elif line_text.startswith(' ' * self.tab_width):
                for _ in range(self.tab_width):
                    cursor.deleteChar()
            elif line_text.startswith(' '):
                cursor.deleteChar()
            
            cursor.movePosition(QTextCursor.Down)
            if cursor.atEnd():
                break
        
        cursor.endEditBlock()
    
    def load_file(self, filepath: str) -> bool:
        """Load a file into the editor"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.filepath = filepath
            self.setPlainText(content)
            self.file_modified_flag = False
            self.file_modified.emit(False)
            
            # Update syntax highlighter
            self._update_syntax_highlighter()
            
            # Detect line ending
            if '\r\n' in content:
                self.line_ending = 'CRLF'
            elif '\r' in content:
                self.line_ending = 'CR'
            else:
                self.line_ending = 'LF'
            
            return True
        
        except Exception as e:
            print(f"Error loading file: {e}")
            return False
    
    def save_file(self, filepath: Optional[str] = None) -> bool:
        """Save the editor content to a file"""
        save_path = filepath or self.filepath
        
        if not save_path:
            return False
        
        try:
            content = self.toPlainText()
            
            # Apply line ending
            if self.line_ending == 'CRLF':
                content = content.replace('\n', '\r\n')
            elif self.line_ending == 'CR':
                content = content.replace('\n', '\r')
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.filepath = save_path
            self.file_modified_flag = False
            self.file_modified.emit(False)
            
            return True
        
        except Exception as e:
            print(f"Error saving file: {e}")
            return False
    
    def goto_line(self, line_number: int):
        """Go to a specific line number"""
        block = self.document().findBlockByNumber(line_number - 1)
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.centerCursor()
    
    def find_text(self, text: str, case_sensitive: bool = False, 
                  whole_words: bool = False, regex: bool = False) -> List[QTextCursor]:
        """Find all occurrences of text in the document"""
        results = []
        document = self.document()
        
        if regex:
            pattern = QRegularExpression(text)
            if not case_sensitive:
                pattern.setPatternOptions(QRegularExpression.CaseInsensitiveOption)
            
            cursor = document.find(pattern)
            while not cursor.isNull():
                results.append(QTextCursor(cursor))
                cursor = document.find(pattern, cursor)
        
        else:
            flags = QTextDocument.FindFlags()
            if case_sensitive:
                flags |= QTextDocument.FindCaseSensitively
            if whole_words:
                flags |= QTextDocument.FindWholeWords
            
            cursor = QTextCursor(document)
            cursor.beginEditBlock()
            
            cursor = document.find(text, cursor, flags)
            while not cursor.isNull():
                results.append(QTextCursor(cursor))
                cursor = document.find(text, cursor, flags)
            
            cursor.endEditBlock()
        
        return results
    
    def replace_text(self, find_text: str, replace_text: str,
                     case_sensitive: bool = False, whole_words: bool = False,
                     replace_all: bool = False) -> int:
        """Replace text in the document"""
        count = 0
        cursor = self.textCursor()
        
        if replace_all:
            # Find all and replace
            results = self.find_text(find_text, case_sensitive, whole_words)
            cursor.beginEditBlock()
            
            # Replace from end to start to preserve positions
            for result_cursor in reversed(results):
                result_cursor.insertText(replace_text)
                count += 1
            
            cursor.endEditBlock()
        else:
            # Replace current selection or next occurrence
            if cursor.hasSelection() and cursor.selectedText() == find_text:
                cursor.insertText(replace_text)
                count = 1
        
        return count
    
    def contextMenuEvent(self, event):
        """Show context menu"""
        menu = QMenu(self)
        
        # Add standard actions
        menu.addAction("Undo", self.undo, QKeySequence.StandardKey.Undo)
        menu.addAction("Redo", self.redo, QKeySequence.StandardKey.Redo)
        menu.addSeparator()
        menu.addAction("Cut", self.cut, QKeySequence.StandardKey.Cut)
        menu.addAction("Copy", self.copy, QKeySequence.StandardKey.Copy)
        menu.addAction("Paste", self.paste, QKeySequence.StandardKey.Paste)
        menu.addSeparator()
        menu.addAction("Select All", self.selectAll, QKeySequence.StandardKey.SelectAll)
        menu.addSeparator()
        menu.addAction("Toggle Comment", self.toggle_comment, QKeySequence(Qt.CTRL | Qt.Key_Slash))
        menu.addAction("Duplicate Line", self.duplicate_line, QKeySequence(Qt.CTRL | Qt.Key_D))
        
        menu.exec(event.globalPos())
    
    def get_file_info(self) -> Dict[str, Any]:
        """Get information about the current file"""
        return {
            'filepath': self.filepath,
            'modified': self.file_modified_flag,
            'encoding': self.encoding,
            'line_ending': self.line_ending,
            'language': self._detect_language(),
            'lines': self.blockCount(),
            'characters': len(self.toPlainText())
        }
    
    def _detect_language(self) -> str:
        """Detect the language based on file extension"""
        if not self.filepath:
            return "Unknown"
        
        ext_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.jsx': 'JavaScript (React)',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript (React)',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.json': 'JSON',
            '.xml': 'XML',
            '.md': 'Markdown',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.sh': 'Shell',
            '.bash': 'Bash',
            '.zsh': 'Zsh',
            '.c': 'C',
            '.cpp': 'C++',
            '.h': 'C Header',
            '.hpp': 'C++ Header',
            '.java': 'Java',
            '.kt': 'Kotlin',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.sql': 'SQL',
            '.txt': 'Plain Text'
        }
        
        _, ext = os.path.splitext(self.filepath)
        return ext_map.get(ext.lower(), 'Unknown')


# Import QKeyEvent for use in keyPressEvent
from PySide6.QtGui import QKeyEvent
