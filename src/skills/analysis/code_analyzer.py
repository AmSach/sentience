"""
Code Analyzer Skill
Static analysis, complexity metrics, and code quality assessment.
"""

import os
import re
import ast
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

METADATA = {
    "name": "code-analyzer",
    "description": "Static analysis, complexity metrics, and code quality assessment for Python, JavaScript, and more",
    "category": "analysis",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["analyze code", "code analysis", "static analysis", "complexity", "code quality"],
    "dependencies": [],
    "tags": ["analysis", "code", "quality", "metrics"]
}

SKILL_NAME = "code-analyzer"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "analysis"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class ComplexityMetrics:
    cyclomatic_complexity: int
    cognitive_complexity: int
    lines_of_code: int
    lines_of_comments: int
    functions_count: int
    classes_count: int
    max_nesting_depth: int


@dataclass
class CodeIssue:
    line: int
    column: int
    severity: str
    message: str
    rule: str


class PythonAnalyzer:
    """Python code analyzer using AST."""
    
    def __init__(self):
        self.issues: List[CodeIssue] = []
        self.metrics = ComplexityMetrics(0, 0, 0, 0, 0, 0, 0)
    
    def analyze(self, code: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "success": False,
                "error": f"Syntax error: {e}",
                "issues": [],
                "metrics": {}
            }
        
        self._analyze_complexity(tree, code)
        self._analyze_quality(tree, code)
        
        return {
            "success": True,
            "metrics": self._metrics_to_dict(),
            "issues": [self._issue_to_dict(i) for i in self.issues],
            "summary": self._generate_summary()
        }
    
    def _analyze_complexity(self, tree: ast.AST, code: str):
        lines = code.split('\n')
        self.metrics.lines_of_code = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
        self.metrics.lines_of_comments = len([l for l in lines if l.strip().startswith('#')])
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.metrics.functions_count += 1
                self.metrics.cyclomatic_complexity += self._count_branches(node)
            elif isinstance(node, ast.ClassDef):
                self.metrics.classes_count += 1
        
        self.metrics.max_nesting_depth = self._max_depth(tree)
    
    def _count_branches(self, node: ast.AST) -> int:
        count = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                count += 1
            elif isinstance(child, ast.BoolOp):
                count += len(child.values) - 1
        return count
    
    def _max_depth(self, tree: ast.AST) -> int:
        def depth(node, current=0):
            max_d = current
            for child in ast.iter_child_nodes(node):
                max_d = max(max_d, depth(child, current + 1))
            return max_d
        return depth(tree)
    
    def _analyze_quality(self, tree: ast.AST, code: str):
        for node in ast.walk(tree):
            # Check for long functions
            if isinstance(node, ast.FunctionDef):
                func_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                if func_lines > 50:
                    self.issues.append(CodeIssue(
                        line=node.lineno,
                        column=0,
                        severity="warning",
                        message=f"Function '{node.name}' is too long ({func_lines} lines)",
                        rule="function-length"
                    ))
            
            # Check for too many arguments
            if isinstance(node, ast.FunctionDef):
                arg_count = len(node.args.args)
                if arg_count > 5:
                    self.issues.append(CodeIssue(
                        line=node.lineno,
                        column=0,
                        severity="warning",
                        message=f"Function '{node.name}' has too many arguments ({arg_count})",
                        rule="argument-count"
                    ))
            
            # Check for empty functions
            if isinstance(node, ast.FunctionDef):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    self.issues.append(CodeIssue(
                        line=node.lineno,
                        column=0,
                        severity="info",
                        message=f"Function '{node.name}' is empty",
                        rule="empty-function"
                    ))
            
            # Check for bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                self.issues.append(CodeIssue(
                    line=node.lineno,
                    column=0,
                    severity="warning",
                    message="Bare except clause - catches all exceptions including KeyboardInterrupt",
                    rule="bare-except"
                ))
    
    def _metrics_to_dict(self) -> Dict[str, Any]:
        return {
            "cyclomatic_complexity": self.metrics.cyclomatic_complexity,
            "cognitive_complexity": self.metrics.cognitive_complexity,
            "lines_of_code": self.metrics.lines_of_code,
            "lines_of_comments": self.metrics.lines_of_comments,
            "functions_count": self.metrics.functions_count,
            "classes_count": self.metrics.classes_count,
            "max_nesting_depth": self.metrics.max_nesting_depth
        }
    
    def _issue_to_dict(self, issue: CodeIssue) -> Dict[str, Any]:
        return {
            "line": issue.line,
            "column": issue.column,
            "severity": issue.severity,
            "message": issue.message,
            "rule": issue.rule
        }
    
    def _generate_summary(self) -> str:
        total_issues = len(self.issues)
        warnings = len([i for i in self.issues if i.severity == "warning"])
        info = len([i for i in self.issues if i.severity == "info"])
        
        return f"Lines: {self.metrics.lines_of_code}, Functions: {self.metrics.functions_count}, Classes: {self.metrics.classes_count}, CC: {self.metrics.cyclomatic_complexity}, Issues: {total_issues} ({warnings} warnings, {info} info)"


