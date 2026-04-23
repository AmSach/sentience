"""
Debug Helper Skill
Debugging assistance and error analysis.
"""

import os
import re
import sys
import traceback
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

METADATA = {
    "name": "debug-helper",
    "description": "Help debug code by analyzing errors, suggesting fixes, and tracing issues",
    "category": "development",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["debug", "debug code", "fix error", "trace error", "analyze error"],
    "dependencies": [],
    "tags": ["debugging", "errors", "troubleshooting", "fix"]
}

SKILL_NAME = "debug-helper"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "development"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class ErrorInfo:
    error_type: str
    message: str
    line: int
    column: int
    file: str
    traceback: str
    suggestions: List[str]


class PythonErrorAnalyzer:
    """Analyze Python errors and suggest fixes."""
    
    # Common error patterns and their solutions
    ERROR_SOLUTIONS = {
        "NameError": {
            "patterns": [
                (r"name '(\w+)' is not defined", "Variable '{0}' is not defined. Check: spelling, scope, or if it needs to be imported.")
            ],
            "general": "Variable or function is not defined. Check spelling, imports, or scope."
        },
        "TypeError": {
            "patterns": [
                (r"'(\w+)' object is not callable", "'{0}' is not a function. Check if you meant to call something else or access an attribute."),
                (r"'(\w+)' object is not subscriptable", "Cannot use [] on {0} object. Check if the object is the expected type."),
                (r"unsupported operand type\(s\) for ([\+\-\*/]): '(\w+)' and '(\w+)'", "Cannot {0} {1} and {2}. Convert to compatible types."),
                (r"missing (\d+) required positional argument", "Function expects {0} argument(s). Check function call."),
                (r"got an unexpected keyword argument '(\w+)'", "Function doesn't accept '{0}' argument. Check spelling or function signature.")
            ],
            "general": "Type mismatch or incorrect usage. Check types and method signatures."
        },
        "AttributeError": {
            "patterns": [
                (r"'(\w+)' object has no attribute '(\w+)'", "{0} objects don't have attribute '{1}'. Check spelling or type."),
                (r"'NoneType' object has no attribute '(\w+)'", "Variable is None. Check if the previous operation returned None unexpectedly.")
            ],
            "general": "Attribute doesn't exist on the object. Check type and spelling."
        },
        "IndexError": {
            "patterns": [
                (r"list index out of range", "Index exceeds list length. Check list size before accessing."),
                (r"tuple index out of range", "Index exceeds tuple length. Check tuple size."),
                (r"string index out of range", "Index exceeds string length. Check string size.")
            ],
            "general": "Index is out of bounds. Check sequence length before accessing."
        },
        "KeyError": {
            "patterns": [
                (r"KeyError: (.+)", "Key {0} not found in dictionary. Use .get() for safe access or check key existence.")
            ],
            "general": "Key not found in dictionary. Use .get() or check existence first."
        },
        "ValueError": {
            "patterns": [
                (r"invalid literal for int\(\) with base (\d+): '(.+)'", "Cannot convert '{1}' to integer (base {0}). Check input format."),
                (r"could not convert string to float: '(.+)'", "Cannot convert '{0}' to float. Check for invalid characters."),
                (r"too many values to unpack \(expected (\d+)\)", "Expected {0} values to unpack. Check sequence length."),
                (r"not enough values to unpack \(expected (\d+), got (\d+)\)", "Expected {0} values but got {1}. Check sequence length.")
            ],
            "general": "Invalid value for operation. Check input format and expected values."
        },
        "IndentationError": {
            "patterns": [
                (r"expected an indented block", "Code block after ':' needs indentation."),
                (r"unindent does not match any outer indentation level", "Indentation doesn't match. Ensure consistent use of tabs/spaces."),
                (r"unexpected indent", "Unexpected indentation. Remove or check if it belongs in a block.")
            ],
            "general": "Indentation is incorrect. Use consistent spaces or tabs (prefer 4 spaces)."
        },
        "SyntaxError": {
            "patterns": [
                (r"invalid syntax", "Syntax error. Check for: missing colons, brackets, operators, or invalid characters."),
                (r"unexpected EOF while parsing", "Missing closing bracket or parenthesis. Check for unbalanced brackets."),
                (r"EOL while scanning string literal", "String not closed. Add matching quote at end of string."),
                (r"Missing parentheses in call to '(\w+)'", "'{0}' is a built-in function. Add parentheses: {0}()")
            ],
            "general": "Python syntax is incorrect. Check for missing punctuation or invalid syntax."
        },
        "ImportError": {
            "patterns": [
                (r"No module named '(\w+)'", "Module '{0}' not installed. Run: pip install {0}"),
                (r"cannot import name '(\w+)' from '(\w+)'", "'{0}' not found in '{1}'. Check if name exists or spelling.")
            ],
            "general": "Import failed. Check if module is installed and name is correct."
        },
        "ZeroDivisionError": {
            "patterns": [
                (r"division by zero", "Cannot divide by zero. Add check for zero divisor.")
            ],
            "general": "Division by zero. Add conditional check before division."
        },
        "FileNotFoundError": {
            "patterns": [
                (r"No such file or directory: '(.+)'", "File not found: {0}. Check path, spelling, and working directory.")
            ],
            "general": "File not found. Check path and working directory."
        },
        "PermissionError": {
            "patterns": [
                (r"Permission denied: '(.+)'", "Permission denied for {0}. Check file permissions or run with appropriate privileges.")
            ],
            "general": "Permission denied. Check file/directory permissions."
        },
        "RecursionError": {
            "patterns": [
                (r"maximum recursion depth exceeded", "Infinite recursion. Add base case or increase recursion limit with sys.setrecursionlimit().")
            ],
            "general": "Maximum recursion depth exceeded. Check for infinite recursion or add base case."
        }
    }
    
    def analyze_error(self, error: Exception, code: str = None) -> ErrorInfo:
        """Analyze an exception and return detailed info."""
        error_type = type(error).__name__
        message = str(error)
        
        # Get traceback
        tb = traceback.format_exc() if sys.exc_info()[0] else ""
        
        # Extract line info from traceback
        line, column, file = self._parse_traceback(tb)
        
        # Get suggestions
        suggestions = self._get_suggestions(error_type, message)
        
        return ErrorInfo(
            error_type=error_type,
            message=message,
            line=line,
            column=column,
            file=file,
            traceback=tb,
            suggestions=suggestions
        )
    
    def _parse_traceback(self, tb: str) -> Tuple[int, int, str]:
        """Extract line number and file from traceback."""
        line, column, file = 0, 0, ""
        
        # Pattern for file and line
        pattern = r'File "([^"]+)", line (\d+)'
        matches = re.findall(pattern, tb)
        
        if matches:
            # Get last match (where error occurred)
            file, line = matches[-1]
            line = int(line)
        
        return line, column, file
    
    def _get_suggestions(self, error_type: str, message: str) -> List[str]:
        """Get fix suggestions for an error."""
        suggestions = []
        
        if error_type in self.ERROR_SOLUTIONS:
            error_info = self.ERROR_SOLUTIONS[error_type]
            
            # Check patterns
            for pattern, solution in error_info.get("patterns", []):
                match = re.search(pattern, message)
                if match:
                    # Format solution with captured groups
                    try:
                        formatted = solution.format(*match.groups())
                        suggestions.append(formatted)
                    except:
                        suggestions.append(solution)
                    break
            
            # Add general solution
            if not suggestions:
                suggestions.append(error_info.get("general", "Check the error details."))
        
        # Add general debugging tips
        suggestions.extend([
            "Use print() or logging to trace variable values",
            "Use a debugger (pdb, ipdb) to step through code",
            "Check recent changes that might have caused the error"
        ])
        
        return suggestions
    
    def analyze_traceback(self, tb: str) -> Dict[str, Any]:
        """Parse and analyze a traceback string."""
        frames = []
        
        # Extract frames
        frame_pattern = r'File "([^"]+)", line (\d+), in (\w+)\s*\n\s*(.+?)(?=\nFile|\Z)'
        
        for match in re.finditer(frame_pattern, tb, re.DOTALL):
            frames.append({
                "file": match.group(1),
                "line": int(match.group(2)),
                "function": match.group(3),
                "code": match.group(4).strip()
            })
        
        # Extract error type and message
        error_pattern = r'(\w+Error|\w+Exception): (.+)$'
        error_match = re.search(error_pattern, tb)
        
        error_type = error_match.group(1) if error_match else "Unknown"
        error_message = error_match.group(2) if error_match else ""
        
        return {
            "frames": frames,
            "error_type": error_type,
            "error_message": error_message,
            "suggestions": self._get_suggestions(error_type, error_message)
        }
    
    def find_common_errors(self, code: str) -> List[Dict[str, Any]]:
        """Scan code for common error patterns."""
        errors = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for common issues
            
            # Missing colon after if/for/while/def/class
            if re.search(r'^\s*(if|elif|else|for|while|def|class|try|except|finally|with)\s+[^:]*$', line):
                if not line.rstrip().endswith(':'):
                    errors.append({
                        "line": i,
                        "type": "SyntaxWarning",
                        "message": f"Possible missing colon after keyword",
                        "code": line.strip()
                    })
            
            # Using = instead of == in conditions
            if re.search(r'\bif\s+.*[^=!<>]=[^=].*:', line):
                errors.append({
                    "line": i,
                    "type": "LogicWarning",
                    "message": "Using = instead of == in condition? (assignment in if)",
                    "code": line.strip()
                })
            
            # Missing parentheses in print (Python 2 style)
            if re.search(r'^\s*print\s+[^(]', line):
                errors.append({
                    "line": i,
                    "type": "SyntaxWarning",
                    "message": "print without parentheses (Python 2 style)",
                    "code": line.strip()
                })
            
            # Using mutable default argument
            if re.search(r'def\s+\w+\([^)]*=\s*(\[\]|\{\})', line):
                errors.append({
                    "line": i,
                    "type": "LogicWarning",
                    "message": "Mutable default argument (will persist between calls)",
                    "code": line.strip()
                })
        
        return errors
    
    def generate_debug_code(self, code: str, breakpoints: List[int] = None) -> str:
        """Generate debugging version of code with print statements."""
        lines = code.split('\n')
        debug_lines = []
        
        breakpoints = breakpoints or []
        
        for i, line in enumerate(lines, 1):
            debug_lines.append(line)
            
            # Add debug print after breakpoints or every assignment
            if i in breakpoints:
                debug_lines.append(f'    print(f"DEBUG line {i}: {{locals()}}")')
        
        return '\n'.join(debug_lines)


