#!/usr/bin/env python3
"""Memory system - knowledge graph, compression, persistence"""
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import lz4.frame

class Memory:
    """
    Advanced memory system with:
    - SQLite persistence
    - LZ4 compression
    - Knowledge graph
    - Semantic search (basic)
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Conversations
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Messages
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                compressed INTEGER DEFAULT 0,
                tool_calls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        
        # Memory store (key-value with metadata)
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                key TEXT PRIMARY KEY,
                value TEXT,
                compressed INTEGER DEFAULT 0,
                tags TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Knowledge graph
        c.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                type TEXT,
                properties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                from_entity TEXT,
                to_entity TEXT,
                relation_type TEXT,
                properties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (from_entity) REFERENCES entities(id),
                FOREIGN KEY (to_entity) REFERENCES entities(id)
            )
        """)
        
        # Skills
        c.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                description TEXT,
                code TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Automations
        c.execute("""
            CREATE TABLE IF NOT EXISTS automations (
                id TEXT PRIMARY KEY,
                name TEXT,
                instruction TEXT,
                schedule TEXT,
                enabled INTEGER DEFAULT 1,
                last_run TIMESTAMP,
                next_run TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _compress(self, data: str) -> bytes:
        """Compress string with LZ4"""
        return lz4.frame.compress(data.encode())
    
    def _decompress(self, data: bytes) -> str:
        """Decompress LZ4 data"""
        return lz4.frame.decompress(data).decode()
    
    # === Conversations ===
    
    def create_conversation(self, id: str, title: str = "New Chat") -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO conversations (id, title) VALUES (?, ?)",
            (id, title)
        )
        conn.commit()
        conn.close()
    
    def get_conversation(self, id: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM conversations WHERE id = ?", (id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}
        return None
    
    def list_conversations(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        )
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]
    
    # === Messages ===
    
    def save_message(
        self, 
        id: str, 
        conversation_id: str, 
        role: str, 
        content: str,
        tool_calls: Optional[List] = None,
        compress: bool = False
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        
        if compress and len(content) > 1000:
            content_data = self._compress(content)
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, compressed, tool_calls) VALUES (?, ?, ?, ?, 1, ?)",
                (id, conversation_id, role, content_data, json.dumps(tool_calls) if tool_calls else None)
            )
        else:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, tool_calls) VALUES (?, ?, ?, ?, ?)",
                (id, conversation_id, role, content, json.dumps(tool_calls) if tool_calls else None)
            )
        
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,)
        )
        conn.commit()
        conn.close()
    
    def get_messages(self, conversation_id: str, limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT id, role, content, compressed, tool_calls FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
            (conversation_id, limit)
        )
        rows = c.fetchall()
        conn.close()
        
        messages = []
        for r in rows:
            content = r[2]
            if r[3]:  # compressed
                content = self._decompress(content)
            messages.append({
                "id": r[0],
                "role": r[1],
                "content": content,
                "tool_calls": json.loads(r[4]) if r[4] else None
            })
        return messages
    
    # === Memory Store ===
    
    def remember(self, key: str, value: str, tags: List[str] = None) -> None:
        """Store a memory with optional tags"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO memory (key, value, tags, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (key, value, json.dumps(tags) if tags else None)
        )
        conn.commit()
        conn.close()
    
    def recall(self, key: str) -> Optional[str]:
        """Retrieve a memory"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value FROM memory WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    
    def search_memory(self, query: str, limit: int = 10) -> List[Dict]:
        """Basic text search in memory"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT key, value, tags FROM memory WHERE value LIKE ? OR key LIKE ? LIMIT ?",
            (f"%{query}%", f"%{query}%", limit)
        )
        rows = c.fetchall()
        conn.close()
        return [{"key": r[0], "value": r[1], "tags": json.loads(r[2]) if r[2] else []} for r in rows]
    
    def list_memory(self) -> List[Dict]:
        """List all memories"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT key, value, tags, updated_at FROM memory ORDER BY updated_at DESC")
        rows = c.fetchall()
        conn.close()
        return [{"key": r[0], "value": r[1], "tags": json.loads(r[2]) if r[2] else [], "updated_at": r[3]} for r in rows]
    
    # === Knowledge Graph ===
    
    def add_entity(self, name: str, type: str = "thing", properties: Dict = None) -> str:
        """Add entity to knowledge graph"""
        entity_id = hashlib.md5(name.encode()).hexdigest()[:12]
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO entities (id, name, type, properties) VALUES (?, ?, ?, ?)",
            (entity_id, name, type, json.dumps(properties or {}))
        )
        conn.commit()
        conn.close()
        return entity_id
    
    def add_relation(self, from_entity: str, to_entity: str, relation_type: str, properties: Dict = None) -> None:
        """Add relation between entities"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO relations (from_entity, to_entity, relation_type, properties) VALUES (?, ?, ?, ?)",
            (from_entity, to_entity, relation_type, json.dumps(properties or {}))
        )
        conn.commit()
        conn.close()
    
    def query_graph(self, entity: str, depth: int = 1) -> Dict:
        """Query knowledge graph around an entity"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Get entity
        c.execute("SELECT * FROM entities WHERE name = ?", (entity,))
        entity_row = c.fetchone()
        
        if not entity_row:
            conn.close()
            return {"entity": None, "relations": []}
        
        result = {
            "entity": {
                "id": entity_row[0],
                "name": entity_row[1],
                "type": entity_row[2],
                "properties": json.loads(entity_row[3])
            },
            "relations": []
        }
        
        # Get outgoing relations
        c.execute(
            "SELECT r.relation_type, r.properties, e.name FROM relations r JOIN entities e ON r.to_entity = e.id WHERE r.from_entity = ?",
            (entity_row[0],)
        )
        for r in c.fetchall():
            result["relations"].append({
                "type": r[0],
                "properties": json.loads(r[1]) if r[1] else {},
                "to": r[2]
            })
        
        conn.close()
        return result
    
    # === Skills ===
    
    def save_skill(self, name: str, description: str, code: str) -> None:
        """Save a skill"""
        import uuid
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO skills (id, name, description, code) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), name, description, code)
        )
        conn.commit()
        conn.close()
    
    def get_skill(self, name: str) -> Optional[Dict]:
        """Get skill by name"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM skills WHERE name = ? AND enabled = 1", (name,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "name": row[1], "description": row[2], "code": row[3]}
        return None
    
    def list_skills(self) -> List[Dict]:
        """List all skills"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT name, description FROM skills WHERE enabled = 1")
        rows = c.fetchall()
        conn.close()
        return [{"name": r[0], "description": r[1]} for r in rows]
    
    # === Automations ===
    
    def save_automation(self, name: str, instruction: str, schedule: str) -> str:
        """Save an automation"""
        import uuid
        auto_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO automations (id, name, instruction, schedule) VALUES (?, ?, ?, ?)",
            (auto_id, name, instruction, schedule)
        )
        conn.commit()
        conn.close()
        return auto_id
    
    def list_automations(self) -> List[Dict]:
        """List all automations"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, name, instruction, schedule, enabled, last_run, next_run FROM automations")
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0],
            "name": r[1],
            "instruction": r[2],
            "schedule": r[3],
            "enabled": bool(r[4]),
            "last_run": r[5],
            "next_run": r[6]
        } for r in rows]
