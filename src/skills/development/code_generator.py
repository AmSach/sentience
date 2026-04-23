"""
Code Generator Skill
Generate code from specifications, templates, and natural language.
"""

import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from string import Template
from textwrap import dedent

METADATA = {
    "name": "code-generator",
    "description": "Generate code from specifications, templates, and natural language descriptions",
    "category": "development",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["generate code", "create code", "write code", "code from spec"],
    "dependencies": [],
    "tags": ["code", "generation", "templates", "scaffolding"]
}

SKILL_NAME = "code-generator"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "development"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class CodeTemplate:
    name: str
    language: str
    template: str
    variables: List[str]
    description: str


class TemplateRegistry:
    """Registry of code templates."""
    
    templates: Dict[str, CodeTemplate] = {}
    
    @classmethod
    def register(cls, template: CodeTemplate):
        cls.templates[template.name] = template
    
    @classmethod
    def get(cls, name: str) -> Optional[CodeTemplate]:
        return cls.templates.get(name)
    
    @classmethod
    def list_templates(cls) -> List[str]:
        return list(cls.templates.keys())


# Register built-in templates
TemplateRegistry.register(CodeTemplate(
    name="python_function",
    language="python",
    template=dedent('''
    def ${name}(${params})${return_type}:
        """
        ${description}
        
        ${args_doc}
        Returns:
            ${returns_doc}
        """
        ${body}
    '''),
    variables=["name", "params", "return_type", "description", "args_doc", "returns_doc", "body"],
    description="Python function with docstring"
))

TemplateRegistry.register(CodeTemplate(
    name="python_class",
    language="python",
    template=dedent('''
    class ${name}${inheritance}:
        """
        ${description}
        """
        
        def __init__(self, ${init_params}):
            ${init_body}
        
        ${methods}
    '''),
    variables=["name", "inheritance", "description", "init_params", "init_body", "methods"],
    description="Python class with __init__"
))

TemplateRegistry.register(CodeTemplate(
    name="python_async_function",
    language="python",
    template=dedent('''
    async def ${name}(${params})${return_type}:
        """
        ${description}
        """
        ${body}
    '''),
    variables=["name", "params", "return_type", "description", "body"],
    description="Async Python function"
))

TemplateRegistry.register(CodeTemplate(
    name="python_dataclass",
    language="python",
    template=dedent('''
    @dataclass
    class ${name}:
        """${description}"""
        ${fields}
    '''),
    variables=["name", "description", "fields"],
    description="Python dataclass"
))

TemplateRegistry.register(CodeTemplate(
    name="python_fastapi_endpoint",
    language="python",
    template=dedent('''
    @app.${method}("${path}")
    async def ${name}(${params})${return_type}:
        """
        ${description}
        """
        ${body}
    '''),
    variables=["method", "path", "name", "params", "return_type", "description", "body"],
    description="FastAPI endpoint"
))

TemplateRegistry.register(CodeTemplate(
    name="python_flask_route",
    language="python",
    template=dedent('''
    @app.route("${path}", methods=[${methods}])
    def ${name}(${params}):
        """
        ${description}
        """
        ${body}
    '''),
    variables=["path", "methods", "name", "params", "description", "body"],
    description="Flask route"
))

TemplateRegistry.register(CodeTemplate(
    name="python_pytest",
    language="python",
    template=dedent('''
    def test_${name}(${params}):
        """${description}"""
        # Arrange
        ${arrange}
        
        # Act
        ${act}
        
        # Assert
        ${assert}
    '''),
    variables=["name", "params", "description", "arrange", "act", "assert"],
    description="Pytest test function"
))

TemplateRegistry.register(CodeTemplate(
    name="javascript_function",
    language="javascript",
    template=dedent('''
    /**
     * ${description}
     * ${params_doc}
     * @returns {${returns}} ${returns_doc}
     */
    function ${name}(${params}) {
        ${body}
    }
    '''),
    variables=["name", "params", "description", "params_doc", "returns", "returns_doc", "body"],
    description="JavaScript function"
))

