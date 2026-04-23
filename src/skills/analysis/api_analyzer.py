"""
API Analyzer Skill
Generate OpenAPI specifications and analyze API structure.
"""

import os
import re
import json
import ast
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

METADATA = {
    "name": "api-analyzer",
    "description": "Analyze APIs and generate OpenAPI/Swagger specifications",
    "category": "analysis",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["analyze api", "generate openapi", "swagger spec", "api documentation"],
    "dependencies": [],
    "tags": ["api", "openapi", "swagger", "documentation"]
}

SKILL_NAME = "api-analyzer"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "analysis"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class APIEndpoint:
    path: str
    method: str
    summary: str = ""
    description: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    request_body: Optional[Dict[str, Any]] = None
    responses: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class APISchema:
    title: str
    version: str
    description: str = ""
    endpoints: List[APIEndpoint] = field(default_factory=list)
    schemas: Dict[str, Any] = field(default_factory=dict)


class OpenAPIGenerator:
    """Generate OpenAPI specifications from code analysis."""
    
    def __init__(self):
        self.spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "API",
                "version": "1.0.0",
                "description": ""
            },
            "paths": {},
            "components": {
                "schemas": {}
            }
        }
        self.endpoints: List[APIEndpoint] = []
    
    def set_info(self, title: str, version: str = "1.0.0", description: str = ""):
        self.spec["info"]["title"] = title
        self.spec["info"]["version"] = version
        self.spec["info"]["description"] = description
    
    def add_endpoint(self, endpoint: APIEndpoint):
        self.endpoints.append(endpoint)
        
        if endpoint.path not in self.spec["paths"]:
            self.spec["paths"][endpoint.path] = {}
        
        method_lower = endpoint.method.lower()
        self.spec["paths"][endpoint.path][method_lower] = {
            "summary": endpoint.summary,
            "description": endpoint.description,
            "parameters": endpoint.parameters,
            "tags": endpoint.tags,
            "responses": endpoint.responses or {"200": {"description": "Success"}}
        }
        
        if endpoint.request_body:
            self.spec["paths"][endpoint.path][method_lower]["requestBody"] = endpoint.request_body
    
    def add_schema(self, name: str, schema: Dict[str, Any]):
        self.spec["components"]["schemas"][name] = schema
    
    def generate(self) -> Dict[str, Any]:
        return self.spec
    
    def to_yaml(self) -> str:
        """Convert spec to YAML format."""
        import io
        try:
            import yaml
            stream = io.StringIO()
            yaml.dump(self.spec, stream, default_flow_style=False)
            return stream.getvalue()
        except ImportError:
            return self._dict_to_yaml(self.spec)
    
    def _dict_to_yaml(self, d: Dict, indent: int = 0) -> str:
        """Simple dict to YAML converter."""
        result = []
        prefix = "  " * indent
        
        for key, value in d.items():
            if isinstance(value, dict):
                result.append(f"{prefix}{key}:")
                result.append(self._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                if not value:
                    result.append(f"{prefix}{key}: []")
                elif isinstance(value[0], dict):
                    result.append(f"{prefix}{key}:")
                    for item in value:
                        result.append(f"{prefix}- ")
                        result.append(self._dict_to_yaml(item, indent + 2))
                else:
                    result.append(f"{prefix}{key}: {json.dumps(value)}")
            else:
                if isinstance(value, str) and ('\n' in value or ':' in value):
                    result.append(f'{prefix}{key}: "{value}"')
                else:
                    result.append(f"{prefix}{key}: {json.dumps(value) if not isinstance(value, str) else value}")
        
        return '\n'.join(result)


class FlaskAnalyzer:
    """Analyze Flask applications to extract API endpoints."""
    
    def __init__(self):
        self.endpoints: List[APIEndpoint] = []
    
    def analyze_file(self, filepath: str) -> List[APIEndpoint]:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        return self.analyze_code(code)
    
    def analyze_code(self, code: str) -> List[APIEndpoint]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        for node in ast.walk(tree):
            # Find route decorators
            if isinstance(node, ast.FunctionDef):
                endpoint = self._extract_endpoint(node, code)
                if endpoint:
                    self.endpoints.append(endpoint)
        
        return self.endpoints
    
    def _extract_endpoint(self, node: ast.FunctionDef, code: str) -> Optional[APIEndpoint]:
        path = None
        methods = ["GET"]
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Attribute):
                    if func.attr in ('route', 'get', 'post', 'put', 'delete', 'patch'):
                        # Get path from first argument
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            path = decorator.args[0].value
                        
                        # Determine method
                        if func.attr != 'route':
                            methods = [func.attr.upper()]
                        else:
                            # Check for methods keyword argument
                            for kw in decorator.keywords:
                                if kw.arg == 'methods':
                                    if isinstance(kw.value, ast.List):
                                        methods = [
                                            elt.value.upper() 
                                            for elt in kw.value.elts 
                                            if isinstance(elt, ast.Constant)
                                        ]
        
        if not path:
            return None
        
        # Extract docstring as summary
        summary = ""
        if (node.body and isinstance(node.body[0], ast.Expr) and
            isinstance(node.body[0].value, ast.Constant)):
            summary = node.body[0].value.value.split('\n')[0]
        
        # Extract parameters from path
        parameters = []
        param_pattern = r'<(\w+)(?::(\w+))?>'
        for match in re.finditer(param_pattern, path):
            param_name = match.group(1)
            param_type = match.group(2) or "string"
            parameters.append({
                "name": param_name,
                "in": "path",
                "required": True,
                "schema": {"type": self._map_type(param_type)}
            })
        
        return APIEndpoint(
            path=re.sub(r'<(\w+)(?::(\w+))?>', r'{\1}', path),
            method=methods[0] if methods else "GET",
            summary=summary or f"{node.name} endpoint",
            description=ast.get_docstring(node) or "",
            parameters=parameters,
            tags=["default"]
        )
    
    def _map_type(self, flask_type: str) -> str:
        type_map = {
            "int": "integer",
            "float": "number",
            "string": "string",
            "path": "string",
            "uuid": "string"
        }
        return type_map.get(flask_type, "string")


