#!/usr/bin/env python3
"""Configuration management"""
import json
from pathlib import Path
from typing import Any, Dict

class Config:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.data: Dict[str, Any] = {}
        
    def load(self):
        """Load config from file"""
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.data = json.load(f)
                
    def save(self):
        """Save config to file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=2)
            
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value"""
        return self.data.get(key, default)
        
    def set(self, key: str, value: Any):
        """Set config value"""
        self.data[key] = value
        self.save()
        
    def delete(self, key: str):
        """Delete config key"""
        if key in self.data:
            del self.data[key]
            self.save()
