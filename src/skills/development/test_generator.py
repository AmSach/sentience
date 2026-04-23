"""
Test Generator Skill
Generate unit tests for code.
"""

import os
import re
import ast
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from textwrap import dedent

METADATA = {
    "name": "test-generator",
    "description": "Generate unit tests for Python and JavaScript code",
    "category": "development",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["generate tests", "write tests", "unit tests", "test cases"],
    "dependencies": [],
    "tags": ["testing", "unit tests", "pytest", "jest"]
}

SKILL_NAME = "test-generator"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "development"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class FunctionInfo:
    name: str
    args: List[str]
    defaults: List[Any]
    returns: Optional[str]
    docstring: str
    is_async: bool
    is_method: bool


class PythonTestGenerator:
    """Generate pytest tests for Python code."""
    
    def __init__(self):
        self.imports = set()
    
    def analyze_function(self, func: ast.FunctionDef) -> FunctionInfo:
        """Extract function information from AST."""
        args = [arg.arg for arg in func.args.args]
        defaults = [d.value if isinstance(d, ast.Constant) else None 
                   for d in func.args.defaults]
        returns = None
        docstring = ast.get_docstring(func) or ""
        
        # Check return annotation
        if func.returns:
            if isinstance(func.returns, ast.Name):
                returns = func.returns.id
            elif isinstance(func.returns, ast.Constant):
                returns = func.returns.value
        
        return FunctionInfo(
            name=func.name,
            args=args,
            defaults=defaults,
            returns=returns,
            docstring=docstring,
            is_async=isinstance(func, ast.AsyncFunctionDef),
            is_method=func.args.args and func.args.args[0].arg == 'self'
        )
    
    def analyze_file(self, filepath: str) -> List[FunctionInfo]:
        """Analyze a Python file and extract function info."""
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        return self.analyze_code(code)
    
    def analyze_code(self, code: str) -> List[FunctionInfo]:
        """Analyze Python code string."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self.analyze_function(node)
                if not func_info.name.startswith('_'):
                    functions.append(func_info)
        
        return functions
    
    def generate_test(self, func: FunctionInfo, module_name: str = "module") -> str:
        """Generate a test function for a given function."""
        self.imports.add(f"from {module_name} import {func.name}")
        
        # Determine test cases based on function signature
        test_cases = self._infer_test_cases(func)
        
        tests = []
        for i, case in enumerate(test_cases, 1):
            test_name = f"test_{func.name}_{case['name']}"
            test_code = self._generate_test_case(func, case, i == 1)
            tests.append(test_code)
        
        return '\n\n'.join(tests)
    
    def _infer_test_cases(self, func: FunctionInfo) -> List[Dict[str, Any]]:
        """Infer test cases from function signature."""
        cases = [
            {"name": "basic", "description": "Basic functionality", "expect_success": True},
            {"name": "edge_case", "description": "Edge cases", "expect_success": True},
            {"name": "invalid_input", "description": "Invalid input handling", "expect_success": False}
        ]
        return cases
    
    def _generate_test_case(self, func: FunctionInfo, case: Dict, is_first: bool) -> str:
        """Generate a single test case."""
        param_str = ", ".join(func.args) if func.args else ""
        
        # Generate test values
        test_values = self._generate_test_values(func)
        
        if func.is_async:
            return dedent(f'''
            @pytest.mark.asyncio
            async def test_{func.name}_{case['name']}():
                """Test {case['description']} for {func.name}."""
                # Arrange
                {self._generate_arrange(func, test_values)}
                
                # Act
                result = await {func.name}({test_values['call_args']})
                
                # Assert
                assert result is not None
            ''').strip()
        else:
            return dedent(f'''
            def test_{func.name}_{case['name']}():
                """Test {case['description']} for {func.name}."""
                # Arrange
                {self._generate_arrange(func, test_values)}
                
                # Act
                result = {func.name}({test_values['call_args']})
                
                # Assert
                assert result is not None
            ''').strip()
    
    def _generate_test_values(self, func: FunctionInfo) -> Dict[str, str]:
        """Generate test values based on argument types."""
        values = {}
        args = []
        
        for arg in func.args:
            if arg == 'self':
                continue
            # Default values based on common patterns
            if 'id' in arg.lower():
                args.append(f"{arg}=1")
            elif 'name' in arg.lower():
                args.append(f"{arg}='test'")
            elif 'count' in arg.lower() or 'num' in arg.lower():
                args.append(f"{arg}=10")
            elif 'data' in arg.lower() or 'value' in arg.lower():
                args.append(f"{arg}={{}}")
            else:
                args.append(f"{arg}='test'")
        
        values['call_args'] = ", ".join(args)
        return values
    
    def _generate_arrange(self, func: FunctionInfo, values: Dict) -> str:
        """Generate arrange section."""
        if not func.args or func.args == ['self']:
            return "pass"
        return f"input_data = {{{values['call_args'].replace('=', ':')}}}"
    
    def generate_test_file(self, filepath: str, output_path: str = None) -> Dict[str, Any]:
        """Generate a complete test file for a Python module."""
        functions = self.analyze_file(filepath)
        
        if not functions:
            return {
                "success": False,
                "error": "No testable functions found"
            }
        
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        
        all_tests = []
        for func in functions:
            test = self.generate_test(func, module_name)
            all_tests.append(test)
        
        # Build complete test file
        self.imports.add("import pytest")
        imports = '\n'.join(sorted(self.imports))
        tests_code = '\n\n'.join(all_tests)
        
        test_file = f'''"""
