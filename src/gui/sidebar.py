"""
Sentience v3.0 - Sidebar Components
File explorer, search panel, git panel, AI chat panel, tools panel, and outline panel
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeView, QTreeWidget, QTreeWidgetItem, QSplitter, QFrame,
    QComboBox, QCheckBox, QMenu, QToolButton, QScrollArea,
    QTextEdit, QListWidget, QListWidgetItem, QTabWidget, QSizePolicy,
    QApplication, QHeaderView, QAbstractItemView
)
from PySide6.QtGui import (
    QIcon, QFont, QColor, QStandardItemModel, QStandardItem,
    QKeySequence, QAction, QCursor, QTextDocument, QTextCursor
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QTimer, QSize, QDir, QFileInfo, QFileSystemWatcher,
    QModelIndex, QAbstractItemModel, QSortFilterProxyModel, QThread
)

from .styles import ThemeColors, get_editor_font


# ============================================================================
# File Explorer Panel
# ============================================================================

@dataclass
class FileItem:
    """Represents a file or directory item"""
    path: str
    name: str
    is_dir: bool
    size: int = 0
    modified: datetime = None
    extension: str = ""


class FileSystemModel(QAbstractItemModel):
    """Custom model for file system tree"""
    
    def __init__(self, root_path: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.root_path = root_path
        self.root_item: Optional[QStandardItem] = None
        self.file_icons: Dict[str, QIcon] = {}
        self.hidden_files_visible = False
        self.show_only_included = False
        self.included_extensions: Set[str] = set()
        
        # File system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._on_directory_changed)
    
    def set_root_path(self, path: str):
        """Set the root path for the model"""
        self.beginResetModel()
        self.root_path = path
        if os.path.isdir(path):
            self.watcher.addPath(path)
        self.endResetModel()
    
    def _on_directory_changed(self, path: str):
        """Handle directory change notification"""
        # Emit dataChanged for the directory
        index = self.index(path)
        self.dataChanged.emit(index, index)
    
    def index(self, path: str, column: int = 0) -> QModelIndex:
        """Get index for a path"""
        if path == self.root_path:
            return QModelIndex()
        
        parent_path = os.path.dirname(path)
        parent_index = self.index(parent_path)
        
        if not parent_index.isValid():
            return QModelIndex()
        
        # Find the item in parent's children
        for i in range(self.rowCount(parent_index)):
            child_index = self.index(i, column, parent_index)
            if self.filePath(child_index) == path:
                return child_index
        
        return QModelIndex()
    
    def filePath(self, index: QModelIndex) -> str:
        """Get file path for an index"""
        if not index.isValid():
            return self.root_path
        
        # Build path from index
        parts = []
        current = index
        while current.isValid():
            parts.append(self.data(current, Qt.DisplayRole))
            current = current.parent()
        
        return os.path.join(self.root_path, *reversed(parts))
    
    def isDir(self, index: QModelIndex) -> bool:
        """Check if index is a directory"""
        path = self.filePath(index)
        return os.path.isdir(path)
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of rows under parent"""
        if parent.column() > 0:
            return 0
        
        path = self.filePath(parent)
        
        if not os.path.isdir(path):
            return 0
        
        try:
            entries = os.listdir(path)
            if not self.hidden_files_visible:
                entries = [e for e in entries if not e.startswith('.')]
            
            return len(entries)
        except PermissionError:
            return 0
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of columns"""
        return 1
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """Return data for role at index"""
        if not index.isValid():
            return None
        
        path = self.filePath(index)
        
        if role == Qt.DisplayRole:
            return os.path.basename(path)
        
        elif role == Qt.DecorationRole:
            if os.path.isdir(path):
                return QApplication.style().standardIcon(QApplication.Style.SP_DirIcon)
            else:
                return self._get_file_icon(path)
        
        elif role == Qt.ToolTipRole:
            return path
        
        return None
    
    def _get_file_icon(self, path: str) -> QIcon:
        """Get icon for a file based on extension"""
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        
        if ext in self.file_icons:
            return self.file_icons[ext]
        
        # Default icon
        return QApplication.style().standardIcon(QApplication.Style.SP_FileIcon)
    
    def parent(self, index: QModelIndex) -> QModelIndex:
        """Return parent of index"""
        if not index.isValid():
            return QModelIndex()
        
        path = self.filePath(index)
        parent_path = os.path.dirname(path)
        
        if parent_path == self.root_path or not parent_path.startswith(self.root_path):
            return QModelIndex()
        
        return self.index(parent_path)
    
    def index_path(self, row: int, column: int, parent: QModelIndex) -> QModelIndex:
        """Create index for row/column under parent"""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        parent_path = self.filePath(parent)
        
        if not os.path.isdir(parent_path):
            return QModelIndex()
        
        try:
            entries = sorted(os.listdir(parent_path))
            if not self.hidden_files_visible:
                entries = [e for e in entries if not e.startswith('.')]
            
            if row >= len(entries):
                return QModelIndex()
            
            child_path = os.path.join(parent_path, entries[row])
            return self.createIndex(row, column, child_path)
        
        except PermissionError:
            return QModelIndex()
    
    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:
        """Check if parent has children"""
        path = self.filePath(parent)
        if os.path.isdir(path):
            try:
                entries = os.listdir(path)
                if not self.hidden_files_visible:
                    entries = [e for e in entries if not e.startswith('.')]
                return len(entries) > 0
            except PermissionError:
                return False
        return False
    
    def canFetchMore(self, parent: QModelIndex) -> bool:
        """Check if more children can be fetched"""
        return self.hasChildren(parent) and not self.hasChildren(parent)
    
    def fetchMore(self, parent: QModelIndex):
        """Fetch more children"""
        self.beginInsertRows(parent, 0, self.rowCount(parent) - 1)
        self.endInsertRows()


class FileExplorerPanel(QWidget):
    """File explorer sidebar panel"""
    
    # Signals
    file_opened = Signal(str)
    file_deleted = Signal(str)
    file_renamed = Signal(str, str)
    directory_changed = Signal(str)
    new_file_requested = Signal(str)
    new_folder_requested = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.root_path = os.getcwd()
        self.hidden_files_visible = False
        
        # Setup UI
        self._setup_ui()
        self._setup_actions()
        self._setup_watcher()
    
    def _setup_ui(self):
        """Setup the file explorer UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        title = QLabel("EXPLORER")
        title.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Action buttons
        self.new_file_btn = QToolButton()
        self.new_file_btn.setText("+")
        self.new_file_btn.setToolTip("New File")
        self.new_file_btn.setFixedSize(20, 20)
        self.new_file_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #858585;
            }
            QToolButton:hover {
                color: #d3d7cf;
            }
        """)
        header_layout.addWidget(self.new_file_btn)
        
        self.new_folder_btn = QToolButton()
        self.new_folder_btn.setText("📁")
        self.new_folder_btn.setToolTip("New Folder")
        self.new_folder_btn.setFixedSize(20, 20)
        self.new_folder_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
            }
            QToolButton:hover {
                background-color: #2d2d30;
            }
        """)
        header_layout.addWidget(self.new_folder_btn)
        
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("↻")
        self.refresh_btn.setToolTip("Refresh")
        self.refresh_btn.setFixedSize(20, 20)
        self.refresh_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #858585;
            }
            QToolButton:hover {
                color: #d3d7cf;
            }
        """)
        header_layout.addWidget(self.refresh_btn)
        
        layout.addWidget(header)
        
        # Quick open / search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                border-bottom: 1px solid {ThemeColors.BORDER};
                padding: 6px 8px;
                color: #d3d7cf;
            }}
        """)
        layout.addWidget(self.search_input)
        
        # File tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameStyle(QFrame.NoFrame)
        self.tree.setAnimated(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                color: #d3d7cf;
            }}
            QTreeWidget::item {{
                padding: 4px 8px;
                border-radius: 2px;
            }}
            QTreeWidget::item:selected {{
                background-color: {ThemeColors.SELECTION};
            }}
            QTreeWidget::item:hover {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
            }}
        """)
        layout.addWidget(self.tree)
        
        # Connect signals
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.refresh_btn.clicked.connect(self.refresh)
        self.new_file_btn.clicked.connect(self._on_new_file)
        self.new_folder_btn.clicked.connect(self._on_new_folder)
    
    def _setup_actions(self):
        """Setup context menu actions"""
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
    
    def _setup_watcher(self):
        """Setup file system watcher"""
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._on_directory_changed)
    
    def set_root_path(self, path: str):
        """Set the root path for the explorer"""
        if os.path.isdir(path):
            self.root_path = path
            self.refresh()
            self.directory_changed.emit(path)
    
    def refresh(self):
        """Refresh the file tree"""
        self.tree.clear()
        self._populate_tree(self.root_path, None)
    
    def _populate_tree(self, path: str, parent: Optional[QTreeWidgetItem]):
        """Populate the tree with files and directories"""
        try:
            entries = sorted(os.listdir(path))
            
            if not self.hidden_files_visible:
                entries = [e for e in entries if not e.startswith('.')]
            
            for entry in entries:
                full_path = os.path.join(path, entry)
                item = QTreeWidgetItem(parent or self.tree)
                item.setText(0, entry)
                item.setData(0, Qt.UserRole, full_path)
                
                if os.path.isdir(full_path):
                    item.setIcon(0, QApplication.style().standardIcon(QApplication.Style.SP_DirIcon))
                    item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                    self._populate_tree(full_path, item)
                else:
                    item.setIcon(0, self._get_file_icon(entry))
            
            # Expand root
            if parent is None:
                self.tree.expandAll()
        
        except PermissionError:
            pass
    
    def _get_file_icon(self, filename: str) -> QIcon:
        """Get icon for a file"""
        _, ext = os.path.splitext(filename.lower())
        
        icon_map = {
            '.py': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.js': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.ts': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.html': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.css': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.json': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.md': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
            '.txt': QApplication.style().standardIcon(QApplication.Style.SP_FileIcon),
        }
        
        return icon_map.get(ext, QApplication.style().standardIcon(QApplication.Style.SP_FileIcon))
    
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item double click"""
        path = item.data(0, Qt.UserRole)
        
        if path and os.path.isfile(path):
            self.file_opened.emit(path)
    
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item click"""
        pass
    
    def _on_search_changed(self, text: str):
        """Handle search text change"""
        # Filter tree items
        text = text.lower()
        
        def hide_items(item: QTreeWidgetItem):
            match = text in item.text(0).lower() if text else True
            
            # Check children
            child_match = False
            for i in range(item.childCount()):
                if hide_items(item.child(i)):
                    child_match = True
            
            should_show = match or child_match
            item.setHidden(not should_show)
            
            return should_show
        
        # Apply filter
        for i in range(self.tree.topLevelItemCount()):
            hide_items(self.tree.topLevelItem(i))
    
    def _on_directory_changed(self, path: str):
        """Handle directory change"""
        self.refresh()
    
    def _on_new_file(self):
        """Handle new file request"""
        current = self.tree.currentItem()
        if current:
            path = current.data(0, Qt.UserRole)
            if os.path.isdir(path):
                self.new_file_requested.emit(path)
            else:
                self.new_file_requested.emit(os.path.dirname(path))
        else:
            self.new_file_requested.emit(self.root_path)
    
    def _on_new_folder(self):
        """Handle new folder request"""
        current = self.tree.currentItem()
        if current:
            path = current.data(0, Qt.UserRole)
            if os.path.isdir(path):
                self.new_folder_requested.emit(path)
            else:
                self.new_folder_requested.emit(os.path.dirname(path))
        else:
            self.new_folder_requested.emit(self.root_path)
    
    def _show_context_menu(self, pos: QPoint):
        """Show context menu"""
        item = self.tree.itemAt(pos)
        
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
                color: #d3d7cf;
                border: 1px solid {ThemeColors.BORDER};
            }}
            QMenu::item:selected {{
                background-color: {ThemeColors.ACCENT};
            }}
        """)
        
        if item:
            path = item.data(0, Qt.UserRole)
            
            if os.path.isfile(path):
                # File actions
                open_action = menu.addAction("Open")
                open_action.triggered.connect(lambda: self.file_opened.emit(path))
                
                menu.addSeparator()
                
                rename_action = menu.addAction("Rename")
                rename_action.triggered.connect(lambda: self._rename_item(item))
                
                delete_action = menu.addAction("Delete")
                delete_action.triggered.connect(lambda: self._delete_item(item))
            
            elif os.path.isdir(path):
                # Directory actions
                new_file_action = menu.addAction("New File")
                new_file_action.triggered.connect(lambda: self.new_file_requested.emit(path))
                
                new_folder_action = menu.addAction("New Folder")
                new_folder_action.triggered.connect(lambda: self.new_folder_requested.emit(path))
                
                menu.addSeparator()
                
                rename_action = menu.addAction("Rename")
                rename_action.triggered.connect(lambda: self._rename_item(item))
                
                delete_action = menu.addAction("Delete")
                delete_action.triggered.connect(lambda: self._delete_item(item))
        
        else:
            # Root actions
            new_file_action = menu.addAction("New File")
            new_file_action.triggered.connect(lambda: self.new_file_requested.emit(self.root_path))
            
            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(lambda: self.new_folder_requested.emit(self.root_path))
        
        menu.exec(self.tree.mapToGlobal(pos))
    
    def _rename_item(self, item: QTreeWidgetItem):
        """Rename an item"""
        self.tree.editItem(item)
    
    def _delete_item(self, item: QTreeWidgetItem):
        """Delete an item"""
        path = item.data(0, Qt.UserRole)
        
        if os.path.isfile(path):
            os.remove(path)
            self.file_deleted.emit(path)
        elif os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
        
        self.refresh()


