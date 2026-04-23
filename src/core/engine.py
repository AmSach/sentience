#!/usr/bin/env python3
"""
Sentience Agent Engine - Think-Act-Observe-Evaluate Loop
Based on: Sujatx/Jarvis, OpenJarvis, vierisid/jarvis
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
import http.client
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

from .config import Config
from .memory import MemorySystem, Memory
from .tools import ToolRegistry, tools, ToolResult
from ..rag import RAGEngine


@dataclass
class Message:
    role: str
    content: str
    tool_calls: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class LLMProvider:
    """Unified LLM provider (OpenAI-compatible API)"""
    
    def __init__(self, config: Config):
        self.config = config
        self.provider_config = config.get_provider()
        
    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.provider_config.api_key:
            headers["Authorization"] = f"Bearer {self.provider_config.api_key}"
        return headers
    
    def _get_url(self) -> str:
        base = self.provider_config.base_url or "https://api.openai.com/v1"
        return f"{base.rstrip('/')}/chat/completions"
    
    def complete(self, messages: List[Dict], tools: List[Dict] = None, 
                 tool_choice: str = "auto", stream: bool = False) -> Dict:
        """Make completion request"""
        payload = {
            "model": self.provider_config.default_model or "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
            
        url = self._get_url()
        headers = self._get_headers()
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode('utf-8'))
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            logger.error(f"LLM API error: {e.code} - {error_body}")
            raise Exception(f"LLM API error: {e.code}")
        except urllib.error.URLError as e:
            logger.error(f"Connection error: {e}")
            raise Exception(f"Connection error: {e}")
    
    def complete_stream(self, messages: List[Dict], tools: List[Dict] = None) -> AsyncGenerator[str, None]:
        """Stream completion (async generator)"""
        # For now, just return the full completion
        result = self.complete(messages, tools, stream=True)
        if 'choices' in result and result['choices']:
            yield result['choices'][0]['message']['content']


class SentienceEngine:
    """
    Main AI Engine with:
    - Tool execution
    - RAG integration  
    - Memory management
    - Conversation history
    """
    
    def __init__(self, config: Config = None):
        self.config = config or Config.load()
        self.config.ensure_dirs()
        
        # Initialize components
        self.memory = MemorySystem(self.config.db_path, self.config.vault_dir)
        self.llm = LLMProvider(self.config)
        self.rag: Optional[RAGEngine] = None
        self.tools = tools
        
        # Conversation state
        self.conversation_id: Optional[str] = None
        self.messages: List[Message] = []
        self.max_history = 50
        
        # Initialize RAG if embeddings available
        try:
            self.rag = RAGEngine(
                db_path=self.config.data_dir / "rag.db",
                embedding_model=self.config.embedding_model,
                chunk_size=self.config.chunk_size
            )
        except Exception as e:
            logger.warning(f"RAG not initialized: {e}")
    
    def start_conversation(self, title: str = None) -> str:
        """Start new conversation"""
        self.conversation_id = self.memory.create_conversation(title)
        self.messages = []
        return self.conversation_id
    
    def load_conversation(self, conversation_id: str) -> None:
        """Load existing conversation"""
        self.conversation_id = conversation_id
        msgs = self.memory.get_conversation(conversation_id, limit=self.max_history)
        self.messages = [
            Message(
                role=m['role'],
                content=m['content'],
                tool_calls=json.loads(m['tool_calls']) if m.get('tool_calls') else [],
                tool_results=json.loads(m['tool_results']) if m.get('tool_results') else []
            )
            for m in msgs
        ]
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with context"""
        return """You are Sentience, a powerful AI assistant running locally on the user's computer.

You have access to tools for:
- File operations (read, write, edit, search)
- Shell commands
- Web requests
- Code analysis
- Memory storage and retrieval

You can:
1. Execute tasks autonomously using tools
2. Remember information across conversations
3. Search through documents and code
4. Control the computer through shell commands

Always explain what you're doing. Ask for confirmation before destructive operations.
Break complex tasks into steps. Report progress and errors clearly.

Respond concisely and helpfully. Use markdown for formatting."""

    def _build_messages(self, user_input: str, context: str = None) -> List[Dict]:
        """Build message list for LLM"""
        messages = [{"role": "system", "content": self._build_system_prompt()}]
        
        # Add context from RAG if available
        if context:
            messages.append({
                "role": "system", 
                "content": f"Relevant context:\n{context}"
            })
        
        # Add conversation history
        for msg in self.messages[-self.max_history:]:
            messages.append({"role": msg.role, "content": msg.content})
            
            # Add tool calls
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": msg.tool_calls
                })
            if msg.tool_results:
                for result in msg.tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result.get("id"),
                        "content": json.dumps(result.get("output", {}))
                    })
        
        # Add current input
        messages.append({"role": "user", "content": user_input})
        
        return messages
    
    async def process(self, user_input: str) -> str:
        """
        Process user input - main agent loop
        """
        # Get context from RAG if available
        context = None
        if self.rag:
            try:
                context = self.rag.get_context(user_input, max_tokens=1000)
            except Exception as e:
                logger.error(f"RAG context failed: {e}")
        
        # Start conversation if needed
        if not self.conversation_id:
            self.start_conversation()
        
        # Save user message
        self.messages.append(Message(role="user", content=user_input))
        self.memory.add_message(self.conversation_id, "user", user_input)
        
        # Build request
        messages = self._build_messages(user_input, context)
        tool_schemas = self.tools.to_schemas()
        
        # Agent loop: Think -> Act -> Observe -> Evaluate
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM
            try:
                response = self.llm.complete(messages, tools=tool_schemas)
            except Exception as e:
                error_msg = f"LLM error: {e}"
                logger.error(error_msg)
                return error_msg
            
            if 'choices' not in response or not response['choices']:
                return "No response from LLM"
            
            choice = response['choices'][0]
            message = choice['message']
            
            # Check for tool calls
            tool_calls = message.get('tool_calls', [])
            
            if tool_calls:
                # Execute tools
                tool_results = []
                for tool_call in tool_calls:
                    tool_name = tool_call['function']['name']
                    tool_args = json.loads(tool_call['function']['arguments'])
                    tool_id = tool_call['id']
                    
                    logger.info(f"Executing tool: {tool_name}({tool_args})")
                    
                    # Execute tool
                    result = await self.tools.execute(tool_name, **tool_args)
                    
                    tool_results.append({
                        "id": tool_id,
                        "name": tool_name,
                        "output": {
                            "success": result.success,
                            "data": result.output,
                            "error": result.error
                        }
                    })
                
                # Add to messages
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls
                })
                
                for tr in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr['id'],
                        "content": json.dumps(tr['output'])
                    })
                
                # Continue loop
                continue
            
            # No tool calls - return final response
            content = message.get('content', '')
            
            # Save assistant message
            self.messages.append(Message(role="assistant", content=content))
            self.memory.add_message(self.conversation_id, "assistant", content)
            
            return content
        
        return "Max iterations reached. Please try again with a simpler request."
    
    def chat(self, user_input: str) -> str:
        """Synchronous chat interface"""
        return asyncio.run(self.process(user_input))
    
    def index_directory(self, path: str) -> int:
        """Index directory into RAG"""
        if not self.rag:
            return 0
        from pathlib import Path
        docs = self.rag.index_directory(Path(path))
        return len(docs)
    
    def index_file(self, path: str) -> bool:
        """Index file into RAG"""
        if not self.rag:
            return False
        from pathlib import Path
        try:
            self.rag.index_file(Path(path))
            return True
        except Exception as e:
            logger.error(f"Failed to index {path}: {e}")
            return False
    
    def search_knowledge(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search RAG knowledge base"""
        if not self.rag:
            return []
        return self.rag.query(query, top_k=top_k)
    
    def store_memory(self, key: str, value: str, metadata: Dict = None) -> str:
        """Store memory"""
        return self.memory.store(key, value, metadata)
    
    def retrieve_memory(self, key: str) -> Optional[Memory]:
        """Retrieve memory"""
        return self.memory.retrieve(key)
    
    def search_memory(self, query: str) -> List[Memory]:
        """Search memories"""
        return self.memory.search(query)


# CLI Entry Point
def main():
    """CLI interface for Sentience"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sentience - Local AI Computer")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--provider", default=None, help="LLM provider to use")
    parser.add_argument("--model", default=None, help="Model to use")
    parser.add_argument("--index", default=None, help="Index directory into RAG")
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Load config
    config = Config.load()
    if args.provider:
        config.default_provider = args.provider
    if args.model:
        config.default_model = args.model
    
    # Initialize engine
    engine = SentienceEngine(config)
    
    # Index if requested
    if args.index:
        count = engine.index_directory(args.index)
        print(f"Indexed {count} documents from {args.index}")
        return
    
    # CLI mode
    if args.cli or True:
        print("=" * 50)
        print("  SENTIENCE v4.0 - Local AI Computer")
        print(f"  Provider: {config.default_provider}")
        print(f"  Model: {config.default_model}")
        print("=" * 50)
        print("\nType your message. Ctrl+C to exit.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                    
                if user_input in ['/exit', '/quit', 'exit', 'quit']:
                    print("Goodbye!")
                    break
                
                # Process
                response = engine.chat(user_input)
                print(f"\nSentience: {response}\n")
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                logger.error(f"Error: {e}")


if __name__ == "__main__":
    main()


__all__ = ['SentienceEngine', 'Message', 'LLMProvider']
