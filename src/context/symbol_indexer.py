"""
Symbol Indexer - AST-based symbol extraction and indexing

Features:
- AST parsing for multiple languages (Python, JavaScript, TypeScript)
- Symbol extraction (functions, classes, variables, imports)
- Reference tracking across files
- Call graph building
"""

import ast
import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SymbolKind(Enum):
    """Types of symbols."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    ALIAS = "alias"
    PARAMETER = "parameter"
    PROPERTY = "property"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"


@dataclass
class Position:
    """Source position."""
    line: int
    column: int
    
    def __lt__(self, other: 'Position') -> bool:
        return (self.line, self.column) < (other.line, other.column)
    
    def __le__(self, other: 'Position') -> bool:
        return (self.line, self.column) <= (other.line, other.column)


@dataclass
class Range:
    """Source range."""
    start: Position
    end: Position
    
    def contains(self, pos: Position) -> bool:
        return self.start <= pos <= self.end


@dataclass
class Symbol:
    """A code symbol."""
    name: str
    kind: SymbolKind
    filepath: str
    range: Range
    scope: Optional[str] = None
    parent: Optional[str] = None
    docstring: Optional[str] = None
    signature: Optional[str] = None
    type_annotation: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)  # File paths where referenced
    calls: List[str] = field(default_factory=list)  # Symbols this calls
    called_by: List[str] = field(default_factory=list)  # Symbols that call this
    hash: str = field(default="")
    
    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute unique hash for this symbol."""
        content = f"{self.name}:{self.kind.value}:{self.filepath}:{self.scope}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'kind': self.kind.value,
            'filepath': self.filepath,
            'range': {
                'start': {'line': self.range.start.line, 'column': self.range.start.column},
                'end': {'line': self.range.end.line, 'column': self.range.end.column}
            },
            'scope': self.scope,
            'parent': self.parent,
            'docstring': self.docstring,
            'signature': self.signature,
            'type_annotation': self.type_annotation,
            'decorators': self.decorators,
            'references': self.references,
            'calls': self.calls,
            'called_by': self.called_by,
            'hash': self.hash
        }


@dataclass
class Import:
    """An import statement."""
    module: str
    name: Optional[str]
    alias: Optional[str]
    filepath: str
    line: int
    is_from_import: bool = False


@dataclass 
class Reference:
    """A reference to a symbol."""
    symbol_name: str
    symbol_file: Optional[str]
    reference_file: str
    line: int
    column: int
    context: str  # 'definition', 'use', 'import', 'call'


@dataclass
class CallEdge:
    """An edge in the call graph."""
    caller: str  # Symbol hash
    callee: str  # Symbol hash
    call_site: Tuple[str, int]  # (filepath, line)
    call_type: str  # 'direct', 'method', 'dynamic'


