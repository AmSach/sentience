"""
JSON Handler Skill
Process and manipulate JSON data.
"""

import os
import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from copy import deepcopy

METADATA = {
    "name": "json-handler",
    "description": "Parse, transform, query, and manipulate JSON data",
    "category": "data",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["json", "parse json", "json data", "json file"],
    "dependencies": [],
    "tags": ["json", "data", "parsing", "transformation"]
}

SKILL_NAME = "json-handler"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "data"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class JSONPath:
    """Simple JSON path expression support."""
    path: str
    
    def parse(self) -> List[Union[str, int]]:
        """Parse path into components."""
        parts = []
        current = ""
        in_bracket = False
        
        for char in self.path:
            if char == '[':
                if current:
                    parts.append(current)
                    current = ""
                in_bracket = True
            elif char == ']':
                if current.isdigit():
                    parts.append(int(current))
                else:
                    parts.append(current.strip("'\""))
                current = ""
                in_bracket = False
            elif char == '.' and not in_bracket:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char
        
        if current:
            parts.append(current)
        
        return parts
    
    def get(self, data: Any) -> Any:
        """Get value at path."""
        parts = self.parse()
        current = data
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                if isinstance(part, int) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            else:
                return None
        
        return current
    
    def set(self, data: Any, value: Any) -> Any:
        """Set value at path."""
        parts = self.parse()
        current = data
        
        for i, part in enumerate(parts[:-1]):
            if isinstance(current, dict):
                if part not in current:
                    # Create nested structure
                    next_part = parts[i + 1]
                    current[part] = [] if isinstance(next_part, int) else {}
                current = current[part]
            elif isinstance(current, list):
                if isinstance(part, int) and 0 <= part < len(current):
                    current = current[part]
        
        # Set final value
        final_part = parts[-1]
        if isinstance(current, dict):
            current[final_part] = value
        elif isinstance(current, list) and isinstance(final_part, int):
            if 0 <= final_part < len(current):
                current[final_part] = value
        
        return data


