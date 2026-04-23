#!/usr/bin/env python3
"""Sentience v1.0 - Full Local AI Computer with all features."""
import os, sys, json, sqlite3, hashlib, uuid, time, subprocess, glob, shutil, zipfile, re, traceback, asyncio
from datetime import datetime, timedelta
from pathlib import Path
from werkzeug.serving import run_simple
try: from flask import Flask, request, jsonify, send_file; from flask_cors import CORS
except: Flask = None

# === CONSTANTS ===
VERSION = "1.0.0"
DB_PATH = os.path.expanduser("~/.sentience/sentience.db")
WORKSPACE = os.path.expanduser("~/.sentience/workspace")
SKILLS_DIR = os.path.expanduser("~/.sentience/skills")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(SKILLS_DIR, exist_ok=True)

# === DATABASE ===
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT, created_at INTEGER, updated_at INTEGER);
    CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, key TEXT UNIQUE, value TEXT, tags TEXT, created_at INTEGER, updated_at INTEGER);
    CREATE TABLE IF NOT EXISTS skills (id TEXT PRIMARY KEY, name TEXT UNIQUE, description TEXT, code TEXT, enabled INTEGER, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS byok (provider TEXT PRIMARY KEY, api_key TEXT, models TEXT, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS automations (id TEXT PRIMARY KEY, name TEXT, instruction TEXT, rrule TEXT, enabled INTEGER, last_run INTEGER, next_run INTEGER, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, path TEXT UNIQUE, content TEXT, encoding TEXT, created_at INTEGER, updated_at INTEGER);
    CREATE TABLE IF NOT EXISTS graph_nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, data TEXT, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS graph_edges (id TEXT PRIMARY KEY, source TEXT, target TEXT, relation TEXT, weight REAL, created_at INTEGER);
    CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
    """)
    db.commit()
    return db

init_db()

print(f"[Sentience v{VERSION}] Database initialized at {DB_PATH}")
print(f"[Sentience] Workspace: {WORKSPACE}")
print(f"[Sentience] Skills: {SKILLS_DIR}")
print(f"[Sentience] Ready.")
