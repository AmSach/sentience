"""
Refactor Engine Skill
Code refactoring and transformation.
"""

import os
import re
import ast
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from textwrap import dedent

METADATA = {
    "name": "refactor-engine",
    "description": "Refactor code: rename, extract, inline, simplify, and transform",
    "category": "development",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["refactor code", "rename variable", "extract function", "simplify code"],
    "dependencies": [],
    "tags": ["refactoring", "transformation", "code-quality"]
}

SKILL_NAME = "refactor-engine"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "development"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class RefactoringResult:
    success: bool
    original: str
    refactored: str
    changes: List[Dict[str, Any]]
    message: str


class PythonRefactorer:
    """Refactoring operations for Python code."""
    
    def __init__(self):
        self.changes = []
    
    def rename_variable(self, code: str, old_name: str, new_name: str) -> RefactoringResult:
        """Rename a variable throughout the code."""
        self.changes = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return RefactoringResult(False, code, code, [], str(e))
        
        # Check if old_name is valid identifier
        if not old_name.isidentifier() or not new_name.isidentifier():
            return RefactoringResult(False, code, code, [], "Invalid identifier name")
        
        # Find all occurrences
        lines = code.split('\n')
        new_lines = []
        
        for i, line in enumerate(lines, 1):
            new_line = self._rename_in_line(line, old_name, new_name)
            if new_line != line:
                self.changes.append({
                    "type": "rename",
                    "line": i,
                    "old": old_name,
                    "new": new_name
                })
            new_lines.append(new_line)
        
        return RefactoringResult(
            True, code, '\n'.join(new_lines), self.changes,
            f"Renamed {old_name} to {new_name} ({len(self.changes)} occurrences)"
        )
    
    def _rename_in_line(self, line: str, old_name: str, new_name: str) -> str:
        """Rename identifier in a line, preserving strings/comments."""
        # Pattern to match identifier not in strings
        result = []
        in_string = None
        current = ""
        
        i = 0
        while i < len(line):
            char = line[i]
            
            # Handle string boundaries
            if char in '"\'':
                if in_string is None:
                    in_string = char
                elif in_string == char and (i == 0 or line[i-1] != '\\'):
                    in_string = None
                current += char
            elif in_string:
                current += char
            else:
                # Not in string - check for identifier
                if char.isalnum() or char == '_':
                    # Collect full identifier
                    j = i
                    while j < len(line) and (line[j].isalnum() or line[j] == '_'):
                        j += 1
                    identifier = line[i:j]
                    
                    if identifier == old_name:
                        result.append(current)
                        current = new_name
                        i = j - 1
                    else:
                        current += identifier
                        i = j - 1
                else:
                    current += char
            
            i += 1
        
        result.append(current)
        return ''.join(result)
    
    def extract_function(self, code: str, start_line: int, end_line: int, 
                         func_name: str) -> RefactoringResult:
        """Extract code block into a new function."""
        self.changes = []
        lines = code.split('\n')
        
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return RefactoringResult(False, code, code, [], "Invalid line range")
        
        # Extract the code block
        extracted = '\n'.join(lines[start_line-1:end_line])
        
        # Find variables used in extracted code
        used_vars = self._find_variables(extracted)
        
        # Find variables defined in extracted code
        defined_vars = self._find_assignments(extracted)
        
        # Parameters are used but not defined in extracted code
        params = [v for v in used_vars if v not in defined_vars]
        
        # Create new function
        param_str = ', '.join(params) if params else ""
        new_func = dedent(f'''
        def {func_name}({param_str}):
            {extracted.replace(chr(10), chr(10) + "    ")}
        ''').strip()
        
        # Create function call
        call = f"{func_name}({param_str})"
        
        # Replace extracted code with call
        new_lines = lines[:start_line-1] + [call] + lines[end_line:]
        
        # Add function definition at top (after imports)
        insert_pos = self._find_insert_position(new_lines)
        new_lines.insert(insert_pos, new_func)
        
        self.changes = [
            {"type": "extract", "function": func_name, "params": params},
            {"type": "insert", "line": insert_pos + 1}
        ]
        
        return RefactoringResult(
            True, code, '\n'.join(new_lines), self.changes,
            f"Extracted function {func_name} with params: {params}"
        )
    
    def _find_variables(self, code: str) -> List[str]:
        """Find all variables used in code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        variables = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                variables.add(node.id)
        return list(variables)
    
    def _find_assignments(self, code: str) -> List[str]:
        """Find all variables assigned in code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        assignments = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.add(target.id)
        return list(assignments)
    
    def _find_insert_position(self, lines: List[str]) -> int:
        """Find position to insert new function (after imports)."""
        for i, line in enumerate(lines):
            if line.strip().startswith(('from ', 'import ')):
                continue
            if line.strip() and not line.strip().startswith('#'):
                return i
        return 0
    
    def inline_variable(self, code: str, var_name: str) -> RefactoringResult:
        """Inline a variable (replace uses with its value)."""
        self.changes = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RefactoringResult(False, code, code, [], "Parse error")
        
        # Find the variable's value
        var_value = None
        var_line = None
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == var_name:
                        var_value = ast.unparse(node.value) if hasattr(ast, 'unparse') else "..."
                        var_line = node.lineno
                        break
        
        if var_value is None:
            return RefactoringResult(False, code, code, [], f"Variable {var_name} not found")
        
        # Replace uses and remove definition
        lines = code.split('\n')
        new_lines = []
        
        for i, line in enumerate(lines, 1):
            if i == var_line:
                continue  # Remove the definition line
            
            new_line = self._rename_in_line(line, var_name, var_value)
            if new_line != line:
                self.changes.append({"type": "inline", "line": i})
            new_lines.append(new_line)
        
        return RefactoringResult(
            True, code, '\n'.join(new_lines), self.changes,
            f"Inlined variable {var_name}"
        )
    
    def simplify_if(self, code: str) -> RefactoringResult:
        """Simplify if statements."""
        self.changes = []
        
        # Replace if True/False patterns
        patterns = [
            (r'if True:\s*\n\s+(.+)\s*\n\s*else:.*', r'\1'),
            (r'if False:\s*\n\s*else:\s*\n\s+(.+)', r'\1'),
            (r'if not False:\s*\n\s+(.+)', r'\1'),
            (r'if not True:\s*\n\s*else:\s*\n\s+(.+)', r'\1'),
        ]
        
        new_code = code
        for pattern, replacement in patterns:
            new_code = re.sub(pattern, replacement, new_code, flags=re.MULTILINE)
        
        if new_code != code:
            self.changes.append({"type": "simplify", "pattern": "if-statement"})
        
        return RefactoringResult(
            True, code, new_code, self.changes,
            f"Simplified {len(self.changes)} if statements"
        )
    
    def convert_to_fstring(self, code: str) -> RefactoringResult:
        """Convert .format() and % formatting to f-strings."""
        self.changes = []
        lines = code.split('\n')
        new_lines = []
        
        for i, line in enumerate(lines, 1):
            new_line = line
            
            # Convert .format() calls
            format_match = re.search(r'(["\'])(.*?)\1\.format\(([^)]+)\)', line)
            if format_match:
                quote = format_match.group(1)
                string = format_match.group(2)
                args = format_match.group(3)
                
                # Replace {} placeholders with {arg}
                if '{}' in string and ',' not in args:
                    arg_name = args.strip()
                    new_string = string.replace('{', '{{').replace('}', '}}')
                    new_string = new_string.replace('{{}}', f'{{{arg_name}}}')
                    new_line = line.replace(format_match.group(0), f'f{quote}{new_string}{quote}')
                    self.changes.append({"type": "fstring", "line": i})
            
            # Convert % formatting
            percent_match = re.search(r'(["\'])(.*?)\1\s*%\s*\(([^)]+)\)', line)
            if percent_match:
                # Skip for now (complex transformation)
                pass
            
            new_lines.append(new_line)
        
        return RefactoringResult(
            True, code, '\n'.join(new_lines), self.changes,
            f"Converted {len(self.changes)} strings to f-strings"
        )
    
    def add_type_hints(self, code: str) -> RefactoringResult:
        """Add basic type hints to function parameters."""
        self.changes = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RefactoringResult(False, code, code, [], "Parse error")
        
        lines = code.split('\n')
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip if already has type hints
                if any(arg.annotation for arg in node.args.args if arg.arg != 'self'):
                    continue
                
                # Add type hints based on defaults or patterns
                for arg in node.args.args:
                    if arg.arg == 'self':
                        continue
                    
                    # Infer type from name patterns
                    inferred_type = self._infer_type(arg.arg)
                    if inferred_type:
                        line_idx = node.lineno - 1
                        line = lines[line_idx]
                        
                        # Add type hint
                        pattern = rf'\b{arg.arg}\b(?!\s*:)'
                        replacement = f'{arg.arg}: {inferred_type}'
                        new_line = re.sub(pattern, replacement, line)
                        
                        if new_line != line:
                            lines[line_idx] = new_line
                            self.changes.append({
                                "type": "type_hint",
                                "param": arg.arg,
                                "hint": inferred_type,
                                "line": node.lineno
                            })
        
        return RefactoringResult(
            True, code, '\n'.join(lines), self.changes,
            f"Added {len(self.changes)} type hints"
        )
    
    def _infer_type(self, name: str) -> Optional[str]:
        """Infer type from variable name."""
        patterns = {
            'id': 'int',
            'count': 'int',
            'num': 'int',
            'index': 'int',
            'size': 'int',
            'name': 'str',
            'path': 'str',
            'file': 'str',
            'url': 'str',
            'text': 'str',
            'message': 'str',
            'enabled': 'bool',
            'is_': 'bool',
            'has_': 'bool',
            'items': 'list',
            'list': 'list',
            'data': 'dict',
            'config': 'dict',
            'options': 'dict',
        }
        
        name_lower = name.lower()
        for pattern, type_hint in patterns.items():
            if pattern in name_lower:
                return type_hint
        
        return None


