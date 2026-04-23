#!/usr/bin/env python3
"""Sentience Server - Flask REST API + Web UI."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="ui", static_url_path="")
CORS(app)

# Import all modules
from storage import init_schema, get_db, create_conversation, list_conversations, get_messages, save_message
from storage import get_byok, save_byok, list_byok, get_memory, set_memory, list_memory
from storage import save_automation, list_automations, save_kv, get_kv
from agent import SentienceAgent, BYOKProvider
from agent.provider import PROVIDERS
from memory.vault import SentienceVault
from memory.compression import SentienceCompression
from memory.graph import SentienceGraph
from integrations import (GmailIntegration, NotionIntegration, SpotifyIntegration,
                          CalendarIntegration, DriveIntegration, DropboxIntegration, LinearIntegration)

from storage import init_schema as init_db; init_db(get_db())

_active_agent = None
_vault = None
_compression = None
_graph = None

def get_agent():
    global _active_agent, _vault, _compression, _graph
    from storage.db import get_db
    db = get_db()
    
    provider_name = "anthropic"
    for p in list_byok():
        provider_name = p; break
    
    byok = get_byok(provider_name)
    if not byok or not byok[1]:
        return None, "No API key configured. Run: python3 sentience.py config add anthropic YOUR_KEY"
    
    provider = BYOKProvider(provider=provider_name, api_key=byok[1])
    agent = SentienceAgent(provider)
    
    from storage.db import get_db as gdb
    _compression = SentienceCompression()
    _vault = SentienceVault(storage=None)
    return agent, None

@app.route("/api/health")
def health(): return jsonify({"status": "ok", "tools": len(__import__("agent.tools", fromlist=["get_registry"]).get_registry().list_tools())})

@app.route("/api/tools")
def tools_route():
    from agent.tools import get_registry
    return jsonify({"tools": get_registry().get_schema()})

@app.route("/api/conversations", methods=["GET"])
def conversations_list():
    rows = list_conversations()
    return jsonify({"conversations": [{"id": r[0], "title": r[1], "updated_at": r[3]} for r in rows]})

@app.route("/api/conversations", methods=["POST"])
def conversations_create():
    import uuid
    data = request.json or {}
    cid = str(uuid.uuid4())[:16]
    create_conversation(cid, data.get("title", "New Chat"))
    return jsonify({"id": cid})

@app.route("/api/conversations/<conv_id>/messages", methods=["GET"])
def messages_get(conv_id):
    rows = get_messages(conv_id)
    return jsonify({"messages": [{"id": r[0], "role": r[2], "content": r[3]} for r in rows]})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    message = data.get("message", "")
    conv_id = data.get("conversation_id") or "default"
    
    agent, err = get_agent()
    if err: return jsonify({"error": err}), 400
    
    result, meta = agent.chat(message, conv_id)
    return jsonify({"content": result, "conversation_id": meta["conversation_id"], "tool_calls": meta.get("tool_calls", 0)})

@app.route("/api/byok", methods=["GET"])
def byok_list(): return jsonify({"providers": list_byok()})

@app.route("/api/byok/<provider>", methods=["POST"])
def byok_add(provider):
    data = request.json or {}
    api_key = data.get("api_key", "")
    models = data.get("models")
    base_url = data.get("base_url")
    if not api_key: return jsonify({"error": "api_key required"}), 400
    save_byok(provider, api_key, models, base_url)
    return jsonify({"success": True, "provider": provider})

@app.route("/api/byok/providers", methods=["GET"])
def byok_providers(): return jsonify({"providers": PROVIDERS})

@app.route("/api/memory", methods=["GET"])
def memory_list(): return jsonify({"memory": [{"key": r[0], "value": r[1]} for r in list_memory()]})

@app.route("/api/memory/<key>", methods=["GET"])
def memory_get(key): return jsonify({"value": get_memory(key)})

@app.route("/api/memory/<key>", methods=["POST"])
def memory_set(key): set_memory(key, request.json.get("value","")); return jsonify({"success": True})

@app.route("/api/vault/search", methods=["GET"])
def vault_search():
    from storage import search_vault
    q = request.args.get("q", "")
    results = search_vault(q)
    return jsonify({"results": [{"id": r[0], "key": r[1], "content": r[2][:200]} for r in results]})

@app.route("/api/vault/create", methods=["POST"])
def vault_create():
    data = request.json or {}
    from memory.vault import SentienceVault
    vault = SentienceVault(storage=None)
    entry = vault.create_note(data.get("title",""), data.get("content",""), data.get("tags",[]))
    return jsonify(entry)

@app.route("/api/compress", methods=["POST"])
def compress():
    data = request.json or {}
    msgs = data.get("messages", [])
    compression = SentienceCompression()
    compressed, stats = compression.compress(msgs)
    return jsonify({"compressed": compressed, "stats": stats})

@app.route("/api/automations", methods=["GET"])
def automations_list():
    rows = list_automations()
    return jsonify({"automations": [{"id": r[0], "name": r[1], "rrule": r[3], "enabled": r[4]} for r in rows]})

@app.route("/api/automations", methods=["POST"])
def automations_create():
    import uuid
    data = request.json or {}
    aid = str(uuid.uuid4())[:16]
    save_automation({"id": aid, "name": data.get("name",""), "instruction": data.get("instruction",""), "rrule": data.get("rrule",""), "enabled": data.get("enabled",1)})
    return jsonify({"id": aid})

@app.route("/api/integrations/gmail/search", methods=["GET"])
def gmail_search():
    q = request.args.get("q", "")
    gmail = GmailIntegration()
    results = gmail.list_messages(q)
    return jsonify({"messages": results})

@app.route("/api/integrations/gmail/send", methods=["POST"])
def gmail_send():
    data = request.json or {}
    gmail = GmailIntegration()
    result = gmail.send_email(data.get("to",""), data.get("subject",""), data.get("body",""))
    return jsonify(result)

@app.route("/api/integrations/notion/search", methods=["GET"])
def notion_search():
    q = request.args.get("q", "")
    notion = NotionIntegration()
    results = notion.search(q)
    return jsonify({"results": results})

@app.route("/api/integrations/spotify/recent", methods=["GET"])
def spotify_recent():
    spotify = SpotifyIntegration()
    results = spotify.get_recently_played()
    return jsonify({"tracks": results})

@app.route("/api/settings", methods=["GET"])
def settings_get():
    return jsonify({"workspace": os.path.expanduser("~/sentience_workspace"), "db": os.path.expanduser("~/.sentience")})

@app.route("/<path:path>")
def static_proxy(path): return send_from_directory("ui", path)

@app.route("/")
def index(): return send_from_directory("ui", "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3132))
    print(f"Sentience server running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
