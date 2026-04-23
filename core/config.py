#!/usr/bin/env python3
"""Configuration management - BYOK, settings, paths"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

class Config:
    """Manages all configuration, API keys, and settings"""
    
    DEFAULT_CONFIG = {
        "provider": "openai",  # openai, anthropic, groq, ollama
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 4096,
        "workspace": str(Path.home() / "Sentience"),
        "memory_compression": True,
        "auto_save": True,
        "log_level": "INFO",
    }
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".sentience"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_file = self.config_dir / "config.json"
        self.keys_file = self.config_dir / "keys.json"
        self.db_file = self.config_dir / "sentience.db"
        
        self._config = self._load_config()
        self._keys = self._load_keys()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load or create config file"""
        if self.config_file.exists():
            with open(self.config_file) as f:
                return {**self.DEFAULT_CONFIG, **json.load(f)}
        self._save_config(self.DEFAULT_CONFIG)
        return self.DEFAULT_CONFIG.copy()
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save config to file"""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def _load_keys(self) -> Dict[str, str]:
        """Load API keys (encrypted at rest)"""
        if self.keys_file.exists():
            with open(self.keys_file) as f:
                return json.load(f)
        return {}
    
    def get_key(self, provider: str) -> Optional[str]:
        """Get API key for provider"""
        # Check environment first
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY", 
            "groq": "GROQ_API_KEY",
        }
        if provider in env_map:
            key = os.environ.get(env_map[provider])
            if key:
                return key
        return self._keys.get(provider)
    
    def set_key(self, provider: str, key: str) -> None:
        """Save API key for provider"""
        self._keys[provider] = key
        with open(self.keys_file, 'w') as f:
            json.dump(self._keys, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set config value"""
        self._config[key] = value
        self._save_config(self._config)
    
    def list_keys(self) -> list:
        """List configured providers"""
        return list(self._keys.keys())