class JSONHandler:
    """Handle JSON data operations."""
    
    def __init__(self):
        self.data: Any = None
    
    def parse(self, json_string: str) -> Any:
        """Parse JSON string."""
        self.data = json.loads(json_string)
        return self.data
    
    def parse_file(self, filepath: str) -> Any:
        """Parse JSON file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        return self.data
    
    def stringify(self, data: Any = None, indent: int = 2) -> str:
        """Convert to JSON string."""
        data = data or self.data
        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)
    
    def write_file(self, filepath: str, data: Any = None, indent: int = 2) -> str:
        """Write JSON to file."""
        data = data or self.data
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
        
        return filepath
    
    def get_path(self, path: str) -> Any:
        """Get value at JSON path."""
        if self.data is None:
            return None
        return JSONPath(path).get(self.data)
    
    def set_path(self, path: str, value: Any) -> Any:
        """Set value at JSON path."""
        if self.data is None:
            return None
        
        jp = JSONPath(path)
        return jp.set(deepcopy(self.data), value)
    
    def flatten(self, data: Any = None, parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
        """Flatten nested JSON to dot-notation keys."""
        data = data or self.data
        items = []
        
        if isinstance(data, dict):
            for k, v in data.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(self.flatten(v, new_key, sep).items())
                elif isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, (dict, list)):
                            items.extend(self.flatten(item, f"{new_key}[{i}]", sep).items())
                        else:
                            items.append((f"{new_key}[{i}]", item))
                else:
                    items.append((new_key, v))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    items.extend(self.flatten(item, f"[{i}]", sep).items())
                else:
                    items.append((f"[{i}]", item))
        else:
            items.append((parent_key, data))
        
        return dict(items)
    
    def unflatten(self, flat_dict: Dict[str, Any], sep: str = '.') -> Dict[str, Any]:
        """Convert flat dict with dot-notation keys back to nested."""
        result = {}
        
        for key, value in flat_dict.items():
            parts = key.replace('][', '.').replace('[', '.').replace(']', '.').split(sep)
            parts = [p for p in parts if p]  # Remove empty parts
            
            current = result
            for i, part in enumerate(parts[:-1]):
                next_part = parts[i + 1] if i + 1 < len(parts) else None
                
                if part.isdigit():
                    part = int(part)
                    if not isinstance(current, list):
                        current = []
                    while len(current) <= part:
                        current.append({})
                else:
                    if part not in current:
                        current[part] = [] if (next_part and next_part.isdigit()) else {}
                
                current = current[part] if not isinstance(current, list) else current[part]
            
            # Set final value
            final = parts[-1]
            if final.isdigit():
                final = int(final)
                if isinstance(current, list):
                    while len(current) <= final:
                        current.append(None)
                    current[final] = value
            else:
                current[final] = value
        
        return result
    
    def merge(self, *dicts: Dict, strategy: str = "deep") -> Dict[str, Any]:
        """Merge multiple dictionaries."""
        result = {}
        
        for d in dicts:
            if strategy == "shallow":
                result.update(d)
            elif strategy == "deep":
                result = self._deep_merge(result, d)
            elif strategy == "union":
                result = self._union_merge(result, d)
        
        return result
    
    def _deep_merge(self, base: Dict, overlay: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = deepcopy(base)
        
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        
        return result
    
    def _union_merge(self, base: Dict, overlay: Dict) -> Dict:
        """Union merge (combine arrays)."""
        result = deepcopy(base)
        
        for key, value in overlay.items():
            if key in result:
                if isinstance(result[key], list) and isinstance(value, list):
                    result[key] = result[key] + value
                elif isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._union_merge(result[key], value)
                else:
                    result[key] = deepcopy(value)
            else:
                result[key] = deepcopy(value)
        
        return result
    
    def query(self, data: Any = None, condition: callable = None) -> List[Any]:
        """Query JSON data with a condition function."""
        data = data or self.data
        results = []
        
        def _traverse(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    if condition is None or condition(v, new_path):
                        results.append({"path": new_path, "value": v})
                    _traverse(v, new_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    new_path = f"{path}[{i}]"
                    if condition is None or condition(item, new_path):
                        results.append({"path": new_path, "value": item})
                    _traverse(item, new_path)
        
        _traverse(data)
        return results
    
    def transform(self, data: Any = None, mapping: Dict[str, str] = None) -> Any:
        """Transform JSON using key mapping."""
        data = data or self.data
        if not mapping:
            return data
        
        result = {}
        
        for old_key, new_key in mapping.items():
            value = JSONPath(old_key).get(data)
            if value is not None:
                jp = JSONPath(new_key)
                result = jp.set(result, value) or result
        
        return result
    
    def validate(self, data: Any = None, schema: Dict = None) -> Dict[str, Any]:
        """Validate JSON against a simple schema."""
        data = data or self.data
        errors = []
        
        if not schema:
            return {"valid": True, "errors": []}
        
        # Check type
        if "type" in schema:
            expected = schema["type"]
            actual = type(data).__name__
            
            type_map = {
                "object": "dict", "array": "list", "string": "str",
                "number": ["int", "float"], "integer": "int",
                "boolean": "bool", "null": "NoneType"
            }
            
            expected_types = type_map.get(expected, expected)
            if isinstance(expected_types, list):
                if actual not in expected_types:
                    errors.append(f"Expected type {expected}, got {actual}")
            elif actual != expected_types:
                errors.append(f"Expected type {expected}, got {actual}")
        
        # Check required properties
        if "required" in schema and isinstance(data, dict):
            for prop in schema["required"]:
                if prop not in data:
                    errors.append(f"Missing required property: {prop}")
        
        # Check properties
        if "properties" in schema and isinstance(data, dict):
            for prop, prop_schema in schema["properties"].items():
                if prop in data:
                    prop_result = self.validate(data[prop], prop_schema)
                    if not prop_result["valid"]:
                        errors.extend([f"{prop}: {e}" for e in prop_result["errors"]])
        
        # Check items
        if "items" in schema and isinstance(data, list):
            for i, item in enumerate(data):
                item_result = self.validate(item, schema["items"])
                if not item_result["valid"]:
                    errors.extend([f"[{i}]: {e}" for e in item_result["errors"]])
        
        # Check min/max
        if "minLength" in schema and isinstance(data, str):
            if len(data) < schema["minLength"]:
                errors.append(f"String length {len(data)} < minLength {schema['minLength']}")
        
        if "maxLength" in schema and isinstance(data, str):
            if len(data) > schema["maxLength"]:
                errors.append(f"String length {len(data)} > maxLength {schema['maxLength']}")
        
        if "minimum" in schema and isinstance(data, (int, float)):
            if data < schema["minimum"]:
                errors.append(f"Value {data} < minimum {schema['minimum']}")
        
        if "maximum" in schema and isinstance(data, (int, float)):
            if data > schema["maximum"]:
                errors.append(f"Value {data} > maximum {schema['maximum']}")
        
        if "minItems" in schema and isinstance(data, list):
            if len(data) < schema["minItems"]:
                errors.append(f"Array length {len(data)} < minItems {schema['minItems']}")
        
        if "maxItems" in schema and isinstance(data, list):
            if len(data) > schema["maxItems"]:
                errors.append(f"Array length {len(data)} > maxItems {schema['maxItems']}")
        
        # Check enum
        if "enum" in schema:
            if data not in schema["enum"]:
                errors.append(f"Value {data} not in enum {schema['enum']}")
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    def diff(self, data1: Any, data2: Any) -> Dict[str, Any]:
        """Compare two JSON objects."""
        differences = []
        
        def _compare(a, b, path=""):
            if type(a) != type(b):
                differences.append({
                    "path": path,
                    "type": "type_mismatch",
                    "old": type(a).__name__,
                    "new": type(b).__name__
                })
                return
            
            if isinstance(a, dict):
                all_keys = set(a.keys()) | set(b.keys())
                for key in all_keys:
                    new_path = f"{path}.{key}" if path else key
                    if key not in a:
                        differences.append({"path": new_path, "type": "added", "value": b[key]})
                    elif key not in b:
                        differences.append({"path": new_path, "type": "removed", "value": a[key]})
                    else:
                        _compare(a[key], b[key], new_path)
            
            elif isinstance(a, list):
                for i in range(max(len(a), len(b))):
                    new_path = f"{path}[{i}]"
                    if i >= len(a):
                        differences.append({"path": new_path, "type": "added", "value": b[i]})
                    elif i >= len(b):
                        differences.append({"path": new_path, "type": "removed", "value": a[i]})
                    else:
                        _compare(a[i], b[i], new_path)
            
            elif a != b:
                differences.append({
                    "path": path,
                    "type": "changed",
                    "old": a,
                    "new": b
                })
        
        _compare(data1, data2)
        
        return {
            "equal": len(differences) == 0,
            "differences": differences,
            "summary": {
                "added": len([d for d in differences if d["type"] == "added"]),
                "removed": len([d for d in differences if d["type"] == "removed"]),
                "changed": len([d for d in differences if d["type"] == "changed"])
            }
        }


def execute(
    filepath: str = None,
    json_string: str = None,
    operation: str = "parse",
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Handle JSON data operations.
    
    Args:
        filepath: Path to JSON file
        json_string: JSON string
        operation: Operation (parse/stringify/query/path/flatten/merge/transform/validate/diff)
        output_file: Output file path
    
    Returns:
        Operation results
    """
    handler = JSONHandler()
    
    # Load data first if needed
    if filepath:
        handler.parse_file(filepath)
    elif json_string:
        handler.parse(json_string)
    
    if operation == "parse":
        if handler.data is None:
            return {"success": False, "error": "No JSON data provided"}
        return {
            "success": True,
            "data": handler.data
        }
    
    elif operation == "stringify":
        data = kwargs.get('data', handler.data)
        return {
            "success": True,
            "json": handler.stringify(data, kwargs.get('indent', 2))
        }
    
    elif operation == "query":
        condition = kwargs.get('condition')
        results = handler.query(handler.data, condition)
        return {
            "success": True,
            "results": results,
            "count": len(results)
        }
    
    elif operation == "path":
        path = kwargs.get('path')
        if not path:
            return {"success": False, "error": "path required"}
        
        if kwargs.get('set'):
            handler.data = handler.set_path(path, kwargs.get('value'))
            return {"success": True, "data": handler.data}
        else:
            return {
                "success": True,
                "value": handler.get_path(path)
            }
    
    elif operation == "flatten":
        return {
            "success": True,
            "flattened": handler.flatten()
        }
    
    elif operation == "unflatten":
        flat = kwargs.get('flat_dict')
        if not flat:
            return {"success": False, "error": "flat_dict required"}
        return {
            "success": True,
            "data": handler.unflatten(flat)
        }
    
    elif operation == "merge":
        dicts = kwargs.get('dicts', [])
        strategy = kwargs.get('strategy', 'deep')
        return {
            "success": True,
            "merged": handler.merge(*dicts, strategy=strategy)
        }
    
    elif operation == "transform":
        mapping = kwargs.get('mapping')
        if not mapping:
            return {"success": False, "error": "mapping required"}
        return {
            "success": True,
            "transformed": handler.transform(handler.data, mapping)
        }
    
    elif operation == "validate":
        schema = kwargs.get('schema')
        result = handler.validate(handler.data, schema)
        return {
            "success": True,
            "valid": result["valid"],
            "errors": result["errors"]
        }
    
    elif operation == "diff":
        data2 = kwargs.get('data2')
        if data2 is None:
            return {"success": False, "error": "data2 required for diff"}
        
        result = handler.diff(handler.data, data2)
        return {
            "success": True,
            "equal": result["equal"],
            "differences": result["differences"],
            "summary": result["summary"]
        }
    
    elif operation == "write":
        if not output_file:
            return {"success": False, "error": "output_file required"}
        
        handler.write_file(output_file, kwargs.get('data'))
        return {
            "success": True,
            "output_file": output_file
        }
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
