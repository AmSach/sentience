"""
Completion Provider - Auto-trigger completion, signature help, and snippet expansion.
Handles completion requests with intelligent triggering and result processing.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from functools import lru_cache

from .manager import LSPManager, LanguageId

logger = logging.getLogger(__name__)


class CompletionTriggerKind(Enum):
    """LSP completion trigger kinds."""
    INVOKED = 1
    TRIGGER_CHARACTER = 2
    TRIGGER_FOR_INCOMPLETE_COMPLETIONS = 3


class CompletionItemKind(Enum):
    """LSP completion item kinds."""
    TEXT = 1
    METHOD = 2
    FUNCTION = 3
    CONSTRUCTOR = 4
    FIELD = 5
    VARIABLE = 6
    CLASS = 7
    INTERFACE = 8
    MODULE = 9
    PROPERTY = 10
    UNIT = 11
    VALUE = 12
    ENUM = 13
    KEYWORD = 14
    SNIPPET = 15
    COLOR = 16
    FILE = 17
    REFERENCE = 18
    FOLDER = 19
    ENUM_MEMBER = 20
    CONSTANT = 21
    STRUCT = 22
    EVENT = 23
    OPERATOR = 24
    TYPE_PARAMETER = 25


class InsertTextFormat(Enum):
    """Text insertion format."""
    PLAIN_TEXT = 1
    SNIPPET = 2


@dataclass
class CompletionItem:
    """A completion item."""
    label: str
    kind: CompletionItemKind = CompletionItemKind.TEXT
    detail: Optional[str] = None
    documentation: Optional[str] = None
    insert_text: Optional[str] = None
    insert_text_format: InsertTextFormat = InsertTextFormat.PLAIN_TEXT
    sort_text: Optional[str] = None
    filter_text: Optional[str] = None
    preselect: bool = False
    deprecated: bool = False
    commit_characters: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Additional fields for UI
    score: float = 0.0
    source: str = "lsp"
    
    @classmethod
    def from_lsp(cls, item: Dict[str, Any]) -> "CompletionItem":
        """Create from LSP completion item."""
        kind_value = item.get("kind", 1)
        kind = CompletionItemKind(kind_value) if 1 <= kind_value <= 25 else CompletionItemKind.TEXT
        
        insert_format_value = item.get("insertTextFormat", 1)
        insert_format = InsertTextFormat(insert_format_value) if insert_format_value in (1, 2) else InsertTextFormat.PLAIN_TEXT
        
        doc = item.get("documentation", "")
        if isinstance(doc, dict):
            doc = doc.get("value", "")
        
        return cls(
            label=item.get("label", ""),
            kind=kind,
            detail=item.get("detail"),
            documentation=doc,
            insert_text=item.get("insertText") or item.get("label", ""),
            insert_text_format=insert_format,
            sort_text=item.get("sortText"),
            filter_text=item.get("filterText"),
            preselect=item.get("preselect", False),
            deprecated=item.get("deprecated", False),
            commit_characters=item.get("commitCharacters", []),
            data=item.get("data", {})
        )


@dataclass
class SignatureInformation:
    """A single signature."""
    label: str
    documentation: Optional[str] = None
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    active_parameter: int = 0
    
    @classmethod
    def from_lsp(cls, sig: Dict[str, Any]) -> "SignatureInformation":
        """Create from LSP signature information."""
        doc = sig.get("documentation", "")
        if isinstance(doc, dict):
            doc = doc.get("value", "")
        
        return cls(
            label=sig.get("label", ""),
            documentation=doc,
            parameters=sig.get("parameters", []),
            active_parameter=sig.get("activeParameter", 0)
        )


@dataclass
class SignatureHelp:
    """Signature help result."""
    signatures: List[SignatureInformation] = field(default_factory=list)
    active_signature: int = 0
    active_parameter: int = 0
    
    @classmethod
    def from_lsp(cls, result: Optional[Dict[str, Any]]) -> Optional["SignatureHelp"]:
        """Create from LSP signature help result."""
        if not result:
            return None
        
        sigs = [SignatureInformation.from_lsp(s) for s in result.get("signatures", [])]
        
        return cls(
            signatures=sigs,
            active_signature=result.get("activeSignature", 0),
            active_parameter=result.get("activeParameter", 0)
        )


@dataclass
class Snippet:
    """A code snippet."""
    prefix: str
    body: str
    description: str
    scope: Optional[str] = None
    
    def expand(self, variables: Optional[Dict[str, str]] = None) -> str:
        """Expand snippet with variables."""
        result = self.body
        variables = variables or {}
        
        # Replace tabstops: $1, $2, etc. -> placeholders
        # Replace variables: ${name} or ${name:default}
        for match in re.finditer(r'\$\{(\w+)(?::([^}]*))?\}', result):
            var_name = match.group(1)
            default = match.group(2) or var_name
            value = variables.get(var_name, default)
            result = result.replace(match.group(0), value)
        
        # Simple tabstops
        result = re.sub(r'\$(\d+)', r'${\1}', result)
        
        return result


class SnippetManager:
    """Manages code snippets."""
    
    def __init__(self):
        self._snippets: Dict[str, List[Snippet]] = {}
        self._load_builtin_snippets()
    
    def _load_builtin_snippets(self) -> None:
        """Load built-in snippets for supported languages."""
        # Python snippets
        self._snippets["python"] = [
            Snippet("if", "if ${condition}:\n\t${pass}", "If statement"),
            Snippet("ife", "if ${condition}:\n\t${pass}\nelse:\n\t${pass}", "If-else statement"),
            Snippet("elif", "elif ${condition}:\n\t${pass}", "Elif clause"),
            Snippet("for", "for ${item} in ${iterable}:\n\t${pass}", "For loop"),
            Snippet("fore", "for ${index}, ${item} in enumerate(${iterable}):\n\t${pass}", "For loop with enumerate"),
            Snippet("while", "while ${condition}:\n\t${pass}", "While loop"),
            Snippet("def", "def ${name}(${params}):\n\t\"\"\"${docstring}\"\"\"\n\t${pass}", "Function definition"),
            Snippet("defc", "def ${name}(${params}):\n\t\"\"\"${docstring}\"\"\"\n\t${pass}\n\treturn ${result}", "Function with return"),
            Snippet("class", "class ${name}:\n\tdef __init__(self, ${params}):\n\t\t${pass}", "Class definition"),
            Snippet("classi", "class ${name}(${base}):\n\tdef __init__(self, ${params}):\n\t\t${pass}", "Class with inheritance"),
            Snippet("try", "try:\n\t${pass}\nexcept ${exception} as e:\n\t${handler}", "Try-except block"),
            Snippet("tryf", "try:\n\t${pass}\nfinally:\n\t${pass}", "Try-finally block"),
            Snippet("with", "with ${context}:\n\t${pass}", "With statement"),
            Snippet("main", 'if __name__ == "__main__":\n\t${pass}', "Main guard"),
            Snippet("imp", "import ${module}", "Import statement"),
            Snippet("from", "from ${module} import ${names}", "From import"),
            Snippet("lambda", "lambda ${params}: ${expression}", "Lambda function"),
            Snippet("prop", "@property\ndef ${name}(self):\n\treturn self._${name}", "Property getter"),
            Snippet("props", "@property\ndef ${name}(self):\n\treturn self._${name}\n\n@${name}.setter\ndef ${name}(self, value):\n\tself._${name} = value", "Property getter and setter"),
        ]
        
        # JavaScript/TypeScript snippets
        js_snippets = [
            Snippet("if", "if (${condition}) {\n\t${pass}\n}", "If statement"),
            Snippet("ife", "if (${condition}) {\n\t${pass}\n} else {\n\t${pass}\n}", "If-else statement"),
            Snippet("for", "for (let ${i} = 0; ${i} < ${length}; ${i}++) {\n\t${pass}\n}", "For loop"),
            Snippet("forof", "for (const ${item} of ${iterable}) {\n\t${pass}\n}", "For-of loop"),
            Snippet("forin", "for (const ${key} in ${object}) {\n\t${pass}\n}", "For-in loop"),
            Snippet("while", "while (${condition}) {\n\t${pass}\n}", "While loop"),
            Snippet("fn", "function ${name}(${params}) {\n\t${pass}\n}", "Function declaration"),
            Snippet("afn", "const ${name} = (${params}) => {\n\t${pass}\n};", "Arrow function"),
            Snippet("afnr", "const ${name} = (${params}) => ${expression};", "Arrow function with return"),
            Snippet("class", "class ${name} {\n\tconstructor(${params}) {\n\t\t${pass}\n\t}\n}", "Class declaration"),
            Snippet("classe", "class ${name} extends ${base} {\n\tconstructor(${params}) {\n\t\tsuper(${args});\n\t\t${pass}\n\t}\n}", "Class with extends"),
            Snippet("try", "try {\n\t${pass}\n} catch (${error}) {\n\t${handler}\n}", "Try-catch block"),
            Snippet("tryf", "try {\n\t${pass}\n} finally {\n\t${pass}\n}", "Try-finally block"),
            Snippet("log", "console.log(${value});", "Console log"),
            Snippet("imp", "import ${module};", "Import statement"),
            Snippet("impd", "import { ${names} } from '${module}';", "Named import"),
            Snippet("impall", "import * as ${alias} from '${module}';", "Import all"),
            Snippet("exp", "export ${declaration};", "Export"),
            Snippet("expd", "export default ${declaration};", "Export default"),
            Snippet("clg", "console.log('${message}', ${value});", "Console log with message"),
            Snippet("clc", "console.clear();", "Console clear"),
            Snippet("clt", "console.table(${value});", "Console table"),
            Snippet("clo", "console.time('${label}');", "Console time start"),
            Snippet("cle", "console.timeEnd('${label}');", "Console time end"),
        ]
        self._snippets["javascript"] = js_snippets
        self._snippets["typescript"] = js_snippets + [
            Snippet("interface", "interface ${name} {\n\t${properties}\n}", "Interface"),
            Snippet("type", "type ${name} = ${definition};", "Type alias"),
            Snippet("enum", "enum ${name} {\n\t${members}\n}", "Enum"),
            Snippet("genn", "function* ${name}(${params}): Generator<${type}> {\n\t${pass}\n}", "Generator function"),
        ]
        self._snippets["javascriptreact"] = js_snippets + [
            Snippet("rfc", "function ${component}() {\n\treturn (\n\t\t${jsx}\n\t);\n}", "React functional component"),
            Snippet("rffc", "function ${component}({ ${props} }) {\n\treturn (\n\t\t${jsx}\n\t);\n}", "React functional component with props"),
            Snippet("rafc", "const ${component} = () => {\n\treturn (\n\t\t${jsx}\n\t);\n};", "Arrow function component"),
            Snippet("rafcf", "const ${component} = ({ ${props} }) => {\n\treturn (\n\t\t${jsx}\n\t);\n};", "Arrow function component with props"),
            Snippet("us", "const [${state}, set${State}] = useState(${initial});", "useState hook"),
            Snippet("ue", "useEffect(() => {\n\t${effect}\n}, [${deps}]);", "useEffect hook"),
            Snippet("uc", "useContext(${context});", "useContext hook"),
            Snippet("ur", "useRef(${initial});", "useRef hook"),
            Snippet("um", "useMemo(() => ${fn}, [${deps}]);", "useMemo hook"),
            Snippet("ucb", "useCallback(${fn}, [${deps}]);", "useCallback hook"),
        ]
        self._snippets["typescriptreact"] = self._snippets["javascriptreact"]
        
        # Go snippets
        self._snippets["go"] = [
            Snippet("pf", 'fmt.Printf("${format}\\n", ${args})', "Printf"),
            Snippet("pln", "fmt.Println(${args})", "Println"),
            Snippet("func", "func ${name}(${params}) ${returns} {\n\t${pass}\n}", "Function"),
            Snippet("funcm", "func (${receiver} ${type}) ${name}(${params}) ${returns} {\n\t${pass}\n}", "Method"),
            Snippet("main", "func main() {\n\t${pass}\n}", "Main function"),
            Snippet("if", "if ${condition} {\n\t${pass}\n}", "If statement"),
            Snippet("ife", "if ${condition} {\n\t${pass}\n} else {\n\t${pass}\n}", "If-else"),
            Snippet("for", "for ${i} := 0; ${i} < ${length}; ${i}++ {\n\t${pass}\n}", "For loop"),
            Snippet("forr", "for ${index}, ${value} := range ${iterable} {\n\t${pass}\n}", "For range"),
            Snippet("gor", "go func() {\n\t${pass}\n}()", "Goroutine"),
            Snippet("sel", "select {\ncase ${case}:\n\t${pass}\ndefault:\n\t${pass}\n}", "Select statement"),
            Snippet("type", "type ${name} ${type}", "Type definition"),
            Snippet("struct", "type ${name} struct {\n\t${fields}\n}", "Struct"),
            Snippet("inter", "type ${name} interface {\n\t${methods}\n}", "Interface"),
            Snippet("err", "if err != nil {\n\t${handler}\n}", "Error check"),
        ]
        
        # Rust snippets
        self._snippets["rust"] = [
            Snippet("fn", "fn ${name}(${params}) -> ${returns} {\n\t${pass}\n}", "Function"),
            Snippet("fnm", "fn ${name}(${params}) -> ${returns} {\n\t${pass}\n}", "Main function template"),
            Snippet("main", "fn main() {\n\t${pass}\n}", "Main function"),
            Snippet("if", "if ${condition} {\n\t${pass}\n}", "If statement"),
            Snippet("ife", "if ${condition} {\n\t${pass}\n} else {\n\t${pass}\n}", "If-else"),
            Snippet("for", "for ${item} in ${iterable} {\n\t${pass}\n}", "For loop"),
            Snippet("loop", "loop {\n\t${pass}\n}", "Infinite loop"),
            Snippet("while", "while ${condition} {\n\t${pass}\n}", "While loop"),
            Snippet("match", "match ${value} {\n\t${pattern} => ${action},\n}", "Match expression"),
            Snippet("struct", "struct ${name} {\n\t${fields}\n}", "Struct"),
            Snippet("enum", "enum ${name} {\n\t${variants}\n}", "Enum"),
            Snippet("impl", "impl ${name} {\n\t${methods}\n}", "Implementation block"),
            Snippet("implt", "impl ${trait} for ${type} {\n\t${methods}\n}", "Trait implementation"),
            Snippet("trait", "trait ${name} {\n\t${methods}\n}", "Trait definition"),
            Snippet("ptest", "#[test]\nfn ${name}() {\n\t${pass}\n}", "Test function"),
            Snippet("println", 'println!("${format}", ${args});', "Println"),
            Snippet("format", 'format!("${format}", ${args})', "Format string"),
        ]
    
    def get_snippets(self, language: str) -> List[Snippet]:
        """Get snippets for a language."""
        return self._snippets.get(language, [])
    
    def find_snippet(self, language: str, prefix: str) -> Optional[Snippet]:
        """Find a snippet by prefix."""
        for snippet in self._snippets.get(language, []):
            if snippet.prefix == prefix:
                return snippet
        return None
    
    def add_snippet(self, language: str, snippet: Snippet) -> None:
        """Add a snippet for a language."""
        if language not in self._snippets:
            self._snippets[language] = []
        self._snippets[language].append(snippet)


class CompletionProvider:
    """Provides intelligent code completion with auto-triggering."""
    
    # Default trigger characters by language
    TRIGGER_CHARS: Dict[str, List[str]] = {
        "python": [".", "(", "[", ",", " ", ":"],
        "javascript": [".", "(", "[", ",", " ", ":", "<", '"', "'"],
        "typescript": [".", "(", "[", ",", " ", ":", "<", '"', "'"],
        "javascriptreact": [".", "(", "[", ",", " ", ":", "<", '"', "'"],
        "typescriptreact": [".", "(", "[", ",", " ", ":", "<", '"', "'"],
        "go": [".", "(", "[", ",", " "],
        "rust": [".", "(", "[", ",", ":", " ", "#"],
    }
    
    # Characters that should cancel/commit completion
    COMMIT_CHARS = ["\t", "\n", ";", ")", "}", "]"]
    
    def __init__(self, manager: LSPManager, snippet_manager: Optional[SnippetManager] = None):
        self.manager = manager
        self.snippet_manager = snippet_manager or SnippetManager()
        
        self._pending_request: Optional[asyncio.Task] = None
        self._last_result: List[CompletionItem] = []
        self._completion_handlers: List[Callable] = []
        self._signature_handlers: List[Callable] = []
        
        # Configuration
        self.auto_trigger = True
        self.trigger_delay_ms = 50  # Delay before triggering after type
        self.max_results = 100
        self.fuzzy_matching = True
    
    def should_trigger(self, uri: str, line: int, character: int, text: str, triggered_char: Optional[str] = None) -> Tuple[bool, Optional[CompletionTriggerKind]]:
        """Determine if completion should be triggered."""
        doc = self.manager.get_document(uri)
        if not doc:
            return False, None
        
        language = doc.language_id.value
        
        # Check trigger characters
        if triggered_char:
            trigger_chars = self.TRIGGER_CHARS.get(language, [".", "("])
            if triggered_char in trigger_chars:
                return True, CompletionTriggerKind.TRIGGER_CHARACTER
        
        # Check for auto-trigger patterns
        if self.auto_trigger:
            # Get text before cursor
            lines = text.split("\n")
            if line < len(lines):
                line_text = lines[line][:character]
                
                # Trigger after identifier or keyword
                if re.search(r'\w+$', line_text):
                    # Don't trigger on keywords
                    keywords = self._get_keywords(language)
                    word = re.search(r'(\w+)$', line_text)
                    if word and word.group(1) not in keywords:
                        return True, CompletionTriggerKind.INVOKED
                
                # Trigger in import statements
                if re.search(r'(import|from|use)\s+\w*$', line_text):
                    return True, CompletionTriggerKind.INVOKED
                
                # Trigger after type annotations
                if re.search(r':\s*\w*$', line_text):
                    return True, CompletionTriggerKind.INVOKED
        
        return False, None
    
    @lru_cache(maxsize=100)
    def _get_keywords(self, language: str) -> set:
        """Get keywords for a language."""
        keywords = {
            "python": {"def", "class", "if", "elif", "else", "for", "while", "try", "except", "finally", "with", "as", "import", "from", "return", "yield", "raise", "pass", "break", "continue", "lambda", "and", "or", "not", "in", "is", "None", "True", "False", "global", "nonlocal", "assert", "async", "await"},
            "javascript": {"function", "var", "let", "const", "if", "else", "for", "while", "do", "switch", "case", "default", "break", "continue", "return", "throw", "try", "catch", "finally", "class", "extends", "new", "this", "super", "import", "export", "from", "as", "async", "await", "yield", "typeof", "instanceof", "in", "of", "null", "undefined", "true", "false"},
            "typescript": {"function", "var", "let", "const", "if", "else", "for", "while", "do", "switch", "case", "default", "break", "continue", "return", "throw", "try", "catch", "finally", "class", "extends", "new", "this", "super", "import", "export", "from", "as", "async", "await", "yield", "typeof", "instanceof", "in", "of", "null", "undefined", "true", "false", "type", "interface", "enum", "namespace", "module", "declare", "readonly", "keyof", "infer", "never", "unknown", "any", "void", "string", "number", "boolean", "object"},
            "go": {"break", "case", "chan", "const", "continue", "default", "defer", "else", "fallthrough", "for", "func", "go", "goto", "if", "import", "interface", "map", "package", "range", "return", "select", "struct", "switch", "type", "var", "true", "false", "nil", "iota"},
            "rust": {"as", "async", "await", "break", "const", "continue", "crate", "dyn", "else", "enum", "extern", "false", "fn", "for", "if", "impl", "in", "let", "loop", "match", "mod", "move", "mut", "pub", "ref", "return", "self", "Self", "static", "struct", "super", "trait", "true", "type", "unsafe", "use", "where", "while"},
        }
        return keywords.get(language, set())
    
    async def get_completions(self, uri: str, line: int, character: int, context: Optional[Dict] = None) -> List[CompletionItem]:
        """Get completion items for a position."""
        doc = self.manager.get_document(uri)
        if not doc:
            return []
        
        # Cancel pending request if any
        if self._pending_request and not self._pending_request.done():
            self._pending_request.cancel()
        
        # Determine trigger kind
        trigger_kind = CompletionTriggerKind.INVOKED
        trigger_char = None
        
        if context:
            trigger_kind = CompletionTriggerKind(context.get("triggerKind", 1))
            trigger_char = context.get("triggerCharacter")
        
        # Build request context
        lsp_context = {
            "triggerKind": trigger_kind.value,
        }
        if trigger_char:
            lsp_context["triggerCharacter"] = trigger_char
        
        # Request from LSP
        lsp_items = await self.manager.request_completion(uri, line, character, lsp_context)
        
        # Get snippets
        snippets = self.snippet_manager.get_snippets(doc.language_id.value)
        
        # Get text before cursor for filtering
        lines = doc.text.split("\n")
        prefix = ""
        if line < len(lines):
            line_text = lines[line][:character]
            match = re.search(r'(\w+)$', line_text)
            if match:
                prefix = match.group(1).lower()
        
        # Combine and filter results
        items = []
        
        # Add LSP items
        for item in lsp_items:
            completion = CompletionItem.from_lsp(item)
            completion.source = "lsp"
            items.append(completion)
        
        # Add snippets that match prefix
        if prefix:
            for snippet in snippets:
                if snippet.prefix.lower().startswith(prefix):
                    items.append(CompletionItem(
                        label=snippet.prefix,
                        kind=CompletionItemKind.SNIPPET,
                        detail=snippet.description,
                        documentation=f"```\n{snippet.body}\n```",
                        insert_text=snippet.expand(),
                        insert_text_format=InsertTextFormat.SNIPPET,
                        source="snippet"
                    ))
        
        # Score and sort
        items = self._score_and_sort(items, prefix)
        
        # Limit results
        self._last_result = items[:self.max_results]
        
        return self._last_result
    
    def _score_and_sort(self, items: List[CompletionItem], prefix: str) -> List[CompletionItem]:
        """Score and sort completion items."""
        if not prefix:
            return items
        
        scored = []
        for item in items:
            score = self._calculate_score(item, prefix)
            item.score = score
            scored.append(item)
        
        # Sort by score (descending), then by sort_text, then by label
        return sorted(scored, key=lambda x: (-x.score, x.sort_text or "", x.label))
    
    def _calculate_score(self, item: CompletionItem, prefix: str) -> float:
        """Calculate relevance score for an item."""
        score = 0.0
        label = item.label.lower()
        prefix = prefix.lower()
        
        # Exact prefix match
        if label.startswith(prefix):
            score += 100
        
        # Word boundary match
        elif self.fuzzy_matching:
            # Fuzzy match score
            idx = 0
            matched = True
            for char in prefix:
                idx = label.find(char, idx)
                if idx == -1:
                    matched = False
                    break
                idx += 1
                score += 10  # Each matched character
            
            if not matched:
                score = 0
            else:
                # Bonus for consecutive matches
                score += 20
        
        # Boost for certain kinds
        if item.kind == CompletionItemKind.FUNCTION:
            score += 5
        elif item.kind == CompletionItemKind.CLASS:
            score += 3
        elif item.kind == CompletionItemKind.VARIABLE:
            score += 2
        
        # Boost for snippets
        if item.kind == CompletionItemKind.SNIPPET:
            score += 8
        
        # Preselect boost
        if item.preselect:
            score += 50
        
        # Penalty for deprecated
        if item.deprecated:
            score -= 20
        
        return score
    
    async def resolve_completion(self, item: CompletionItem) -> CompletionItem:
        """Resolve additional information for a completion item."""
        doc = self.manager.get_document(item.data.get("uri", ""))
        if not doc:
            return item
        
        client = self.manager.get_client(doc.language_id)
        if not client or not client.initialized:
            return item
        
        try:
            result = await client.send_request("completionItem/resolve", {
                "label": item.label,
                "kind": item.kind.value,
                "data": item.data
            })
            
            if result:
                item.documentation = result.get("documentation", item.documentation)
                item.detail = result.get("detail", item.detail)
                item.insert_text = result.get("insertText", item.insert_text)
        except Exception as e:
            logger.debug(f"Failed to resolve completion: {e}")
        
        return item
    
    async def get_signature_help(self, uri: str, line: int, character: int) -> Optional[SignatureHelp]:
        """Get signature help for a position."""
        result = await self.manager.request_signature_help(uri, line, character)
        return SignatureHelp.from_lsp(result)
    
    def format_signature(self, sig: SignatureInformation, active_param: int = -1) -> str:
        """Format a signature for display."""
        if active_param < 0:
            active_param = sig.active_parameter
        
        label = sig.label
        
        # Highlight active parameter
        if sig.parameters and 0 <= active_param < len(sig.parameters):
            param = sig.parameters[active_param]
            param_label = param.get("label", "")
            
            if isinstance(param_label, list) and len(param_label) == 2:
                # Label is [start, end] indices
                start, end = param_label
                label = label[:start] + f"**{label[start:end]}**" + label[end:]
            elif isinstance(param_label, str):
                # Label is the parameter text
                label = label.replace(param_label, f"**{param_label}**")
        
        return label
    
    def format_documentation(self, item: CompletionItem) -> str:
        """Format documentation for display."""
        parts = []
        
        if item.detail:
            parts.append(f"**{item.detail}**")
        
        if item.documentation:
            parts.append(item.documentation)
        
        return "\n\n".join(parts) if parts else ""
    
    def expand_snippet(self, snippet: Snippet, variables: Optional[Dict[str, str]] = None) -> str:
        """Expand a snippet template."""
        return snippet.expand(variables)
    
    def on_completions_ready(self, handler: Callable) -> None:
        """Register handler for completion results."""
        self._completion_handlers.append(handler)
    
    def on_signature_help_ready(self, handler: Callable) -> None:
        """Register handler for signature help."""
        self._signature_handlers.append(handler)


# Test module
if __name__ == "__main__":
    import sys
    
    async def test_completion():
        """Test completion provider."""
        print("Testing Completion Provider...")
        
        # Create manager
        manager = LSPManager("/tmp")
        
        # Create provider
        provider = CompletionProvider(manager)
        
        # Test trigger detection
        print("\nTesting trigger detection...")
        should, kind = provider.should_trigger("test.py", 0, 5, "hello", ".")
        print(f"Should trigger after dot: {should}, kind: {kind}")
        
        should, kind = provider.should_trigger("test.py", 0, 5, "os.", ".")
        print(f"Should trigger after 'os.': {should}, kind: {kind}")
        
        # Test snippets
        print("\nTesting snippets...")
        snippet_mgr = SnippetManager()
        
        py_snippets = snippet_mgr.get_snippets("python")
        print(f"Python snippets: {len(py_snippets)}")
        
        def_snippet = snippet_mgr.find_snippet("python", "def")
        if def_snippet:
            print(f"def snippet: {def_snippet.body}")
            expanded = def_snippet.expand({"name": "hello", "params": "name", "docstring": "Say hello", "pass": "print(f'Hello {name}')"})
            print(f"Expanded:\n{expanded}")
        
        # Test scoring
        print("\nTesting scoring...")
        items = [
            CompletionItem(label="print", kind=CompletionItemKind.FUNCTION),
            CompletionItem(label="printf", kind=CompletionItemKind.FUNCTION),
            CompletionItem(label="process", kind=CompletionItemKind.VARIABLE),
            CompletionItem(label="parsed", kind=CompletionItemKind.VARIABLE),
        ]
        
        scored = provider._score_and_sort(items, "pr")
        for item in scored:
            print(f"  {item.label}: score={item.score}")
    
    asyncio.run(test_completion())
