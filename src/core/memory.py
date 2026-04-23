#!/usr/bin/env python3
"""Sentience Memory System - SQLite + LZ4 Compression + Knowledge Graph"""
import sqlite3
import json
import hashlib
import zlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Optional LZ4 for better compression
try:
    import lz4.frame as lz4
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False
    logger.warning("lz4 not installed, using zlib compression")


@dataclass
class Memory:
    id: str
    key: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = None
    created_at: datetime = None
    updated_at: datetime = None
    access_count: int = 0


class MemorySystem:
    """Obsidian-like vault with compression and knowledge graph"""
    
    def __init__(self, db_path: Path, vault_dir: Path):
        self.db_path = Path(db_path)
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database with all tables"""
        with sqlite3.connect(self.db_path) as conn:
            # Core memory table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    key TEXT UNIQUE NOT NULL,
                    content_compressed BLOB,
                    compression TEXT DEFAULT 'lz4',
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    access_count INTEGER DEFAULT 0
                )
            """)
            
            # Embeddings table (separate for size)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    memory_id TEXT PRIMARY KEY,
                    embedding BLOB,
                    model TEXT,
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                )
            """)
            
            # Knowledge graph - nodes
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    properties TEXT,
                    created_at TEXT
                )
            """)
            
            # Knowledge graph - edges
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    properties TEXT,
                    FOREIGN KEY (source_id) REFERENCES graph_nodes(id),
                    FOREIGN KEY (target_id) REFERENCES graph_nodes(id)
                )
            """)
            
            # Conversations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            
            # Messages
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    tool_results TEXT,
                    created_at TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
            
            conn.commit()
            
    def _compress(self, data: str) -> Tuple[bytes, str]:
        """Compress data using LZ4 or zlib"""
        raw = data.encode('utf-8')
        if HAS_LZ4:
            return lz4.compress(raw), 'lz4'
        return zlib.compress(raw, level=9), 'zlib'
    
    def _decompress(self, data: bytes, method: str) -> str:
        """Decompress data"""
        if method == 'lz4' and HAS_LZ4:
            return lz4.decompress(data).decode('utf-8')
        return zlib.decompress(data).decode('utf-8')
    
    def store(self, key: str, content: str, metadata: Dict = None) -> str:
        """Store memory with compression"""
        memory_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        compressed, method = self._compress(content)
        now = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata or {})
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO memories (id, key, content_compressed, compression, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET 
                    content_compressed = excluded.content_compressed,
                    compression = excluded.compression,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at,
                    access_count = access_count + 1
            """, (memory_id, key, compressed, method, metadata_json, now, now))
            conn.commit()
        
        # Also save to vault as markdown
        vault_path = self.vault_dir / f"{key.replace('/', '_')}.md"
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        with open(vault_path, 'w') as f:
            f.write(f"---\nkey: {key}\ncreated: {now}\n---\n\n{content}")
            
        return memory_id
    
    def retrieve(self, key: str) -> Optional[Memory]:
        """Retrieve memory by key"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM memories WHERE key = ?", (key,)
            ).fetchone()
            
            if not row:
                return None
                
            content = self._decompress(row['content_compressed'], row['compression'])
            
            # Update access count
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1 WHERE id = ?",
                (row['id'],)
            )
            conn.commit()
            
            return Memory(
                id=row['id'],
                key=row['key'],
                content=content,
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                access_count=row['access_count']
            )
    
    def search(self, query: str, limit: int = 10) -> List[Memory]:
        """Search memories by key/content (simple text search)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, key, content_compressed, compression, metadata, created_at, updated_at, access_count
                FROM memories 
                WHERE key LIKE ? OR metadata LIKE ?
                ORDER BY access_count DESC, updated_at DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit)).fetchall()
            
            results = []
            for row in rows:
                content = self._decompress(row['content_compressed'], row['compression'])
                if query.lower() in content.lower() or query.lower() in row['key'].lower():
                    results.append(Memory(
                        id=row['id'],
                        key=row['key'],
                        content=content,
                        metadata=json.loads(row['metadata']) if row['metadata'] else {},
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                        access_count=row['access_count']
                    ))
            return results
    
    # === Knowledge Graph ===
    
    def add_node(self, node_id: str, node_type: str, label: str, properties: Dict = None) -> None:
        """Add node to knowledge graph"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO graph_nodes (id, type, label, properties, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET label = excluded.label, properties = excluded.properties
            """, (node_id, node_type, label, json.dumps(properties or {}), datetime.utcnow().isoformat()))
            conn.commit()
    
    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0, properties: Dict = None) -> None:
        """Add edge to knowledge graph"""
        edge_id = hashlib.sha256(f"{source_id}:{relation}:{target_id}".encode()).hexdigest()[:16]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO graph_edges (id, source_id, target_id, relation, weight, properties)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET weight = excluded.weight, properties = excluded.properties
            """, (edge_id, source_id, target_id, relation, weight, json.dumps(properties or {})))
            conn.commit()
    
    def get_related(self, node_id: str, relation: str = None, depth: int = 1) -> List[Dict]:
        """Get related nodes from knowledge graph"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT e.*, n.label, n.type 
                FROM graph_edges e
                JOIN graph_nodes n ON e.target_id = n.id
                WHERE e.source_id = ?
            """
            params = [node_id]
            if relation:
                query += " AND e.relation = ?"
                params.append(relation)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    # === Conversations ===
    
    def create_conversation(self, title: str = None) -> str:
        """Create new conversation"""
        conv_id = hashlib.sha256(datetime.utcnow().isoformat().encode()).hexdigest()[:16]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conv_id, title or "New Chat", datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
            )
            conn.commit()
        return conv_id
    
    def add_message(self, conversation_id: str, role: str, content: str, tool_calls: List = None, tool_results: List = None) -> str:
        """Add message to conversation"""
        msg_id = hashlib.sha256(f"{conversation_id}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, tool_calls, tool_results, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, conversation_id, role, content, 
                 json.dumps(tool_calls) if tool_calls else None,
                 json.dumps(tool_results) if tool_results else None,
                 datetime.utcnow().isoformat())
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), conversation_id)
            )
            conn.commit()
        return msg_id
    
    def get_conversation(self, conversation_id: str, limit: int = 100) -> List[Dict]:
        """Get conversation messages"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
                (conversation_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]


# Export
__all__ = ['MemorySystem', 'Memory']