# ============================================================================
# Search Panel
# ============================================================================

@dataclass
class SearchResult:
    """Represents a search result"""
    file_path: str
    line_number: int
    column: int
    line_text: str
    match_text: str


class SearchPanel(QWidget):
    """Search panel for searching files and content"""
    
    # Signals
    result_selected = Signal(str, int, int)  # file, line, column
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.results: List[SearchResult] = []
        self.root_path = os.getcwd()
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the search panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("SEARCH")
        header.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        layout.addWidget(header)
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                color: #d3d7cf;
            }}
        """)
        layout.addWidget(self.search_input)
        
        # Options row
        options = QWidget()
        options_layout = QHBoxLayout(options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(8)
        
        self.case_sensitive = QCheckBox("Aa")
        self.case_sensitive.setStyleSheet("color: #858585;")
        options_layout.addWidget(self.case_sensitive)
        
        self.whole_word = QCheckBox("W")
        self.whole_word.setToolTip("Match whole word")
        self.whole_word.setStyleSheet("color: #858585;")
        options_layout.addWidget(self.whole_word)
        
        self.regex = QCheckBox(".*")
        self.regex.setToolTip("Regular expression")
        self.regex.setStyleSheet("color: #858585;")
        options_layout.addWidget(self.regex)
        
        options_layout.addStretch()
        
        layout.addWidget(options)
        
        # Files to include/exclude
        self.include_input = QLineEdit()
        self.include_input.setPlaceholderText("Files to include (e.g., *.py)")
        self.include_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                color: #d3d7cf;
            }}
        """)
        layout.addWidget(self.include_input)
        
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("Files to exclude")
        self.exclude_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                color: #d3d7cf;
            }}
        """)
        layout.addWidget(self.exclude_input)
        
        # Search button
        self.search_btn = QPushButton("Search")
        self.search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.ACCENT_HOVER};
            }}
        """)
        layout.addWidget(self.search_btn)
        
        # Results count
        self.results_label = QLabel("0 results")
        self.results_label.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(self.results_label)
        
        # Results list
        self.results_list = QTreeWidget()
        self.results_list.setHeaderHidden(True)
        self.results_list.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                color: #d3d7cf;
            }}
            QTreeWidget::item {{
                padding: 2px 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: {ThemeColors.SELECTION};
            }}
        """)
        layout.addWidget(self.results_list)
        
        # Connect signals
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.results_list.itemDoubleClicked.connect(self._on_result_clicked)
    
    def set_root_path(self, path: str):
        """Set the root path for searching"""
        self.root_path = path
    
    def _search(self):
        """Execute search"""
        query = self.search_input.text()
        
        if not query:
            return
        
        self.results.clear()
        self.results_list.clear()
        
        # Get include/exclude patterns
        include = self.include_input.text()
        exclude = self.exclude_input.text()
        
        # Build regex pattern
        if self.regex.isChecked():
            pattern = re.compile(query)
        else:
            pattern = re.compile(re.escape(query))
        
        flags = 0 if self.case_sensitive.isChecked() else re.IGNORECASE
        
        # Search files
        for root, dirs, files in os.walk(self.root_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                # Check include/exclude
                if include and not any(fnmatch.fnmatch(filename, p) for p in include.split(',')):
                    continue
                if exclude and any(fnmatch.fnmatch(filename, p) for p in exclude.split(',')):
                    continue
                
                filepath = os.path.join(root, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f):
                            matches = list(pattern.finditer(line))
                            for match in matches:
                                result = SearchResult(
                                    file_path=filepath,
                                    line_number=i + 1,
                                    column=match.start(),
                                    line_text=line.strip(),
                                    match_text=match.group()
                                )
                                self.results.append(result)
                
                except Exception:
                    pass
        
        # Update results list
        self._update_results()
    
    def _update_results(self):
        """Update the results list"""
        self.results_label.setText(f"{len(self.results)} results")
        
        # Group by file
        files: Dict[str, List[SearchResult]] = {}
        for result in self.results:
            if result.file_path not in files:
                files[result.file_path] = []
            files[result.file_path].append(result)
        
        # Add to tree
        for filepath, results in files.items():
            file_item = QTreeWidgetItem(self.results_list)
            file_item.setText(0, os.path.basename(filepath))
            file_item.setToolTip(0, filepath)
            
            for result in results:
                result_item = QTreeWidgetItem(file_item)
                result_item.setText(0, f"{result.line_number}: {result.line_text}")
                result_item.setData(0, Qt.UserRole, result)
        
        self.results_list.expandAll()
    
    def _on_result_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle result click"""
        result = item.data(0, Qt.UserRole)
        
        if isinstance(result, SearchResult):
            self.result_selected.emit(
                result.file_path,
                result.line_number,
                result.column
            )


