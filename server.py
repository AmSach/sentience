#!/usr/bin/env python3
"""Sentience Server - Flask REST API."""
import os, sys, json

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.serving import run_simple

# Import all modules
from storage import init_schema, get_db, create_conversation, list_conversations, get_conversation, get_messages, save_message, save_byok_key, get_byok_keys, set_memory, get_memory, list_memories, delete_memory, create_skill, list_skills, get_skill, update_skill, delete_skill, save_automation, get_automations, delete_automation, update_automation, get_automation_history
from agent.tools import get_registry, ToolContext
from agent.engine import SentienceAgent
from skills.registry import SkillRegistry, list_all_skills, get_skill_by_name, execute_skill, install_skill_from_url, create_custom_skill
from skills.registry import SKILL_DIR
from memory.vault import SentienceVault
from memory.compression import SentienceCompression
from memory.graph import SentienceGraph
from automation import get_automation
from hosting import get_host
from remote import RemoteControl, get_remote
from email.listener import EmailListener, configure_gmail, get_listener
from cloud import CloudStorage, get_cloud
from integrations.gmail_client import GmailClient
from integrations.notion_client import NotionClient
from integrations.calendar_client import CalendarClient
from integrations.spotify_client import SpotifyClient

app = Flask(__name__, static_folder="ui", static_url_path="")
CORS(app)

# Init DB
init_schema(get_db())

# Global instances
_agent = None
_vault = SentienceVault()
_compression = SentienceCompression()
_graph = SentienceGraph()
_automation = get_automation()
_host = get_host()
_automation_started = False

def get_agent():
    global _agent
    if _agent is None:
        api_keys = {p["provider"]: p["api_key"] for p in get_byok_keys()}
        _agent = SentienceAgent(api_keys, vault=_vault, compression=_compression)
    return _agent

# === API ROUTES ===

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "modules": {"vault": bool(_vault), "compression": bool(_compression), "graph": bool(_graph), "automation": _automation_started, "hosting": True, "remote": True, "email": True}})

# --- Conversations ---
@app.route("/api/conversations", methods=["GET"])
def api_list_conversations():
    return jsonify({"conversations": list_conversations()})

@app.route("/api/conversations", methods=["POST"])
def api_create_conversation():
    data = request.json
    cid = data.get("id", os.urandom(8).hex())
    title = data.get("title", "New Chat")
    create_conversation(cid, title)
    return jsonify({"id": cid, "title": title})

@app.route("/api/conversations/<cid>/messages")
def api_get_messages(cid):
    limit = request.args.get("limit", 100, type=int)
    return jsonify({"messages": get_messages(cid, limit)})

# --- Chat ---
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    cid = data.get("conversation_id", "default")
    msg = data.get("message", "")
    model = data.get("model", None)
    stream = data.get("stream", False)

    # Save user message
    save_message({"id": os.urandom(8).hex(), "conversation_id": cid, "role": "user", "content": msg})

    # Create conversation if needed
    if not get_conversation(cid):
        create_conversation(cid, msg[:50])

    # Run agent
    agent = get_agent()
    response = agent.run(msg, conversation_id=cid, model=model)

    # Save assistant response
    save_message({"id": os.urandom(8).hex(), "conversation_id": cid, "role": "assistant", "content": response})

    return jsonify({"response": response, "conversation_id": cid})

# --- Tools ---
@app.route("/api/tools")
def api_tools():
    reg = get_registry()
    tools = []
    for name, fn in reg._tools.items():
        tools.append({"name": name, "description": fn.__doc__ or "", "category": getattr(fn, "_category", "general")})
    return jsonify({"tools": tools, "count": len(tools)})

@app.route("/api/tools/execute", methods=["POST"])
def api_execute_tool():
    data = request.json
    name = data.get("name")
    args = data.get("args", {})
    ctx = ToolContext(workspace="/home/workspace")
    reg = get_registry()
    try:
        result = reg.call(name, args, ctx)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- Skills ---
@app.route("/api/skills")
def api_skills():
    return jsonify({"skills": list_all_skills()})

@app.route("/api/skills/<name>", methods=["GET"])
def api_get_skill(name):
    s = get_skill_by_name(name)
    if s: return jsonify(s)
    return jsonify({"error": "skill not found"}), 404

@app.route("/api/skills/execute", methods=["POST"])
def api_execute_skill():
    data = request.json
    name = data.get("name")
    args = data.get("args", {})
    ctx = ToolContext(workspace="/home/workspace")
    try:
        result = execute_skill(name, args, ctx)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/skills", methods=["POST"])
def api_create_skill():
    data = request.json
    skill = create_custom_skill(data.get("name"), data.get("description"), data.get("code"), data.get("category", "custom"))
    return jsonify({"created": skill})

@app.route("/api/skills/<name>", methods=["DELETE"])
def api_delete_skill(name):
    delete_skill(name)
    return jsonify({"deleted": name})

# --- Memory ---
@app.route("/api/memory")
def api_memory():
    return jsonify({"memories": list_memories()})

@app.route("/api/memory", methods=["POST"])
def api_set_memory():
    data = request.json
    set_memory(data.get("key"), data.get("value"))
    return jsonify({"stored": True})

@app.route("/api/memory/<key>", methods=["GET"])
def api_get_memory(key):
    return jsonify({"key": key, "value": get_memory(key)})

@app.route("/api/memory/<key>", methods=["DELETE"])
def api_delete_memory(key):
    delete_memory(key)
    return jsonify({"deleted": key})

