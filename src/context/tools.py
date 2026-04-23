"""
Tools - Agent tools for context management

Features:
- analyze_project tool - Full project analysis
- find_symbol tool - Symbol search and lookup
- get_context tool - Context retrieval
- search_code tool - Code search with relevance
"""

import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from functools import wraps
from abc import ABC, abstractmethod
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Type variables
T = TypeVar('T')
R = TypeVar('R')


# ==================== Tool Infrastructure ====================

@dataclass
class ToolParameter:
    """A tool parameter definition."""
    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'metadata': self.metadata,
            'execution_time_ms': self.execution_time_ms
        }


class BaseTool(ABC):
    """Base class for all tools."""
    
    name: str = ""
    description: str = ""
    parameters: List[ToolParameter] = []
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for LLM."""
        return {
            'name': self.name,
            'description': self.description,
            'parameters': {
                'type': 'object',
                'properties': {
                    p.name: {
                        'type': p.type,
                        'description': p.description,
                        **({'enum': p.enum} if p.enum else {}),
                        **({'default': p.default} if p.default is not None else {})
                    }
                    for p in self.parameters
                },
                'required': [p.name for p in self.parameters if p.required]
            }
        }
    
    def validate_params(self, kwargs: Dict[str, Any]) -> Optional[str]:
        """Validate parameters. Returns error message or None."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
            
            if param.name in kwargs:
                value = kwargs[param.name]
                
                # Type validation
                if param.type == 'string' and not isinstance(value, str):
                    return f"Parameter {param.name} must be a string"
                elif param.type == 'number' and not isinstance(value, (int, float)):
                    return f"Parameter {param.name} must be a number"
                elif param.type == 'boolean' and not isinstance(value, bool):
                    return f"Parameter {param.name} must be a boolean"
                elif param.type == 'array' and not isinstance(value, list):
                    return f"Parameter {param.name} must be an array"
                elif param.type == 'object' and not isinstance(value, dict):
                    return f"Parameter {param.name} must be an object"
                
                # Enum validation
                if param.enum and value not in param.enum:
                    return f"Parameter {param.name} must be one of: {param.enum}"
        
        return None


def timing_decorator(func: Callable[..., R]) -> Callable[..., ToolResult]:
    """Decorator to measure execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> ToolResult:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        
        result.execution_time_ms = (end_time - start_time) * 1000
        return result
    
    return wrapper


# ==================== Analyze Project Tool ====================

class AnalyzeProjectTool(BaseTool):
    """Tool to analyze a project's structure, languages, and dependencies."""
    
    name = "analyze_project"
    description = "Analyze a project's structure, detect languages, frameworks, and dependencies"
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to the project root directory",
            required=True
        ),
        ToolParameter(
            name="include_structure",
            type="boolean",
            description="Include detailed directory structure",
            required=False,
            default=True
        ),
        ToolParameter(
            name="include_dependencies",
            type="boolean",
            description="Include dependency analysis",
            required=False,
            default=True
        ),
        ToolParameter(
            name="max_depth",
            type="number",
            description="Maximum depth for directory traversal",
            required=False,
            default=10
        )
    ]
    
    def __init__(self):
        from .project_analyzer import ProjectAnalyzer
        self._analyzer_class = ProjectAnalyzer
        self._cache: Dict[str, Any] = {}
    
    @timing_decorator
    def execute(self, **kwargs) -> ToolResult:
        # Validate
        error = self.validate_params(kwargs)
        if error:
            return ToolResult(success=False, data=None, error=error)
        
        path = kwargs.get('path', '.')
        include_structure = kwargs.get('include_structure', True)
        include_dependencies = kwargs.get('include_dependencies', True)
        max_depth = kwargs.get('max_depth', 10)
        
        # Check path
        if not os.path.exists(path):
            return ToolResult(
                success=False,
                data=None,
                error=f"Path does not exist: {path}"
            )
        
        # Check cache
        cache_key = hashlib.sha256(f"{path}:{max_depth}".encode()).hexdigest()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return ToolResult(
                success=True,
                data=cached,
                metadata={'cached': True}
            )
        
        try:
            analyzer = self._analyzer_class(path, max_depth=max_depth)
            analysis = analyzer.analyze()
            
            # Build result
            result_data = {
                'root_path': analysis.root_path,
                'languages': [
                    {
                        'name': lang.name,
                        'file_count': lang.file_count,
                        'percentage': lang.percentage,
                        'primary': lang.primary
                    }
                    for lang in analysis.languages
                ],
                'primary_language': analysis.primary_language.name if analysis.primary_language else None,
                'frameworks': [
                    {
                        'name': fw.name,
                        'version': fw.version,
                        'category': fw.category,
                        'confidence': fw.confidence
                    }
                    for fw in analysis.frameworks
                ],
                'total_files': analysis.structure.total_files,
                'total_directories': analysis.structure.total_dirs,
            }
            
            if include_structure:
                result_data['structure'] = {
                    'directories': analysis.structure.directories,
                    'file_types': analysis.structure.file_types,
                    'depth': analysis.structure.depth
                }
            
            if include_dependencies:
                result_data['dependencies'] = [
                    {
                        'name': dep.name,
                        'version': dep.version,
                        'source': dep.source,
                        'dev': dep.dev,
                        'direct': dep.direct
                    }
                    for dep in analysis.dependencies
                ]
            
            result_data['config_files'] = [
                {
                    'path': cfg.path,
                    'type': cfg.type,
                    'parser': cfg.parser
                }
                for cfg in analysis.configs
            ]
            
            # Cache result
            self._cache[cache_key] = result_data
            
            return ToolResult(
                success=True,
                data=result_data,
                metadata={'cached': False}
            )
        
        except Exception as e:
            logger.exception(f"Error analyzing project: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Error analyzing project: {str(e)}"
            )


