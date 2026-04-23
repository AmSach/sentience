"""
XML Parser Skill
Process and manipulate XML data.
"""

import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from xml.dom import minidom

METADATA = {
    "name": "xml-parser",
    "description": "Parse, transform, and manipulate XML documents",
    "category": "data",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["parse xml", "xml file", "xml data", "xml document"],
    "dependencies": [],
    "tags": ["xml", "parsing", "transformation", "xpath"]
}

SKILL_NAME = "xml-parser"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "data"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class XMLNode:
    tag: str
    text: str
    attributes: Dict[str, str]
    children: List['XMLNode']


class XMLParser:
    """Parse and manipulate XML documents."""
    
    def __init__(self):
        self.root: Optional[ET.Element] = None
        self.namespaces: Dict[str, str] = {}
    
    def parse_string(self, xml_string: str) -> ET.Element:
        """Parse XML string."""
        self.root = ET.fromstring(xml_string)
        self._extract_namespaces()
        return self.root
    
    def parse_file(self, filepath: str) -> ET.Element:
        """Parse XML file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        tree = ET.parse(filepath)
        self.root = tree.getroot()
        self._extract_namespaces()
        return self.root
    
    def _extract_namespaces(self):
        """Extract namespace declarations from document."""
        self.namespaces = {}
        
        if self.root is not None:
            # Check root element for namespaces
            for key, value in self.root.attrib.items():
                if key.startswith('xmlns'):
                    if ':' in key:
                        prefix = key.split(':')[1]
                    else:
                        prefix = ''
                    self.namespaces[prefix] = value
    
    def find(self, path: str) -> Optional[ET.Element]:
        """Find element by path."""
        if self.root is None:
            return None
        return self.root.find(path, self.namespaces)
    
    def findall(self, path: str) -> List[ET.Element]:
        """Find all elements matching path."""
        if self.root is None:
            return []
        return self.root.findall(path, self.namespaces)
    
    def xpath(self, expression: str) -> List[Any]:
        """Simple XPath-like query (limited support)."""
        # Simplified XPath implementation
        results = []
        
        if not expression.startswith('/'):
            expression = '//' + expression
        
        # Convert XPath to ElementTree path
        et_path = expression.lstrip('/')
        et_path = et_path.replace('//', './/')
        
        return self.findall(et_path)
    
    def to_dict(self, element: ET.Element = None) -> Dict[str, Any]:
        """Convert XML element to dictionary."""
        element = element or self.root
        
        if element is None:
            return {}
        
        result = {
            '_tag': element.tag,
            '_text': (element.text or '').strip(),
            '_attributes': dict(element.attrib)
        }
        
        # Process children
        children = {}
        for child in element:
            child_dict = self.to_dict(child)
            child_tag = child.tag
            
            # Handle namespaced tags
            if '}' in child_tag:
                child_tag = child_tag.split('}')[1]
            
            if child_tag in children:
                if not isinstance(children[child_tag], list):
                    children[child_tag] = [children[child_tag]]
                children[child_tag].append(child_dict)
            else:
                children[child_tag] = child_dict
        
        if children:
            result['_children'] = children
        
        return result
    
    def to_json(self, element: ET.Element = None, indent: int = 2) -> str:
        """Convert XML to JSON string."""
        import json
        data = self.to_dict(element)
        return json.dumps(data, indent=indent, ensure_ascii=False)
    
    def from_dict(self, data: Dict[str, Any]) -> ET.Element:
        """Create XML element from dictionary."""
        tag = data.get('_tag', 'root')
        element = ET.Element(tag)
        
        # Add attributes
        for key, value in data.get('_attributes', {}).items():
            element.set(key, str(value))
        
        # Add text
        if '_text' in data:
            element.text = data['_text']
        
        # Add children
        children = data.get('_children', {})
        for child_tag, child_data in children.items():
            if isinstance(child_data, list):
                for item in child_data:
                    child_element = self.from_dict(item)
                    element.append(child_element)
            else:
                child_element = self.from_dict(child_data)
                element.append(child_element)
        
        return element
    
    def get_text(self, path: str) -> str:
        """Get text content of element at path."""
        element = self.find(path)
        return (element.text or '').strip() if element is not None else ""
    
    def get_attribute(self, path: str, attribute: str) -> str:
        """Get attribute value of element at path."""
        element = self.find(path)
        return element.get(attribute, '') if element is not None else ""
    
    def get_all_texts(self, path: str) -> List[str]:
        """Get text content of all elements matching path."""
        elements = self.findall(path)
        return [(e.text or '').strip() for e in elements]
    
    def get_all_attributes(self, path: str, attribute: str) -> List[str]:
        """Get attribute values from all matching elements."""
        elements = self.findall(path)
        return [e.get(attribute, '') for e in elements]
    
    def to_pretty_string(self, element: ET.Element = None) -> str:
        """Convert XML to pretty-printed string."""
        element = element or self.root
        
        if element is None:
            return ""
        
        rough_string = ET.tostring(element, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
    
    def to_string(self, element: ET.Element = None) -> str:
        """Convert XML to string."""
        element = element or self.root
        
        if element is None:
            return ""
        
        return ET.tostring(element, encoding='unicode')
    
    def write_file(self, filepath: str, element: ET.Element = None, pretty: bool = True) -> str:
        """Write XML to file."""
        content = self.to_pretty_string(element) if pretty else self.to_string(element)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
    
    def modify_element(self, path: str, text: str = None, attributes: Dict[str, str] = None) -> bool:
        """Modify an element's text or attributes."""
        element = self.find(path)
        
        if element is None:
            return False
        
        if text is not None:
            element.text = text
        
        if attributes:
            for key, value in attributes.items():
                element.set(key, value)
        
        return True
    
    def add_element(self, parent_path: str, tag: str, text: str = "", 
                   attributes: Dict[str, str] = None) -> bool:
        """Add a new element."""
        parent = self.find(parent_path)
        
        if parent is None:
            return False
        
        new_element = ET.SubElement(parent, tag)
        new_element.text = text
        
        if attributes:
            for key, value in attributes.items():
                new_element.set(key, value)
        
        return True
    
    def remove_element(self, path: str) -> bool:
        """Remove element at path."""
        element = self.find(path)
        
        if element is None:
            return False
        
        parent = self._find_parent(element)
        
        if parent is not None:
            parent.remove(element)
            return True
        
        return False
    
    def _find_parent(self, target: ET.Element, current: ET.Element = None) -> Optional[ET.Element]:
        """Find parent of an element."""
        current = current or self.root
        
        if current is None:
            return None
        
        for child in current:
            if child is target:
                return current
            result = self._find_parent(target, child)
            if result is not None:
                return result
        
        return None
    
    def extract_table(self, row_path: str, column_paths: Dict[str, str]) -> List[Dict[str, str]]:
        """Extract tabular data from XML."""
        rows = self.findall(row_path)
        results = []
        
        for row in rows:
            row_data = {}
            for col_name, col_path in column_paths.items():
                if col_path.startswith('@'):
                    # Attribute
                    attr_name = col_path[1:]
                    row_data[col_name] = row.get(attr_name, '')
                else:
                    # Element text
                    elem = row.find(col_path)
                    row_data[col_name] = (elem.text or '').strip() if elem is not None else ''
            results.append(row_data)
        
        return results


