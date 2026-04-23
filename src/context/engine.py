#!/usr/bin/env python3
"""Context Engine - Full project awareness and analysis"""
import os
import ast
import json
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
from collections import defaultdict

@dataclass
class Symbol:
    name: str
    kind: str  # function, class, variable, import, constant
    file: str
    line: int
    end_line: int
    docstring: Optional[str] = None
    references: List[str] = field(default_factory=list)
    definition: Optional[str] = None

@dataclass
class FileContext:
    path: str
    language: str
    imports: List[str]
    exports: List[str]
    symbols: List[Symbol]
    dependencies: List[str]
    hash: str

@dataclass
class ProjectContext:
    root: str
    language: str
    framework: Optional[str]
    structure: Dict[str, List[str]]
    dependencies: Dict[str, str]
    symbols: Dict[str, Symbol]
    entry_points: List[str]

class ProjectAnalyzer:
    """Analyze project structure and content"""
    
    LANGUAGE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.go': 'go',
        '.rs': 'rust',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.rb': 'ruby',
        '.php': 'php',
    }
    
    FRAMEWORK_SIGNATURES = {
        'python': {
            'django': ['django', 'settings.py'],
            'flask': ['flask', 'app.py'],
            'fastapi': ['fastapi', 'main.py'],
            'pytest': ['pytest'],
        },
        'javascript': {
            'react': ['react', 'react-dom'],
            'vue': ['vue'],
            'angular': ['@angular/core'],
            'express': ['express'],
            'next': ['next'],
        }
    }
    
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.context: Optional[ProjectContext] = None
        
    def analyze(self) -> ProjectContext:
        """Full project analysis"""
        language = self._detect_language()
        framework = self._detect_framework(language)
        structure = self._analyze_structure()
        dependencies = self._analyze_dependencies(language)
        symbols = self._index_symbols()
        entry_points = self._find_entry_points(language, framework)
        
        self.context = ProjectContext(
            root=str(self.root_dir),
            language=language,
            framework=framework,
            structure=structure,
            dependencies=dependencies,
            symbols=symbols,
            entry_points=entry_points
        )
        
        return self.context
        
    def _detect_language(self) -> str:
        """Detect primary language"""
        counts = defaultdict(int)
        
        for file in self.root_dir.rglob("*"):
            if file.is_file():
                ext = file.suffix.lower()
                if ext in self.LANGUAGE_MAP:
                    counts[self.LANGUAGE_MAP[ext]] += 1
                    
        if counts:
            return max(counts, key=counts.get)
        return 'unknown'
        
    def _detect_framework(self, language: str) -> Optional[str]:
        """Detect framework"""
        signatures = self.FRAMEWORK_SIGNATURES.get(language, {})
        
        for framework, indicators in signatures.items():
            for indicator in indicators:
                # Check dependencies
                deps = self._check_deps_file(language)
                if deps and indicator in deps:
                    return framework
                    
                # Check files
                for pattern in [f"*.py", "*.js", "*.ts"]:
                    for file in self.root_dir.rglob(pattern):
                        if file.name == indicator:
                            return framework
                        try:
                            content = file.read_text()
                            if indicator in content:
                                return framework
                        except:
                            pass
                            
        return None
        
    def _check_deps_file(self, language: str) -> Optional[str]:
        """Check dependencies file"""
        deps_files = {
            'python': ['requirements.txt', 'pyproject.toml', 'setup.py'],
            'javascript': ['package.json'],
            'go': ['go.mod'],
            'rust': ['Cargo.toml'],
        }
        
        for deps_file in deps_files.get(language, []):
            path = self.root_dir / deps_file
            if path.exists():
                return path.read_text()
        return None
        
    def _analyze_structure(self) -> Dict[str, List[str]]:
        """Analyze directory structure"""
        structure = defaultdict(list)
        
        for file in self.root_dir.rglob("*"):
            if file.is_file() and not file.name.startswith('.'):
                rel_path = file.relative_to(self.root_dir)
                dir_name = str(rel_path.parent) if rel_path.parent != Path('.') else 'root'
                structure[dir_name].append(file.name)
                
        return dict(structure)
        
    def _analyze_dependencies(self, language: str) -> Dict[str, str]:
        """Analyze project dependencies"""
        deps = {}
        
        if language == 'python':
            req_file = self.root_dir / 'requirements.txt'
            if req_file.exists():
                for line in req_file.read_text().split('\n'):
                    if line and not line.startswith('#'):
                        parts = line.split('==')
                        if len(parts) == 2:
                            deps[parts[0]] = parts[1]
                        else:
                            deps[line] = 'latest'
                            
        elif language in ['javascript', 'typescript']:
            pkg_file = self.root_dir / 'package.json'
            if pkg_file.exists():
                pkg = json.loads(pkg_file.read_text())
                deps.update(pkg.get('dependencies', {}))
                deps.update(pkg.get('devDependencies', {}))
                
        return deps
        
    def _index_symbols(self) -> Dict[str, Symbol]:
        """Index all symbols in project"""
        symbols = {}
        
        for file in self.root_dir.rglob("*.py"):
            try:
                file_symbols = self._parse_python_file(file)
                for sym in file_symbols:
                    symbols[f"{file.stem}.{sym.name}"] = sym
            except:
                pass
                
        return symbols
        
    def _parse_python_file(self, file: Path) -> List[Symbol]:
        """Parse Python file for symbols"""
        content = file.read_text()
        tree = ast.parse(content)
        symbols = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append(Symbol(
                    name=node.name,
                    kind='function',
                    file=str(file),
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node),
                    definition=ast.unparse(node)[:200] if hasattr(ast, 'unparse') else None
                ))
            elif isinstance(node, ast.ClassDef):
                symbols.append(Symbol(
                    name=node.name,
                    kind='class',
                    file=str(file),
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node)
                ))
                
        return symbols
        
    def _find_entry_points(self, language: str, framework: str) -> List[str]:
        """Find entry points"""
        entry_points = []
        
        if language == 'python':
            for pattern in ['main.py', 'app.py', '__main__.py', 'manage.py']:
                for file in self.root_dir.rglob(pattern):
                    entry_points.append(str(file))
                    
        elif language in ['javascript', 'typescript']:
            for pattern in ['index.js', 'index.ts', 'app.js', 'server.js']:
                for file in self.root_dir.rglob(pattern):
                    entry_points.append(str(file))
                    
        return entry_points


