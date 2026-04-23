#!/usr/bin/env python3
"""Sentience Storage: SQLite + Vault Memory + Entity Graph."""
import sqlite3, json, time, os, hashlib, re
from typing import Optional, List, Any

DB_PATH = os.path.join(os.path.expanduser("~/.sentience"), "sentience.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_db = None

def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA synchronous=NORMAL")
        init_schema(_db)
    return _db

def init_schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT, created_at INTEGER, updated_at INTEGER);
        CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, tool_calls TEXT, tool_results TEXT, tokens_used INTEGER, created_at INTEGER);
        CREATE TABLE IF NOT EXISTS agent_memory (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER);
        CREATE TABLE IF NOT EXISTS vault (id TEXT PRIMARY KEY, key TEXT, content TEXT, tags TEXT, links TEXT, entity_type TEXT, entity_id TEXT, created_at INTEGER, updated_at INTEGER, last_accessed INTEGER, access_count INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS vault_index (term TEXT, vault_id TEXT, position INTEGER, PRIMARY KEY (term, vault_id, position));
        CREATE TABLE IF NOT EXISTS entity_graph (id TEXT PRIMARY KEY, entity_type TEXT, entity_name TEXT, properties TEXT, created_at INTEGER, updated_at INTEGER);
        CREATE TABLE IF NOT EXISTS graph_edges (id TEXT PRIMARY KEY, from_id TEXT, to_id TEXT, rel_type TEXT, weight REAL DEFAULT 1.0, created_at INTEGER);
        CREATE TABLE IF NOT EXISTS automations (id TEXT PRIMARY KEY, name TEXT, instruction TEXT, rrule TEXT, enabled INTEGER DEFAULT 1, last_run INTEGER, next_run INTEGER, created_at INTEGER);
        CREATE TABLE IF NOT EXISTS byok_keys (provider TEXT PRIMARY KEY, api_key TEXT, models TEXT, base_url TEXT, created_at INTEGER);
        CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT, created_at INTEGER, updated_at INTEGER);
        CREATE INDEX IF NOT EXISTS idx_vault_key ON vault(key);
        CREATE INDEX IF NOT EXISTS idx_vault_entity ON vault(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_vault_updated ON vault(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_graph_from ON graph_edges(from_id);
        CREATE INDEX IF NOT EXISTS idx_graph_to ON graph_edges(to_id);
    """)

def create_conversation(id, title="New Chat"):
    now = int(time.time()*1000)
    get_db().execute("INSERT OR IGNORE INTO conversations VALUES (?,?,?,?)", (id, title, now, now))

def get_conversation(id): return get_db().execute("SELECT * FROM conversations WHERE id=?", (id,)).fetchone()
def list_conversations(limit=50): return get_db().execute("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
def get_messages(conv_id, limit=200): return get_db().execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC LIMIT ?", (conv_id, limit)).fetchall()
def save_message(msg):
    now = int(time.time()*1000)
    get_db().execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
        (msg["id"], msg["conversation_id"], msg["role"], msg["content"],
         json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None,
         json.dumps(msg.get("tool_results")) if msg.get("tool_results") else None,
         msg.get("tokens_used", 0), now))

def set_memory(key, value):
    now = int(time.time()*1000)
    get_db().execute("INSERT OR REPLACE INTO agent_memory VALUES (?,?,?)", (key, value, now))
def get_memory(key): return get_db().execute("SELECT value FROM agent_memory WHERE key=?", (key,)).fetchone()
def list_memory(): return get_db().execute("SELECT * FROM agent_memory ORDER BY updated_at DESC").fetchall()

def save_byok(provider, api_key, models=None, base_url=None):
    now = int(time.time()*1000)
    get_db().execute("INSERT OR REPLACE INTO byok_keys VALUES (?,?,?,?,?)", (provider, api_key, models, base_url, now))
def get_byok(provider): return get_db().execute("SELECT * FROM byok_keys WHERE provider=?", (provider,)).fetchone()
def list_byok(): return [r[0] for r in get_db().execute("SELECT provider FROM byok_keys").fetchall()]

def save_kv(key, value):
    now = int(time.time()*1000)
    get_db().execute("INSERT OR REPLACE INTO kv_store VALUES (?,?,?,?)", (key, value, now, now))
def get_kv(key): return get_db().execute("SELECT value FROM kv_store WHERE key=?", (key,)).fetchone()

def save_vault_entry(entry):
    now = int(time.time()*1000)
    get_db().execute("""INSERT OR REPLACE INTO vault (id,key,content,tags,links,entity_type,entity_id,created_at,updated_at,last_accessed,access_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (entry["id"], entry.get("key"), entry.get("content",""), json.dumps(entry.get("tags",[])),
         json.dumps(entry.get("links",[])), entry.get("entity_type"), entry.get("entity_id"),
         entry.get("created_at", now), now, now, entry.get("access_count", 0)))
    for i, term in enumerate(re.findall(r'\w+', entry.get("content","").lower())):
        if len(term) > 2:
            try: get_db().execute("INSERT OR IGNORE INTO vault_index VALUES (?,?,?)", (term, entry["id"], i))
            except: pass

def search_vault(query, limit=20):
    db = get_db()
    terms = [t for t in re.findall(r'\w+', query.lower()) if len(t) > 2]
    if not terms: return []
    ids = set()
    for term in terms:
        for r in db.execute("SELECT vault_id FROM vault_index WHERE term=?", (term,)).fetchall(): ids.add(r[0])
    return [db.execute("SELECT * FROM vault WHERE id=?", (vid,)).fetchone() for vid in list(ids)[:limit] if db.execute("SELECT id FROM vault WHERE id=?", (vid,)).fetchone()]

def update_vault_access(vault_id):
    now = int(time.time()*1000)
    get_db().execute("UPDATE vault SET last_accessed=?, access_count=access_count+1 WHERE id=?", (now, vault_id))

def add_entity(entity_type, entity_name, properties=None):
    eid = hashlib.sha256(f"{entity_type}:{entity_name}".encode()).hexdigest()[:16]
    now = int(time.time()*1000)
    get_db().execute("INSERT OR IGNORE INTO entity_graph VALUES (?,?,?,?,?,?)", (eid, entity_type, entity_name, json.dumps(properties or {}), now, now))
    return eid

def add_edge(from_id, to_id, rel_type, weight=1.0):
    eid = hashlib.sha256(f"{from_id}:{to_id}:{rel_type}".encode()).hexdigest()[:16]
    now = int(time.time()*1000)
    get_db().execute("INSERT OR IGNORE INTO graph_edges VALUES (?,?,?,?,?,?)", (eid, from_id, to_id, rel_type, weight, now))

def get_connected_entities(entity_id, rel_type=None, depth=2):
    db = get_db()
    if depth == 1:
        if rel_type: return db.execute("SELECT g.*, e.rel_type, e.weight FROM graph_edges e JOIN entity_graph g ON g.id=e.to_id WHERE e.from_id=? AND e.rel_type=?", (entity_id, rel_type)).fetchall()
        return db.execute("SELECT g.*, e.rel_type, e.weight FROM graph_edges e JOIN entity_graph g ON g.id=e.to_id WHERE e.from_id=?", (entity_id,)).fetchall()
    ids = {entity_id}
    for _ in range(depth):
        new_ids = set()
        for eid in ids: new_ids.update(r[0] for r in db.execute("SELECT to_id FROM graph_edges WHERE from_id=?", (eid,)).fetchall())
        ids.update(new_ids)
    placeholders = ",".join("?" * len(ids))
    if rel_type: return db.execute(f"SELECT g.*, e.rel_type, e.weight FROM graph_edges e JOIN entity_graph g ON g.id=e.to_id WHERE e.from_id IN ({placeholders}) AND e.rel_type=?", (*list(ids), rel_type)).fetchall()
    return db.execute(f"SELECT g.*, e.rel_type, e.weight FROM graph_edges e JOIN entity_graph g ON g.id=e.to_id WHERE e.from_id IN ({placeholders})", (*list(ids),)).fetchall()

def save_automation(automation):
    now = int(time.time()*1000)
    get_db().execute("INSERT OR REPLACE INTO automations VALUES (?,?,?,?,?,?,?,?)",
        (automation["id"], automation["name"], automation["instruction"], automation["rrule"],
         automation.get("enabled",1), automation.get("last_run"), automation.get("next_run"), now))
def list_automations(): return get_db().execute("SELECT * FROM automations ORDER BY created_at DESC").fetchall()