class JavaScriptErrorAnalyzer:
    """Analyze JavaScript errors."""
    
    ERROR_SOLUTIONS = {
        "TypeError": {
            "patterns": [
                (r"Cannot read property '(\w+)' of (null|undefined)", "Variable is {1}. Check if object exists before accessing '{0}'."),
                (r"(\w+) is not a function", "'{0}' is not a function. Check type or if it's a property."),
                (r"Cannot set property '(\w+)' of (null|undefined)", "Cannot set '{0}' on {1}. Initialize object first.")
            ],
            "general": "Type error. Check if variables are defined and have expected types."
        },
        "ReferenceError": {
            "patterns": [
                (r"(\w+) is not defined", "Variable '{0}' is not defined. Check spelling or scope."),
                (r"Cannot access '(\w+)' before initialization", "'{0}' used before declaration. Move declaration or use after definition.")
            ],
            "general": "Variable not defined. Check scope and spelling."
        },
        "SyntaxError": {
            "patterns": [
                (r"Unexpected token '(\w+)'", "Unexpected '{0}'. Check for missing brackets, operators, or invalid syntax."),
                (r"Unexpected end of input", "Missing closing bracket. Check for unbalanced parentheses/brackets."),
                (r"Missing initializer in const declaration", "const must be initialized. Add = value after declaration.")
            ],
            "general": "Syntax error. Check for missing punctuation or invalid syntax."
        }
    }
    
    def analyze_error(self, message: str) -> Dict[str, Any]:
        """Analyze JavaScript error message."""
        error_type = "Unknown"
        
        # Extract error type
        for known_type in self.ERROR_SOLUTIONS:
            if message.startswith(known_type):
                error_type = known_type
                break
        
        suggestions = []
        
        if error_type in self.ERROR_SOLUTIONS:
            error_info = self.ERROR_SOLUTIONS[error_type]
            
            for pattern, solution in error_info.get("patterns", []):
                match = re.search(pattern, message)
                if match:
                    suggestions.append(solution.format(*match.groups()))
                    break
            
            if not suggestions:
                suggestions.append(error_info.get("general", ""))
        
        return {
            "error_type": error_type,
            "message": message,
            "suggestions": suggestions
        }


