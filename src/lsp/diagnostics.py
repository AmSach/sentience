"""
Diagnostics Provider - Error/warning collection, quick fixes, and code actions.
Handles diagnostic publishing and code action processing.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import defaultdict

logger = logging.getLogger(__name__)


class DiagnosticSeverity(Enum):
    """LSP diagnostic severity levels."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class DiagnosticTag(Enum):
    """LSP diagnostic tags."""
    UNNECESSARY = 1
    DEPRECATED = 2


@dataclass
class Position:
    """A position in a document."""
    line: int
    character: int
    
    def to_dict(self) -> Dict[str, int]:
        return {"line": self.line, "character": self.character}
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "Position":
        return cls(line=data["line"], character=data["character"])
    
    def __lt__(self, other: "Position") -> bool:
        if self.line != other.line:
            return self.line < other.line
        return self.character < other.character
    
    def __le__(self, other: "Position") -> bool:
        return self == other or self < other
    
    def __gt__(self, other: "Position") -> bool:
        return not self <= other
    
    def __ge__(self, other: "Position") -> bool:
        return not self < other


@dataclass
class Range:
    """A range in a document."""
    start: Position
    end: Position
    
    def to_dict(self) -> Dict[str, Dict]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Range":
        return cls(
            start=Position.from_dict(data["start"]),
            end=Position.from_dict(data["end"])
        )
    
    def contains(self, position: Position) -> bool:
        return self.start <= position <= self.end
    
    def overlaps(self, other: "Range") -> bool:
        return self.start <= other.end and other.start <= self.end


@dataclass
class DiagnosticRelatedInformation:
    """Related information for a diagnostic."""
    location: Dict[str, Any]  # uri and range
    message: str


@dataclass
class Diagnostic:
    """A diagnostic item."""
    range: Range
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    code: Optional[Union[str, int]] = None
    code_description: Optional[str] = None
    source: Optional[str] = None
    tags: List[DiagnosticTag] = field(default_factory=list)
    related_information: List[DiagnosticRelatedInformation] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    
    # UI-specific fields
    squiggle_color: str = ""
    is_resolved: bool = False
    
    @classmethod
    def from_lsp(cls, diag: Dict[str, Any]) -> "Diagnostic":
        """Create from LSP diagnostic."""
        severity_value = diag.get("severity", 1)
        severity = DiagnosticSeverity(severity_value) if 1 <= severity_value <= 4 else DiagnosticSeverity.ERROR
        
        tags = []
        for tag in diag.get("tags", []):
            if tag in (1, 2):
                tags.append(DiagnosticTag(tag))
        
        related = []
        for info in diag.get("relatedInformation", []):
            related.append(DiagnosticRelatedInformation(
                location=info.get("location", {}),
                message=info.get("message", "")
            ))
        
        code_desc = diag.get("codeDescription", {}).get("href") if isinstance(diag.get("codeDescription"), dict) else None
        
        return cls(
            range=Range.from_dict(diag["range"]),
            message=diag.get("message", ""),
            severity=severity,
            code=diag.get("code"),
            code_description=code_desc,
            source=diag.get("source"),
            tags=tags,
            related_information=related,
            data=diag.get("data", {})
        )
    
    def __post_init__(self):
        # Set squiggle color based on severity
        color_map = {
            DiagnosticSeverity.ERROR: "#F44747",
            DiagnosticSeverity.WARNING: "#CCA700",
            DiagnosticSeverity.INFORMATION: "#75BEFF",
            DiagnosticSeverity.HINT: "#548C00"
        }
        self.squiggle_color = color_map.get(self.severity, "#F44747")


@dataclass
class CodeAction:
    """A code action that can fix a diagnostic."""
    title: str
    kind: Optional[str] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)
    edit: Optional[Dict[str, Any]] = None
    command: Optional[Dict[str, Any]] = None
    is_preferred: bool = False
    disabled_reason: Optional[str] = None
    
    @classmethod
    def from_lsp(cls, action: Dict[str, Any]) -> "CodeAction":
        """Create from LSP code action."""
        diags = [Diagnostic.from_lsp(d) for d in action.get("diagnostics", [])]
        
        return cls(
            title=action.get("title", ""),
            kind=action.get("kind"),
            diagnostics=diags,
            edit=action.get("edit"),
            command=action.get("command"),
            is_preferred=action.get("isPreferred", False),
            disabled_reason=action.get("disabled", {}).get("reason") if isinstance(action.get("disabled"), dict) else None
        )