TemplateRegistry.register(CodeTemplate(
    name="typescript_interface",
    language="typescript",
    template=dedent('''
    interface ${name} {
        /** ${description} */
        ${fields}
    }
    '''),
    variables=["name", "description", "fields"],
    description="TypeScript interface"
))

TemplateRegistry.register(CodeTemplate(
    name="react_component",
    language="javascript",
    template=dedent('''
    import React from 'react';
    
    interface ${name}Props {
        ${props_interface}
    }
    
    const ${name}: React.FC<${name}Props> = ({ ${props} }) => {
        ${body}
        
        return (
            ${jsx}
        );
    };
    
    export default ${name};
    '''),
    variables=["name", "props_interface", "props", "body", "jsx"],
    description="React functional component"
))

TemplateRegistry.register(CodeTemplate(
    name="sql_table",
    language="sql",
    template=dedent('''
    CREATE TABLE ${name} (
        ${fields}
        ${constraints}
    );
    '''),
    variables=["name", "fields", "constraints"],
    description="SQL CREATE TABLE"
))

TemplateRegistry.register(CodeTemplate(
    name="html_page",
    language="html",
    template=dedent('''
    <!DOCTYPE html>
    <html lang="${lang}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>${title}</title>
        ${head}
    </head>
    <body>
        ${body}
    </body>
    </html>
    '''),
    variables=["lang", "title", "head", "body"],
    description="HTML page"
))


