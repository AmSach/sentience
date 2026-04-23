#!/usr/bin/env python3
"""Sentience Engine - LLM integration"""
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: str
    
class SentienceEngine:
    """Main LLM engine with BYOK support"""
    
    PROVIDERS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "models": ["llama3", "codellama", "mistral"]
        }
    }
    
    def __init__(self, provider: str = "openai", model: str = "gpt-4o", api_key: str = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.history: List[Message] = []
        
        # Initialize client
        self._init_client()
        
    def _init_client(self):
        """Initialize API client"""
        if self.provider == "openai":
            import openai
            self.client = openai.OpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "groq":
            import openai
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.PROVIDERS["groq"]["base_url"]
            )
        else:
            # Ollama
            import openai
            self.client = openai.OpenAI(
                api_key="ollama",
                base_url=self.PROVIDERS["ollama"]["base_url"]
            )
            
    def process(self, message: str, tools: Any = None, memory: Any = None, 
                context: Dict = None) -> str:
        """Process a message"""
        # Build system prompt
        system_prompt = self._build_system_prompt(tools, memory, context)
        
        # Add to history
        self.history.append(Message(role="user", content=message))
        
        try:
            if self.provider == "anthropic":
                response = self._call_anthropic(system_prompt, message)
            else:
                response = self._call_openai(system_prompt, message, tools)
                
            # Add to history
            self.history.append(Message(role="assistant", content=response))
            
            return response
            
        except Exception as e:
            return f"Error: {str(e)}"
            
    def _build_system_prompt(self, tools, memory, context) -> str:
        """Build system prompt"""
        prompt = """You are Sentience, a local AI computer assistant.

You have access to tools, memory, and context about the user's projects.

When the user asks you to do something:
1. Use the appropriate tool if available
2. Remember important information
3. Be helpful and concise

"""
        
        if tools:
            prompt += f"\nAvailable tools: {', '.join(tools.tools.keys())}\n"
            
        if context:
            prompt += f"\nProject context: {json.dumps(context, indent=2)}\n"
            
        return prompt
        
    def _call_openai(self, system: str, message: str, tools) -> str:
        """Call OpenAI-compatible API"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ]
        
        # Add history
        for msg in self.history[:-1]:
            messages.append({"role": msg.role, "content": msg.content})
            
        # Check if tool use is needed
        tool_schemas = []
        if tools:
            for name, func in tools.tools.items():
                tool_schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": func.__doc__ or name,
                        "parameters": {"type": "object", "properties": {}}
                    }
                })
                
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tool_schemas if tool_schemas else None,
            max_tokens=4096
        )
        
        # Handle tool calls
        if response.choices[0].message.tool_calls:
            tool_results = []
            for call in response.choices[0].message.tool_calls:
                tool_name = call.function.name
                if tools and tool_name in tools.tools:
                    try:
                        result = tools.tools[tool_name]()
                        tool_results.append(f"{tool_name}: {result}")
                    except Exception as e:
                        tool_results.append(f"{tool_name} error: {e}")
            return "\n".join(tool_results)
            
        return response.choices[0].message.content
        
    def _call_anthropic(self, system: str, message: str) -> str:
        """Call Anthropic API"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": message}]
        )
        
        return response.content[0].text
        
    def clear_history(self):
        """Clear conversation history"""
        self.history = []
