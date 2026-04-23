"""
YAML Manager Skill
Process and manipulate YAML configurations.
"""

import os
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

METADATA = {
    "name": "yaml-manager",
    "description": "Parse, modify, and manage YAML configuration files",
    "category": "data",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["yaml", "parse yaml", "yaml config", "yaml file"],
    "dependencies": [],
    "tags": ["yaml", "configuration", "parsing", "settings"]
}

SKILL_NAME = "yaml-manager"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "data"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


class YAMLParser:
    """Simple YAML parser and serializer."""
    
    def __init__(self):
        self.data: Any = None
        self.indent: int = 2
    
    def parse_string(self, yaml_string: str) -> Any:
        """Parse YAML string."""
        # Simple YAML parser implementation
        self.data = self._parse_yaml(yaml_string)
        return self.data
    
    def parse_file(self, filepath: str) -> Any:
        """Parse YAML file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.data = self._parse_yaml(content)
        return self.data
    
    def _parse_yaml(self, content: str) -> Any:
        """Parse YAML content."""
        lines = content.split('\n')
        return self._parse_lines(lines, 0, 0)[0]
    
    def _parse_lines(self, lines: List[str], start: int, base_indent: int) -> tuple:
        """Parse lines starting at given index."""
        result = {}
        i = start
        
        while i < len(lines):
            line = lines[i]
            
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                i += 1
                continue
            
            # Calculate indentation
            current_indent = len(line) - len(line.lstrip())
            
            # Check if we've dedented
            if current_indent < base_indent:
                break
            
            # Parse key-value pair
            stripped = line.strip()
            
            if ':' in stripped:
                colon_pos = stripped.index(':')
                key = stripped[:colon_pos].strip()
                value_part = stripped[colon_pos + 1:].strip()
                
                if value_part:
                    # Inline value
                    value = self._parse_value(value_part)
                    result[key] = value
                    i += 1
                else:
                    # Nested block or list
                    i += 1
                    if i < len(lines):
                        next_line = lines[i]
                        next_stripped = next_line.strip()
                        next_indent = len(next_line) - len(next_line.lstrip())
                        
                        if next_stripped.startswith('- '):
                            # It's a list
                            list_result, i = self._parse_list(lines, i, next_indent)
                            result[key] = list_result
                        elif next_indent > current_indent:
                            # Nested dict
                            nested, i = self._parse_lines(lines, i, next_indent)
                            result[key] = nested
                        else:
                            result[key] = None
                    else:
                        result[key] = None
            else:
                i += 1
        
        return result, i
    
    def _parse_list(self, lines: List[str], start: int, base_indent: int) -> tuple:
        """Parse YAML list."""
        result = []
        i = start
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped or stripped.startswith('#'):
                i += 1
                continue
            
            current_indent = len(line) - len(line.lstrip())
            
            if current_indent < base_indent:
                break
            
            if stripped.startswith('- '):
                value_part = stripped[2:].strip()
                
                if value_part:
                    if ':' in value_part:
                        # Inline dict in list item
                        colon_pos = value_part.index(':')
                        inline_key = value_part[:colon_pos].strip()
                        inline_value = value_part[colon_pos + 1:].strip()
                        
                        if inline_value:
                            result.append({inline_key: self._parse_value(inline_value)})
                            i += 1
                        else:
                            # Multi-line dict in list
                            i += 1
                            if i < len(lines):
                                next_indent = len(lines[i]) - len(lines[i].lstrip())
                                if next_indent > current_indent:
                                    nested, i = self._parse_lines(lines, i, next_indent)
                                    result[-1][inline_key] = nested
                                else:
                                    result[-1][inline_key] = None
                            else:
                                result[-1][inline_key] = None
                    else:
                        result.append(self._parse_value(value_part))
                        i += 1
                else:
                    # Empty list item or nested structure
                    i += 1
            else:
                break
        
        return result, i
    
    def _parse_value(self, value: str) -> Any:
        """Parse a YAML value."""
        value = value.strip()
        
        # Remove quotes
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        # Boolean
        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False
        
        # Null
        if value.lower() in ('null', '~', ''):
            return None
        
        # Number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        # Date/time (basic detection)
        if len(value) == 10 and value.count('-') == 2:
            try:
                import datetime
                return datetime.date(*map(int, value.split('-')))
            except:
                pass
        
        return value
    
    def stringify(self, data: Any = None, indent: int = 2) -> str:
        """Convert data to YAML string."""
        data = data or self.data
        return self._to_yaml(data, 0, indent)
    
    def _to_yaml(self, data: Any, level: int, indent: int) -> str:
        """Convert data to YAML string."""
        prefix = ' ' * (level * indent)
        
        if data is None:
            return 'null'
        
        if isinstance(data, bool):
            return 'true' if data else 'false'
        
        if isinstance(data, (int, float)):
            return str(data)
        
        if isinstance(data, str):
            # Check if quoting needed
            if any(c in data for c in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']):
                return f'"{data}"'
            if data.lower() in ('true', 'false', 'null', 'yes', 'no'):
                return f'"{data}"'
            if data.isdigit() or (data.startswith('-') and data[1:].isdigit()):
                return f'"{data}"'
            return data
        
        if isinstance(data, list):
            if not data:
                return '[]'
            
            lines = []
            for item in data:
                if isinstance(item, dict):
                    lines.append(f"{prefix}- ")
                    for k, v in item.items():
                        val_yaml = self._to_yaml(v, level + 2, indent)
                        if isinstance(v, (dict, list)) and v:
                            lines.append(f"{prefix}  {k}:")
                            lines.append(f"{' ' * ((level + 2) * indent)}{val_yaml}")
                        else:
                            lines.append(f"{prefix}  {k}: {val_yaml}")
                else:
                    lines.append(f"{prefix}- {self._to_yaml(item, level + 1, indent)}")
            
            return '\n'.join(lines)
        
        if isinstance(data, dict):
            if not data:
                return '{}'
            
            lines = []
            for key, value in data.items():
                val_yaml = self._to_yaml(value, level + 1, indent)
                
                if isinstance(value, (dict, list)) and value:
                    lines.append(f"{prefix}{key}:")
                    lines.append(val_yaml)
                else:
                    lines.append(f"{prefix}{key}: {val_yaml}")
            
            return '\n'.join(lines)
        
        return str(data)
    
    def write_file(self, filepath: str, data: Any = None, indent: int = 2) -> str:
        """Write YAML to file."""
        content = self.stringify(data, indent)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
    
    def get(self, path: str = None) -> Any:
        """Get value at dot-notation path."""
        if self.data is None:
            return None
        
        if not path:
            return self.data
        
        parts = path.split('.')
        current = self.data
        
        for part in parts:
            if '[' in part:
                # Array index
                key = part[:part.index('[')]
                idx = int(part[part.index('[') + 1:part.index(']')])
                
                if key:
                    current = current.get(key, [])
                if isinstance(current, list) and 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
        
        return current
    
    def set(self, path: str, value: Any) -> bool:
        """Set value at dot-notation path."""
        if self.data is None:
            self.data = {}
        
        parts = path.split('.')
        current = self.data
        
        for part in parts[:-1]:
            if '[' in part:
                key = part[:part.index('[')]
                idx = int(part[part.index('[') + 1:part.index(']')])
                
                if key:
                    if key not in current:
                        current[key] = []
                    current = current[key]
                
                if isinstance(current, list):
                    while len(current) <= idx:
                        current.append({})
                    current = current[idx]
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        # Set final value
        final = parts[-1]
        if '[' in final:
            key = final[:final.index('[')]
            idx = int(final[final.index('[') + 1:final.index(']')])
            
            if key:
                if key not in current:
                    current[key] = []
                current = current[key]
            
            if isinstance(current, list):
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
        else:
            current[final] = value
        
        return True
    
    def merge(self, other_data: Dict, strategy: str = "deep") -> Dict:
        """Merge other data into current data."""
        if self.data is None:
            self.data = {}
        
        if strategy == "shallow":
            self.data.update(other_data)
        elif strategy == "deep":
            self.data = self._deep_merge(self.data, other_data)
        
        return self.data
    
    def _deep_merge(self, base: Dict, overlay: Dict) -> Dict:
        """Deep merge dictionaries."""
        result = dict(base)
        
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def validate_schema(self, schema: Dict) -> Dict[str, Any]:
        """Validate data against a schema."""
        errors = []
        
        if "required" in schema:
            for field in schema["required"]:
                if field not in (self.data or {}):
                    errors.append(f"Missing required field: {field}")
        
        if "properties" in schema:
            for field, field_schema in schema["properties"].items():
                if field in (self.data or {}):
                    value = self.data[field]
                    expected_type = field_schema.get("type")
                    
                    if expected_type == "string" and not isinstance(value, str):
                        errors.append(f"Field '{field}' should be string")
                    elif expected_type == "integer" and not isinstance(value, int):
                        errors.append(f"Field '{field}' should be integer")
                    elif expected_type == "number" and not isinstance(value, (int, float)):
                        errors.append(f"Field '{field}' should be number")
                    elif expected_type == "boolean" and not isinstance(value, bool):
                        errors.append(f"Field '{field}' should be boolean")
                    elif expected_type == "array" and not isinstance(value, list):
                        errors.append(f"Field '{field}' should be array")
                    elif expected_type == "object" and not isinstance(value, dict):
                        errors.append(f"Field '{field}' should be object")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }


def execute(
    filepath: str = None,
    yaml_string: str = None,
    operation: str = "parse",
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Process YAML files.
    
    Args:
        filepath: Path to YAML file
        yaml_string: YAML string
        operation: Operation (parse/stringify/get/set/merge/validate)
        output_file: Output file path
    
    Returns:
        Operation results
    """
    parser = YAMLParser()
    
    # Load YAML first
    if filepath:
        parser.parse_file(filepath)
    elif yaml_string:
        parser.parse_string(yaml_string)
    
    if operation == "parse":
        if parser.data is None:
            return {"success": False, "error": "No YAML data provided"}
        return {
            "success": True,
            "data": parser.data
        }
    
    elif operation == "stringify":
        data = kwargs.get('data', parser.data)
        indent = kwargs.get('indent', 2)
        return {
            "success": True,
            "yaml": parser.stringify(data, indent)
        }
    
    elif operation == "get":
        path = kwargs.get('path')
        return {
            "success": True,
            "value": parser.get(path)
        }
    
    elif operation == "set":
        path = kwargs.get('path')
        value = kwargs.get('value')
        
        if not path:
            return {"success": False, "error": "path required"}
        
        parser.set(path, value)
        return {
            "success": True,
            "data": parser.data
        }
    
    elif operation == "merge":
        other_data = kwargs.get('data')
        strategy = kwargs.get('strategy', 'deep')
        
        if other_data is None:
            return {"success": False, "error": "data required for merge"}
        
        parser.merge(other_data, strategy)
        return {
            "success": True,
            "data": parser.data
        }
    
    elif operation == "validate":
        schema = kwargs.get('schema')
        result = parser.validate_schema(schema or {})
        return {
            "success": True,
            "valid": result["valid"],
            "errors": result["errors"]
        }
    
    elif operation == "write":
        if not output_file:
            return {"success": False, "error": "output_file required"}
        
        parser.write_file(output_file, kwargs.get('data'))
        return {
            "success": True,
            "output_file": output_file
        }
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