# ==================== Find Symbol Tool ====================

class FindSymbolTool(BaseTool):
    """Tool to find symbols in the codebase."""
    
    name = "find_symbol"
    description = "Find symbols (functions, classes, variables) in the codebase by name or pattern"
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="Symbol name or pattern to search for",
            required=True
        ),
        ToolParameter(
            name="symbol_type",
            type="string",
            description="Type of symbol to find",
            required=False,
            default="all",
            enum=["all", "function", "class", "variable", "constant", "method", "interface", "type", "enum"]
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Path to search within (defaults to project root)",
            required=False,
            default=None
        ),
        ToolParameter(
            name="include_definition",
            type="boolean",
            description="Include the symbol definition in results",
            required=False,
            default=False
        ),
        ToolParameter(
            name="max_results",
            type="number",
            description="Maximum number of results to return",
            required=False,
            default=20
        )
    ]
    
    def __init__(self, index_path: Optional[str] = None):
        self._index_path = index_path
        self._index = None
    
    def _ensure_index(self, path: str) -> bool:
        """Ensure symbol index is loaded."""
        if self._index is not None:
            return True
        
        try:
            from .symbol_indexer import SymbolIndexer
            
            # Try to load existing index
            if self._index_path and os.path.exists(self._index_path):
                indexer = SymbolIndexer(path)
                indexer.load_index(self._index_path)
                self._index = indexer.index
                return True
            
            # Build new index
            indexer = SymbolIndexer(path)
            indexer.index_project()
            self._index = indexer.index
            
            return True
        except Exception as e:
            logger.error(f"Error loading symbol index: {e}")
            return False
    
    @timing_decorator
    def execute(self, **kwargs) -> ToolResult:
        # Validate
        error = self.validate_params(kwargs)
        if error:
            return ToolResult(success=False, data=None, error=error)
        
        query = kwargs.get('query')
        symbol_type = kwargs.get('symbol_type', 'all')
        path = kwargs.get('path', '.')
        include_definition = kwargs.get('include_definition', False)
        max_results = kwargs.get('max_results', 20)
        
        # Ensure index
        if not self._ensure_index(path):
            return ToolResult(
                success=False,
                data=None,
                error="Could not load symbol index"
            )
        
        try:
            from .symbol_indexer import SymbolKind
            
            # Map symbol type string to enum
            type_map = {
                'all': None,
                'function': SymbolKind.FUNCTION,
                'class': SymbolKind.CLASS,
                'variable': SymbolKind.VARIABLE,
                'constant': SymbolKind.CONSTANT,
                'method': SymbolKind.METHOD,
                'interface': SymbolKind.INTERFACE,
                'type': SymbolKind.TYPE,
                'enum': SymbolKind.ENUM,
            }
            
            target_kind = type_map.get(symbol_type.lower())
            
            # Search by name
            symbols = self._index.find_symbols_by_name(query)
            
            # Filter by kind
            if target_kind:
                symbols = [s for s in symbols if s.kind == target_kind]
            
            # Limit results
            symbols = symbols[:max_results]
            
            # Build result
            results = []
            for symbol in symbols:
                result_item = {
                    'name': symbol.name,
                    'kind': symbol.kind.value,
                    'filepath': symbol.filepath,
                    'line': symbol.range.start.line,
                    'column': symbol.range.start.column,
                    'signature': symbol.signature,
                    'docstring': symbol.docstring,
                }
                
                if include_definition and symbol.docstring:
                    result_item['docstring'] = symbol.docstring
                
                results.append(result_item)
            
            return ToolResult(
                success=True,
                data={
                    'query': query,
                    'symbol_type': symbol_type,
                    'total_found': len(symbols),
                    'results': results
                }
            )
        
        except Exception as e:
            logger.exception(f"Error finding symbol: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Error finding symbol: {str(e)}"
            )


