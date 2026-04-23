#!/usr/bin/env python3
"""Sentience Server - Flask REST API with all features."""
import os, sys, json

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.serving import run_simple

from storage import init_schema, get_db
from agent.engine import SentienceAgent
from agent.tools.registry import tool_registry

app = Flask(__name__, static_folder="ui", static_url_path="")
CORS(app)

PORT = int(os.environ.get("SENTIENCE_PORT", 3132))
AGENT = None

def get_agent():
    global AGENT
    if AGENT is None:
        AGENT = SentienceAgent()
    return AGENT

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "tools": len(tool_registry.list_tools())})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    conversation_id = data.get("conversation_id", "default")
    if not message:
        return jsonify({"error": "No message"}), 400
    agent = get_agent()
    try:
        response = agent.process(message, conversation_id)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools", methods=["GET"])
def list_tools():
    tools = tool_registry.list_tools()
    return jsonify({"tools": [{"name": t.name, "description": t.description, "parameters": list(t.parameters.keys()) if t.parameters else []} for t in tools], "count": len(tools)})

@app.route("/api/tools/<tool_name>", methods=["POST"])
def call_tool(tool_name):
    data = request.json or {}
    result = tool_registry.call_tool(tool_name, data)
    return jsonify(result)

@app.route("/api/forms/templates", methods=["GET"])
def list_templates():
    from forms.engine import list_available_templates
    return jsonify({"templates": list_available_templates()})

@app.route("/api/forms/create", methods=["POST"])
def create_form():
    from forms.engine import create_form_from_template
    data = request.json
    form = create_form_from_template(data.get("template_name", "government_form"))
    return jsonify({"form": {"name": form.name, "type": form.type, "fields": [{"name": f.name, "type": f.type, "label": f.label, "required": f.required} for f in form.fields]}})

@app.route("/api/forms/fill", methods=["POST"])
def fill_form():
    from forms.engine import AutoFillEngine, create_form_from_template
    data = request.json
    form = create_form_from_template(data.get("form_type", "government_form"))
    engine = AutoFillEngine(get_agent())
    filled = engine.fill_form(form, data.get("reference_docs", []), data.get("profile", {}))
    return jsonify({"fields": [{"name": f.name, "value": f.value, "confidence": f.confidence} for f in filled.fields]})

@app.route("/api/analysis", methods=["POST"])
def analyze():
    from analysis.engine import SentienceAnalysis
    data = request.json
    text = data.get("text", "")
    mode = data.get("mode", "full")
    analyzer = SentienceAnalysis()
    return jsonify(analyzer.analyze_document(text, mode))

@app.route("/api/research", methods=["POST"])
def research():
    from research.engine import ResearchEngine
    data = request.json
    query = data.get("query", "")
    deep = data.get("deep", False)
    engine = ResearchEngine()
    if deep:
        return jsonify(engine.deep_research(query, data.get("depth", 3)))
    return jsonify(engine.quick_research(query))

@app.route("/api/knowledge", methods=["GET", "POST"])
def knowledge():
    from knowledge.engine import KnowledgeBase
    kb = KnowledgeBase()
    if request.method == "GET":
        q = request.args.get("q", "")
        cat = request.args.get("category", None)
        if q:
            results = kb.search(q, category=cat)
            return jsonify({"results": [{"title": r.entry.title, "content": r.entry.content[:200], "score": r.score} for r in results]})
        return jsonify({"stats": kb.get_stats()})
    else:
        data = request.json
        kb_id = kb.add(data.get("title", ""), data.get("content", ""), data.get("tags", []), data.get("category", "general"))
        return jsonify({"id": kb_id})

@app.route("/api/tasks", methods=["GET", "POST"])
def tasks():
    from execution.engine import ExecutionEngine
    agent = get_agent()
    engine = ExecutionEngine(agent)
    if request.method == "POST":
        data = request.json
        task_id = engine.submit_task(data.get("instruction", ""), context=data.get("context"))
        return jsonify({"task_id": task_id})
    else:
        status = request.args.get("status", None)
        return jsonify({"tasks": engine.list_tasks(status)})

@app.route("/ui/<path:path>")
def serve_ui(path):
    return send_from_directory(app.static_folder, path)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    init_schema(get_db())
    print(f"Sentience server running on http://localhost:{PORT}")
    print(f"API docs: http://localhost:{PORT}/api")
    run_simple("0.0.0.0", PORT, app, use_reloader=False)
