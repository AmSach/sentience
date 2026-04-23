#!/usr/bin/env python3
"""Sentience CLI - Terminal interface"""
import sys
import os

def main():
    """Main CLI entry point"""
    from pathlib import Path
    from core.engine import Sentience
    
    print("=" * 50)
    print("  Sentience v2.0 - Local AI Computer")
    print("=" * 50)
    
    # Initialize
    sentience = Sentience()
    
    # Check provider
    provider = sentience.config.get("provider")
    model = sentience.config.get("model")
    
    key = sentience.config.get_key(provider)
    if not key and provider != "ollama":
        print(f"\n⚠ No API key configured for {provider}")
        print(f"Set it with: sentience config key {provider} YOUR_KEY")
        print("\nOr set environment variable:")
        print(f"  export {sentience.PROVIDERS[provider]['env_key']}=YOUR_KEY")
        
        # Interactive key setup
        response = input(f"\nEnter {provider} API key (or press Enter to skip): ").strip()
        if response:
            sentience.config.set_key(provider, response)
            print(f"✓ Saved {provider} API key")
    
    print(f"\nProvider: {provider}")
    print(f"Model: {model}")
    print(f"Workspace: {sentience.config.get('workspace')}")
    print(f"\nTools: {len(sentience.tools.list_tools())}")
    print("\nType 'help' for commands, 'quit' to exit.\n")
    
    # Command loop
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        # Handle commands
        if user_input in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        
        elif user_input == "help":
            print("""
Commands:
  help          Show this help
  quit          Exit Sentience
  new           Start new conversation
  list          List conversations
  load <id>     Load conversation
  provider      List providers
  use <p> [m]   Switch provider/model
  tools         List available tools
  config        Show configuration
  clear         Clear conversation history
  
Or just chat naturally with the AI.
""")
        
        elif user_input == "new":
            conv_id = sentience.new_conversation()
            print(f"Started new conversation: {conv_id[:8]}...")
        
        elif user_input == "list":
            convs = sentience.memory.list_conversations(10)
            for c in convs:
                print(f"  {c['id'][:8]}... {c['title'][:40]} {c['updated_at'][:10]}")
        
        elif user_input.startswith("load "):
            conv_id = user_input[5:].strip()
            if sentience.load_conversation(conv_id):
                print(f"Loaded conversation: {conv_id[:8]}...")
            else:
                print(f"Conversation not found: {conv_id}")
        
        elif user_input == "provider":
            providers = sentience.list_providers()
            for p, info in providers.items():
                status = "✓" if info["configured"] else "✗"
                print(f"  {status} {p}: {', '.join(info['models'][:3])}")
        
        elif user_input.startswith("use "):
            parts = user_input[4:].split()
            if parts:
                try:
                    provider = parts[0]
                    model = parts[1] if len(parts) > 1 else None
                    sentience.set_provider(provider, model)
                    print(f"Switched to {sentience.config.get('provider')} / {sentience.config.get('model')}")
                except ValueError as e:
                    print(f"Error: {e}")
        
        elif user_input == "tools":
            for t in sentience.tools.list_tools():
                print(f"  {t['name']}: {t['description'][:50]}...")
        
        elif user_input == "config":
            print(f"Provider: {sentience.config.get('provider')}")
            print(f"Model: {sentience.config.get('model')}")
            print(f"Workspace: {sentience.config.get('workspace')}")
            print(f"Keys configured: {sentience.config.list_keys()}")
        
        elif user_input == "clear":
            sentience.history = []
            print("Conversation cleared.")
        
        else:
            # Chat
            response = sentience.chat(user_input)
            print(f"\nSentience: {response}")

if __name__ == "__main__":
    main()