class SymbolIndexer:
    """Symbol indexing and search"""
    
    def __init__(self):
        self.symbols: Dict[str, Symbol] = {}
        self.references: Dict[str, Set[str]] = defaultdict(set)
        
    def add_symbol(self, symbol: Symbol):
        """Add a symbol"""
        self.symbols[symbol.name] = symbol
        
    def add_reference(self, symbol_name: str, file: str):
        """Add a reference to a symbol"""
        self.references[symbol_name].add(file)
        
    def find_symbol(self, name: str) -> List[Symbol]:
        """Find symbols by name"""
        results = []
        for sym_name, sym in self.symbols.items():
            if name.lower() in sym_name.lower():
                results.append(sym)
        return results
        
    def find_references(self, symbol_name: str) -> List[str]:
        """Find all references to a symbol"""
        return list(self.references.get(symbol_name, []))
        
    def get_callers(self, function_name: str) -> List[Symbol]:
        """Find callers of a function"""
        callers = []
        for sym in self.symbols.values():
            if sym.kind == 'function' and sym.definition:
                if function_name in sym.definition:
                    callers.append(sym)
        return callers


class ContextManager:
    """Manage context for LLM"""
    
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self.current_file: Optional[str] = None
        self.project_context: Optional[ProjectContext] = None
        self.recent_files: List[str] = []
        self.symbol_indexer = SymbolIndexer()
        
    def set_project(self, root_dir: str):
        """Set project context"""
        analyzer = ProjectAnalyzer(root_dir)
        self.project_context = analyzer.analyze()
        
        # Index symbols
        for sym_name, sym in self.project_context.symbols.items():
            self.symbol_indexer.add_symbol(sym)
            
    def set_current_file(self, file_path: str):
        """Set current file context"""
        self.current_file = file_path
        if file_path not in self.recent_files:
            self.recent_files.insert(0, file_path)
            self.recent_files = self.recent_files[:10]
            
    def get_context_window(self) -> Dict[str, Any]:
        """Get context for LLM prompt"""
        context = {
            "project": None,
            "current_file": None,
            "recent_files": self.recent_files,
            "symbols": []
        }
        
        if self.project_context:
            context["project"] = {
                "language": self.project_context.language,
                "framework": self.project_context.framework,
                "structure": self.project_context.structure,
                "dependencies": self.project_context.dependencies,
                "entry_points": self.project_context.entry_points
            }
            
        if self.current_file:
            try:
                content = Path(self.current_file).read_text()
                context["current_file"] = {
                    "path": self.current_file,
                    "content": content[:2000]  # Truncate for token limit
                }
            except:
                pass
                
        # Add relevant symbols
        for sym_name, sym in list(self.symbol_indexer.symbols.items())[:20]:
            context["symbols"].append({
                "name": sym.name,
                "kind": sym.kind,
                "file": sym.file,
                "line": sym.line
            })
            
        return context
        
    def find_relevant_context(self, query: str) -> List[Symbol]:
        """Find symbols relevant to query"""
        results = []
        query_lower = query.lower()
        
        for sym_name, sym in self.symbol_indexer.symbols.items():
            # Check if symbol name or docstring matches query
            if query_lower in sym_name.lower():
                results.append(sym)
            elif sym.docstring and query_lower in sym.docstring.lower():
                results.append(sym)
                
        return results[:10]