class JavaScriptAnalyzer:
    """JavaScript/TypeScript code analyzer."""
    
    def __init__(self):
        self.issues: List[CodeIssue] = []
        self.metrics = ComplexityMetrics(0, 0, 0, 0, 0, 0, 0)
    
    def analyze(self, code: str) -> Dict[str, Any]:
        lines = code.split('\n')
        self.metrics.lines_of_code = len([l for l in lines if l.strip() and not l.strip().startswith(('//', '/*', '*'))])
        self.metrics.lines_of_comments = self._count_comment_lines(code)
        
        self._analyze_structure(code)
        self._analyze_patterns(code)
        
        return {
            "success": True,
            "metrics": self._metrics_to_dict(),
            "issues": [self._issue_to_dict(i) for i in self.issues],
            "summary": self._generate_summary()
        }
    
    def _count_comment_lines(self, code: str) -> int:
        count = 0
        in_block = False
        for line in code.split('\n'):
            if '/*' in line:
                in_block = True
            if '*/' in line:
                in_block = False
                count += 1
                continue
            if in_block or line.strip().startswith('//'):
                count += 1
        return count
    
    def _analyze_structure(self, code: str):
        self.metrics.functions_count = len(re.findall(r'\bfunction\s+\w+|\b=>\s*{|\w+\s*\([^)]*\)\s*{', code))
        self.metrics.classes_count = len(re.findall(r'\bclass\s+\w+', code))
        
        # Estimate cyclomatic complexity
        if_count = len(re.findall(r'\bif\s*\(', code))
        for_count = len(re.findall(r'\bfor\s*\(', code))
        while_count = len(re.findall(r'\bwhile\s*\(', code))
        case_count = len(re.findall(r'\bcase\s+', code))
        and_count = len(re.findall(r'&&', code))
        or_count = len(re.findall(r'\|\|', code))
        
        self.metrics.cyclomatic_complexity = 1 + if_count + for_count + while_count + case_count + and_count + or_count
    
    def _analyze_patterns(self, code: str):
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for var usage
            if re.search(r'\bvar\s+', line):
                self.issues.append(CodeIssue(
                    line=i, column=0, severity="warning",
                    message="Use 'let' or 'const' instead of 'var'",
                    rule="no-var"
                ))
            
            # Check for == instead of ===
            if re.search(r'[^=!]==[^=]', line) and '===' not in line:
                self.issues.append(CodeIssue(
                    line=i, column=0, severity="warning",
                    message="Use '===' instead of '=='",
                    rule="eqeqeq"
                ))
            
            # Check for console.log
            if 'console.log' in line and not line.strip().startswith('//'):
                self.issues.append(CodeIssue(
                    line=i, column=0, severity="info",
                    message="Remove console.log before production",
                    rule="no-console"
                ))
            
            # Check for debugger
            if 'debugger' in line and not line.strip().startswith('//'):
                self.issues.append(CodeIssue(
                    line=i, column=0, severity="warning",
                    message="Remove debugger statement",
                    rule="no-debugger"
                ))
    
    def _metrics_to_dict(self) -> Dict[str, Any]:
        return {
            "cyclomatic_complexity": self.metrics.cyclomatic_complexity,
            "lines_of_code": self.metrics.lines_of_code,
            "lines_of_comments": self.metrics.lines_of_comments,
            "functions_count": self.metrics.functions_count,
            "classes_count": self.metrics.classes_count
        }
    
    def _issue_to_dict(self, issue: CodeIssue) -> Dict[str, Any]:
        return {
            "line": issue.line,
            "column": issue.column,
            "severity": issue.severity,
            "message": issue.message,
            "rule": issue.rule
        }
    
    def _generate_summary(self) -> str:
        total = len(self.issues)
        return f"Lines: {self.metrics.lines_of_code}, Functions: {self.metrics.functions_count}, Classes: {self.metrics.classes_count}, CC: {self.metrics.cyclomatic_complexity}, Issues: {total}"


def detect_language(filepath: str) -> str:
    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'javascript',
        '.tsx': 'javascript',
        '.mjs': 'javascript',
        '.cjs': 'javascript'
    }
    ext = os.path.splitext(filepath)[1].lower()
    return ext_map.get(ext, 'unknown')


def execute(filepath: str = None, code: str = None, language: str = None, **kwargs) -> Dict[str, Any]:
    """
    Analyze code for quality, complexity, and potential issues.
    
    Args:
        filepath: Path to source file
        code: Source code string (if no filepath)
        language: Language override (python/javascript)
    
    Returns:
        Analysis results with metrics and issues
    """
    if filepath:
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        language = language or detect_language(filepath)
    elif not code:
        return {"success": False, "error": "Either filepath or code must be provided"}
    
    language = language or 'python'
    
    if language == 'python':
        analyzer = PythonAnalyzer()
    elif language in ('javascript', 'typescript', 'js', 'ts'):
        analyzer = JavaScriptAnalyzer()
    else:
        return {"success": False, "error": f"Unsupported language: {language}"}
    
    result = analyzer.analyze(code)
    result["language"] = language
    result["filepath"] = filepath
    
    return result