@app.route("/api/vault/compress", methods=["POST"])
def api_vault_compress():
    data = request.json
    text = data.get("text", "")
    return jsonify({"compressed": _compression.compress(text), "original_size": len(text)})

@app.route("/api/vault/decompress", methods=["POST"])
def api_vault_decompress():
    data = request.json
    compressed = data.get("compressed", "")
    return jsonify({"decompressed": _compression.decompress(compressed)})

@app.route("/api/graph/entities", methods=["GET"])
def api_graph_entities():
    return jsonify({"entities": _graph.list_entities()})

@app.route("/api/graph/entities", methods=["POST"])
def api_graph_add_entity():
    data = request.json
    _graph.add_entity(data.get("entity_type"), data.get("name"), data.get("properties", {}))
    return jsonify({"added": True})

# --- BYOK ---
@app.route("/api/byok", methods=["GET"])
def api_byok():
    return jsonify({"providers": get_byok_keys()})

@app.route("/api/byok", methods=["POST"])
def api_byok_save():
    data = request.json
    save_byok_key(data.get("provider"), data.get("api_key"), data.get("models"))
    return jsonify({"saved": True})

# --- Automations ---
@app.route("/api/automations", methods=["GET"])
def api_automations():
    return jsonify({"automations": get_automations()})

@app.route("/api/automations", methods=["POST"])
def api_create_automation():
    data = request.json
    id = save_automation(data.get("name"), data.get("instruction"), data.get("rrule"), data.get("enabled", True))
    return jsonify({"id": id})

@app.route("/api/automations/<id>", methods=["DELETE"])
def api_delete_automation(id):
    delete_automation(id)
    return jsonify({"deleted": id})

@app.route("/api/automations/<id>", methods=["PATCH"])
def api_update_automation(id):
    data = request.json
    update_automation(id, data)
    return jsonify({"updated": True})

@app.route("/api/automations/history")
def api_automation_history():
    return jsonify({"history": get_automation_history()})

# --- Hosting ---
@app.route("/api/hosting/sites", methods=["GET"])
def api_sites():
    return jsonify({"sites": _host.list_sites()})

@app.route("/api/hosting/sites", methods=["POST"])
def api_create_site():
    data = request.json
    return jsonify(_host.create_site(data.get("name"), data.get("domain")))

@app.route("/api/hosting/sites/<name>", methods=["DELETE"])
def api_delete_site(name):
    return jsonify(_host.delete_site(name))

@app.route("/api/hosting/sites/<name>/url")
def api_site_url(name):
    return jsonify({"url": _host.get_public_url(name)})

# --- Remote ---
@app.route("/api/remote/connect", methods=["POST"])
def api_remote_connect():
    data = request.json
    rc = get_remote()
    result = rc.connect(data.get("host"), data.get("username"), data.get("password"), data.get("port", 22))
    return jsonify(result)

@app.route("/api/remote/execute", methods=["POST"])
def api_remote_execute():
    data = request.json
    rc = get_remote()
    result = rc.execute(data.get("command"), data.get("timeout", 30))
    return jsonify({"output": result})

@app.route("/api/remote/sftp/upload", methods=["POST"])
def api_remote_upload():
    data = request.json
    rc = get_remote()
    result = rc.upload_file(data.get("local_path"), data.get("remote_path"))
    return jsonify(result)

# --- Email ---
@app.route("/api/email/send", methods=["POST"])
def api_email_send():
    data = request.json
    listener = get_listener()
    result = listener.send_email(data.get("to"), data.get("subject"), data.get("body"), data.get("cc"), data.get("attachments"))
    return jsonify(result)

@app.route("/api/email/inbox")
def api_email_inbox():
    limit = request.args.get("limit", 20, type=int)
    return jsonify({"emails": get_listener().fetch_recent(limit)})

@app.route("/api/email/configure", methods=["POST"])
def api_configure_email():
    data = request.json()
    result = configure_gmail(data.get("username"), data.get("password"), data.get("poll_interval", 60))
    return jsonify(result)

@app.route("/api/email/rules", methods=["POST"])
def api_email_rule():
    data = request.json
    listener = get_listener()
    listener.add_rule(data.get("from"), data.get("subject_contains"), data.get("body_contains"), data.get("action"), data.get("action_data"))
    return jsonify({"rule_added": True})

# --- Cloud ---
@app.route("/api/cloud/providers")
def api_cloud_providers():
    return jsonify({"providers": ["dropbox", "onedrive", "google_drive"]})

@app.route("/api/cloud/configure", methods=["POST"])
def api_cloud_configure():
    data = request.json
    cloud = get_cloud(data.get("provider", "dropbox"))
    cloud.configure(data.get("token"), data.get("client_id"), data.get("client_secret"))
    return jsonify({"configured": True})

@app.route("/api/cloud/upload", methods=["POST"])
def api_cloud_upload():
    data = request.json
    cloud = get_cloud(data.get("provider", "dropbox"))
    result = cloud.upload(data.get("local_path"), data.get("remote_path"))
    return jsonify(result)

@app.route("/api/cloud/list", methods=["GET"])
def api_cloud_list():
    provider = request.args.get("provider", "dropbox")
    path = request.args.get("path", "")
    cloud = get_cloud(provider)
    return jsonify({"files": cloud.list_files(path)})

# --- UI ---
@app.route("/")
def index():
    return send_from_directory("ui", "index.html")

@app.route("/assets/<path:path>")
def assets(path):
    return send_from_directory("ui", f"assets/{path}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3132))
    print(f"Sentience server running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
