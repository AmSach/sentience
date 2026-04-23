"""Skill Registry — Zo-style skill loader and executor."""
import os, json, re, importlib, inspect, traceback
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent

class SkillResult:
    def __init__(self, success: bool, output: str = "", error: str = "", tools: list = None):
        self.success = success
        self.output = output
        self.error = error
        self.tools = tools or []

class Skill:
    def __init__(self, name: str, description: str, path: Path):
        self.name = name
        self.description = description
        self.path = path
        self.module = None
        self.loaded = False
        
    def load(self):
        if self.loaded:
            return True
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{self.name}", self.path)
            if spec and spec.loader:
                self.module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.module)
                self.loaded = True
                return True
        except Exception as e:
            print(f"Skill load error {self.name}: {e}")
        return False
    
    def execute(self, instruction: str, context: dict) -> SkillResult:
        if not self.loaded:
            if not self.load():
                return SkillResult(False, error=f"Failed to load skill: {self.name}")
        fn = getattr(self.module, 'execute', None)
        if not fn:
            return SkillResult(False, error=f"Skill {self.name} has no execute() function")
        try:
            result = fn(instruction, context)
            if isinstance(result, dict):
                return SkillResult(True, **result)
            return SkillResult(True, output=str(result))
        except Exception as e:
            return SkillResult(False, error=traceback.format_exc())

def load_skills() -> list:
    """Discover and load all skills from skills/ directory."""
    skills = []
    for item in SKILLS_DIR.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            meta = parse_skill_meta(item / "SKILL.md")
            skills.append(Skill(meta.get('name', item.name), meta.get('description', ''), item / "scripts" / f"{item.name}.py" if (item / "scripts").exists() else None))
    return skills

def parse_skill_meta(path: Path) -> dict:
    try:
        content = path.read_text()
        meta = {}
        if match := re.match(r'^name:\s*(.+)$', content, re.M): meta['name'] = match.group(1).strip()
        if match := re.match(r'^description:\s*(.+)$', content, re.M): meta['description'] = match.group(1).strip()
        return meta
    except: return {}

class SkillRegistry:
    def __init__(self):
        self.skills = load_skills()
        self.by_name = {s.name: s for s in self.skills}
        
    def match(self, instruction: str) -> Optional[Skill]:
        instruction_lower = instruction.lower()
        for skill in self.skills:
            keywords = skill.name.replace('-', ' ').lower().split()
            if any(kw in instruction_lower for kw in keywords):
                return skill
        return None
    
    def run(self, instruction: str, context: dict) -> SkillResult:
        skill = self.match(instruction)
        if not skill:
            return SkillResult(False, error="No matching skill found")
        return skill.execute(instruction, context)
    
    def list_skills(self) -> list:
        return [{'name': s.name, 'description': s.description, 'loaded': s.loaded} for s in self.skills]

registry = SkillRegistry()
