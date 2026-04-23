#!/usr/bin/env python3
"""Sentience Vault - Obsidian-like memory with bidirectional linking."""
import os, json, time, hashlib, re
from typing import List, Dict, Any, Optional
from datetime import datetime

WORKSPACE = os.path.expanduser("~/sentience_vault")
os.makedirs(WORKSPACE, exist_ok=True)

class SentienceVault:
    def __init__(self, storage, compression=None):
        self.storage = storage
        self.compression = compression
        self.workspace = WORKSPACE
    
    def note_path(self, note_id: str) -> str:
        return os.path.join(self.workspace, f"{note_id}.md")
    
    def create_note(self, title: str, content: str = "", tags: List[str] = None, links: List[str] = None, entity_type: str = None, entity_id: str = None) -> dict:
        nid = hashlib.sha256(f"{title}{time.time()}".encode()).hexdigest()[:16]
        now = int(time.time()*1000)
        entry = {"id": nid, "key": title, "content": content, "tags": tags or [], "links": links or [], "entity_type": entity_type, "entity_id": entity_id, "created_at": now}
        self.storage.save_vault_entry(entry)
        with open(self.note_path(nid), "w") as f:
            f.write(f"# {title}\n\n{content}")
        if entity_type and entity_id:
            self.storage.add_entity(entity_type, entity_name=title, properties={"note_id": nid, "tags": tags})
        return entry
    
    def update_note(self, note_id: str, content: str, tags: List[str] = None) -> None:
        entry = self.storage.search_vault(note_id, limit=1)
        path = self.note_path(note_id)
        if os.path.exists(path):
            with open(path) as f: lines = f.readlines()
            if lines: lines[0] = f"# {content.split(chr(10))[0]}\n"
            with open(path, "w") as f: f.write(content)
        now = int(time.time()*1000)
        self.storage.save_vault_entry({"id": note_id, "content": content, "tags": tags or [], "updated_at": now})
    
    def link_notes(self, from_id: str, to_id: str, rel: str = "linked_to") -> None:
        self.storage.add_edge(from_id, to_id, rel)
        self.storage.add_edge(to_id, from_id, "linked_from")
        from_path = self.note_path(from_id)
        to_path = self.note_path(to_id)
        if os.path.exists(from_path) and os.path.exists(to_path):
            with open(from_path) as f: fc = f.read()
            link_text = f"[[{to_id}]]"
            if link_text not in fc: 
                with open(from_path, "a") as f: f.write(f"\n\n{link_text}")
    
    def get_note(self, note_id: str) -> Optional[dict]:
        self.storage.update_vault_access(note_id)
        path = self.note_path(note_id)
        if os.path.exists(path):
            with open(path) as f: content = f.read()
            return {"id": note_id, "content": content}
        rows = self.storage.search_vault(note_id, limit=1)
        if rows: return {"id": note_id, "content": rows[0][2] if len(rows[0]) > 2 else ""}
        return None
    
    def search_notes(self, query: str, limit: int = 20) -> List[dict]:
        return self.storage.search_vault(query, limit)
    
    def get_backlinks(self, note_id: str) -> List[dict]:
        rows = self.storage.get_connected_entities(note_id, rel_type="linked_from", depth=1)
        results = []
        for row in rows:
            if len(row) >= 4: results.append({"id": row[0], "entity_type": row[1], "entity_name": row[2]})
        return results
    
    def get_graph_view(self, center_id: str = None, depth: int = 2) -> dict:
        nodes, edges = [], []
        if center_id:
            rows = self.storage.get_connected_entities(center_id, depth=depth)
            for row in rows:
                if len(row) >= 4:
                    nodes.append({"id": row[0], "type": row[1], "label": row[2], "props": json.loads(row[3]) if row[3] else {}})
                    edges.append({"from": center_id, "to": row[0], "rel": row[4], "weight": row[5]})
        else:
            all_nodes = self.storage.list_memory()
        return {"nodes": nodes, "edges": edges}
    
    def daily_note(self, date: datetime = None) -> dict:
        d = date or datetime.now()
        title = d.strftime("%Y-%m-%d")
        path = os.path.join(self.workspace, "daily", f"{title}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"# {title}\n\n## Tasks\n\n## Notes\n\n## Reflections\n")
        with open(path) as f: content = f.read()
        return {"title": title, "content": content, "path": path}
