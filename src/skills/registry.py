#!/usr/bin/env python3
"""Skills System - Modular, extensible skill management"""
import json
import asyncio
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from datetime import datetime
import importlib.util
import inspect

class Skill:
    """Base skill class"""
    
    name: str = "unnamed"
    description: str = "No description"
    version: str = "1.0.0"
    author: str = "Unknown"
    triggers: List[str] = []
    
    def __init__(self, context: Dict = None):
        self.context = context or {}
        self.enabled = True
    
    def can_execute(self, query: str) -> bool:
        """Check if skill can handle the query"""
        if not self.enabled:
            return False
        query_lower = query.lower()
        return any(trigger in query_lower for trigger in self.triggers)
    
    async def execute(self, query: str, context: Dict = None) -> Dict:
        """Execute the skill. Override in subclass."""
        raise NotImplementedError("Skill must implement execute method")
    
    def enable(self):
        """Enable the skill"""
        self.enabled = True
    
    def disable(self):
        """Disable the skill"""
        self.enabled = False


class SkillRegistry:
    """Registry for managing skills"""
    
    def __init__(self, skills_dir: str = None):
        self.skills_dir = Path(skills_dir or (Path.home() / ".sentience" / "skills"))
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, Skill] = {}
        self._tool_functions: Dict[str, Callable] = {}
    
    def register(self, skill: Skill) -> bool:
        """Register a skill"""
        if not isinstance(skill, Skill):
            return False
        
        self._skills[skill.name] = skill
        return True
    
    def unregister(self, name: str) -> bool:
        """Unregister a skill"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Skill]:
        """Get skill by name"""
        return self._skills.get(name)
    
    def list_skills(self) -> List[Dict]:
        """List all registered skills"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "enabled": s.enabled,
                "triggers": s.triggers
            }
            for s in self._skills.values()
        ]
    
    def find_matching(self, query: str) -> List[Skill]:
        """Find skills that match a query"""
        return [s for s in self._skills.values() if s.can_execute(query)]
    
    async def execute_matching(self, query: str, context: Dict = None) -> List[Dict]:
        """Execute all skills matching a query"""
        results = []
        for skill in self.find_matching(query):
            try:
                result = await skill.execute(query, context)
                results.append({
                    "skill": skill.name,
                    "result": result
                })
            except Exception as e:
                results.append({
                    "skill": skill.name,
                    "error": str(e)
                })
        return results
    
    def register_tool(self, name: str, func: Callable, description: str = None):
        """Register a tool function that can be called by AI"""
        self._tool_functions[name] = {
            "function": func,
            "description": description or func.__doc__ or "No description"
        }
    
    def get_tool_schema(self) -> List[Dict]:
        """Get tool schema for all registered tools"""
        tools = []
        for name, data in self._tool_functions.items():
            func = data["function"]
            sig = inspect.signature(func)
            
            # Build parameters schema
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                    
                param_type = "string"  # Default
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == int:
                        param_type = "integer"
                    elif param.annotation == float:
                        param_type = "number"
                    elif param.annotation == bool:
                        param_type = "boolean"
                    elif param.annotation == list:
                        param_type = "array"
                    elif param.annotation == dict:
                        param_type = "object"
                
                properties[param_name] = {"type": param_type}
                
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
            
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": data["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })
        
        return tools
    
    async def call_tool(self, name: str, **kwargs) -> Dict:
        """Call a registered tool function"""
        if name not in self._tool_functions:
            return {"success": False, "error": f"Tool not found: {name}"}
        
        try:
            func = self._tool_functions[name]["function"]
            
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)
            
            if isinstance(result, dict):
                return result
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def save_skill(self, skill: Skill) -> bool:
        """Save skill configuration to file"""
        config_path = self.skills_dir / f"{skill.name}.json"
        try:
            config = {
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
                "author": skill.author,
                "triggers": skill.triggers,
                "enabled": skill.enabled,
                "saved_at": datetime.now().isoformat()
            }
            config_path.write_text(json.dumps(config, indent=2))
            return True
        except Exception as e:
            print(f"Error saving skill: {e}")
            return False
    
    def load_skill(self, name: str) -> Optional[Dict]:
        """Load skill configuration from file"""
        config_path = self.skills_dir / f"{name}.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except:
                return None
        return None
    
    def load_skill_module(self, filepath: str) -> Optional[Skill]:
        """Load skill from Python module file"""
        path = Path(filepath)
        if not path.exists():
            return None
        
        try:
            spec = importlib.util.spec_from_file_location(path.stem, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find Skill subclass in module
            for item in dir(module):
                obj = getattr(module, item)
                if (inspect.isclass(obj) and 
                    issubclass(obj, Skill) and 
                    obj is not Skill):
                    return obj()
            
            return None
        except Exception as e:
            print(f"Error loading skill module: {e}")
            return None


# Built-in skills
class WebSearchSkill(Skill):
    """Web search skill"""
    name = "web_search"
    description = "Search the web for information"
    triggers = ["search", "look up", "find", "google"]
    
    async def execute(self, query: str, context: Dict = None) -> Dict:
        # Extract search query
        search_query = query
        for trigger in self.triggers:
            search_query = search_query.lower().replace(trigger, "", 1).strip()
        
        # This would integrate with a search API
        return {
            "success": True,
            "message": f"Would search for: {search_query}",
            "query": search_query
        }


class CodeSkill(Skill):
    """Code generation and analysis skill"""
    name = "code"
    description = "Generate, analyze, and debug code"
    triggers = ["code", "function", "script", "debug", "fix"]
    
    async def execute(self, query: str, context: Dict = None) -> Dict:
        return {
            "success": True,
            "message": "Code skill triggered",
            "query": query
        }


class FileSkill(Skill):
    """File operations skill"""
    name = "files"
    description = "Read, write, and manage files"
    triggers = ["file", "read", "write", "create", "delete", "folder", "directory"]
    
    async def execute(self, query: str, context: Dict = None) -> Dict:
        return {
            "success": True,
            "message": "File skill triggered",
            "query": query
        }


class SystemSkill(Skill):
    """System operations skill"""
    name = "system"
    description = "Run system commands and manage processes"
    triggers = ["run", "execute", "command", "terminal", "shell", "process"]
    
    async def execute(self, query: str, context: Dict = None) -> Dict:
        return {
            "success": True,
            "message": "System skill triggered",
            "query": query
        }


# Tool definitions for AI
SKILL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "skill_list",
            "description": "List all available skills",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_enable",
            "description": "Enable a skill",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_disable",
            "description": "Disable a skill",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"}
                },
                "required": ["name"]
            }
        }
    }
]

# Singleton
_skill_registry: Optional[SkillRegistry] = None

def get_skill_registry() -> SkillRegistry:
    """Get or create skill registry"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
        # Register built-in skills
        _skill_registry.register(WebSearchSkill())
        _skill_registry.register(CodeSkill())
        _skill_registry.register(FileSkill())
        _skill_registry.register(SystemSkill())
    return _skill_registry

def execute_skill_tool(name: str, args: Dict) -> Dict:
    """Execute skill tool by name"""
    registry = get_skill_registry()
    
    if name == "skill_list":
        return {"success": True, "skills": registry.list_skills()}
    elif name == "skill_enable":
        skill = registry.get(args.get("name"))
        if skill:
            skill.enable()
            return {"success": True, "message": f"Skill {skill.name} enabled"}
        return {"success": False, "error": "Skill not found"}
    elif name == "skill_disable":
        skill = registry.get(args.get("name"))
        if skill:
            skill.disable()
            return {"success": True, "message": f"Skill {skill.name} disabled"}
        return {"success": False, "error": "Skill not found"}
    else:
        return {"success": False, "error": f"Unknown skill tool: {name}"}
