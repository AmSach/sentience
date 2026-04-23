"""
Doc Generator Skill
Generate documentation from code.
"""

import os
import re
import ast
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from textwrap import dedent

METADATA = {
    "name": "doc-generator",
    "description": "Generate documentation from code including docstrings, API docs, and READMEs",
    "category": "development",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["generate docs", "create documentation", "document code", "docstring"],
    "dependencies": [],
    "tags": ["documentation", "docstrings", "readme", "api-docs"]
}

SKILL_NAME = "doc-generator"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "development"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class ModuleDoc:
    name: str
    description: str
    functions: List[Dict[str, Any]]
    classes: List[Dict[str, Any]]
    constants: List[Dict[str, Any]]


class PythonDocGenerator:
    """Generate documentation for Python code."""
    
    def __init__(self):
        self.style = "google"  # google, numpy, sphinx
    
    def analyze_file(self, filepath: str) -> ModuleDoc:
        """Analyze a Python file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        return self.analyze_code(code, os.path.basename(filepath))
    
    def analyze_code(self, code: str, name: str = "module") -> ModuleDoc:
        """Analyze Python code and extract documentation info."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return ModuleDoc(name, "", [], [], [])
        
        # Module docstring
        module_doc = ast.get_docstring(tree) or ""
        
        functions = []
        classes = []
        constants = []
        
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._analyze_function(node))
            elif isinstance(node, ast.ClassDef):
                classes.append(self._analyze_class(node))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants.append({
                            "name": target.id,
                            "value": self._get_value(node.value),
                            "line": node.lineno
                        })
        
        return ModuleDoc(name, module_doc, functions, classes, constants)
    
    def _analyze_function(self, node: ast.FunctionDef) -> Dict[str, Any]:
        """Analyze a function definition."""
        args = []
        for i, arg in enumerate(node.args.args):
            arg_info = {"name": arg.arg, "type": "Any"}
            if arg.arg == 'self':
                arg_info["type"] = "self"
            elif node.args.annotation:
                arg_info["type"] = self._get_annotation(arg.annotation)
            args.append(arg_info)
        
        returns = None
        if node.returns:
            returns = self._get_annotation(node.returns)
        
        return {
            "name": node.name,
            "args": args,
            "defaults": [self._get_value(d) for d in node.args.defaults],
            "returns": returns,
            "docstring": ast.get_docstring(node) or "",
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "decorators": [self._get_decorator(d) for d in node.decorator_list],
            "line": node.lineno
        }
    
    def _analyze_class(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Analyze a class definition."""
        methods = []
        attributes = []
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(self._analyze_function(item))
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append({
                            "name": target.id,
                            "value": self._get_value(item.value)
                        })
        
        bases = []
        for base in node.bases:
            bases.append(self._get_annotation(base))
        
        return {
            "name": node.name,
            "bases": bases,
            "docstring": ast.get_docstring(node) or "",
            "methods": methods,
            "attributes": attributes,
            "line": node.lineno
        }
    
    def _get_annotation(self, node: ast.AST) -> str:
        """Get type annotation as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            return f"{self._get_annotation(node.value)}[{self._get_annotation(node.slice)}]"
        return "Any"
    
    def _get_value(self, node: ast.AST) -> str:
        """Get value as string."""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.List):
            return "[]"
        elif isinstance(node, ast.Dict):
            return "{}"
        return "..."
    
    def _get_decorator(self, node: ast.AST) -> str:
        """Get decorator name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return f"{node.func.value.id}.{node.func.attr}"
        return "..."
    
    def generate_docstring(self, func: Dict, style: str = "google") -> str:
        """Generate a docstring for a function."""
        if func.get("docstring"):
            return func["docstring"]
        
        if style == "google":
            return self._google_docstring(func)
        elif style == "numpy":
            return self._numpy_docstring(func)
        elif style == "sphinx":
            return self._sphinx_docstring(func)
        return self._google_docstring(func)
    
    def _google_docstring(self, func: Dict) -> str:
        """Generate Google-style docstring."""
        lines = [f"{func['name']} function."]
        
        args = [a for a in func.get("args", []) if a["name"] != "self"]
        if args:
            lines.append("")
            lines.append("Args:")
            for arg in args:
                arg_type = arg.get("type", "Any")
                lines.append(f"    {arg['name']} ({arg_type}): Description.")
        
        if func.get("returns"):
            lines.append("")
            lines.append("Returns:")
            lines.append(f"    {func['returns']}: Description.")
        
        return '\n'.join(lines)
    
    def _numpy_docstring(self, func: Dict) -> str:
        """Generate NumPy-style docstring."""
        lines = [f"{func['name']} function."]
        
        args = [a for a in func.get("args", []) if a["name"] != "self"]
        if args:
            lines.append("")
            lines.append("Parameters")
            lines.append("----------")
            for arg in args:
                arg_type = arg.get("type", "Any")
                lines.append(f"{arg['name']} : {arg_type}")
                lines.append("    Description.")
        
        if func.get("returns"):
            lines.append("")
            lines.append("Returns")
            lines.append("-------")
            lines.append(f"{func['returns']}")
            lines.append("    Description.")
        
        return '\n'.join(lines)
    
    def _sphinx_docstring(self, func: Dict) -> str:
        """Generate Sphinx-style docstring."""
        lines = [f"{func['name']} function."]
        
        args = [a for a in func.get("args", []) if a["name"] != "self"]
        for arg in args:
            arg_type = arg.get("type", "Any")
            lines.append(f":param {arg['name']}: Description.")
            lines.append(f":type {arg['name']}: {arg_type}")
        
        if func.get("returns"):
            lines.append(f":return: Description.")
            lines.append(f":rtype: {func['returns']}")
        
        return '\n'.join(lines)
    
    def generate_readme(self, module: ModuleDoc, project_info: Dict = None) -> str:
        """Generate a README for a module."""
        lines = [f"# {module.name}", ""]
        
        if module.description:
            lines.append(module.description)
            lines.append("")
        
        if module.functions:
            lines.append("## Functions")
            lines.append("")
            for func in module.functions:
                if func["name"].startswith("_"):
                    continue
                lines.append(f"### `{func['name']}`")
                if func.get("docstring"):
                    lines.append(func["docstring"].split('\n')[0])
                lines.append("")
        
        if module.classes:
            lines.append("## Classes")
            lines.append("")
            for cls in module.classes:
                lines.append(f"### `{cls['name']}`")
                if cls.get("docstring"):
                    lines.append(cls["docstring"].split('\n')[0])
                lines.append("")
        
        if module.constants:
            lines.append("## Constants")
            lines.append("")
            for const in module.constants:
                lines.append(f"- `{const['name']}`: {const['value']}")
            lines.append("")
        
        return '\n'.join(lines)
    
    def generate_api_docs(self, module: ModuleDoc) -> str:
        """Generate API reference documentation."""
        lines = [f"# API Reference: {module.name}", ""]
        
        lines.append("## Functions")
        lines.append("")
        
        for func in module.functions:
            if func["name"].startswith("_"):
                continue
            
            sig = self._format_signature(func)
            lines.append(f"### `{sig}`")
            lines.append("")
            
            if func.get("docstring"):
                lines.append(func["docstring"])
            else:
                lines.append(self.generate_docstring(func))
            
            lines.append("")
        
        if module.classes:
            lines.append("---")
            lines.append("")
            lines.append("## Classes")
            lines.append("")
            
            for cls in module.classes:
                lines.append(f"### `class {cls['name']}`")
                if cls.get("bases"):
                    lines.append(f"Inherits from: {', '.join(cls['bases'])}")
                lines.append("")
                
                if cls.get("docstring"):
                    lines.append(cls["docstring"])
                lines.append("")
                
                if cls.get("methods"):
                    lines.append("#### Methods")
                    lines.append("")
                    for method in cls["methods"]:
                        sig = self._format_signature(method)
                        lines.append(f"- `{sig}`")
                    lines.append("")
        
        return '\n'.join(lines)
    
    def _format_signature(self, func: Dict) -> str:
        """Format function signature."""
        args = []
        for a in func.get("args", []):
            if a["name"] == "self":
                args.append("self")
            else:
                arg_type = a.get("type", "")
                if arg_type:
                    args.append(f"{a['name']}: {arg_type}")
                else:
                    args.append(a["name"])
        
        sig = f"{func['name']}({', '.join(args)})"
        if func.get("returns"):
            sig += f" -> {func['returns']}"
        
        return sig


class MarkdownDocGenerator:
    """Generate Markdown documentation."""
    
    def generate_toc(self, sections: List[str]) -> str:
        """Generate table of contents."""
        lines = ["## Table of Contents", ""]
        for section in sections:
            anchor = section.lower().replace(" ", "-").replace("/", "")
            lines.append(f"- [{section}](#{anchor})")
        return '\n'.join(lines)
    
    def generate_installation(self, package: str, manager: str = "pip") -> str:
        """Generate installation section."""
        if manager == "pip":
            return dedent(f'''
            ## Installation
            
            ```bash
            pip install {package}
            ```
            ''').strip()
        elif manager == "npm":
            return dedent(f'''
            ## Installation
            
            ```bash
            npm install {package}
            ```
            ''').strip()
        return ""
    
    def generate_usage_examples(self, examples: List[Dict[str, str]]) -> str:
        """Generate usage examples section."""
        lines = ["## Usage", ""]
        
        for ex in examples:
            lines.append(f"### {ex.get('title', 'Example')}")
            lines.append("")
            if ex.get("description"):
                lines.append(ex["description"])
                lines.append("")
            if ex.get("code"):
                lang = ex.get("language", "python")
                lines.append(f"```{lang}")
                lines.append(ex["code"])
                lines.append("```")
                lines.append("")
        
        return '\n'.join(lines)


def execute(
    filepath: str = None,
    code: str = None,
    doc_type: str = "docstring",
    style: str = "google",
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate documentation from code.
    
    Args:
        filepath: Path to source file
        code: Source code string
        doc_type: Type of documentation (docstring/readme/api-docs)
        style: Docstring style (google/numpy/sphinx)
        output_file: Output file path
    
    Returns:
        Generated documentation
    """
    generator = PythonDocGenerator()
    generator.style = style
    
    if filepath:
        module = generator.analyze_file(filepath)
    elif code:
        module = generator.analyze_code(code)
    else:
        return {"success": False, "error": "Either filepath or code must be provided"}
    
    if doc_type == "docstring":
        # Generate missing docstrings
        results = []
        for func in module.functions:
            if not func.get("docstring"):
                results.append({
                    "name": func["name"],
                    "docstring": generator.generate_docstring(func, style),
                    "line": func["line"]
                })
        
        return {
            "success": True,
            "docstrings": results,
            "style": style
        }
    
    elif doc_type == "readme":
        readme = generator.generate_readme(module)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(readme)
        
        return {
            "success": True,
            "readme": readme,
            "output_file": output_file
        }
    
    elif doc_type == "api-docs":
        docs = generator.generate_api_docs(module)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(docs)
        
        return {
            "success": True,
            "api_docs": docs,
            "output_file": output_file
        }
    
    return {"success": False, "error": f"Unknown doc_type: {doc_type}"}