class CodeGenerator:
    """Generate code from templates and specifications."""
    
    def __init__(self):
        self.registry = TemplateRegistry
    
    def from_template(self, template_name: str, **kwargs) -> Dict[str, Any]:
        """Generate code from a registered template."""
        template = self.registry.get(template_name)
        if not template:
            return {
                "success": False,
                "error": f"Template not found: {template_name}",
                "available_templates": self.registry.list_templates()
            }
        
        # Check for required variables
        missing = [v for v in template.variables if v not in kwargs]
        if missing:
            # Provide defaults for missing variables
            defaults = {
                "params": "",
                "return_type": "",
                "description": "",
                "body": "# TODO: Implement",
                "init_body": "pass",
                "methods": "pass",
                "fields": "pass",
                "inheritance": "",
                "args_doc": "",
                "returns_doc": "",
                "params_doc": "",
                "returns": "void",
                "init_params": "",
                "props_interface": "",
                "props": "",
                "jsx": "<div></div>",
                "constraints": "",
                "head": "",
                "lang": "en",
                "arrange": "# Setup",
                "act": "# Execute",
                "assert": "# Verify"
            }
            kwargs = {**defaults, **kwargs}
        
        try:
            t = Template(template.template)
            code = t.substitute(**kwargs)
            # Clean up extra whitespace
            code = dedent(code).strip()
            
            return {
                "success": True,
                "code": code,
                "template": template_name,
                "language": template.language,
                "variables_used": {k: v for k, v in kwargs.items() if k in template.variables}
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Template substitution failed: {e}"
            }
    
    def function_from_spec(self, spec: Dict[str, Any], language: str = "python") -> Dict[str, Any]:
        """Generate a function from a specification."""
        name = spec.get("name", "function")
        params = spec.get("parameters", [])
        returns = spec.get("returns", None)
        description = spec.get("description", "")
        is_async = spec.get("async", False)
        
        # Build parameter string
        if language == "python":
            param_str = ", ".join(
                f"{p['name']}: {p.get('type', 'Any')}" 
                if isinstance(p, dict) else str(p)
                for p in params
            )
            return_type = f" -> {returns}" if returns else ""
            template_name = "python_async_function" if is_async else "python_function"
            
        elif language in ("javascript", "typescript"):
            param_str = ", ".join(
                p['name'] if isinstance(p, dict) else str(p)
                for p in params
            )
            return_type = returns or "void"
            template_name = "javascript_function"
            
        else:
            return {"success": False, "error": f"Unsupported language: {language}"}
        
        return self.from_template(
            template_name,
            name=name,
            params=param_str,
            return_type=return_type,
            description=description,
            returns_doc=returns or "None"
        )
    
    def class_from_spec(self, spec: Dict[str, Any], language: str = "python") -> Dict[str, Any]:
        """Generate a class from a specification."""
        name = spec.get("name", "Class")
        description = spec.get("description", "")
        fields = spec.get("fields", [])
        methods = spec.get("methods", [])
        inherits = spec.get("inherits", None)
        
        if language == "python":
            # Build fields
            fields_str = "\n    ".join(
                f"{f['name']}: {f.get('type', 'Any')}"
                for f in fields
            ) if fields else "pass"
            
            inheritance = f"({inherits})" if inherits else ""
            
            # Build methods
            methods_str = ""
            for m in methods:
                m_code = self.function_from_spec(m, "python")
                if m_code.get("success"):
                    methods_str += "\n    " + m_code["code"].replace("\n", "\n    ") + "\n"
            
            return self.from_template(
                "python_class",
                name=name,
                inheritance=inheritance,
                description=description,
                init_params=", ".join(f["name"] for f in fields),
                init_body=f"self.{f['name']} = {f['name']}" if fields else "pass",
                methods=methods_str or "pass"
            )
            
        elif language == "typescript":
            fields_str = "\n        ".join(
                f"{f['name']}: {f.get('type', 'any')};"
                for f in fields
            )
            
            return self.from_template(
                "typescript_interface",
                name=name,
                description=description,
                fields=fields_str
            )
        
        return {"success": False, "error": f"Unsupported language: {language}"}
    
    def api_endpoint_from_spec(self, spec: Dict[str, Any], framework: str = "fastapi") -> Dict[str, Any]:
        """Generate an API endpoint from a specification."""
        path = spec.get("path", "/")
        method = spec.get("method", "get").lower()
        name = spec.get("name", path.replace("/", "_").strip("_") or "endpoint")
        description = spec.get("description", "")
        params = spec.get("parameters", [])
        returns = spec.get("returns", "dict")
        
        param_str = ", ".join(
            f"{p['name']}: {p.get('type', 'str')}"
            for p in params
        )
        return_type = f" -> {returns}" if returns else ""
        
        if framework == "fastapi":
            return self.from_template(
                "python_fastapi_endpoint",
                method=method,
                path=path,
                name=name,
                params=param_str,
                return_type=return_type,
                description=description,
                body="pass"
            )
        elif framework == "flask":
            return self.from_template(
                "python_flask_route",
                path=path,
                methods=f"'{method.upper()}'",
                name=name,
                params=param_str,
                description=description,
                body="pass"
            )
        
        return {"success": False, "error": f"Unsupported framework: {framework}"}
    
    def generate_file(self, filepath: str, code: str) -> Dict[str, Any]:
        """Write generated code to a file."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code)
            
            return {
                "success": True,
                "filepath": filepath,
                "lines": len(code.split('\n'))
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


def execute(
    template: str = None,
    spec: Dict = None,
    language: str = "python",
    framework: str = None,
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate code from templates or specifications.
    
    Args:
        template: Name of registered template
        spec: Specification dict (for function/class/endpoint)
        language: Target language
        framework: Target framework (for API endpoints)
        output_file: Optional file path to write generated code
        **kwargs: Template variables
    
    Returns:
        Generated code or error
    """
    generator = CodeGenerator()
    
    if template:
        result = generator.from_template(template, **kwargs)
    elif spec:
        spec_type = spec.get("type", "function")
        
        if spec_type == "function":
            result = generator.function_from_spec(spec, language)
        elif spec_type == "class":
            result = generator.class_from_spec(spec, language)
        elif spec_type == "endpoint":
            result = generator.api_endpoint_from_spec(spec, framework or "fastapi")
        else:
            result = {"success": False, "error": f"Unknown spec type: {spec_type}"}
    else:
        result = {"success": False, "error": "Provide either template name or spec"}
    
    if result.get("success") and output_file:
        file_result = generator.generate_file(output_file, result["code"])
        result["file"] = file_result
    
    return result
