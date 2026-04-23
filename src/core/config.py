#!/usr/bin/env python3
"""Sentience Configuration - BYOK + Settings"""
import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List

@dataclass
class ProviderConfig:
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: List[str] = field(default_factory=list)
    default_model: Optional[str] = None

@dataclass 
class Config:
    data_dir: Path = field(default_factory=lambda: Path.home() / ".sentience")
    vault_dir: Path = field(default_factory=lambda: Path.home() / ".sentience" / "vault")
    db_path: Path = field(default_factory=lambda: Path.home() / ".sentience" / "sentience.db")
    log_level: str = "INFO"
    
    # Providers
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    default_provider: str = "groq"
    default_model: str = "llama-3.3-70b-versatile"
    
    # RAG Settings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50
    vector_db: str = "chroma"
    
    # Automation
    max_tool_retries: int = 3
    tool_timeout: int = 60
    enable_voice: bool = False
    
    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.vault_dir = Path(self.vault_dir)
        self.db_path = Path(self.db_path)
        self._load_providers()
        
    def _load_providers(self):
        """Load provider configs from environment"""
        # Groq (free tier available)
        if os.getenv("GROQ_API_KEY"):
            self.providers["groq"] = ProviderConfig(
                name="groq",
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
                models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
                default_model="llama-3.3-70b-versatile"
            )
        
        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            self.providers["openai"] = ProviderConfig(
                name="openai",
                api_key=os.getenv("OPENAI_API_KEY"),
                models=["gpt-4o", "gpt-4o-mini"],
                default_model="gpt-4o"
            )
        
        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            self.providers["anthropic"] = ProviderConfig(
                name="anthropic",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                models=["claude-sonnet-4-20250514"],
                default_model="claude-sonnet-4-20250514"
            )
        
        # Ollama (local)
        ollama_path = Path.home() / ".ollama"
        if os.getenv("OLLAMA_HOST") or ollama_path.exists():
            self.providers["ollama"] = ProviderConfig(
                name="ollama",
                base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                models=["llama3.2", "llama3.1", "mistral"],
                default_model="llama3.2"
            )
    
    def get_provider(self, name: Optional[str] = None) -> ProviderConfig:
        name = name or self.default_provider
        if name not in self.providers:
            # Demo mode - return a mock provider
            print(f"Warning: Provider '{name}' not configured. Running in demo mode.")
            print(f"Set {name.upper()}_API_KEY for full functionality.")
            return ProviderConfig(
                name=name,
                base_url="https://api.groq.com/openai/v1",
                models=["demo-model"],
                default_model="demo-model"
            )
        return self.providers[name]
    
    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        
    def save(self):
        self.ensure_dirs()
        config_path = self.data_dir / "config.json"
        data = {
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "embedding_model": self.embedding_model,
            "chunk_size": self.chunk_size,
            "enable_voice": self.enable_voice,
        }
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
            
    @classmethod
    def load(cls) -> "Config":
        config_path = Path.home() / ".sentience" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            cfg = cls(
                default_provider=data.get("default_provider", "groq"),
                default_model=data.get("default_model", "llama-3.3-70b-versatile"),
            )
            cfg.embedding_model = data.get("embedding_model", cfg.embedding_model)
            cfg.chunk_size = data.get("chunk_size", cfg.chunk_size)
            cfg.enable_voice = data.get("enable_voice", False)
            return cfg
        return cls()
