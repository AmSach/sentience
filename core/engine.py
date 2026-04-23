#!/usr/bin/env python3
"""Sentience Engine - Main agent loop with BYOK support"""
import json
import uuid
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from .config import Config
from .memory import Memory
from .tools import create_registry, ToolContext, ToolResult

@dataclass
class Message:
    role: str
    content: str
    tool_calls: List = field(default_factory=list)
    tool_results: List = field(default_factory=list)

class Sentience:
    """
    Main Sentience Agent.
    
    Supports:
    - Multiple LLM providers (OpenAI, Anthropic, Groq, Ollama)
    - Tool calling
    - Multi-turn conversations
    - Memory persistence
    - Self-improvement
    """
    
    PROVIDERS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            "env_key": "OPENAI_API_KEY"
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
            "env_key": "ANTHROPIC_API_KEY"
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
            "env_key": "GROQ_API_KEY"
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "models": ["llama3", "mistral", "codellama"],
            "env_key": None
        }
    }
    
    SYSTEM_PROMPT = """You are Sentience, an advanced AI assistant running locally on the user's machine.

You have access to tools for:
- File operations (read, write, edit, search)
- Shell commands (run any command)
- Code analysis (analyze, refactor, debug)
- Web access (fetch URLs, search the web)
- Memory (remember and recall information)
- Git operations (commit, push, pull, branch)

Guidelines:
1. Be helpful, accurate, and concise
2. Use tools when needed to accomplish tasks
3. Explain your reasoning briefly before taking action
4. When editing files, show the changes you'll make
5. For complex tasks, break them into steps
6. Ask for clarification if a request is ambiguous

You have full access to the user's machine. Be careful with destructive operations.
Always confirm before deleting files or running potentially dangerous commands.
"""
    
    def __init__(self, config_dir: Path = None):
        self.config = Config(config_dir)
        self.memory = Memory(self.config.db_file)
        self.tools = create_registry()
        self.conversation_id = str(uuid.uuid4())
        self.history: List[Message] = []
        self._provider_clients = {}
        
        # Create workspace if needed
        workspace = Path(self.config.get("workspace"))
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Initialize conversation in memory
        self.memory.create_conversation(self.conversation_id)
    
    def _get_client(self, provider: str):
        """Get or create API client for provider"""
        if provider in self._provider_clients:
            return self._provider_clients[provider]
        
        api_key = self.config.get_key(provider)
        if not api_key and provider != "ollama":
            raise ValueError(f"No API key for {provider}. Set it with: config.set_key('{provider}', 'your-key')")
        
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        else:
            import openai
            client = openai.OpenAI(
                api_key=api_key or "ollama",
                base_url=self.PROVIDERS[provider]["base_url"]
            )
        
        self._provider_clients[provider] = client
        return client
    
    def chat(self, message: str, on_token: Callable = None) -> str:
        """Send a message and get response (with tool calling)"""
        # Add to history
        self.history.append(Message("user", message))
        self.memory.save_message(
            str(uuid.uuid4()),
            self.conversation_id,
            "user",
            message
        )
        
        # Build messages for API
        messages = self._build_messages()
        
        # Get response
        provider = self.config.get("provider")
        model = self.config.get("model")
        
        for _ in range(10):  # Max tool call iterations
            try:
                response = self._call_api(provider, model, messages, on_token)
            except Exception as e:
                return f"Error calling {provider}: {e}"
            
            # Add to history
            assistant_msg = Message("assistant", response.get("content", ""))
            if response.get("tool_calls"):
                assistant_msg.tool_calls = response["tool_calls"]
            self.history.append(assistant_msg)
            
            # Handle tool calls
            if response.get("tool_calls"):
                tool_results = []
                for tc in response["tool_calls"]:
                    result = self._execute_tool(tc)
                    tool_results.append(result)
                
                assistant_msg.tool_results = tool_results
                
                # Add tool results to messages for next call
                messages.append({
                    "role": "assistant",
                    "content": response.get("content"),
                    "tool_calls": response.get("tool_calls")
                })
                for tr in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["content"]
                    })
                continue
            
            # No tool calls - we're done
            self.memory.save_message(
                str(uuid.uuid4()),
                self.conversation_id,
                "assistant",
                response.get("content", "")
            )
            return response.get("content", "")
        
        return "Error: Too many tool call iterations"
    
    def _build_messages(self) -> List[Dict]:
        """Build message list for API"""
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        
        for msg in self.history[-20:]:  # Last 20 messages for context
            m = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            messages.append(m)
        
        return messages
    
    def _call_api(self, provider: str, model: str, messages: List[Dict], on_token: Callable = None) -> Dict:
        """Call the LLM API"""
        client = self._get_client(provider)
        tools = self._format_tools()
        
        if provider == "anthropic":
            # Anthropic format
            response = client.messages.create(
                model=model,
                max_tokens=self.config.get("max_tokens", 4096),
                system=self.SYSTEM_PROMPT,
                messages=[m for m in messages if m["role"] != "system"],
                tools=tools if tools else None
            )
            
            content = ""
            tool_calls = []
            
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text
                elif hasattr(block, "name"):  # Tool use
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input)
                        }
                    })
            
            return {"content": content, "tool_calls": tool_calls if tool_calls else None}
        
        else:
            # OpenAI-compatible format
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools if tools else None,
                temperature=self.config.get("temperature", 0.7),
                max_tokens=self.config.get("max_tokens", 4096),
                stream=on_token is not None
            )
            
            if on_token:
                # Streaming
                content = ""
                tool_calls = []
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        content += token
                        on_token(token)
                return {"content": content}
            else:
                # Non-streaming
                choice = response.choices[0]
                return {
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in (choice.message.tool_calls or [])
                    ] or None
                }
    
    def _format_tools(self) -> List[Dict]:
        """Format tools for API"""
        tools = []
        for t in self.tools.list_tools():
            tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"]
                }
            })
        return tools
    
    def _execute_tool(self, tool_call: Dict) -> Dict:
        """Execute a tool call"""
        name = tool_call["function"]["name"]
        args = json.loads(tool_call["function"]["arguments"])
        tool_id = tool_call["id"]
        
        ctx = ToolContext(
            workspace=Path(self.config.get("workspace")),
            conversation_id=self.conversation_id,
            config=self.config._config,
            memory=self.memory
        )
        
        result = self.tools.execute(name, args, ctx)
        
        return {
            "tool_call_id": tool_id,
            "content": json.dumps({
                "success": result.success,
                "output": result.output,
                "error": result.error
            })
        }
    
    def set_provider(self, provider: str, model: str = None) -> None:
        """Switch LLM provider"""
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Options: {list(self.PROVIDERS.keys())}")
        
        self.config.set("provider", provider)
        if model:
            self.config.set("model", model)
        elif self.PROVIDERS[provider]["models"]:
            self.config.set("model", self.PROVIDERS[provider]["models"][0])
    
    def list_providers(self) -> Dict:
        """List available providers and models"""
        return {
            p: {
                "models": info["models"],
                "configured": bool(self.config.get_key(p))
            }
            for p, info in self.PROVIDERS.items()
        }
    
    def new_conversation(self) -> str:
        """Start a new conversation"""
        self.conversation_id = str(uuid.uuid4())
        self.history = []
        self.memory.create_conversation(self.conversation_id)
        return self.conversation_id
    
    def load_conversation(self, conv_id: str) -> bool:
        """Load an existing conversation"""
        conv = self.memory.get_conversation(conv_id)
        if not conv:
            return False
        
        self.conversation_id = conv_id
        self.history = []
        
        for msg in self.memory.get_messages(conv_id):
            self.history.append(Message(
                msg["role"],
                msg["content"],
                msg.get("tool_calls", []),
                msg.get("tool_results", [])
            ))
        
        return True
    
    def run_automation(self, instruction: str) -> str:
        """Run an autonomous task"""
        # Add automation context
        system = f"""
You are running in autonomous mode. The user has instructed you to:

{instruction}

Work independently to complete this task. Use tools as needed.
When finished, provide a summary of what you did.
"""
        # Temporarily modify system prompt
        old_prompt = self.SYSTEM_PROMPT
        self.SYSTEM_PROMPT = system
        
        try:
            response = self.chat("Begin the task.")
        finally:
            self.SYSTEM_PROMPT = old_prompt
        
        return response