# ==================== Get Context Tool ====================

class GetContextTool(BaseTool):
    """Tool to get context for a file or location."""
    
    name = "get_context"
    description = "Get context for a file, including related files, imports, and symbols"
    parameters = [
        ToolParameter(
            name="filepath",
            type="string",
            description="Path to the file to get context for",
            required=True
        ),
        ToolParameter(
            name="include_related",
            type="boolean",
            description="Include related files (imports, references)",
            required=False,
            default=True
        ),
        ToolParameter(
            name="include_symbols",
            type="boolean",
            description="Include symbols from the file",
            required=False,
            default=True
        ),
        ToolParameter(
            name="include_git_context",
            type="boolean",
            description="Include git context (blame, recent changes)",
            required=False,
            default=False
        ),
        ToolParameter(
            name="max_related_files",
            type="number",
            description="Maximum number of related files to include",
            required=False,
            default=10
        )
    ]
    
    def __init__(self, root_path: Optional[str] = None):
        self._root_path = root_path
        self._manager = None
    
    def _ensure_manager(self) -> bool:
        """Ensure context manager is initialized."""
        if self._manager is not None:
            return True
        
        try:
            from .context_manager import ContextManager
            self._manager = ContextManager(self._root_path or '.')
            return True
        except Exception as e:
            logger.error(f"Error initializing context manager: {e}")
            return False
    
    @timing_decorator
    def execute(self, **kwargs) -> ToolResult:
        # Validate
        error = self.validate_params(kwargs)
        if error:
            return ToolResult(success=False, data=None, error=error)
        
        filepath = kwargs.get('filepath')
        include_related = kwargs.get('include_related', True)
        include_symbols = kwargs.get('include_symbols', True)
        include_git_context = kwargs.get('include_git_context', False)
        max_related_files = kwargs.get('max_related_files', 10)
        
        # Check file exists
        if not os.path.exists(filepath):
            return ToolResult(
                success=False,
                data=None,
                error=f"File does not exist: {filepath}"
            )
        
        # Ensure manager
        if not self._ensure_manager():
            return ToolResult(
                success=False,
                data=None,
                error="Could not initialize context manager"
            )
        
        try:
            # Get file context
            file_context = self._manager.get_file_context(filepath)
            
            result = {
                'filepath': filepath,
                'language': file_context.language,
                'size': file_context.size,
                'line_count': file_context.line_count,
                'imports': file_context.imports,
                'exports': file_context.exports,
            }
            
            # Get related files
            if include_related:
                related = self._manager.get_related_files(filepath, max_related_files)
                result['related_files'] = related
            
            # Get symbols
            if include_symbols:
                from .symbol_indexer import SymbolIndexer
                indexer = SymbolIndexer(self._root_path or os.path.dirname(filepath))
                indexer.index_file(filepath)
                
                symbols = indexer.index.get_file_symbols(filepath)
                result['symbols'] = [
                    {
                        'name': s.name,
                        'kind': s.kind.value,
                        'line': s.range.start.line,
                        'signature': s.signature
                    }
                    for s in symbols
                ]
            
            # Get git context
            if include_git_context:
                git_context = self._manager.get_git_context()
                
                if git_context.is_repo:
                    result['git'] = {
                        'branch': git_context.branch,
                        'status': git_context.status,
                        'modified': filepath in git_context.modified_files,
                        'staged': filepath in git_context.staged_files,
                    }
                    
                    # Get blame
                    blame = self._manager.get_file_blame(filepath)
                    if blame:
                        result['git']['blame'] = [
                            {
                                'line': i + 1,
                                'author': b.get('author'),
                                'message': b.get('message', '')[:50]
                            }
                            for i, b in enumerate(blame[:20])
                        ]
            
            return ToolResult(
                success=True,
                data=result,
                metadata={'file': filepath}
            )
        
        except Exception as e:
            logger.exception(f"Error getting context: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Error getting context: {str(e)}"
            )