class SymbolIndex:
    """Index of all symbols in a project."""
    
    def __init__(self):
        self.symbols: Dict[str, Symbol] = {}  # hash -> Symbol
        self.name_index: Dict[str, Set[str]] = defaultdict(set)  # name -> set of hashes
        self.file_index: Dict[str, Set[str]] = defaultdict(set)  # filepath -> set of hashes
        self.imports: List[Import] = []
        self.references: List[Reference] = []
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)  # caller -> set of callees
        self.reverse_call_graph: Dict[str, Set[str]] = defaultdict(set)  # callee -> set of callers
    
    def add_symbol(self, symbol: Symbol) -> None:
        """Add a symbol to the index."""
        self.symbols[symbol.hash] = symbol
        self.name_index[symbol.name].add(symbol.hash)
        self.file_index[symbol.filepath].add(symbol.hash)
    
    def get_symbol(self, hash_key: str) -> Optional[Symbol]:
        """Get symbol by hash."""
        return self.symbols.get(hash_key)
    
    def find_symbols_by_name(self, name: str) -> List[Symbol]:
        """Find all symbols with a given name."""
        hashes = self.name_index.get(name, set())
        return [self.symbols[h] for h in hashes if h in self.symbols]
    
    def get_file_symbols(self, filepath: str) -> List[Symbol]:
        """Get all symbols in a file."""
        hashes = self.file_index.get(filepath, set())
        return [self.symbols[h] for h in hashes if h in self.symbols]
    
    def add_call_edge(self, edge: CallEdge) -> None:
        """Add an edge to the call graph."""
        self.call_graph[edge.caller].add(edge.callee)
        self.reverse_call_graph[edge.callee].add(edge.caller)
    
    def get_callers(self, symbol_hash: str) -> Set[str]:
        """Get all symbols that call this symbol."""
        return self.reverse_call_graph.get(symbol_hash, set())
    
    def get_callees(self, symbol_hash: str) -> Set[str]:
        """Get all symbols this symbol calls."""
        return self.call_graph.get(symbol_hash, set())
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize index to dictionary."""
        return {
            'symbols': {h: s.to_dict() for h, s in self.symbols.items()},
            'name_index': {k: list(v) for k, v in self.name_index.items()},
            'file_index': {k: list(v) for k, v in self.file_index.items()},
            'imports': [
                {
                    'module': i.module,
                    'name': i.name,
                    'alias': i.alias,
                    'filepath': i.filepath,
                    'line': i.line,
                    'is_from_import': i.is_from_import
                }
                for i in self.imports
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SymbolIndex':
        """Deserialize index from dictionary."""
        index = cls()
        
        for hash_key, sym_data in data.get('symbols', {}).items():
            symbol = Symbol(
                name=sym_data['name'],
                kind=SymbolKind(sym_data['kind']),
                filepath=sym_data['filepath'],
                range=Range(
                    start=Position(**sym_data['range']['start']),
                    end=Position(**sym_data['range']['end'])
                ),
                scope=sym_data.get('scope'),
                parent=sym_data.get('parent'),
                docstring=sym_data.get('docstring'),
                signature=sym_data.get('signature'),
                type_annotation=sym_data.get('type_annotation'),
                decorators=sym_data.get('decorators', []),
                hash=hash_key
            )
            index.symbols[hash_key] = symbol
        
        for name, hashes in data.get('name_index', {}).items():
            index.name_index[name] = set(hashes)
        
        for filepath, hashes in data.get('file_index', {}).items():
            index.file_index[filepath] = set(hashes)
        
        for imp_data in data.get('imports', []):
            index.imports.append(Import(
                module=imp_data['module'],
                name=imp_data.get('name'),
                alias=imp_data.get('alias'),
                filepath=imp_data['filepath'],
                line=imp_data['line'],
                is_from_import=imp_data.get('is_from_import', False)
            ))
        
        return index


class PythonSymbolExtractor:
    """Extract symbols from Python source code using AST."""
    
    def extract(self, source: str, filepath: str) -> Tuple[List[Symbol], List[Import], List[Reference]]:
        """Extract all symbols, imports, and references from Python source."""
        symbols: List[Symbol] = []
        imports: List[Import] = []
        references: List[Reference] = []
        
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {filepath}: {e}")
            return symbols, imports, references
        
        # Track scope
        scope_stack: List[str] = ['module']
        
        # Extract module-level docstring
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            symbols.append(Symbol(
                name=os.path.basename(filepath),
                kind=SymbolKind.MODULE,
                filepath=filepath,
                range=Range(Position(1, 0), Position(1, 0)),
                docstring=module_docstring
            ))
        
        # First pass: extract all definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.extend(self._extract_class(node, filepath, source))
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # Only top-level functions here
                if not self._is_method(node, tree):
                    symbols.append(self._extract_function(node, filepath, source))
            elif isinstance(node, ast.Import):
                imports.extend(self._extract_import(node, filepath))
            elif isinstance(node, ast.ImportFrom):
                imports.extend(self._extract_from_import(node, filepath))
        
        # Second pass: extract references
        references = self._extract_references(tree, filepath, source)
        
        return symbols, imports, references
    
    def _is_method(self, node: ast.FunctionDef, tree: ast.AST) -> bool:
        """Check if a function is a method inside a class."""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                for child in parent.body:
                    if child is node:
                        return True
        return False
    
    def _extract_class(self, node: ast.ClassDef, filepath: str, source: str) -> List[Symbol]:
        """Extract class and its members."""
        symbols: List[Symbol] = []
        
        lines = source.splitlines()
        
        # Class symbol
        class_symbol = Symbol(
            name=node.name,
            kind=SymbolKind.CLASS,
            filepath=filepath,
            range=Range(
                Position(node.lineno, node.col_offset),
                Position(node.end_lineno or node.lineno, node.end_col_offset or 0)
            ),
            docstring=ast.get_docstring(node),
            decorators=[self._get_decorator_name(d) for d in node.decorator_list]
        )
        
        # Get base classes
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_attribute_name(base))
        if bases:
            class_symbol.signature = f"class {node.name}({', '.join(bases)})"
        
        symbols.append(class_symbol)
        
        # Extract class members
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_symbol = self._extract_function(item, filepath, source)
                method_symbol.kind = SymbolKind.METHOD
                method_symbol.parent = node.name
                method_symbol.scope = f"{node.name}.{item.name}"
                symbols.append(method_symbol)
            elif isinstance(item, ast.AnnAssign) and item.annotation:
                # Class attribute with type annotation
                if isinstance(item.target, ast.Name):
                    attr_name = item.target.id
                    type_str = self._get_annotation_string(item.annotation)
                    symbols.append(Symbol(
                        name=attr_name,
                        kind=SymbolKind.PROPERTY,
                        filepath=filepath,
                        range=Range(
                            Position(item.lineno, item.col_offset),
                            Position(item.end_lineno or item.lineno, item.end_col_offset or 0)
                        ),
                        parent=node.name,
                        scope=f"{node.name}.{attr_name}",
                        type_annotation=type_str
                    ))
        
        return symbols
    
    def _extract_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], 
                          filepath: str, source: str) -> Symbol:
        """Extract a function symbol."""
        # Build signature
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_annotation_string(arg.annotation)}"
            args.append(arg_str)
        
        # Handle *args
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        
        # Handle **kwargs
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        
        signature = f"{node.name}({', '.join(args)})"
        
        # Return type
        if node.returns:
            signature += f" -> {self._get_annotation_string(node.returns)}"
        
        return Symbol(
            name=node.name,
            kind=SymbolKind.FUNCTION,
            filepath=filepath,
            range=Range(
                Position(node.lineno, node.col_offset),
                Position(node.end_lineno or node.lineno, node.end_col_offset or 0)
            ),
            docstring=ast.get_docstring(node),
            signature=signature,
            decorators=[self._get_decorator_name(d) for d in node.decorator_list]
        )
    
    def _extract_import(self, node: ast.Import, filepath: str) -> List[Import]:
        """Extract import statements."""
        imports: List[Import] = []
        for alias in node.names:
            imports.append(Import(
                module=alias.name,
                name=alias.name,
                alias=alias.asname,
                filepath=filepath,
                line=node.lineno,
                is_from_import=False
            ))
        return imports
    
    def _extract_from_import(self, node: ast.ImportFrom, filepath: str) -> List[Import]:
        """Extract from...import statements."""
        imports: List[Import] = []
        module = node.module or ''
        for alias in node.names:
            imports.append(Import(
                module=module,
                name=alias.name,
                alias=alias.asname,
                filepath=filepath,
                line=node.lineno,
                is_from_import=True
            ))
        return imports
    
    def _extract_references(self, tree: ast.AST, filepath: str, source: str) -> List[Reference]:
        """Extract all name references."""
        references: List[Reference] = []
        
        class ReferenceVisitor(ast.NodeVisitor):
            def __init__(self, parent):
                self.parent = parent
                self.refs: List[Reference] = []
            
            def visit_Name(self, node: ast.Name):
                # Determine context
                ctx = 'use'
                if isinstance(node.ctx, ast.Store):
                    ctx = 'definition'
                elif isinstance(node.ctx, ast.Load):
                    ctx = 'use'
                elif isinstance(node.ctx, ast.Del):
                    ctx = 'use'
                
                self.refs.append(Reference(
                    symbol_name=node.id,
                    symbol_file=None,
                    reference_file=filepath,
                    line=node.lineno,
                    column=node.col_offset,
                    context=ctx
                ))
                self.generic_visit(node)
            
            def visit_Attribute(self, node: ast.Attribute):
                self.refs.append(Reference(
                    symbol_name=node.attr,
                    symbol_file=None,
                    reference_file=filepath,
                    line=node.lineno,
                    column=node.col_offset,
                    context='use'
                ))
                self.generic_visit(node)
            
            def visit_Call(self, node: ast.Call):
                # Mark call references
                if isinstance(node.func, ast.Name):
                    self.refs.append(Reference(
                        symbol_name=node.func.id,
                        symbol_file=None,
                        reference_file=filepath,
                        line=node.lineno,
                        column=node.col_offset,
                        context='call'
                    ))
                elif isinstance(node.func, ast.Attribute):
                    self.refs.append(Reference(
                        symbol_name=node.func.attr,
                        symbol_file=None,
                        reference_file=filepath,
                        line=node.lineno,
                        column=node.col_offset,
                        context='call'
                    ))
                self.generic_visit(node)
        
        visitor = ReferenceVisitor(self)
        visitor.visit(tree)
        references = visitor.refs
        
        return references
    
    def _get_decorator_name(self, node: ast.AST) -> str:
        """Get decorator name as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return 'unknown'
    
    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """Get full attribute name (e.g., 'module.Class')."""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attribute_name(node.value)}.{node.attr}"
        return node.attr
    
    def _get_annotation_string(self, node: ast.AST) -> str:
        """Get type annotation as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                return f"{node.value.id}[{self._get_annotation_string(node.slice)}]"
        elif isinstance(node, ast.Tuple):
            return ', '.join(self._get_annotation_string(el) for el in node.elts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Union type (Python 3.10+)
            return f"{self._get_annotation_string(node.left)} | {self._get_annotation_string(node.right)}"
        return 'Any'


class JavaScriptSymbolExtractor:
    """Extract symbols from JavaScript/TypeScript source code using regex parsing."""
    
    def extract(self, source: str, filepath: str) -> Tuple[List[Symbol], List[Import], List[Reference]]:
        """Extract all symbols, imports, and references from JavaScript/TypeScript source."""
        symbols: List[Symbol] = []
        imports: List[Import] = []
        references: List[Reference] = []
        
        lines = source.splitlines()
        is_typescript = filepath.endswith(('.ts', '.tsx'))
        
        # Extract imports
        import_patterns = [
            r"import\s+(\{[^}]+\}|\*)\s+from\s+['\"]([^'\"]+)['\"]",
            r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
            r"import\s+(\{[^}]+\})\s*,\s*(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        ]
        
        for i, line in enumerate(lines, 1):
            # Default import
            match = re.search(r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]", line)
            if match:
                imports.append(Import(
                    module=match.group(2),
                    name=match.group(1),
                    alias=None,
                    filepath=filepath,
                    line=i,
                    is_from_import=True
                ))
                continue
            
            # Named import
            match = re.search(r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]", line)
            if match:
                names = [n.strip().split(' as ') for n in match.group(1).split(',')]
                for name_parts in names:
                    name = name_parts[0].strip()
                    alias = name_parts[1].strip() if len(name_parts) > 1 else None
                    imports.append(Import(
                        module=match.group(2),
                        name=name,
                        alias=alias,
                        filepath=filepath,
                        line=i,
                        is_from_import=True
                    ))
                continue
            
            # Require
            match = re.search(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", line)
            if match:
                imports.append(Import(
                    module=match.group(1),
                    name=None,
                    alias=None,
                    filepath=filepath,
                    line=i,
                    is_from_import=False
                ))
        
        # Extract classes
        class_pattern = r"(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?"
        for match in re.finditer(class_pattern, source):
            start_pos = self._find_position(source, match.start())
            class_name = match.group(1)
            extends = match.group(2)
            
            signature = f"class {class_name}"
            if extends:
                signature += f" extends {extends}"
            
            symbols.append(Symbol(
                name=class_name,
                kind=SymbolKind.CLASS,
                filepath=filepath,
                range=Range(start_pos, start_pos),
                signature=signature
            ))
        
        # Extract functions (named and arrow)
        func_patterns = [
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>",
            r"(?:export\s+)?(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>\s*\{",
        ]
        
        for match in re.finditer(func_patterns[0], source):
            start_pos = self._find_position(source, match.start())
            func_name = match.group(1)
            params = match.group(2)
            
            symbols.append(Symbol(
                name=func_name,
                kind=SymbolKind.FUNCTION,
                filepath=filepath,
                range=Range(start_pos, start_pos),
                signature=f"function {func_name}({params})"
            ))
        
        # Extract methods
        method_pattern = r"(\w+)\s*\(([^)]*)\)\s*\{"
        for match in re.finditer(method_pattern, source):
            # Skip if it's inside a function call
            before = source[:match.start()]
            if before.rstrip().endswith(('if', 'while', 'for', 'switch', 'catch', '(')):
                continue
            
            start_pos = self._find_position(source, match.start())
            method_name = match.group(1)
            params = match.group(2)
            
            # Skip common keywords
            if method_name in ('if', 'while', 'for', 'switch', 'catch', 'function', 'class'):
                continue
            
            symbols.append(Symbol(
                name=method_name,
                kind=SymbolKind.METHOD,
                filepath=filepath,
                range=Range(start_pos, start_pos),
                signature=f"{method_name}({params})"
            ))
        
        # Extract variables/constants
        var_pattern = r"(?:export\s+)?(?:const|let|var)\s+(\w+)(?:\s*:\s*(\w+))?"
        for match in re.finditer(var_pattern, source):
            start_pos = self._find_position(source, match.start())
            var_name = match.group(1)
            type_ann = match.group(2) if is_typescript else None
            
            # Skip if it's a function/arrow assignment
            if '=>' in source[match.start():match.start() + 50]:
                continue
            
            symbols.append(Symbol(
                name=var_name,
                kind=SymbolKind.VARIABLE,
                filepath=filepath,
                range=Range(start_pos, start_pos),
                type_annotation=type_ann
            ))
        
        # Extract interfaces (TypeScript)
        if is_typescript:
            interface_pattern = r"(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+(\w+))?"
            for match in re.finditer(interface_pattern, source):
                start_pos = self._find_position(source, match.start())
                iface_name = match.group(1)
                extends = match.group(2)
                
                signature = f"interface {iface_name}"
                if extends:
                    signature += f" extends {extends}"
                
                symbols.append(Symbol(
                    name=iface_name,
                    kind=SymbolKind.INTERFACE,
                    filepath=filepath,
                    range=Range(start_pos, start_pos),
                    signature=signature
                ))
            
            # Extract types
            type_pattern = r"(?:export\s+)?type\s+(\w+)(?:\s*=)"
            for match in re.finditer(type_pattern, source):
                start_pos = self._find_position(source, match.start())
                symbols.append(Symbol(
                    name=match.group(1),
                    kind=SymbolKind.TYPE,
                    filepath=filepath,
                    range=Range(start_pos, start_pos),
                    signature=f"type {match.group(1)}"
                ))
            
            # Extract enums
            enum_pattern = r"(?:export\s+)?enum\s+(\w+)"
            for match in re.finditer(enum_pattern, source):
                start_pos = self._find_position(source, match.start())
                symbols.append(Symbol(
                    name=match.group(1),
                    kind=SymbolKind.ENUM,
                    filepath=filepath,
                    range=Range(start_pos, start_pos),
                    signature=f"enum {match.group(1)}"
                ))
        
        # Extract references
        identifier_pattern = r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b'
        for i, line in enumerate(lines, 1):
            for match in re.finditer(identifier_pattern, line):
                name = match.group(1)
                # Skip keywords
                if name in ('const', 'let', 'var', 'function', 'class', 'if', 'else', 'for', 'while', 'return', 'import', 'export', 'from', 'async', 'await', 'new', 'this', 'super'):
                    continue
                
                # Determine context
                context = 'use'
                if i > 1 and 'function' in lines[i-2]:
                    context = 'definition'
                
                references.append(Reference(
                    symbol_name=name,
                    symbol_file=None,
                    reference_file=filepath,
                    line=i,
                    column=match.start(),
                    context=context
                ))
        
        return symbols, imports, references
    
    def _find_position(self, source: str, offset: int) -> Position:
        """Convert byte offset to line/column position."""
        line = source[:offset].count('\n') + 1
        last_newline = source[:offset].rfind('\n')
        column = offset - last_newline - 1 if last_newline >= 0 else offset
        return Position(line, column)


class SymbolIndexer:
    """Main symbol indexer that coordinates extraction across languages."""
    
    LANGUAGE_EXTRACTORS = {
        '.py': PythonSymbolExtractor,
        '.pyi': PythonSymbolExtractor,
        '.js': JavaScriptSymbolExtractor,
        '.jsx': JavaScriptSymbolExtractor,
        '.ts': JavaScriptSymbolExtractor,
        '.tsx': JavaScriptSymbolExtractor,
        '.mjs': JavaScriptSymbolExtractor,
        '.cjs': JavaScriptSymbolExtractor,
    }
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        self.index = SymbolIndex()
        self._extractors: Dict[str, Any] = {}
    
    def get_extractor(self, ext: str):
        """Get or create extractor for file extension."""
        if ext not in self._extractors:
            if ext in self.LANGUAGE_EXTRACTORS:
                self._extractors[ext] = self.LANGUAGE_EXTRACTORS[ext]()
        return self._extractors.get(ext)
    
    def index_file(self, filepath: str) -> bool:
        """Index a single file."""
        path = Path(filepath)
        ext = path.suffix.lower()
        
        extractor = self.get_extractor(ext)
        if not extractor:
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
            
            symbols, imports, references = extractor.extract(source, filepath)
            
            # Add symbols to index
            for symbol in symbols:
                self.index.add_symbol(symbol)
            
            # Add imports
            self.index.imports.extend(imports)
            
            # Add references
            self.index.references.extend(references)
            
            return True
        except (IOError, OSError) as e:
            logger.warning(f"Error reading {filepath}: {e}")
            return False
    
    def index_project(self, include_patterns: List[str] = None, 
                      exclude_patterns: List[str] = None) -> int:
        """Index all files in the project."""
        if include_patterns is None:
            include_patterns = ['*.py', '*.pyi', '*.js', '*.jsx', '*.ts', '*.tsx', '*.mjs', '*.cjs']
        
        if exclude_patterns is None:
            exclude_patterns = ['node_modules/*', 'venv/*', '.venv/*', '__pycache__/*', 
                               'dist/*', 'build/*', '*.min.js', '*.d.ts']
        
        indexed_count = 0
        
        for root, dirs, files in os.walk(self.root_path):
            # Filter directories
            dirs[:] = [d for d in dirs if not self._should_exclude(d, exclude_patterns)]
            
            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Check include patterns
                if not self._should_include(filepath, include_patterns):
                    continue
                
                # Check exclude patterns
                if self._should_exclude(filepath, exclude_patterns):
                    continue
                
                if self.index_file(filepath):
                    indexed_count += 1
        
        # Build call graph
        self._build_call_graph()
        
        return indexed_count
    
    def _should_include(self, filepath: str, patterns: List[str]) -> bool:
        """Check if file matches include patterns."""
        import fnmatch
        for pattern in patterns:
            if fnmatch.fnmatch(filepath, pattern) or fnmatch.fnmatch(os.path.basename(filepath), pattern):
                return True
        return False
    
    def _should_exclude(self, path: str, patterns: List[str]) -> bool:
        """Check if path matches exclude patterns."""
        import fnmatch
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
        return False
    
    def _build_call_graph(self) -> None:
        """Build call graph from indexed symbols and references."""
        # Map symbol names to their hashes (in current project)
        name_to_hashes: Dict[str, Set[str]] = defaultdict(set)
        for sym in self.index.symbols.values():
            name_to_hashes[sym.name].add(sym.hash)
        
        # Process call references
        for ref in self.index.references:
            if ref.context != 'call':
                continue
            
            # Find caller symbol
            caller_hash = self._find_symbol_at_location(ref.reference_file, ref.line)
            if not caller_hash:
                continue
            
            # Find callee symbols
            callee_hashes = name_to_hashes.get(ref.symbol_name, set())
            
            for callee_hash in callee_hashes:
                self.index.add_call_edge(CallEdge(
                    caller=caller_hash,
                    callee=callee_hash,
                    call_site=(ref.reference_file, ref.line),
                    call_type='direct'
                ))
    
    def _find_symbol_at_location(self, filepath: str, line: int) -> Optional[str]:
        """Find symbol at a given location."""
        file_symbols = self.index.get_file_symbols(filepath)
        
        for symbol in file_symbols:
            if symbol.range.start.line <= line <= symbol.range.end.line:
                return symbol.hash
        
        return None
    
    def resolve_imports(self) -> Dict[str, Optional[str]]:
        """Resolve imports to actual file paths."""
        resolved: Dict[str, Optional[str]] = {}
        
        for imp in self.index.imports:
            module_name = imp.module
            symbol_name = imp.name or module_name
            
            # Try to find the module in indexed files
            candidates = []
            
            # Direct match with file
            module_path = module_name.replace('.', '/')
            for ext in self.LANGUAGE_EXTRACTORS.keys():
                potential_path = str(self.root_path / f"{module_path}{ext}")
                if potential_path in self.index.file_index:
                    candidates.append(potential_path)
                
                # Check index files
                potential_init = str(self.root_path / module_path / f"__init__{ext}")
                if potential_init in self.index.file_index:
                    candidates.append(potential_init)
            
            if candidates:
                resolved[f"{imp.filepath}:{imp.line}"] = candidates[0]
            else:
                resolved[f"{imp.filepath}:{imp.line}"] = None
        
        return resolved
    
    def save_index(self, output_path: str) -> None:
        """Save index to file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.index.to_dict(), f, indent=2)
    
    def load_index(self, input_path: str) -> None:
        """Load index from file."""
        with open(input_path, 'r', encoding='utf-8') as f:
            self.index = SymbolIndex.from_dict(json.load(f))


def index_project(root_path: str, output_path: Optional[str] = None) -> SymbolIndex:
    """Convenience function to index a project."""
    indexer = SymbolIndexer(root_path)
    indexer.index_project()
    
    if output_path:
        indexer.save_index(output_path)
    
    return indexer.index


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        index = index_project(sys.argv[1])
        print(f"Indexed {len(index.symbols)} symbols")
        print(f"Imports: {len(index.imports)}")
        print(f"References: {len(index.references)}")
        
        # Show some symbol names
        for i, sym in enumerate(list(index.symbols.values())[:10]):
            print(f"  {sym.kind.value}: {sym.name}")