class FastAPIAnalyzer:
    """Analyze FastAPI applications to extract API endpoints."""
    
    def __init__(self):
        self.endpoints: List[APIEndpoint] = []
    
    def analyze_file(self, filepath: str) -> List[APIEndpoint]:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        return self.analyze_code(code)
    
    def analyze_code(self, code: str) -> List[APIEndpoint]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                endpoint = self._extract_endpoint(node, code)
                if endpoint:
                    self.endpoints.append(endpoint)
        
        return self.endpoints
    
    def _extract_endpoint(self, node: ast.FunctionDef, code: str) -> Optional[APIEndpoint]:
        path = None
        method = "GET"
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Attribute):
                    if func.attr in ('get', 'post', 'put', 'delete', 'patch'):
                        method = func.attr.upper()
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            path = decorator.args[0].value
        
        if not path:
            return None
        
        # Extract function parameters for OpenAPI spec
        parameters = []
        for arg in node.args.args:
            if arg.arg == 'self' or arg.arg == 'request':
                continue
            parameters.append({
                "name": arg.arg,
                "in": "query",
                "required": arg.arg in [a.arg for a in node.args.args],
                "schema": {"type": "string"}
            })
        
        summary = ast.get_docstring(node) or f"{node.name} endpoint"
        
        return APIEndpoint(
            path=path,
            method=method,
            summary=summary.split('\n')[0],
            description=summary,
            parameters=parameters,
            tags=["default"]
        )


def execute(
    filepath: str = None,
    code: str = None,
    framework: str = None,
    title: str = "API",
    version: str = "1.0.0",
    output_format: str = "json",
    **kwargs
) -> Dict[str, Any]:
    """
    Analyze API code and generate OpenAPI specification.
    
    Args:
        filepath: Path to source file
        code: Source code string
        framework: Framework (flask/fastapi/auto)
        title: API title
        version: API version
        output_format: Output format (json/yaml)
    
    Returns:
        OpenAPI specification
    """
    if filepath:
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
    elif not code:
        return {"success": False, "error": "Either filepath or code must be provided"}
    
    # Auto-detect framework
    if not framework:
        if '@app.route' in code or 'flask' in code.lower():
            framework = 'flask'
        elif 'FastAPI' in code or '@app.' in code and 'get(' in code:
            framework = 'fastapi'
        else:
            framework = 'flask'
    
    # Analyze code
    if framework == 'flask':
        analyzer = FlaskAnalyzer()
    else:
        analyzer = FastAPIAnalyzer()
    
    endpoints = analyzer.analyze_code(code)
    
    # Generate OpenAPI spec
    generator = OpenAPIGenerator()
    generator.set_info(title, version, f"API generated from {framework} code")
    
    for endpoint in endpoints:
        generator.add_endpoint(endpoint)
    
    spec = generator.generate()
    
    result = {
        "success": True,
        "framework": framework,
        "endpoints_count": len(endpoints),
        "endpoints": [
            {
                "path": e.path,
                "method": e.method,
                "summary": e.summary
            }
            for e in endpoints
        ],
        "openapi_spec": spec
    }
    
    if output_format == 'yaml':
        result["openapi_yaml"] = generator.to_yaml()
    
    return result