def execute(
    error: Exception = None,
    traceback_str: str = None,
    code: str = None,
    filepath: str = None,
    language: str = "python",
    **kwargs
) -> Dict[str, Any]:
    """
    Debug code by analyzing errors and suggesting fixes.
    
    Args:
        error: Exception object
        traceback_str: Traceback string
        code: Source code to analyze
        filepath: Path to source file
        language: Language (python/javascript)
    
    Returns:
        Debug analysis results
    """
    if language == "python":
        analyzer = PythonErrorAnalyzer()
        
        if error:
            info = analyzer.analyze_error(error, code)
            return {
                "success": True,
                "error_type": info.error_type,
                "message": info.message,
                "line": info.line,
                "file": info.file,
                "traceback": info.traceback,
                "suggestions": info.suggestions
            }
        
        if traceback_str:
            return {
                "success": True,
                **analyzer.analyze_traceback(traceback_str)
            }
        
        if filepath:
            if not os.path.exists(filepath):
                return {"success": False, "error": f"File not found: {filepath}"}
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
        
        if code:
            errors = analyzer.find_common_errors(code)
            return {
                "success": True,
                "potential_errors": errors,
                "total_issues": len(errors)
            }
    
    elif language == "javascript":
        analyzer = JavaScriptErrorAnalyzer()
        
        error_message = kwargs.get("error_message", "")
        if error_message:
            return {
                "success": True,
                **analyzer.analyze_error(error_message)
            }
    
    return {"success": False, "error": "Provide error, traceback, or code to analyze"}


# Import Tuple for type hints
from typing import Tuple
