#!/usr/bin/env python3
"""BYOK Provider - Anthropic, OpenAI, Groq, Cerebras, Ollama, OpenRouter."""
import os, json, requests
from typing import Optional, Dict, Any, List

PROVIDERS = {
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "models": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-opus-latest", "claude-3-sonnet-latest", "claude-3-haiku-latest"]},
    "openai": {"base_url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma-7b-it"]},
    "cerebras": {"base_url": "https://api.cerebras.ai/v1", "models": ["llama-3.3-70b", "qwen-2.5-32b"]},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "models": ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-2.0-flash-thinking", "meta-llama/llama-3-3-70b-instruct"]},
    "ollama": {"base_url": "http://localhost:11434/v1", "models": ["llama3.3", "mistral", "codellama", "phi3", "qwen2.5"]},
}

class BYOKProvider:
    def __init__(self, provider: str = None, api_key: str = None, model: str = None, base_url: str = None):
        self.provider = provider or "anthropic"
        self.api_key = api_key or os.environ.get(f"{self.provider.upper()}_API_KEY", "")
        self.model = model
        self.base_url = base_url
        self._config = PROVIDERS.get(self.provider, PROVIDERS["anthropic"])
    
    def chat(self, messages: List[dict], max_tokens: int = 4096, tools: List[dict] = None, tool_choice: str = None, **kwargs) -> Dict[str, Any]:
        if self.provider == "anthropic": return self._anthropic(messages, max_tokens, tools, tool_choice)
        elif self.provider == "ollama": return self._ollama(messages, max_tokens, tools)
        else: return self._openai_compat(messages, max_tokens, tools, tool_choice)
    
    def _anthropic(self, messages: List[dict], max_tokens: int, tools: List[dict] = None, tool_choice: str = None) -> Dict[str, Any]:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        msgs = [m for m in messages if m["role"] != "system"]
        body = {"model": self.model or "claude-3-5-sonnet-latest", "max_tokens": max_tokens, "system": system, "messages": msgs}
        if tools: body["tools"] = tools
        if tool_choice: body["tool_choice"] = {"type": "tool", "name": tool_choice} if isinstance(tool_choice, str) else tool_choice
        try:
            import requests
            resp = requests.post(f"{self._config['base_url']}/messages",
                headers={"x-api-key": self.api_key, "Content-Type": "application/json", "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true"},
                json=body, timeout=120)
            if resp.status_code == 200: return resp.json()
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e: return {"error": str(e)}
    
    def _openai_compat(self, messages: List[dict], max_tokens: int, tools: List[dict] = None, tool_choice: str = None) -> Dict[str, Any]:
        body = {"model": self.model or self._config["models"][0], "messages": messages, "max_tokens": max_tokens}
        if tools: body["tools"] = tools
        if tool_choice: body["tool_choice"] = tool_choice if isinstance(tool_choice, str) else {"type": "tool", "function": {"name": tool_choice}}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            import requests
            resp = requests.post(f"{self._config['base_url']}/chat/completions",
                headers=headers, json=body, timeout=120)
            if resp.status_code == 200: return resp.json()
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e: return {"error": str(e)}
    
    def _ollama(self, messages: List[dict], max_tokens: int, tools: List[dict] = None) -> Dict[str, Any]:
        body = {"model": self.model or "llama3.3", "messages": messages, "options": {"num_predict": max_tokens}}
        if tools: body["tools"] = tools
        try:
            import requests
            resp = requests.post(f"{self._config['base_url']}/chat", json=body, timeout=120)
            if resp.status_code == 200: return resp.json()
            return {"error": str(resp.status_code)}
        except Exception as e: return {"error": str(e)}
    
    def count_tokens(self, text: str) -> int:
        return len(text.split()) + len(text) // 4
    
    def get_models(self) -> List[str]:
        return self._config["models"]
    
    def get_available_providers(self) -> List[str]:
        return list(PROVIDERS.keys())