def execute(
    code: str = None,
    filepath: str = None,
    operation: str = "rename",
    old_name: str = None,
    new_name: str = None,
    start_line: int = None,
    end_line: int = None,
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Refactor code with various operations.
    
    Args:
        code: Source code string
        filepath: Path to source file
        operation: Refactoring operation (rename/extract/inline/simplify/fstring/typehints)
        old_name: Old name (for rename)
        new_name: New name (for rename/extract)
        start_line: Start line (for extract)
        end_line: End line (for extract)
        output_file: Output file path
    
    Returns:
        Refactoring result
    """
    if filepath:
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
    elif not code:
        return {"success": False, "error": "Either filepath or code must be provided"}
    
    refactorer = PythonRefactorer()
    
    if operation == "rename":
        if not old_name or not new_name:
            return {"success": False, "error": "old_name and new_name required for rename"}
        result = refactorer.rename_variable(code, old_name, new_name)
    
    elif operation == "extract":
        if not all([start_line, end_line, new_name]):
            return {"success": False, "error": "start_line, end_line, and new_name required for extract"}
        result = refactorer.extract_function(code, start_line, end_line, new_name)
    
    elif operation == "inline":
        if not old_name:
            return {"success": False, "error": "old_name (variable name) required for inline"}
        result = refactorer.inline_variable(code, old_name)
    
    elif operation == "simplify":
        result = refactorer.simplify_if(code)
    
    elif operation == "fstring":
        result = refactorer.convert_to_fstring(code)
    
    elif operation == "typehints":
        result = refactorer.add_type_hints(code)
    
    else:
        return {"success": False, "error": f"Unknown operation: {operation}"}
    
    if output_file and result.success:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result.refactored)
    
    return {
        "success": result.success,
        "original": result.original,
        "refactored": result.refactored,
        "changes": result.changes,
        "message": result.message,
        "output_file": output_file
    }
