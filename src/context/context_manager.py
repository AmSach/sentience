"""
Context Manager - Manages context for LLM interactions

Features:
- Current file context
- Project-wide context
- Git context (branch, status, recent commits)
- Environment context (variables, runtime info)
"""

import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context for a single file."""
    filepath: str
    content: Optional[str] = None
    language: Optional[str] = None
    size: int = 0
    line_count: int = 0
    last_modified: Optional[datetime] = None
    cursor_position: Optional[tuple] = None  # (line, column)
    selected_text: Optional[str] = None
    visible_range: Optional[tuple] = None  # (start_line, end_line)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    related_files: List[str] = field(default_factory=list)


@dataclass
class GitContext:
    """Git repository context."""
    is_repo: bool = False
    root: Optional[str] = None
    branch: Optional[str] = None
    remote: Optional[str] = None
    remote_url: Optional[str] = None
    status: str = "clean"  # clean, modified, staged, untracked, conflicted
    staged_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    conflicted_files: List[str] = field(default_factory=list)
    recent_commits: List[Dict[str, Any]] = field(default_factory=list)
    current_author: Optional[str] = None
    current_email: Optional[str] = None


@dataclass
class CommitInfo:
    """Git commit information."""
    hash: str
    short_hash: str
    author: str
    email: str
    date: datetime
    message: str
    files_changed: List[str] = field(default_factory=list)


@dataclass
class EnvironmentContext:
    """Runtime environment context."""
    os_type: str = ""
    os_version: str = ""
    python_version: str = ""
    node_version: Optional[str] = None
    cwd: str = ""
    home: str = ""
    shell: str = ""
    env_vars: Dict[str, str] = field(default_factory=dict)
    path: List[str] = field(default_factory=list)
    installed_tools: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class ProjectContext:
    """Project-wide context."""
    root: str
    name: str
    type: str  # library, application, service, monorepo
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    test_dirs: List[str] = field(default_factory=list)
    source_dirs: List[str] = field(default_factory=list)
    docs_dirs: List[str] = field(default_factory=list)
    build_config: Optional[Dict[str, Any]] = None
    package_manager: Optional[str] = None


@dataclass
class ContextSnapshot:
    """Complete context snapshot."""
    timestamp: datetime
    file_contexts: List[FileContext]
    git_context: GitContext
    environment_context: EnvironmentContext
    project_context: Optional[ProjectContext]
    active_file: Optional[str]
    open_files: List[str]
    recent_files: List[str]
    working_directory: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextManager:
    """Manages all context for LLM interactions."""
    
    MAX_RECENT_FILES = 20
    MAX_OPEN_FILES = 10
    MAX_RECENT_COMMITS = 10
    
    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self._file_contexts: Dict[str, FileContext] = {}
        self._git_context: Optional[GitContext] = None
        self._environment_context: Optional[EnvironmentContext] = None
        self._project_context: Optional[ProjectContext] = None
        self._recent_files: deque = deque(maxlen=self.MAX_RECENT_FILES)
        self._open_files: List[str] = []
        self._active_file: Optional[str] = None
        self._context_cache: Dict[str, Any] = {}
        self._watched_dirs: Set[str] = set()
    
    def get_full_context(self) -> ContextSnapshot:
        """Get complete context snapshot."""
        return ContextSnapshot(
            timestamp=datetime.utcnow(),
            file_contexts=list(self._file_contexts.values()),
            git_context=self.get_git_context(),
            environment_context=self.get_environment_context(),
            project_context=self.get_project_context(),
            active_file=self._active_file,
            open_files=self._open_files.copy(),
            recent_files=list(self._recent_files),
            working_directory=str(self.root_path)
        )
    
    # ==================== File Context ====================
    
    def get_file_context(self, filepath: str, 
                         load_content: bool = True,
                         max_content_size: int = 100000) -> FileContext:
        """Get context for a file."""
        abs_path = self._resolve_path(filepath)
        
        # Check cache
        cache_key = f"file:{abs_path}"
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]
        
        context = FileContext(filepath=str(abs_path))
        
        if not os.path.exists(abs_path):
            return context
        
        # Get file stats
        stat = os.stat(abs_path)
        context.size = stat.st_size
        context.last_modified = datetime.fromtimestamp(stat.st_mtime)
        
        # Detect language
        context.language = self._detect_language(abs_path)
        
        # Load content if requested and not too large
        if load_content and context.size <= max_content_size:
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    context.content = f.read()
                context.line_count = context.content.count('\n') + 1
                
                # Extract imports and exports
                context.imports = self._extract_imports(context.content, context.language)
                context.exports = self._extract_exports(context.content, context.language)
            except (IOError, OSError) as e:
                logger.warning(f"Error reading {abs_path}: {e}")
        
        self._context_cache[cache_key] = context
        return context
    
    def set_active_file(self, filepath: str) -> FileContext:
        """Set the active file being edited."""
        abs_path = self._resolve_path(filepath)
        context = self.get_file_context(abs_path)
        
        self._active_file = str(abs_path)
        
        # Add to recent files
        if str(abs_path) in self._recent_files:
            self._recent_files.remove(str(abs_path))
        self._recent_files.appendleft(str(abs_path))
        
        # Add to open files if not already
        if str(abs_path) not in self._open_files:
            if len(self._open_files) >= self.MAX_OPEN_FILES:
                self._open_files.pop(0)
            self._open_files.append(str(abs_path))
        
        return context
    
    def update_cursor_position(self, filepath: str, line: int, column: int) -> None:
        """Update cursor position for a file."""
        abs_path = self._resolve_path(filepath)
        if str(abs_path) in self._file_contexts:
            self._file_contexts[str(abs_path)].cursor_position = (line, column)
    
    def set_selected_text(self, filepath: str, text: str, 
                          start_line: int, start_col: int,
                          end_line: int, end_col: int) -> None:
        """Set selected text range for a file."""
        abs_path = self._resolve_path(filepath)
        cache_key = f"file:{abs_path}"
        if cache_key in self._context_cache:
            context = self._context_cache[cache_key]
            context.selected_text = text
            context.visible_range = (start_line, end_line)
    
    def close_file(self, filepath: str) -> None:
        """Mark a file as closed."""
        abs_path = self._resolve_path(filepath)
        if str(abs_path) in self._open_files:
            self._open_files.remove(str(abs_path))
        
        # Clear cache
        cache_key = f"file:{abs_path}"
        if cache_key in self._context_cache:
            del self._context_cache[cache_key]
    
    def get_related_files(self, filepath: str, max_results: int = 10) -> List[str]:
        """Get files related to the given file."""
        abs_path = self._resolve_path(filepath)
        context = self.get_file_context(abs_path, load_content=True)
        
        related: List[str] = []
        
        # Find files with same imports
        for imp in context.imports:
            resolved = self._resolve_import(imp, abs_path)
            if resolved and resolved not in related:
                related.append(resolved)
        
        # Find files that import this file
        filename = os.path.basename(abs_path)
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'venv', '__pycache__')]
            
            for f in files:
                if f == filename:
                    continue
                
                other_path = os.path.join(root, f)
                other_context = self.get_file_context(other_path, load_content=True)
                
                # Check if other file imports this file
                for other_imp in other_context.imports:
                    if self._import_references_file(other_imp, abs_path):
                        if other_path not in related:
                            related.append(other_path)
                
                if len(related) >= max_results:
                    return related[:max_results]
        
        return related[:max_results]
    
    # ==================== Git Context ====================
    
    def get_git_context(self) -> GitContext:
        """Get Git repository context."""
        if self._git_context is not None:
            return self._git_context
        
        context = GitContext()
        
        # Check if we're in a git repo
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True, text=True, cwd=self.root_path
            )
            
            if result.returncode == 0:
                context.is_repo = True
                context.root = result.stdout.strip()
            else:
                return context
        except (subprocess.SubprocessError, FileNotFoundError):
            return context
        
        # Get branch
        try:
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                capture_output=True, text=True, cwd=self.root_path
            )
            context.branch = result.stdout.strip() if result.returncode == 0 else None
        except subprocess.SubprocessError:
            pass
        
        # Get remote
        try:
            result = subprocess.run(
                ['git', 'remote', '-v'],
                capture_output=True, text=True, cwd=self.root_path
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines:
                    parts = lines[0].split()
                    context.remote = parts[0] if parts else None
                    context.remote_url = parts[1] if len(parts) > 1 else None
        except subprocess.SubprocessError:
            pass
        
        # Get status
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True, text=True, cwd=self.root_path
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
                
                for line in lines:
                    if not line:
                        continue
                    
                    status_code = line[:2]
                    filepath = line[3:]
                    
                    if 'M' in status_code:
                        context.modified_files.append(filepath)
                    elif 'A' in status_code or 'R' in status_code:
                        context.staged_files.append(filepath)
                    elif '?' in status_code:
                        context.untracked_files.append(filepath)
                    elif 'U' in status_code:
                        context.conflicted_files.append(filepath)
                
                if context.conflicted_files:
                    context.status = 'conflicted'
                elif context.modified_files or context.staged_files:
                    context.status = 'modified'
                elif context.untracked_files:
                    context.status = 'untracked'
                else:
                    context.status = 'clean'
        except subprocess.SubprocessError:
            pass
        
        # Get recent commits
        try:
            result = subprocess.run(
                ['git', 'log', f'-{self.MAX_RECENT_COMMITS}', 
                 '--pretty=format:%H|%h|%an|%ae|%at|%s'],
                capture_output=True, text=True, cwd=self.root_path
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    
                    parts = line.split('|')
                    if len(parts) >= 6:
                        commit = {
                            'hash': parts[0],
                            'short_hash': parts[1],
                            'author': parts[2],
                            'email': parts[3],
                            'date': datetime.fromtimestamp(int(parts[4])),
                            'message': parts[5]
                        }
                        context.recent_commits.append(commit)
        except subprocess.SubprocessError:
            pass
        
        # Get current author
        try:
            result = subprocess.run(
                ['git', 'config', 'user.name'],
                capture_output=True, text=True, cwd=self.root_path
            )
            context.current_author = result.stdout.strip() if result.returncode == 0 else None
            
            result = subprocess.run(
                ['git', 'config', 'user.email'],
                capture_output=True, text=True, cwd=self.root_path
            )
            context.current_email = result.stdout.strip() if result.returncode == 0 else None
        except subprocess.SubprocessError:
            pass
        
        self._git_context = context
        return context
    
    def get_commit_diff(self, commit_hash: str) -> str:
        """Get diff for a commit."""
        try:
            result = subprocess.run(
                ['git', 'show', '--stat', commit_hash],
                capture_output=True, text=True, cwd=self.root_path
            )
            return result.stdout if result.returncode == 0 else ""
        except subprocess.SubprocessError:
            return ""
    
    def get_file_blame(self, filepath: str) -> List[Dict[str, Any]]:
        """Get git blame for a file."""
        abs_path = self._resolve_path(filepath)
        blame_info: List[Dict[str, Any]] = []
        
        try:
            result = subprocess.run(
                ['git', 'blame', '-w', '-M', '-C', '--line-porcelain', 
                 os.path.relpath(abs_path, self.root_path)],
                capture_output=True, text=True, cwd=self.root_path
            )
            
            if result.returncode == 0:
                current_info = {}
                for line in result.stdout.split('\n'):
                    if line.startswith('author '):
                        current_info['author'] = line[7:]
                    elif line.startswith('author-mail '):
                        current_info['email'] = line[12:]
                    elif line.startswith('author-time '):
                        current_info['time'] = datetime.fromtimestamp(int(line[12:]))
                    elif line.startswith('summary '):
                        current_info['message'] = line[8:]
                    elif line.startswith('\t'):
                        current_info['code'] = line[1:]
                        blame_info.append(current_info.copy())
                        current_info = {}
        except subprocess.SubprocessError:
            pass
        
        return blame_info
    
    # ==================== Environment Context ====================
    
    def get_environment_context(self) -> EnvironmentContext:
        """Get runtime environment context."""
        if self._environment_context is not None:
            return self._environment_context
        
        import platform
        import sys
        
        context = EnvironmentContext()
        
        # OS info
        context.os_type = platform.system()
        context.os_version = platform.version()
        context.cwd = os.getcwd()
        context.home = os.path.expanduser('~')
        context.shell = os.environ.get('SHELL', os.environ.get('COMSPEC', ''))
        
        # Python version
        context.python_version = platform.python_version()
        
        # Node version
        try:
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True, text=True
            )
            context.node_version = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # PATH
        path_str = os.environ.get('PATH', '')
        context.path = path_str.split(os.pathsep) if path_str else []
        
        # Select environment variables (non-sensitive)
        safe_env_vars = [
            'HOME', 'USER', 'USERNAME', 'LANG', 'TERM', 'SHELL',
            'EDITOR', 'VISUAL', 'PAGER', 'PWD', 'OLDPWD',
            'NODE_ENV', 'DEBUG', 'VERBOSE', 'LOG_LEVEL',
            'VIRTUAL_ENV', 'CONDA_DEFAULT_ENV', 'JAVA_HOME',
            'GOPATH', 'GOROOT', 'CARGO_HOME', 'RUSTUP_HOME'
        ]
        
        for var in safe_env_vars:
            if var in os.environ:
                context.env_vars[var] = os.environ[var]
        
        # Check installed tools
        tools = ['python', 'pip', 'node', 'npm', 'yarn', 'pnpm', 'bun',
                 'git', 'docker', 'kubectl', 'terraform', 'ansible',
                 'make', 'cmake', 'cargo', 'go', 'rustc', 'javac', 'mvn', 'gradle']
        
        for tool in tools:
            try:
                if tool in ('python', 'pip'):
                    cmd = [tool, '--version'] if tool == 'pip' else [tool, '-V']
                else:
                    cmd = [tool, '--version']
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                context.installed_tools[tool] = result.stdout.strip().split('\n')[0] if result.returncode == 0 else None
            except (subprocess.SubprocessError, FileNotFoundError):
                context.installed_tools[tool] = None
        
        self._environment_context = context
        return context
    
    # ==================== Project Context ====================
    
    def get_project_context(self) -> Optional[ProjectContext]:
        """Get project-wide context."""
        if self._project_context is not None:
            return self._project_context
        
        context = ProjectContext(
            root=str(self.root_path),
            name=self.root_path.name,
            type=self._detect_project_type()
        )
        
        # Detect languages
        context.languages = self._detect_project_languages()
        
        # Detect frameworks
        context.frameworks = self._detect_frameworks()
        
        # Find directories
        context.source_dirs = self._find_source_dirs()
        context.test_dirs = self._find_test_dirs()
        context.docs_dirs = self._find_docs_dirs()
        
        # Find config files
        context.config_files = self._find_config_files()
        
        # Find entry points
        context.entry_points = self._find_entry_points()
        
        # Detect package manager
        context.package_manager = self._detect_package_manager()
        
        # Load build config if available
        context.build_config = self._load_build_config()
        
        self._project_context = context
        return context
    
    # ==================== Context Serialization ====================
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary."""
        snapshot = self.get_full_context()
        
        return {
            'timestamp': snapshot.timestamp.isoformat(),
            'working_directory': snapshot.working_directory,
            'active_file': snapshot.active_file,
            'open_files': snapshot.open_files,
            'recent_files': snapshot.recent_files,
            'file_contexts': [
                {
                    'filepath': fc.filepath,
                    'language': fc.language,
                    'size': fc.size,
                    'line_count': fc.line_count,
                    'imports': fc.imports,
                    'exports': fc.exports
                }
                for fc in snapshot.file_contexts
            ],
            'git': {
                'is_repo': snapshot.git_context.is_repo,
                'branch': snapshot.git_context.branch,
                'status': snapshot.git_context.status,
                'modified_files': snapshot.git_context.modified_files,
                'recent_commits': [
                    {
                        'hash': c['hash'],
                        'short_hash': c['short_hash'],
                        'author': c['author'],
                        'message': c['message'],
                        'date': c['date'].isoformat() if isinstance(c['date'], datetime) else c['date']
                    }
                    for c in snapshot.git_context.recent_commits
                ]
            } if snapshot.git_context else None,
            'environment': {
                'os_type': snapshot.environment_context.os_type,
                'python_version': snapshot.environment_context.python_version,
                'node_version': snapshot.environment_context.node_version,
                'cwd': snapshot.environment_context.cwd
            } if snapshot.environment_context else None,
            'project': {
                'name': snapshot.project_context.name,
                'type': snapshot.project_context.type,
                'languages': snapshot.project_context.languages,
                'frameworks': snapshot.project_context.frameworks,
                'package_manager': snapshot.project_context.package_manager
            } if snapshot.project_context else None
        }
    
    def save(self, filepath: str) -> None:
        """Save context to file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'ContextManager':
        """Load context from file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        manager = cls(data['working_directory'])
        
        if data.get('active_file'):
            manager._active_file = data['active_file']
        
        if data.get('open_files'):
            manager._open_files = data['open_files']
        
        if data.get('recent_files'):
            manager._recent_files = deque(data['recent_files'], maxlen=cls.MAX_RECENT_FILES)
        
        return manager
    
    # ==================== Helper Methods ====================
    
    def _resolve_path(self, filepath: str) -> Path:
        """Resolve a path relative to root."""
        path = Path(filepath)
        if path.is_absolute():
            return path
        return self.root_path / filepath
    
    def _detect_language(self, filepath: str) -> str:
        """Detect language from file extension."""
        ext_to_lang = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.jsx': 'JavaScript JSX',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript JSX',
            '.java': 'Java',
            '.kt': 'Kotlin',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.c': 'C',
            '.cpp': 'C++',
            '.h': 'C Header',
            '.hpp': 'C++ Header',
            '.cs': 'C#',
            '.swift': 'Swift',
            '.m': 'Objective-C',
            '.scala': 'Scala',
            '.ex': 'Elixir',
            '.exs': 'Elixir',
            '.erl': 'Erlang',
            '.hs': 'Haskell',
            '.lua': 'Lua',
            '.r': 'R',
            '.sh': 'Shell',
            '.bash': 'Bash',
            '.ps1': 'PowerShell',
            '.sql': 'SQL',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.less': 'LESS',
            '.vue': 'Vue',
            '.svelte': 'Svelte',
            '.dart': 'Dart',
            '.md': 'Markdown',
            '.json': 'JSON',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.toml': 'TOML',
            '.xml': 'XML',
        }
        
        ext = os.path.splitext(filepath)[1].lower()
        return ext_to_lang.get(ext, 'Unknown')
    
    def _extract_imports(self, content: str, language: str) -> List[str]:
        """Extract import statements from content."""
        imports: List[str] = []
        
        if language == 'Python':
            patterns = [
                r'^import\s+(\S+)',
                r'^from\s+(\S+)\s+import',
            ]
        elif language in ('JavaScript', 'TypeScript', 'JavaScript JSX', 'TypeScript JSX'):
            patterns = [
                r"import\s+.*?from\s+['\"]([^'\"]+)['\"]",
                r"import\s+['\"]([^'\"]+)['\"]",
                r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            ]
        else:
            return imports
        
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                imports.append(match.group(1))
        
        return imports
    
    def _extract_exports(self, content: str, language: str) -> List[str]:
        """Extract export statements from content."""
        exports: List[str] = []
        
        if language in ('JavaScript', 'TypeScript', 'JavaScript JSX', 'TypeScript JSX'):
            patterns = [
                r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)',
                r'export\s+\{\s*([^}]+)\s*\}',
            ]
            
            for match in re.finditer(patterns[0], content):
                exports.append(match.group(1))
            
            for match in re.finditer(patterns[1], content):
                names = [n.strip() for n in match.group(1).split(',')]
                exports.extend(names)
        
        return exports
    
    def _resolve_import(self, import_path: str, from_file: str) -> Optional[str]:
        """Resolve import to actual file path."""
        # Relative import
        if import_path.startswith('.'):
            from_dir = os.path.dirname(from_file)
            resolved = os.path.normpath(os.path.join(from_dir, import_path))
            
            # Try different extensions
            for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs']:
                path = resolved + ext
                if os.path.exists(path):
                    return path
            
            # Try as directory with index
            for ext in ['.py', '.js', '.ts']:
                index_path = os.path.join(resolved, f'__index__{ext}')
                if os.path.exists(index_path):
                    return index_path
                index_path = os.path.join(resolved, f'index{ext}')
                if os.path.exists(index_path):
                    return index_path
        
        # Absolute import - search in project
        for ext in ['.py', '.js', '.ts', '.jsx', '.tsx']:
            path = str(self.root_path / (import_path.replace('.', '/') + ext))
            if os.path.exists(path):
                return path
        
        return None
    
    def _import_references_file(self, import_path: str, filepath: str) -> bool:
        """Check if import references a file."""
        resolved = self._resolve_import(import_path, filepath)
        return resolved == filepath if resolved else False
    
    def _detect_project_type(self) -> str:
        """Detect project type."""
        files = set(os.listdir(self.root_path))
        
        if 'setup.py' in files or 'pyproject.toml' in files or 'setup.cfg' in files:
            return 'library'
        elif 'package.json' in files:
            pkg = self._read_json(os.path.join(self.root_path, 'package.json'))
            if pkg:
                if 'main' in pkg or 'bin' in pkg:
                    return 'application'
                elif 'exports' in pkg:
                    return 'library'
            return 'application'
        elif 'Dockerfile' in files or 'docker-compose.yml' in files:
            return 'service'
        elif 'pnpm-workspace.yaml' in files or 'lerna.json' in files:
            return 'monorepo'
        
        return 'application'
    
    def _detect_project_languages(self) -> List[str]:
        """Detect languages used in project."""
        language_counts: Dict[str, int] = {}
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      ('node_modules', 'venv', '__pycache__', 'dist', 'build', 'target')]
            
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                lang = self._detect_language(f)
                if lang != 'Unknown':
                    language_counts[lang] = language_counts.get(lang, 0) + 1
        
        return sorted(language_counts.keys(), key=lambda l: language_counts[l], reverse=True)
    
    def _detect_frameworks(self) -> List[str]:
        """Detect frameworks used in project."""
        frameworks: List[str] = []
        
        # Check package.json
        pkg_path = os.path.join(self.root_path, 'package.json')
        if os.path.exists(pkg_path):
            pkg = self._read_json(pkg_path)
            if pkg:
                deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                
                fw_map = {
                    'react': 'React',
                    'vue': 'Vue',
                    'angular': 'Angular',
                    'svelte': 'Svelte',
                    'next': 'Next.js',
                    'nuxt': 'Nuxt',
                    'express': 'Express',
                    'fastify': 'Fastify',
                    'nestjs': 'NestJS',
                    'django': 'Django',
                    'flask': 'Flask',
                    'fastapi': 'FastAPI',
                }
                
                for dep, name in fw_map.items():
                    if dep in deps:
                        frameworks.append(name)
        
        # Check requirements.txt
        req_path = os.path.join(self.root_path, 'requirements.txt')
        if os.path.exists(req_path):
            try:
                with open(req_path, 'r') as f:
                    content = f.read().lower()
                    
                py_fw = {
                    'django': 'Django',
                    'flask': 'Flask',
                    'fastapi': 'FastAPI',
                    'tornado': 'Tornado',
                    'sanic': 'Sanic',
                }
                
                for dep, name in py_fw.items():
                    if dep in content:
                        frameworks.append(name)
            except IOError:
                pass
        
        return frameworks
    
    def _find_source_dirs(self) -> List[str]:
        """Find source code directories."""
        source_names = {'src', 'lib', 'source', 'app', 'main', 'packages', 'libs'}
        dirs: List[str] = []
        
        for item in os.listdir(self.root_path):
            item_path = os.path.join(self.root_path, item)
            if os.path.isdir(item_path) and item in source_names:
                dirs.append(item)
        
        return dirs
    
    def _find_test_dirs(self) -> List[str]:
        """Find test directories."""
        test_names = {'test', 'tests', '__tests__', 'spec', 'specs'}
        dirs: List[str] = []
        
        for item in os.listdir(self.root_path):
            item_path = os.path.join(self.root_path, item)
            if os.path.isdir(item_path) and item in test_names:
                dirs.append(item)
        
        return dirs
    
    def _find_docs_dirs(self) -> List[str]:
        """Find documentation directories."""
        doc_names = {'docs', 'doc', 'documentation', 'wiki'}
        dirs: List[str] = []
        
        for item in os.listdir(self.root_path):
            item_path = os.path.join(self.root_path, item)
            if os.path.isdir(item_path) and item in doc_names:
                dirs.append(item)
        
        return dirs
    
    def _find_config_files(self) -> List[str]:
        """Find configuration files."""
        config_names = {
            'package.json', 'tsconfig.json', 'jsconfig.json',
            'pyproject.toml', 'setup.py', 'setup.cfg',
            'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle',
            '.eslintrc', '.prettierrc', 'prettier.config.js',
            'webpack.config.js', 'vite.config.js', 'rollup.config.js',
            'Dockerfile', 'docker-compose.yml',
            '.env', '.env.local', '.env.development',
        }
        
        files: List[str] = []
        
        for item in os.listdir(self.root_path):
            if item in config_names:
                files.append(item)
        
        return files
    
    def _find_entry_points(self) -> List[str]:
        """Find project entry points."""
        entry_points: List[str] = []
        
        # Python
        for name in ['main.py', 'app.py', '__main__.py', 'wsgi.py', 'asgi.py']:
            path = os.path.join(self.root_path, name)
            if os.path.exists(path):
                entry_points.append(name)
        
        # JavaScript/TypeScript
        for name in ['index.js', 'index.ts', 'main.js', 'main.ts', 'server.js', 'server.ts']:
            path = os.path.join(self.root_path, name)
            if os.path.exists(path):
                entry_points.append(name)
        
        # Check package.json main
        pkg_path = os.path.join(self.root_path, 'package.json')
        if os.path.exists(pkg_path):
            pkg = self._read_json(pkg_path)
            if pkg and 'main' in pkg:
                entry_points.append(pkg['main'])
        
        # Check pyproject.toml scripts
        pyproject_path = os.path.join(self.root_path, 'pyproject.toml')
        if os.path.exists(pyproject_path):
            try:
                import tomli
                with open(pyproject_path, 'rb') as f:
                    data = tomli.load(f)
                    scripts = data.get('project', {}).get('scripts', {})
                    entry_points.extend(scripts.keys())
            except Exception:
                pass
        
        return entry_points
    
    def _detect_package_manager(self) -> Optional[str]:
        """Detect package manager."""
        files = set(os.listdir(self.root_path))
        
        if 'yarn.lock' in files:
            return 'yarn'
        elif 'pnpm-lock.yaml' in files:
            return 'pnpm'
        elif 'bun.lockb' in files:
            return 'bun'
        elif 'package-lock.json' in files:
            return 'npm'
        elif 'poetry.lock' in files:
            return 'poetry'
        elif 'Pipfile.lock' in files:
            return 'pipenv'
        elif 'requirements.txt' in files:
            return 'pip'
        elif 'Cargo.lock' in files:
            return 'cargo'
        elif 'go.sum' in files:
            return 'go mod'
        
        return None
    
    def _load_build_config(self) -> Optional[Dict[str, Any]]:
        """Load build configuration."""
        # Try package.json
        pkg_path = os.path.join(self.root_path, 'package.json')
        if os.path.exists(pkg_path):
            return self._read_json(pkg_path)
        
        # Try pyproject.toml
        pyproject_path = os.path.join(self.root_path, 'pyproject.toml')
        if os.path.exists(pyproject_path):
            try:
                import tomli
                with open(pyproject_path, 'rb') as f:
                    return tomli.load(f)
            except Exception:
                pass
        
        return None
    
    def _read_json(self, filepath: str) -> Optional[Dict]:
        """Read JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            return None
    
    def clear_cache(self) -> None:
        """Clear context cache."""
        self._context_cache.clear()
        self._git_context = None
        self._environment_context = None
        self._project_context = None


def get_context(root_path: str = ".") -> ContextSnapshot:
    """Convenience function to get full context."""
    manager = ContextManager(root_path)
    return manager.get_full_context()


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    context = get_context(path)
    
    print(f"Working directory: {context.working_directory}")
    print(f"Git repo: {context.git_context.is_repo}")
    if context.git_context.is_repo:
        print(f"  Branch: {context.git_context.branch}")
        print(f"  Status: {context.git_context.status}")
    print(f"Project: {context.project_context.name if context.project_context else 'N/A'}")
    print(f"Languages: {context.project_context.languages if context.project_context else []}")