def execute(
    filepath: str = None,
    xml_string: str = None,
    operation: str = "parse",
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Process XML documents.
    
    Args:
        filepath: Path to XML file
        xml_string: XML string
        operation: Operation (parse/query/to_dict/to_json/modify/add/remove/extract)
        output_file: Output file path
    
    Returns:
        Operation results
    """
    parser = XMLParser()
    
    # Load XML first
    if filepath:
        parser.parse_file(filepath)
    elif xml_string:
        parser.parse_string(xml_string)
    
    if operation == "parse":
        if parser.root is None:
            return {"success": False, "error": "No XML data provided"}
        return {
            "success": True,
            "root_tag": parser.root.tag,
            "namespaces": parser.namespaces
        }
    
    elif operation == "query" or operation == "find":
        path = kwargs.get('path')
        if not path:
            return {"success": False, "error": "path required"}
        
        elements = parser.findall(path)
        return {
            "success": True,
            "elements": [
                {
                    "tag": e.tag,
                    "text": (e.text or '').strip(),
                    "attributes": dict(e.attrib)
                }
                for e in elements
            ],
            "count": len(elements)
        }
    
    elif operation == "get_text":
        path = kwargs.get('path')
        if not path:
            return {"success": False, "error": "path required"}
        
        return {
            "success": True,
            "text": parser.get_text(path)
        }
    
    elif operation == "get_attribute":
        path = kwargs.get('path')
        attribute = kwargs.get('attribute')
        if not path or not attribute:
            return {"success": False, "error": "path and attribute required"}
        
        return {
            "success": True,
            "value": parser.get_attribute(path, attribute)
        }
    
    elif operation == "to_dict":
        return {
            "success": True,
            "data": parser.to_dict()
        }
    
    elif operation == "to_json":
        return {
            "success": True,
            "json": parser.to_json()
        }
    
    elif operation == "to_string":
        pretty = kwargs.get('pretty', True)
        return {
            "success": True,
            "xml": parser.to_pretty_string() if pretty else parser.to_string()
        }
    
    elif operation == "modify":
        path = kwargs.get('path')
        text = kwargs.get('text')
        attributes = kwargs.get('attributes')
        
        if not path:
            return {"success": False, "error": "path required"}
        
        success = parser.modify_element(path, text, attributes)
        return {
            "success": success,
            "message": "Element modified" if success else "Element not found"
        }
    
    elif operation == "add":
        parent_path = kwargs.get('parent_path')
        tag = kwargs.get('tag')
        text = kwargs.get('text', '')
        attributes = kwargs.get('attributes')
        
        if not parent_path or not tag:
            return {"success": False, "error": "parent_path and tag required"}
        
        success = parser.add_element(parent_path, tag, text, attributes)
        return {
            "success": success,
            "message": "Element added" if success else "Parent not found"
        }
    
    elif operation == "remove":
        path = kwargs.get('path')
        if not path:
            return {"success": False, "error": "path required"}
        
        success = parser.remove_element(path)
        return {
            "success": success,
            "message": "Element removed" if success else "Element not found"
        }
    
    elif operation == "extract":
        row_path = kwargs.get('row_path')
        columns = kwargs.get('columns')
        
        if not row_path or not columns:
            return {"success": False, "error": "row_path and columns required"}
        
        data = parser.extract_table(row_path, columns)
        return {
            "success": True,
            "data": data,
            "rows": len(data)
        }
    
    elif operation == "write":
        if not output_file:
            return {"success": False, "error": "output_file required"}
        
        parser.write_file(output_file, pretty=kwargs.get('pretty', True))
        return {
            "success": True,
            "output_file": output_file
        }
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