# ============================================================================
# Git Panel
# ============================================================================

class GitPanel(QWidget):
    """Git panel for version control"""
    
    # Signals
    file_status_clicked = Signal(str, str)  # file, status
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.repo_path = os.getcwd()
        self.is_repo = False
        
        self._setup_ui()
        self._detect_repo()
    
    def _setup_ui(self):
        """Setup the git panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("SOURCE CONTROL")
        header.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        layout.addWidget(header)
        
        # Branch info
        branch_widget = QWidget()
        branch_layout = QHBoxLayout(branch_widget)
        branch_layout.setContentsMargins(0, 0, 0, 0)
        
        self.branch_label = QLabel("main")
        self.branch_label.setStyleSheet(f"""
            QLabel {{
                background-color: {ThemeColors.ACCENT};
                color: white;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
        """)
        branch_layout.addWidget(self.branch_label)
        branch_layout.addStretch()
        
        layout.addWidget(branch_widget)
        
        # Commit message input
        self.commit_input = QLineEdit()
        self.commit_input.setPlaceholderText("Commit message...")
        self.commit_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                color: #d3d7cf;
            }}
        """)
        layout.addWidget(self.commit_input)
        
        # Commit button
        commit_btn = QPushButton("Commit")
        commit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.ACCENT_HOVER};
            }}
        """)
        layout.addWidget(commit_btn)
        
        # Changes list
        changes_label = QLabel("Changes")
        changes_label.setStyleSheet("color: #858585; font-weight: bold; margin-top: 8px;")
        layout.addWidget(changes_label)
        
        self.changes_list = QTreeWidget()
        self.changes_list.setHeaderHidden(True)
        self.changes_list.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                color: #d3d7cf;
            }}
            QTreeWidget::item {{
                padding: 2px 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: {ThemeColors.SELECTION};
            }}
        """)
        layout.addWidget(self.changes_list)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(self.status_label)
        
        # Connect signals
        self.changes_list.itemDoubleClicked.connect(self._on_file_clicked)
        commit_btn.clicked.connect(self._commit)
    
    def set_repo_path(self, path: str):
        """Set the repository path"""
        self.repo_path = path
        self._detect_repo()
    
    def _detect_repo(self):
        """Detect if path is a git repository"""
        git_dir = os.path.join(self.repo_path, '.git')
        self.is_repo = os.path.isdir(git_dir)
        
        if self.is_repo:
            self._refresh_status()
        else:
            self.status_label.setText("Not a git repository")
    
    def _refresh_status(self):
        """Refresh git status"""
        if not self.is_repo:
            return
        
        self.changes_list.clear()
        
        # Run git status
        try:
            import subprocess
            
            # Get branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self.branch_label.setText(result.stdout.strip() or "HEAD")
            
            # Get status
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                changes = result.stdout.strip().split('\n')
                changes = [c for c in changes if c]
                
                for change in changes:
                    status = change[:2]
                    filepath = change[3:]
                    
                    item = QTreeWidgetItem(self.changes_list)
                    item.setText(0, filepath)
                    item.setData(0, Qt.UserRole, filepath)
                    
                    # Color based on status
                    if 'M' in status:
                        item.setForeground(0, QColor(ThemeColors.WARNING))
                    elif 'A' in status:
                        item.setForeground(0, QColor(ThemeColors.SUCCESS))
                    elif 'D' in status:
                        item.setForeground(0, QColor(ThemeColors.ERROR))
                    elif '?' in status:
                        item.setForeground(0, QColor(ThemeColors.FOREGROUND_DIM))
                
                self.status_label.setText(f"{len(changes)} changes")
        
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
    
    def _on_file_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle file click"""
        filepath = item.data(0, Qt.UserRole)
        status = item.text(0)[:2]
        self.file_status_clicked.emit(filepath, status)
    
    def _commit(self):
        """Commit changes"""
        message = self.commit_input.text()
        
        if not message:
            return
        
        try:
            import subprocess
            
            # Add all
            subprocess.run(['git', 'add', '.'], cwd=self.repo_path)
            
            # Commit
            result = subprocess.run(
                ['git', 'commit', '-m', message],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.commit_input.clear()
                self._refresh_status()
        
        except Exception as e:
            print(f"Commit error: {e}")


# ============================================================================
# Tools Panel
# ============================================================================

class ToolsPanel(QWidget):
    """Tools panel with various development tools"""
    
    tool_activated = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the tools panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("TOOLS")
        header.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        layout.addWidget(header)
        
        # Tools list
        self.tools_list = QListWidget()
        self.tools_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                color: #d3d7cf;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {ThemeColors.SELECTION};
            }}
            QListWidget::item:hover {{
                background-color: {ThemeColors.BACKGROUND_LIGHTER};
            }}
        """)
        layout.addWidget(self.tools_list)
        
        # Add tools
        tools = [
            ("Package Manager", "📦"),
            ("Database Browser", "🗄️"),
            ("API Client", "🌐"),
            ("Task Runner", "⚙️"),
            ("Docker Manager", "🐳"),
            ("Environment Manager", "🐍"),
            ("Code Generator", "✨"),
            ("Documentation", "📚"),
        ]
        
        for name, icon in tools:
            item = QListWidgetItem(f"{icon} {name}")
            item.setData(Qt.UserRole, name)
            self.tools_list.addItem(item)
        
        # Connect signals
        self.tools_list.itemDoubleClicked.connect(self._on_tool_clicked)
    
    def _on_tool_clicked(self, item: QListWidgetItem):
        """Handle tool click"""
        tool_name = item.data(Qt.UserRole)
        self.tool_activated.emit(tool_name)