# ==================== Search Code Tool ====================

class SearchCodeTool(BaseTool):
    """Tool to search code with relevance scoring."""
    
    name = "search_code"
    description = "Search for code across the project with relevance scoring"
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="Search query (natural language or code pattern)",
            required=True
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Path to search within",
            required=False,
            default=None
        ),
        ToolParameter(
            name="file_pattern",
            type="string",
            description="File pattern to match (e.g., '*.py', '*.js')",
            required=False,
            default=None
        ),
        ToolParameter(
            name="include_snippets",
            type="boolean",
            description="Include code snippets in results",
            required=False,
            default=True
        ),
        ToolParameter(
            name="max_results",
            type="number",
            description="Maximum number of results",
            required=False,
            default=20
        ),
        ToolParameter(
            name="max_snippet_lines",
            type="number",
            description="Maximum lines per snippet",
            required=False,
            default=10
        )
    ]
    
    def __init__(self, index_path: Optional[str] = None):
        self._index_path = index_path
        self._scorer = None
        self._content_cache: Dict[str, str] = {}
    
    def _ensure_scorer(self, path: str) -> bool:
        """Ensure relevance scorer is initialized."""
        if self._scorer is not None:
            return True
        
        try:
            from .relevance import RelevanceScorer
            
            self._scorer = RelevanceScorer()
            
            # Try to load existing index
            if self._index_path and os.path.exists(self._index_path):
                self._scorer.load_index(self._index_path)
                return True
            
            # Build index from files
            self._index_project(path)
            return True
        except Exception as e:
            logger.error(f"Error initializing scorer: {e}")
            return False
    
    def _index_project(self, path: str) -> None:
        """Index project files for search."""
        import fnmatch
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      ('node_modules', 'venv', '__pycache__', 'dist', 'build', 'target')]
            
            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Check file pattern if specified
                
                # Index code files
                if filename.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.rb', '.php', '.c', '.cpp', '.h', '.hpp', '.cs', '.swift', '.kt', '.scala', '.ex', '.exs', '.erl', '.hs', '.lua', '.r', '.sh', '.sql', '.html', '.css', '.scss', '.less', '.vue', '.svelte', '.dart', '.md', '.json', '.yaml', '.yml', '.toml', '.xml')):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        self._scorer.index_file(filepath, content)
                        self._content_cache[filepath] = content
                    except IOError:
                        pass
    
    @timing_decorator
    def execute(self, **kwargs) -> ToolResult:
        # Validate
        error = self.validate_params(kwargs)
        if error:
            return ToolResult(success=False, data=None, error=error)
        
        query = kwargs.get('query')
        path = kwargs.get('path', '.')
        file_pattern = kwargs.get('file_pattern')
        include_snippets = kwargs.get('include_snippets', True)
        max_results = kwargs.get('max_results', 20)
        max_snippet_lines = kwargs.get('max_snippet_lines', 10)
        
        # Ensure scorer
        if not self._ensure_scorer(path):
            return ToolResult(
                success=False,
                data=None,
                error="Could not initialize search"
            )
        
        try:
            # Search with relevance
            results = self._scorer.search(
                query,
                top_k=max_results * 2,  # Get more to filter
                content_map=self._content_cache
            )
            
            # Filter by file pattern
            if file_pattern:
                import fnmatch
                results = [
                    r for r in results
                    if fnmatch.fnmatch(os.path.basename(r.filepath), file_pattern)
                ]
            
            # Limit results
            results = results[:max_results]
            
            # Build result
            search_results = []
            for result in results:
                item = {
                    'filepath': result.filepath,
                    'relevance_score': round(result.combined_score, 4),
                    'matched_terms': result.matched_terms,
                    'scores': {
                        'tfidf': round(result.tfidf_score, 4),
                        'semantic': round(result.semantic_score, 4),
                        'frequency': round(result.frequency_score, 4),
                        'recency': round(result.recency_score, 4),
                    }
                }
                
                # Include snippets
                if include_snippets and result.filepath in self._content_cache:
                    content = self._content_cache[result.filepath]
                    snippets = self._extract_snippets(content, result.matched_terms, max_snippet_lines)
                    item['snippets'] = snippets
                
                search_results.append(item)
            
            return ToolResult(
                success=True,
                data={
                    'query': query,
                    'total_results': len(results),
                    'results': search_results
                }
            )
        
        except Exception as e:
            logger.exception(f"Error searching code: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Error searching code: {str(e)}"
            )
    
    def _extract_snippets(self, content: str, terms: List[str], max_lines: int) -> List[Dict[str, Any]]:
        """Extract relevant snippets from content."""
        lines = content.split('\n')
        snippets: List[Dict[str, Any]] = []
        
        # Find lines containing matched terms
        matched_lines: List[int] = []
        terms_lower = [t.lower() for t in terms]
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(term in line_lower for term in terms_lower):
                matched_lines.append(i)
        
        # Extract snippets around matched lines
        seen_ranges: set = set()
        
        for line_num in matched_lines[:5]:  # Limit to 5 snippets
            # Calculate range
            start = max(0, line_num - 2)
            end = min(len(lines), line_num + max_lines - 2)
            
            # Check if overlaps with existing
            range_key = (start, end)
            if any(s <= start < e or s < end <= e for s, e in seen_ranges):
                continue
            
            seen_ranges.add(range_key)
            
            # Extract snippet
            snippet_lines = lines[start:end]
            snippet = '\n'.join(snippet_lines)
            
            snippets.append({
                'start_line': start + 1,
                'end_line': end,
                'content': snippet,
                'matched_line': line_num + 1
            })
        
        return snippets


