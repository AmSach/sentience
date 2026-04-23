#!/usr/bin/env python3
"""Sentience CLI - terminal interface."""
import sys, os, argparse, json, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from storage import init_schema, get_db, create_conversation, list_conversations, get_messages, save_message, set_memory, get_memory, list_memory, save_byok, get_byok, list_byok
from agent import SentienceAgent, BYOKProvider

def main():
    parser = argparse.ArgumentParser(description="Sentience CLI")
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument("--conversation-id", "-c")
    args = parser.parse_args()

    init_schema(get_db())
    workspace = args.workspace
    conv_id = args.conversation_id or str(uuid.uuid4())
    if not get_conversation(conv_id):
        create_conversation(conv_id)
    
    provider = BYOKProvider.load()
    agent = SentienceAgent(conv_id, workspace, provider)
    
    print("Sentience v1.0 | Type 'exit' to quit")
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ("exit", "quit"): break
            response = agent.process(user_input)
            print(f"\nSentience: {response}")
        except KeyboardInterrupt:
            break
    print("Goodbye.")

if __name__ == "__main__":
    main()
