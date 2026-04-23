"""Skill Registry - loads and executes skills."""
import os, importlib, traceback, inspect
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent

class Skill:
    def __init__(self, name, meta, path):
        self.name = name
        self.meta = meta
        self.path = path
        self._module = None

    def load(self):
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{self.name}", self.path)
            self._module = importlib.module_from_spec(spec)
            spec.loader.exec_module(self._module)
            return True
        except: return False

    def execute(self, instruction, context):
        if not self._module: self.load()
        func = getattr(self._module, "execute", None)
        if not func: return {"error": "No execute() in " + self.name}
        try: return {"result": func(instruction, context)}
        except Exception as e: return {"error": str(e)}

class SkillRegistry:
    def __init__(self):
        self._skills = {}
        self._meta = {}
        self.scan()

    def scan(self):
        for item in SKILLS_DIR.iterdir():
            if item.is_dir() and (item/"skill.py").exists():
                meta = self._load_meta(item)
                name = item.name
                self._skills[name] = Skill(name, meta, item/"skill.py")
                self._meta[name] = meta

    def _load_meta(self, path):
        meta = {"name": path.name, "description": "", "triggers": [], "tools": []}
        for line in (path/"skill.py").read_text().split("\n"):
            if line.startswith("##"):