# ==================== Tool Registry ====================

class ToolRegistry:
    """Registry of available tools."""
    
    def __init__(self, root_path: Optional[str] = None, index_path: Optional[str] = None):
        self._tools: Dict[str, BaseTool] = {}
        self._root_path = root_path
        self._index_path = index_path
        
        # Register default tools
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register default tools."""
        self.register(AnalyzeProjectTool())
        self.register(FindSymbolTool(self._index_path))
        self.register(GetContextTool(self._root_path))
        self.register(SearchCodeTool(self._index_path))
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all tool names."""
        return list(self._tools.keys())
    
    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all tools."""
        return [tool.get_schema() for tool in self._tools.values()]
    
    def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        tool = self.get(name)
        
        if tool is None:
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool not found: {name}"
            )
        
        return tool.execute(**kwargs)
    
    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Export tools in OpenAI function calling format."""
        return [
            {
                'type': 'function',
                'function': tool.get_schema()
            }
            for tool in self._tools.values()
        ]
    
    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """Export tools in Anthropic tool use format."""
        return [
            {
                'name': tool.name,
                'description': tool.description,
                'input_schema': tool.get_schema()['parameters']
            }
            for tool in self._tools.values()
        ]


# ==================== Convenience Functions ====================

def create_tool_registry(root_path: str = ".", index_path: Optional[str] = None) -> ToolRegistry:
    """Create a tool registry with default tools."""
    return ToolRegistry(root_path, index_path)


def analyze_project(path: str = ".") -> Dict[str, Any]:
    """Quick project analysis."""
    tool = AnalyzeProjectTool()
    result = tool.execute(path=path)
    return result.to_dict()


def find_symbol(query: str, path: str = ".", symbol_type: str = "all") -> Dict[str, Any]:
    """Quick symbol search."""
    tool = FindSymbolTool()
    tool._ensure_index(path)
    result = tool.execute(query=query, path=path, symbol_type=symbol_type)
    return result.to_dict()


def get_context(filepath: str, root_path: str = ".") -> Dict[str, Any]:
    """Quick context retrieval."""
    tool = GetContextTool(root_path)
    result = tool.execute(filepath=filepath)
    return result.to_dict()


def search_code(query: str, path: str = ".") -> Dict[str, Any]:
    """Quick code search."""
    tool = SearchCodeTool()
    result = tool.execute(query=query, path=path)
    return result.to_dict()


if __name__ == '__main__':
    import sys
    
    # Demo
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    registry = create_tool_registry(path)
    
    print("Available tools:")
    for name in registry.list_tools():
        print(f"  - {name}")
    
    # Analyze project
    print(f"\nAnalyzing project: {path}")
    result = registry.execute("analyze_project", path=path)
    
    if result.success:
        print(f"Languages: {[l['name'] for l in result.data.get('languages', [])]}")
        print(f"Frameworks: {[f['name'] for f in result.data.get('frameworks', [])]}")
        print(f"Total files: {result.data.get('total_files', 0)}")
    else:
        print(f"Error: {result.error}")