# ============================================================================
# Outline Panel
# ============================================================================

@dataclass
class OutlineItem:
    """Represents an outline item (function, class, etc.)"""
    name: str
    kind: str
    line: int
    column: int
    children: List['OutlineItem'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


class OutlinePanel(QWidget):
    """Outline panel showing code structure"""
    
    item_clicked = Signal(int)  # line number
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.items: List[OutlineItem] = []
        self.current_document = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the outline panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("OUTLINE")
        header.setStyleSheet("font-weight: bold; font-size: 11px; color: #858585;")
        layout.addWidget(header)
        
        # Outline tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border: none;
                color: #d3d7cf;
            }}
            QTreeWidget::item {{
                padding: 2px 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: {ThemeColors.SELECTION};
            }}
        """)
        layout.addWidget(self.tree)
        
        # Connect signals
        self.tree.itemClicked.connect(self._on_item_clicked)
    
    def parse_document(self, content: str, language: str = "python"):
        """Parse document and extract outline"""
        self.items.clear()
        self.tree.clear()
        
        if language == "python":
            self._parse_python(content)
        elif language in ["javascript", "typescript"]:
            self._parse_javascript(content)
        
        self._update_tree()
    
    def _parse_python(self, content: str):
        """Parse Python code for structure"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # Classes
            if line.strip().startswith('class '):
                match = re.match(r'class\s+(\w+)', line.strip())
                if match:
                    item = OutlineItem(
                        name=match.group(1),
                        kind='class',
                        line=i + 1,
                        column=0
                    )
                    self.items.append(item)
            
            # Functions
            elif line.strip().startswith('def '):
                match = re.match(r'def\s+(\w+)', line.strip())
                if match:
                    item = OutlineItem(
                        name=match.group(1),
                        kind='function',
                        line=i + 1,
                        column=0
                    )
                    self.items.append(item)
    
    def _parse_javascript(self, content: str):
        """Parse JavaScript/TypeScript code for structure"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # Classes
            if re.search(r'\bclass\s+\w+', line):
                match = re.search(r'class\s+(\w+)', line)
                if match:
                    item = OutlineItem(
                        name=match.group(1),
                        kind='class',
                        line=i + 1,
                        column=0
                    )
                    self.items.append(item)
            
            # Functions
            elif re.search(r'\bfunction\s+\w+', line):
                match = re.search(r'function\s+(\w+)', line)
                if match:
                    item = OutlineItem(
                        name=match.group(1),
                        kind='function',
                        line=i + 1,
                        column=0
                    )
                    self.items.append(item)
            
            # Arrow functions
            elif re.search(r'const\s+\w+\s*=\s*\([^)]*\)\s*=>', line):
                match = re.search(r'const\s+(\w+)', line)
                if match:
                    item = OutlineItem(
                        name=match.group(1),
                        kind='function',
                        line=i + 1,
                        column=0
                    )
                    self.items.append(item)
    
    def _update_tree(self):
        """Update the tree widget"""
        for item in self.items:
            tree_item = QTreeWidgetItem(self.tree)
            tree_item.setText(0, item.name)
            tree_item.setData(0, Qt.UserRole, item.line)
            
            # Set icon based on kind
            if item.kind == 'class':
                tree_item.setForeground(0, QColor(ThemeColors.SYNTAX_CLASS))
            elif item.kind == 'function':
                tree_item.setForeground(0, QColor(ThemeColors.SYNTAX_FUNCTION))
    
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item click"""
        line = item.data(0, Qt.UserRole)
        if line:
            self.item_clicked.emit(line)