Tests for {module_name}
Auto-generated by test-generator skill.
"""

{imports}


{tests_code}
'''
        
        # Write to file if path provided
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(test_file)
        
        return {
            "success": True,
            "test_file": test_file,
            "functions_tested": len(functions),
            "test_count": sum(3 for _ in functions),  # 3 tests per function
            "output_path": output_path
        }


class JestTestGenerator:
    """Generate Jest tests for JavaScript/TypeScript code."""
    
    def analyze_file(self, filepath: str) -> List[Dict[str, Any]]:
        """Analyze a JS/TS file and extract function info."""
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        return self.analyze_code(code)
    
    def analyze_code(self, code: str) -> List[Dict[str, Any]]:
        """Analyze JavaScript code."""
        functions = []
        
        # Match function declarations
        func_pattern = r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(func_pattern, code):
            functions.append({
                "name": match.group(1),
                "params": [p.strip() for p in match.group(2).split(',') if p.strip()],
                "is_async": 'async' in match.group(0)
            })
        
        # Match arrow functions
        arrow_pattern = r'(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>'
        for match in re.finditer(arrow_pattern, code):
            functions.append({
                "name": match.group(1),
                "params": [],
                "is_async": 'async' in match.group(0)
            })
        
        return functions
    
    def generate_test(self, func: Dict, import_path: str = "./module") -> str:
        """Generate a Jest test for a function."""
        name = func["name"]
        is_async = func.get("is_async", False)
        
        if is_async:
            return dedent(f'''
            describe('{name}', () => {{
                it('should work correctly', async () => {{
                    // Arrange
                    const input = 'test';
                    
                    // Act
                    const result = await {name}(input);
                    
                    // Assert
                    expect(result).toBeDefined();
                }});
                
                it('should handle edge cases', async () => {{
                    // Arrange
                    const input = null;
                    
                    // Act & Assert
                    await expect({name}(input)).resolves.not.toThrow();
                }});
                
                it('should handle invalid input', async () => {{
                    // Act & Assert
                    await expect({name}()).rejects.toThrow();
                }});
            }});
            ''').strip()
        else:
            return dedent(f'''
            describe('{name}', () => {{
                it('should work correctly', () => {{
                    // Arrange
                    const input = 'test';
                    
                    // Act
                    const result = {name}(input);
                    
                    // Assert
                    expect(result).toBeDefined();
                }});
                
                it('should handle edge cases', () => {{
                    // Arrange
                    const input = null;
                    
                    // Act
                    const result = {name}(input);
                    
                    // Assert
                    expect(result).toBeDefined();
                }});
                
                it('should handle invalid input', () => {{
                    // Act & Assert
                    expect(() => {name}()).toThrow();
                }});
            }});
            ''').strip()
    
    def generate_test_file(self, filepath: str, output_path: str = None) -> Dict[str, Any]:
        """Generate a complete Jest test file."""
        functions = self.analyze_file(filepath)
        
        if not functions:
            return {
                "success": False,
                "error": "No testable functions found"
            }
        
        import_path = os.path.splitext(filepath)[0]
        imports = f"import {{ {', '.join(f['name'] for f in functions)} }} from '{import_path}';"
        
        all_tests = []
        for func in functions:
            test = self.generate_test(func, import_path)
            all_tests.append(test)
        
        test_file = f'''/**
 * Tests for {os.path.basename(filepath)}
 * Auto-generated by test-generator skill.
 */

{imports}

{chr(10).join(all_tests)}
'''
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(test_file)
        
        return {
            "success": True,
            "test_file": test_file,
            "functions_tested": len(functions),
            "test_count": sum(3 for _ in functions),
            "output_path": output_path
        }


def execute(
    filepath: str = None,
    code: str = None,
    language: str = None,
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate unit tests for code.
    
    Args:
        filepath: Path to source file
        code: Source code string
        language: Language (python/javascript/auto)
        output_file: Output test file path
    
    Returns:
        Generated tests
    """
    # Auto-detect language
    if not language and filepath:
        ext = os.path.splitext(filepath)[1].lower()
        language = 'javascript' if ext in ('.js', '.jsx', '.ts', '.tsx') else 'python'
    elif not language:
        language = 'python'
    
    if language == 'python':
        generator = PythonTestGenerator()
    else:
        generator = JestTestGenerator()
    
    if filepath:
        return generator.generate_test_file(filepath, output_file)
    elif code:
        # Analyze code directly
        functions = generator.analyze_code(code)
        if not functions:
            return {"success": False, "error": "No testable functions found"}
        
        all_tests = []
        for func in functions:
            test = generator.generate_test(func, "module")
            all_tests.append(test)
        
        return {
            "success": True,
            "tests": all_tests,
            "functions_tested": len(functions)
        }
    
    return {"success": False, "error": "Either filepath or code must be provided"}
