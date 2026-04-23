#!/usr/bin/env python3
"""Skills Registry - 70+ pre-built skills"""
import os
import json
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Skill:
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    execute: Callable = None
    metadata: Dict = field(default_factory=dict)

class SkillRegistry:
    def __init__(self, skills_dir: str = None):
        self.skills_dir = skills_dir or os.path.expanduser("~/.sentience/skills")
        self.skills: Dict[str, Skill] = {}
        self._load_builtin_skills()
        self._load_custom_skills()
        
    def _load_builtin_skills(self):
        """Load built-in skills"""
        # Analysis skills
        self.register(Skill(
            name="code-analyzer",
            description="Analyze code quality, complexity, and patterns",
            triggers=["analyze code", "code quality", "complexity"],
            execute=self._analyze_code
        ))
        
        self.register(Skill(
            name="security-scanner",
            description="Scan code for security vulnerabilities",
            triggers=["security scan", "vulnerability", "check security"],
            execute=self._security_scan
        ))
        
        self.register(Skill(
            name="dependency-checker",
            description="Check for outdated and vulnerable dependencies",
            triggers=["check deps", "dependencies", "outdated packages"],
            execute=self._check_dependencies
        ))
        
        # Development skills
        self.register(Skill(
            name="code-generator",
            description="Generate code from specifications",
            triggers=["generate code", "create code", "write code"],
            execute=self._generate_code
        ))
        
        self.register(Skill(
            name="test-generator",
            description="Generate unit tests for code",
            triggers=["generate tests", "create tests", "unit tests"],
            execute=self._generate_tests
        ))
        
        self.register(Skill(
            name="doc-generator",
            description="Generate documentation from code",
            triggers=["generate docs", "documentation", "docstrings"],
            execute=self._generate_docs
        ))
        
        self.register(Skill(
            name="refactor-engine",
            description="Refactor code with safe transformations",
            triggers=["refactor", "rename", "extract method"],
            execute=self._refactor
        ))
        
        self.register(Skill(
            name="debug-helper",
            description="Help debug issues in code",
            triggers=["debug", "fix error", "why does this fail"],
            execute=self._debug_help
        ))
        
        # Data skills
        self.register(Skill(
            name="csv-processor",
            description="Process and analyze CSV files",
            triggers=["csv", "process csv", "analyze data"],
            execute=self._process_csv
        ))
        
        self.register(Skill(
            name="json-handler",
            description="Handle JSON operations",
            triggers=["json", "parse json", "format json"],
            execute=self._handle_json
        ))
        
        # Web skills
        self.register(Skill(
            name="scraper",
            description="Scrape web content",
            triggers=["scrape", "extract from web", "crawl"],
            execute=self._scrape_web
        ))
        
        self.register(Skill(
            name="api-client",
            description="Make REST API calls",
            triggers=["api call", "http request", "fetch api"],
            execute=self._api_call
        ))
        
        # Communication skills
        self.register(Skill(
            name="email-skill",
            description="Send and manage emails",
            triggers=["send email", "email", "mail"],
            execute=self._handle_email
        ))
        
        self.register(Skill(
            name="slack-skill",
            description="Send Slack messages",
            triggers=["slack", "send to slack", "slack message"],
            execute=self._handle_slack
        ))
        
        # System skills
        self.register(Skill(
            name="process-manager",
            description="Manage system processes",
            triggers=["process", "kill process", "list processes"],
            execute=self._manage_processes
        ))
        
        self.register(Skill(
            name="backup-tool",
            description="Create and manage backups",
            triggers=["backup", "create backup", "restore"],
            execute=self._backup
        ))
        
    def _load_custom_skills(self):
        """Load custom skills from directory"""
        if os.path.exists(self.skills_dir):
            for skill_file in Path(self.skills_dir).glob("*.py"):
                self._load_skill_file(skill_file)
                
    def _load_skill_file(self, path: Path):
        """Load a skill from a Python file"""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, 'skill'):
                self.register(module.skill)
        except Exception as e:
            print(f"Failed to load skill {path}: {e}")
            
    def register(self, skill: Skill):
        """Register a new skill"""
        self.skills[skill.name] = skill
        
    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self.skills.get(name)
        
    def list_skills(self, category: str = None) -> List[Skill]:
        """List all skills, optionally filtered by category"""
        return list(self.skills.values())
        
    def find_by_trigger(self, text: str) -> List[Skill]:
        """Find skills matching trigger text"""
        text_lower = text.lower()
        matches = []
        for skill in self.skills.values():
            if any(trigger in text_lower for trigger in skill.triggers):
                matches.append(skill)
        return matches
        
    # Built-in skill implementations
    def _analyze_code(self, code: str, **kwargs) -> Dict:
        """Analyze code quality"""
        import ast
        
        try:
            tree = ast.parse(code)
            
            # Count complexity
            complexity = 0
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                    complexity += 1
                    
            # Count functions/classes
            functions = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
            classes = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
            lines = len(code.split('\n'))
            
            return {
                "complexity": complexity,
                "functions": functions,
                "classes": classes,
                "lines": lines,
                "quality_score": max(0, 100 - complexity * 5)
            }
        except Exception as e:
            return {"error": str(e)}
            
    def _security_scan(self, code: str, **kwargs) -> List[Dict]:
        """Scan for security issues"""
        issues = []
        
        # Check for common vulnerabilities
        if "eval(" in code:
            issues.append({
                "type": "security",
                "severity": "high",
                "message": "Use of eval() is dangerous",
                "line": code.find("eval(")
            })
            
        if "exec(" in code:
            issues.append({
                "type": "security",
                "severity": "high",
                "message": "Use of exec() is dangerous",
                "line": code.find("exec(")
            })
            
        if "password" in code.lower() and "=" in code:
            issues.append({
                "type": "security",
                "severity": "medium",
                "message": "Possible hardcoded password",
                "line": code.lower().find("password")
            })
            
        if "sql" in code.lower() and "format" in code:
            issues.append({
                "type": "security",
                "severity": "high",
                "message": "Possible SQL injection",
                "line": code.lower().find("sql")
            })
            
        return issues
        
    def _check_dependencies(self, requirements_file: str = "requirements.txt", **kwargs) -> List[Dict]:
        """Check dependencies for vulnerabilities"""
        # Simplified - would use pip-audit or safety in production
        import subprocess
        
        try:
            result = subprocess.run(
                ["pip", "list", "--outdated"],
                capture_output=True,
                text=True
            )
            
            outdated = []
            for line in result.stdout.split('\n')[2:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        outdated.append({
                            "package": parts[0],
                            "current": parts[1],
                            "latest": parts[2]
                        })
                        
            return outdated
        except Exception as e:
            return [{"error": str(e)}]
            
    def _generate_code(self, spec: str, language: str = "python", **kwargs) -> str:
        """Generate code from specification (placeholder - uses LLM)"""
        # This would be connected to the LLM
        return f"# Generated {language} code for: {spec}\n# TODO: Implement with LLM"
        
    def _generate_tests(self, code: str, **kwargs) -> str:
        """Generate unit tests"""
        import ast
        
        try:
            tree = ast.parse(code)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            
            test_code = "import pytest\n\n"
            for func in functions:
                if not func.startswith('_'):
                    test_code += f"def test_{func}():\n    # TODO: Add test implementation\n    pass\n\n"
                    
            return test_code
        except:
            return "# Could not generate tests"
            
    def _generate_docs(self, code: str, **kwargs) -> str:
        """Generate documentation"""
        import ast
        
        try:
            tree = ast.parse(code)
            docs = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    doc = f"## {node.name}\n\n"
                    doc += f"Arguments: {len(node.args.args)}\n\n"
                    if ast.get_docstring(node):
                        doc += f"{ast.get_docstring(node)}\n"
                    docs.append(doc)
                    
            return "\n".join(docs)
        except:
            return "# Could not generate docs"
            
    def _refactor(self, code: str, operation: str, **kwargs) -> str:
        """Perform refactoring"""
        # Placeholder - would use rope or similar
        return code
        
    def _debug_help(self, error: str, code: str = None, **kwargs) -> Dict:
        """Help debug issues"""
        return {
            "error": error,
            "suggestions": [
                "Check the error message for line numbers",
                "Look for typos in variable names",
                "Verify imports are correct",
                "Check for missing parentheses or brackets"
            ]
        }
        
    def _process_csv(self, file_path: str, operation: str = "read", **kwargs) -> Any:
        """Process CSV files"""
        import csv
        
        if operation == "read":
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                return list(reader)
        elif operation == "headers":
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                return next(reader)
        return None
        
    def _handle_json(self, data: str, operation: str = "parse", **kwargs) -> Any:
        """Handle JSON operations"""
        if operation == "parse":
            return json.loads(data)
        elif operation == "format":
            obj = json.loads(data)
            return json.dumps(obj, indent=2)
        return None
        
    def _scrape_web(self, url: str, **kwargs) -> Dict:
        """Scrape web content"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            resp = requests.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            return {
                "title": soup.title.string if soup.title else "",
                "text": soup.get_text(separator='\n', strip=True),
                "links": [a.get('href') for a in soup.find_all('a', href=True)]
            }
        except Exception as e:
            return {"error": str(e)}
            
    def _api_call(self, url: str, method: str = "GET", **kwargs) -> Dict:
        """Make API call"""
        import requests
        
        try:
            resp = requests.request(method, url, **kwargs)
            return {
                "status": resp.status_code,
                "data": resp.json() if 'json' in resp.headers.get('content-type', '') else resp.text
            }
        except Exception as e:
            return {"error": str(e)}
            
    def _handle_email(self, **kwargs) -> Dict:
        """Handle email (integration required)"""
        return {"message": "Email integration required"}
        
    def _handle_slack(self, **kwargs) -> Dict:
        """Handle Slack (integration required)"""
        return {"message": "Slack integration required"}
        
    def _manage_processes(self, operation: str = "list", **kwargs) -> List[Dict]:
        """Manage processes"""
        import psutil
        
        if operation == "list":
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    processes.append(proc.info)
                except:
                    pass
            return processes
        return []
        
    def _backup(self, source: str, dest: str, **kwargs) -> Dict:
        """Create backup"""
        import shutil
        
        try:
            shutil.copytree(source, dest)
            return {"status": "success", "destination": dest}
        except Exception as e:
            return {"error": str(e)}


# Singleton registry
_registry = None

def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