# ============================================================================
# Left Sidebar (Composite)
# ============================================================================

class LeftSidebar(QWidget):
    """Left sidebar with file explorer, search, and git panels"""
    
    file_opened = Signal(str)
    file_deleted = Signal(str)
    directory_changed = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setMinimumWidth(250)
        self.setMaximumWidth(500)
        
        self._setup_ui()
        self._setup_connections()
    
    def _setup_ui(self):
        """Setup the left sidebar UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Tab bar
        self.tab_bar = QWidget()
        tab_layout = QHBoxLayout(self.tab_bar)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(0)
        
        self.tab_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        # Tab buttons
        self.file_btn = QToolButton()
        self.file_btn.setText("📄")
        self.file_btn.setCheckable(True)
        self.file_btn.setChecked(True)
        self.file_btn.setFixedSize(28, 28)
        self.file_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QToolButton:checked {
                border-bottom: 2px solid #007acc;
            }
        """)
        tab_layout.addWidget(self.file_btn)
        
        self.search_btn = QToolButton()
        self.search_btn.setText("🔍")
        self.search_btn.setCheckable(True)
        self.search_btn.setFixedSize(28, 28)
        self.search_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QToolButton:checked {
                border-bottom: 2px solid #007acc;
            }
        """)
        tab_layout.addWidget(self.search_btn)
        
        self.git_btn = QToolButton()
        self.git_btn.setText("🔀")
        self.git_btn.setCheckable(True)
        self.git_btn.setFixedSize(28, 28)
        self.git_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QToolButton:checked {
                border-bottom: 2px solid #007acc;
            }
        """)
        tab_layout.addWidget(self.git_btn)
        
        tab_layout.addStretch()
        
        layout.addWidget(self.tab_bar)
        
        # Stack widget for panels
        self.stack = QFrame()
        self.stack.setStyleSheet(f"background-color: {ThemeColors.BACKGROUND_DARKER};")
        
        stack_layout = QVBoxLayout(self.stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create panels
        self.file_explorer = FileExplorerPanel()
        self.search_panel = SearchPanel()
        self.git_panel = GitPanel()
        
        stack_layout.addWidget(self.file_explorer)
        stack_layout.addWidget(self.search_panel)
        stack_layout.addWidget(self.git_panel)
        
        # Show file explorer by default
        self.search_panel.hide()
        self.git_panel.hide()
        
        layout.addWidget(self.stack)
    
    def _setup_connections(self):
        """Setup signal connections"""
        # Tab buttons
        self.file_btn.clicked.connect(self._show_file_explorer)
        self.search_btn.clicked.connect(self._show_search)
        self.git_btn.clicked.connect(self._show_git)
        
        # File explorer signals
        self.file_explorer.file_opened.connect(self.file_opened.emit)
        self.file_explorer.file_deleted.connect(self.file_deleted.emit)
        self.file_explorer.directory_changed.connect(self.directory_changed.emit)
    
    def _show_file_explorer(self):
        """Show file explorer panel"""
        self.file_btn.setChecked(True)
        self.search_btn.setChecked(False)
        self.git_btn.setChecked(False)
        
        self.file_explorer.show()
        self.search_panel.hide()
        self.git_panel.hide()
    
    def _show_search(self):
        """Show search panel"""
        self.file_btn.setChecked(False)
        self.search_btn.setChecked(True)
        self.git_btn.setChecked(False)
        
        self.file_explorer.hide()
        self.search_panel.show()
        self.git_panel.hide()
    
    def _show_git(self):
        """Show git panel"""
        self.file_btn.setChecked(False)
        self.search_btn.setChecked(False)
        self.git_btn.setChecked(True)
        
        self.file_explorer.hide()
        self.search_panel.hide()
        self.git_panel.show()
    
    def set_root_path(self, path: str):
        """Set the root path for all panels"""
        self.file_explorer.set_root_path(path)
        self.search_panel.set_root_path(path)
        self.git_panel.set_repo_path(path)


# ============================================================================
# Right Sidebar (Composite)
# ============================================================================

class RightSidebar(QWidget):
    """Right sidebar with AI chat, tools, and outline panels"""
    
    outline_item_clicked = Signal(int)
    tool_activated = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setMinimumWidth(250)
        self.setMaximumWidth(500)
        
        self._setup_ui()
        self._setup_connections()
    
    def _setup_ui(self):
        """Setup the right sidebar UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Tab bar
        self.tab_bar = QWidget()
        tab_layout = QHBoxLayout(self.tab_bar)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(0)
        
        self.tab_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND_DARKER};
                border-bottom: 1px solid {ThemeColors.BORDER};
            }}
        """)
        
        # Tab buttons
        self.ai_btn = QToolButton()
        self.ai_btn.setText("🤖")
        self.ai_btn.setCheckable(True)
        self.ai_btn.setChecked(True)
        self.ai_btn.setFixedSize(28, 28)
        self.ai_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QToolButton:checked {
                border-bottom: 2px solid #007acc;
            }
        """)
        tab_layout.addWidget(self.ai_btn)
        
        self.tools_btn = QToolButton()
        self.tools_btn.setText("🔧")
        self.tools_btn.setCheckable(True)
        self.tools_btn.setFixedSize(28, 28)
        self.tools_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QToolButton:checked {
                border-bottom: 2px solid #007acc;
            }
        """)
        tab_layout.addWidget(self.tools_btn)
        
        self.outline_btn = QToolButton()
        self.outline_btn.setText("📋")
        self.outline_btn.setCheckable(True)
        self.outline_btn.setFixedSize(28, 28)
        self.outline_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QToolButton:checked {
                border-bottom: 2px solid #007acc;
            }
        """)
        tab_layout.addWidget(self.outline_btn)
        
        tab_layout.addStretch()
        
        layout.addWidget(self.tab_bar)
        
        # Stack widget for panels
        self.stack = QFrame()
        self.stack.setStyleSheet(f"background-color: {ThemeColors.BACKGROUND_DARKER};")
        
        stack_layout = QVBoxLayout(self.stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        
        # Import AI chat panel (defined in chat_panel.py)
        from .chat_panel import AIChatPanel
        
        # Create panels
        self.ai_chat = AIChatPanel()
        self.tools_panel = ToolsPanel()
        self.outline_panel = OutlinePanel()
        
        stack_layout.addWidget(self.ai_chat)
        stack_layout.addWidget(self.tools_panel)
        stack_layout.addWidget(self.outline_panel)
        
        # Show AI chat by default
        self.tools_panel.hide()
        self.outline_panel.hide()
        
        layout.addWidget(self.stack)
    
    def _setup_connections(self):
        """Setup signal connections"""
        # Tab buttons
        self.ai_btn.clicked.connect(self._show_ai_chat)
        self.tools_btn.clicked.connect(self._show_tools)
        self.outline_btn.clicked.connect(self._show_outline)
        
        # Panel signals
        self.outline_panel.item_clicked.connect(self.outline_item_clicked.emit)
        self.tools_panel.tool_activated.connect(self.tool_activated.emit)
    
    def _show_ai_chat(self):
        """Show AI chat panel"""
        self.ai_btn.setChecked(True)
        self.tools_btn.setChecked(False)
        self.outline_btn.setChecked(False)
        
        self.ai_chat.show()
        self.tools_panel.hide()
        self.outline_panel.hide()
    
    def _show_tools(self):
        """Show tools panel"""
        self.ai_btn.setChecked(False)
        self.tools_btn.setChecked(True)
        self.outline_btn.setChecked(False)
        
        self.ai_chat.hide()
        self.tools_panel.show()
        self.outline_panel.hide()
    
    def _show_outline(self):
        """Show outline panel"""
        self.ai_btn.setChecked(False)
        self.tools_btn.setChecked(False)
        self.outline_btn.setChecked(True)
        
        self.ai_chat.hide()
        self.tools_panel.hide()
        self.outline_panel.show()


# Import fnmatch for search
import fnmatch
