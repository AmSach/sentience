#!/usr/bin/env python3
"""Sentience Agent Engine - full agent loop with tool calling and memory."""
import os, json, time, uuid
from typing import List, Dict, Any, Optional
from storage import init_schema as init_db, get_db, init_schema as init_db, get_messages, save_message, create_conversation, set_memory, get_memory, get_db
from agent.provider import BYOKProvider
from agent.tools.registry import ToolContext, get_registry, ToolResult
from agent.tools import filesystem, bash_tools, git_tools, web_tools, browser_tools, search_tools, memory_tools

class SentienceAgent:
    def __init__(self, provider: BYOKProvider, workspace: str = None):
        self.provider = provider
        self.workspace = workspace or os.path.expanduser("~/sentience_workspace")
        self.registry = get_registry()
        self.max_turns = 50
        self.compression_ratio = 4.0
        os.makedirs(self.workspace, exist_ok=True)
    
    def chat(self, message: str, conversation_id: str = None, ctx_kwargs: dict = None) -> tuple[str, dict]:
        conv_id = conversation_id or str(uuid.uuid4())[:16]
        if not get_messages(conv_id): create_conversation(conv_id)
        
        ctx = ToolContext(
            workspace_path=self.workspace,
            conversation_id=conv_id,
            user_id="local",
            memory=None, vault=None, compression=None, graph=None
        )
        if ctx_kwargs:
            for k, v in ctx_kwargs.items(): setattr(ctx, k, v)
        
        messages = self._build_messages(conv_id, message)
        response = self._run_loop(messages, ctx)
        
        save_message({"id": str(uuid.uuid4()), "conversation_id": conv_id, "role": "user", "content": message})
        save_message({"id": str(uuid.uuid4()), "conversation_id": conv_id, "role": "assistant", "content": response["content"]})
        
        return response["content"], {"conversation_id": conv_id, "tool_calls": len(response.get("tool_calls", []))}
    
    def _build_messages(self, conv_id: str, new_message: str) -> List[dict]:
        history = get_messages(conv_id, limit=200)
        msgs = []
        for m in history:
            role = m[2] if len(m) > 2 else "user"
            content = m[3] if len(m) > 3 else ""
            msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": new_message})
        
        total = sum(len(m.get("content","").split()) + len(m.get("content",""))//4 for m in msgs)
        if total > 150000:
            keep = int(150000 / self.compression_ratio)
            msgs = msgs[-keep:] if len(msgs) > keep else msgs
        
        system = (
            "You are Sentience, an advanced AI agent with access to tools. "
            "You have a persistent memory (vault), knowledge graph, file operations, "
            "bash commands, git, web browsing, and integrations (Gmail, Notion, Spotify, Calendar, Drive, Dropbox, Linear). "
            "Use tools proactively. Be thorough and helpful."
        )
        return [{"role": "system", "content": system}] + msgs
    
    def _run_loop(self, messages: List[dict], ctx: ToolContext) -> dict:
        tools = self.registry.get_schema()
        for turn in range(self.max_turns):
            resp = self.provider.chat(messages, max_tokens=4096, tools=tools)
            
            if "error" in resp: return {"content": f"Provider error: {resp['error']}", "tool_calls": []}
            
            if self.provider.provider == "anthropic":
                content = resp.get("content", [])
                text_content = ""
                tool_calls = []
                for block in (content or []):
                    if block.get("type") == "text": text_content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_calls.append({"name": block["name"], "input": block["input"]})
            else:
                choices = resp.get("choices", [{}])
                msg = choices[0].get("message", {}) if choices else {}
                text_content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", []) or []
                if isinstance(tool_calls, list) and tool_calls and hasattr(tool_calls[0], 'function'):
                    tool_calls = [{"name": tc.function.name, "input": json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments} for tc in tool_calls]
                elif isinstance(tool_calls, list) and tool_calls and isinstance(tool_calls[0], dict):
                    pass
            
            if tool_calls:
                results = []
                for tc in tool_calls:
                    name = tc.get("name", tc.get("function", {}).get("name",""))
                    args = tc.get("input", tc.get("function", {}).get("arguments", {}))
                    if isinstance(args, str): args = json.loads(args) if args else {}
                    r = self.registry.execute(name, args, ctx)
                    results.append({"name": name, "result": str(r)})
                    messages.append({"role": "user", "content": "", "type": "tool_result", "tool_use_id": tc.get("id",""), "content": str(r)})
                
                if text_content: messages.append({"role": "assistant", "content": text_content})
                continue
            else:
                if text_content: messages.append({"role": "assistant", "content": text_content})
                return {"content": text_content, "tool_calls": tool_calls}
        
        return {"content": "Max turns reached", "tool_calls": []}