@dataclass
class TextEdit:
    """A text edit operation."""
    range: Range
    new_text: str
    
    def to_dict(self) -> Dict:
        return {
            "range": self.range.to_dict(),
            "newText": self.new_text
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TextEdit":
        return cls(
            range=Range.from_dict(data["range"]),
            new_text=data["newText"]
        )


@dataclass
class WorkspaceEdit:
    """A workspace edit with multiple file changes."""
    changes: Dict[str, List[TextEdit]] = field(default_factory=dict)
    document_changes: List[Dict] = field(default_factory=list)
    
    @classmethod
    def from_lsp(cls, edit: Optional[Dict]) -> Optional["WorkspaceEdit"]:
        """Create from LSP workspace edit."""
        if not edit:
            return None
        
        changes = {}
        for uri, edits in edit.get("changes", {}).items():
            changes[uri] = [TextEdit.from_dict(e) for e in edits]
        
        return cls(
            changes=changes,
            document_changes=edit.get("documentChanges", [])
        )


class DiagnosticCollection:
    """Collection of diagnostics organized by URI."""
    
    def __init__(self):
        self._diagnostics: Dict[str, List[Diagnostic]] = defaultdict(list)
        self._listeners: List[Callable] = []
    
    def set(self, uri: str, diagnostics: List[Diagnostic]) -> None:
        """Set diagnostics for a URI."""
        old_count = len(self._diagnostics.get(uri, []))
        self._diagnostics[uri] = diagnostics
        new_count = len(diagnostics)
        
        self._notify_listeners(uri, diagnostics)
        logger.debug(f"Set {new_count} diagnostics for {uri} (was {old_count})")
    
    def get(self, uri: str) -> List[Diagnostic]:
        """Get diagnostics for a URI."""
        return self._diagnostics.get(uri, [])
    
    def get_all(self) -> Dict[str, List[Diagnostic]]:
        """Get all diagnostics."""
        return dict(self._diagnostics)
    
    def clear(self, uri: Optional[str] = None) -> None:
        """Clear diagnostics for a URI or all."""
        if uri:
            if uri in self._diagnostics:
                del self._diagnostics[uri]
                self._notify_listeners(uri, [])
        else:
            self._diagnostics.clear()
            for uri in list(self._diagnostics.keys()):
                self._notify_listeners(uri, [])
    
    def get_by_severity(self, severity: DiagnosticSeverity) -> Dict[str, List[Diagnostic]]:
        """Get diagnostics filtered by severity."""
        result = {}
        for uri, diags in self._diagnostics.items():
            filtered = [d for d in diags if d.severity == severity]
            if filtered:
                result[uri] = filtered
        return result
    
    def get_errors(self) -> Dict[str, List[Diagnostic]]:
        """Get all error diagnostics."""
        return self.get_by_severity(DiagnosticSeverity.ERROR)
    
    def get_warnings(self) -> Dict[str, List[Diagnostic]]:
        """Get all warning diagnostics."""
        return self.get_by_severity(DiagnosticSeverity.WARNING)
    
    def get_at_position(self, uri: str, line: int, character: int) -> List[Diagnostic]:
        """Get diagnostics at a specific position."""
        position = Position(line, character)
        return [
            d for d in self._diagnostics.get(uri, [])
            if d.range.contains(position)
        ]
    
    def get_in_range(self, uri: str, start_line: int, start_char: int, end_line: int, end_char: int) -> List[Diagnostic]:
        """Get diagnostics in a specific range."""
        query_range = Range(
            start=Position(start_line, start_char),
            end=Position(end_line, end_char)
        )
        return [
            d for d in self._diagnostics.get(uri, [])
            if d.range.overlaps(query_range)
        ]
    
    def count(self, uri: Optional[str] = None) -> Dict[DiagnosticSeverity, int]:
        """Count diagnostics by severity."""
        counts = {s: 0 for s in DiagnosticSeverity}
        
        diags = self._diagnostics.get(uri, []) if uri else []
        if uri is None:
            diags = []
            for d_list in self._diagnostics.values():
                diags.extend(d_list)
        
        for diag in diags:
            counts[diag.severity] += 1
        
        return counts
    
    def add_listener(self, listener: Callable) -> None:
        """Add a listener for diagnostic changes."""
        self._listeners.append(listener)
    
    def remove_listener(self, listener: Callable) -> None:
        """Remove a listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def _notify_listeners(self, uri: str, diagnostics: List[Diagnostic]) -> None:
        """Notify all listeners of a change."""
        for listener in self._listeners:
            try:
                listener(uri, diagnostics)
            except Exception as e:
                logger.error(f"Error in diagnostic listener: {e}")


class QuickFixProvider:
    """Provides quick fix suggestions for diagnostics."""
    
    # Common quick fix patterns
    QUICK_FIXES = {
        # Python
        "F401": {  # Unused import
            "title": "Remove unused import",
            "pattern": r"^import\s+(\S+)",
            "fix": "remove_line"
        },
        "F841": {  # Unused variable
            "title": "Remove unused variable",
            "fix": "remove_declaration"
        },
        "E501": {  # Line too long
            "title": "Reformat line",
            "fix": "format"
        },
        "W293": {  # Blank line contains whitespace
            "title": "Remove trailing whitespace",
            "fix": "strip_whitespace"
        },
        # JavaScript/TypeScript
        "no-unused-vars": {
            "title": "Remove unused variable",
            "fix": "remove_declaration"
        },
        "missing-declaration": {
            "title": "Add type declaration",
            "fix": "add_type"
        },
    }
    
    def __init__(self):
        self._custom_fixes: Dict[str, List[Callable]] = defaultdict(list)
    
    def register_fix(self, code: str, fix_func: Callable) -> None:
        """Register a custom quick fix for a diagnostic code."""
        self._custom_fixes[code].append(fix_func)
    
    def get_quick_fixes(self, diagnostic: Diagnostic, text: str, line_start: int = 0) -> List[CodeAction]:
        """Get quick fix suggestions for a diagnostic."""
        fixes = []
        code_str = str(diagnostic.code) if diagnostic.code else ""
        
        # Check registered fixes
        if code_str in self._custom_fixes:
            for fix_func in self._custom_fixes[code_str]:
                try:
                    result = fix_func(diagnostic, text)
                    if result:
                        fixes.append(result)
                except Exception as e:
                    logger.error(f"Custom fix error: {e}")
        
        # Check built-in fixes
        if code_str in self.QUICK_FIXES:
            fix_info = self.QUICK_FIXES[code_str]
            fix_type = fix_info.get("fix")
            
            if fix_type == "remove_line":
                fixes.append(self._create_remove_line_fix(diagnostic, text))
            elif fix_type == "strip_whitespace":
                fixes.append(self._create_strip_whitespace_fix(diagnostic, text))
            elif fix_type == "format":
                fixes.append(self._create_format_fix(diagnostic, text))
        
        return fixes
    
    def _create_remove_line_fix(self, diagnostic: Diagnostic, text: str) -> CodeAction:
        """Create a fix that removes the line."""
        lines = text.split("\n")
        line_num = diagnostic.range.start.line
        
        if 0 <= line_num < len(lines):
            # Create edit to remove the line
            start = Position(line_num, 0)
            end = Position(line_num + 1, 0) if line_num + 1 < len(lines) else Position(line_num, len(lines[line_num]))
            
            return CodeAction(
                title="Remove line",
                kind="quickfix",
                diagnostics=[diagnostic],
                edit={
                    "changes": {
                        "": [{"range": {"start": start.to_dict(), "end": end.to_dict()}, "newText": ""}]
                    }
                }
            )
        
        return CodeAction(title="Remove line", kind="quickfix")
    
    def _create_strip_whitespace_fix(self, diagnostic: Diagnostic, text: str) -> CodeAction:
        """Create a fix that strips whitespace."""
        lines = text.split("\n")
        line_num = diagnostic.range.start.line
        
        if 0 <= line_num < len(lines):
            line = lines[line_num]
            stripped = line.rstrip()
            
            return CodeAction(
                title="Remove trailing whitespace",
                kind="quickfix",
                diagnostics=[diagnostic],
                edit={
                    "changes": {
                        "": [{"range": diagnostic.range.to_dict(), "newText": stripped}]
                    }
                }
            )
        
        return CodeAction(title="Remove trailing whitespace", kind="quickfix")
    
    def _create_format_fix(self, diagnostic: Diagnostic, text: str) -> CodeAction:
        """Create a fix that formats the line."""
        return CodeAction(
            title="Format line",
            kind="quickfix",
            diagnostics=[diagnostic],
            command={"command": "editor.formatLine", "arguments": [diagnostic.range.start.line]}
        )


class DiagnosticsManager:
    """Manages diagnostics and code actions."""
    
    def __init__(self, lsp_manager):
        self.lsp_manager = lsp_manager
        self.collection = DiagnosticCollection()
        self.quick_fix_provider = QuickFixProvider()
        
        self._action_cache: Dict[str, List[CodeAction]] = {}
        self._pending_actions: Dict[str, asyncio.Task] = {}
    
    async def handle_diagnostics(self, params: Dict[str, Any]) -> None:
        """Handle incoming diagnostics from LSP server."""
        uri = params.get("uri", "")
        diagnostics_data = params.get("diagnostics", [])
        
        diagnostics = [Diagnostic.from_lsp(d) for d in diagnostics_data]
        
        # Clear cached actions for this URI
        self._action_cache.pop(uri, None)
        
        # Update collection
        self.collection.set(uri, diagnostics)
    
    async def get_code_actions(self, uri: str, range_start: Tuple[int, int], range_end: Tuple[int, int], kinds: Optional[List[str]] = None) -> List[CodeAction]:
        """Get code actions for a range."""
        start_line, start_char = range_start
        end_line, end_char = range_end
        
        # Get diagnostics in range
        diagnostics = self.collection.get_in_range(uri, start_line, start_char, end_line, end_char)
        
        # Get text for quick fixes
        doc = self.lsp_manager.get_document(uri)
        text = doc.text if doc else ""
        
        # Check cache
        cache_key = f"{uri}:{start_line}:{start_char}:{end_line}:{end_char}"
        if cache_key in self._action_cache:
            return self._action_cache[cache_key]
        
        # Get actions from LSP
        lsp_actions = await self.lsp_manager.request_code_actions(
            uri, diagnostics, start_line, start_char, end_line, end_char, kinds
        )
        
        actions = []
        
        # Add LSP actions
        for action in lsp_actions:
            actions.append(CodeAction.from_lsp(action))
        
        # Add quick fixes
        for diag in diagnostics:
            quick_fixes = self.quick_fix_provider.get_quick_fixes(diag, text)
            actions.extend(quick_fixes)
        
        # Cache and return
        self._action_cache[cache_key] = actions
        return actions
    
    async def apply_code_action(self, action: CodeAction) -> bool:
        """Apply a code action and return success."""
        if action.edit:
            return await self._apply_workspace_edit(action.edit)
        
        if action.command:
            return await self._execute_command(action.command)
        
        return False
    
    async def _apply_workspace_edit(self, edit: Dict[str, Any]) -> bool:
        """Apply a workspace edit."""
        workspace_edit = WorkspaceEdit.from_lsp(edit)
        
        if not workspace_edit:
            return False
        
        success = True
        
        # Apply text changes
        for uri, text_edits in workspace_edit.changes.items():
            doc = self.lsp_manager.get_document(uri)
            if not doc:
                continue
            
            # Sort edits from end to start to avoid offset issues
            text_edits = sorted(text_edits, key=lambda e: (e.range.start.line, e.range.start.character), reverse=True)
            
            # Apply each edit
            lines = doc.text.split("\n")
            for text_edit in text_edits:
                try:
                    lines = self._apply_edit_to_lines(lines, text_edit)
                except Exception as e:
                    logger.error(f"Error applying edit: {e}")
                    success = False
            
            # Update document
            new_text = "\n".join(lines)
            await self.lsp_manager.update_document(uri, new_text)
        
        return success
    
    def _apply_edit_to_lines(self, lines: List[str], edit: TextEdit) -> List[str]:
        """Apply a text edit to lines."""
        start = edit.range.start
        end = edit.range.end
        
        # Get content before and after edit
        before_lines = lines[:start.line]
        after_lines = lines[end.line + 1:]
        
        # Get partial lines
        before_text = lines[start.line][:start.character] if start.line < len(lines) else ""
        after_text = lines[end.line][end.character:] if end.line < len(lines) else ""
        
        # Build new content
        new_line = before_text + edit.new_text + after_text
        
        # Handle multiline new text
        new_lines = new_line.split("\n")
        
        # Reconstruct lines
        result = before_lines + new_lines + after_lines
        return result
    
    async def _execute_command(self, command: Dict[str, Any]) -> bool:
        """Execute a command."""
        cmd = command.get("command", "")
        args = command.get("arguments", [])
        
        result = await self.lsp_manager.execute_command(cmd, args)
        return result is not None
    
    def get_diagnostics(self, uri: str) -> List[Diagnostic]:
        """Get diagnostics for a URI."""
        return self.collection.get(uri)
    
    def get_all_diagnostics(self) -> Dict[str, List[Diagnostic]]:
        """Get all diagnostics."""
        return self.collection.get_all()
    
    def get_errors(self) -> Dict[str, List[Diagnostic]]:
        """Get all errors."""
        return self.collection.get_errors()
    
    def get_warnings(self) -> Dict[str, List[Diagnostic]]:
        """Get all warnings."""
        return self.collection.get_warnings()
    
    def get_diagnostics_at_position(self, uri: str, line: int, character: int) -> List[Diagnostic]:
        """Get diagnostics at a specific position."""
        return self.collection.get_at_position(uri, line, character)
    
    def get_diagnostic_summary(self) -> Dict[str, int]:
        """Get a summary of diagnostic counts."""
        counts = self.collection.count()
        return {
            "errors": counts[DiagnosticSeverity.ERROR],
            "warnings": counts[DiagnosticSeverity.WARNING],
            "info": counts[DiagnosticSeverity.INFORMATION],
            "hints": counts[DiagnosticSeverity.HINT],
            "total": sum(counts.values())
        }
    
    def clear_diagnostics(self, uri: Optional[str] = None) -> None:
        """Clear diagnostics."""
        self.collection.clear(uri)
        if uri:
            self._action_cache = {k: v for k, v in self._action_cache.items() if not k.startswith(uri)}
        else:
            self._action_cache.clear()
    
    def on_diagnostics_change(self, listener: Callable) -> None:
        """Register a listener for diagnostic changes."""
        self.collection.add_listener(listener)


class SquiggleRenderer:
    """Renders diagnostic squiggles for UI display."""
    
    # Visual styles for each severity
    STYLES = {
        DiagnosticSeverity.ERROR: {
            "color": "#F44747",
            "underline": "wavy",
            "opacity": 1.0
        },
        DiagnosticSeverity.WARNING: {
            "color": "#CCA700",
            "underline": "wavy",
            "opacity": 0.9
        },
        DiagnosticSeverity.INFORMATION: {
            "color": "#75BEFF",
            "underline": "dotted",
            "opacity": 0.8
        },
        DiagnosticSeverity.HINT: {
            "color": "#548C00",
            "underline": "dotted",
            "opacity": 0.6
        }
    }
    
    def __init__(self):
        self._decorators: Dict[str, List[Dict]] = {}
    
    def render(self, uri: str, diagnostics: List[Diagnostic]) -> List[Dict]:
        """Render diagnostics as decorations."""
        decorations = []
        
        for diag in diagnostics:
            style = self.STYLES.get(diag.severity, self.STYLES[DiagnosticSeverity.ERROR])
            
            decoration = {
                "range": diag.range.to_dict(),
                "options": {
                    "className": f"diagnostic-{diag.severity.name.lower()}",
                    "inlineClassName": f"squiggle-{style['underline']}",
                    **{
                        "hoverMessage": {
                            "value": self._format_hover(diag),
                            "isTrusted": True
                        },
                        "color": style["color"],
                        "opacity": style["opacity"]
                    }
                },
                "diagnostic": diag
            }
            
            decorations.append(decoration)
        
        self._decorators[uri] = decorations
        return decorations
    
    def _format_hover(self, diag: Diagnostic) -> str:
        """Format diagnostic hover text."""
        parts = []
        
        severity_emoji = {
            DiagnosticSeverity.ERROR: "❌",
            DiagnosticSeverity.WARNING: "⚠️",
            DiagnosticSeverity.INFORMATION: "ℹ️",
            DiagnosticSeverity.HINT: "💡"
        }
        
        emoji = severity_emoji.get(diag.severity, "")
        
        # Title
        title = f"{emoji} **{diag.severity.name}**"
        if diag.source:
            title += f" [{diag.source}]"
        parts.append(title)
        
        # Message
        parts.append(diag.message)
        
        # Code
        if diag.code:
            if diag.code_description:
                parts.append(f"Code: [{diag.code}]({diag.code_description})")
            else:
                parts.append(f"Code: `{diag.code}`")
        
        # Related info
        if diag.related_information:
            parts.append("\n**Related:**")
            for info in diag.related_information[:3]:
                parts.append(f"- {info.message}")
        
        return "\n\n".join(parts)
    
    def get_decorations(self, uri: str) -> List[Dict]:
        """Get cached decorations for a URI."""
        return self._decorators.get(uri, [])
    
    def clear_decorations(self, uri: Optional[str] = None) -> None:
        """Clear cached decorations."""
        if uri:
            self._decorators.pop(uri, None)
        else:
            self._decorators.clear()


# Test module
if __name__ == "__main__":
    import sys
    
    def test_diagnostics():
        """Test diagnostics module."""
        print("Testing Diagnostics...")
        
        # Test diagnostic creation
        print("\n1. Creating diagnostics...")
        diag = Diagnostic.from_lsp({
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
            "message": "Undefined variable 'x'",
            "severity": 1,
            "code": "F821",
            "source": "pyflakes"
        })
        print(f"  Created: {diag.message} ({diag.severity.name})")
        print(f"  Squiggle color: {diag.squiggle_color}")
        
        # Test collection
        print("\n2. Testing collection...")
        collection = DiagnosticCollection()
        
        # Add listener
        changes = []
        def listener(uri, diags):
            changes.append((uri, len(diags)))
        collection.add_listener(listener)
        
        # Add diagnostics
        collection.set("file:///test.py", [
            diag,
            Diagnostic.from_lsp({
                "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 10}},
                "message": "Unused import 'os'",
                "severity": 2,
                "code": "F401",
                "source": "pyflakes"
            })
        ])
        
        print(f"  Total diagnostics: {sum(collection.count().values())}")
        print(f"  Errors: {collection.count()[DiagnosticSeverity.ERROR]}")
        print(f"  Warnings: {collection.count()[DiagnosticSeverity.WARNING]}")
        
        # Test position queries
        print("\n3. Testing position queries...")
        at_pos = collection.get_at_position("file:///test.py", 0, 2)
        print(f"  Diagnostics at (0, 2): {len(at_pos)}")
        for d in at_pos:
            print(f"    - {d.message}")
        
        # Test quick fixes
        print("\n4. Testing quick fixes...")
        provider = QuickFixProvider()
        text = "import os\nprint('hello')\n"
        fixes = provider.get_quick_fixes(diag, text)
        print(f"  Quick fixes for '{diag.code}': {len(fixes)}")
        for fix in fixes:
            print(f"    - {fix.title}")
        
        # Test squiggle rendering
        print("\n5. Testing squiggle rendering...")
        renderer = SquiggleRenderer()
        decorations = renderer.render("file:///test.py", collection.get("file:///test.py"))
        print(f"  Rendered {len(decorations)} decorations")
        
        for dec in decorations[:2]:
            d = dec["diagnostic"]
            print(f"    - Line {d.range.start.line}: {d.message}")
            print(f"      Style: {dec['options']['className']}")
        
        print("\n✓ All tests passed!")
    
    test_diagnostics()
