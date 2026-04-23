#!/usr/bin/env python3
"""Memory Engine - Obsidian-like vault with learning"""
import os
import json
import sqlite3
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import hashlib
import lz4.frame

@dataclass
class Note:
    id: str
    title: str
    content: str
    path: str
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
@dataclass
class Entity:
    id: str
    name: str
    type: str  # person, concept, project, technology
    properties: Dict = field(default_factory=dict)
    relations: List[Dict] = field(default_factory=list)

class SentienceVault:
    """Obsidian-like knowledge vault"""
    
    def __init__(self, vault_dir: str = None):
        self.vault_dir = Path(vault_dir or Path.home() / ".sentience" / "vault")
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.vault_dir / ".index.db"
        self._init_index()
        
    def _init_index(self):
        """Initialize SQLite index"""
        conn = sqlite3.connect(self.index_file)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                tags TEXT,
                links TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                properties TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                weight REAL DEFAULT 1.0
            )
        """)
        
        c.execute("CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title)")
        
        conn.commit()
        conn.close()
        
    def create_note(self, title: str, content: str, tags: List[str] = None) -> Note:
        """Create a new note"""
        import uuid
        
        note_id = str(uuid.uuid4())
        file_name = f"{title.replace('/', '-').replace(' ', '_')}.md"
        note_path = self.vault_dir / file_name
        
        # Extract links (wiki-style [[link]])
        links = []
        import re
        for match in re.finditer(r'\[\[([^\]]+)\]\]', content):
            links.append(match.group(1))
            
        note = Note(
            id=note_id,
            title=title,
            content=content,
            path=str(note_path),
            tags=tags or [],
            links=links
        )
        
        # Write file
        with open(note_path, 'w') as f:
            f.write(f"---\n")
            f.write(f"id: {note_id}\n")
            f.write(f"title: {title}\n")
            f.write(f"tags: {json.dumps(tags or [])}\n")
            f.write(f"created: {note.created_at}\n")
            f.write(f"---\n\n")
            f.write(content)
            
        # Index
        self._index_note(note)
        
        return note
        
    def _index_note(self, note: Note):
        """Index a note in SQLite"""
        conn = sqlite3.connect(self.index_file)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR REPLACE INTO notes (id, title, path, tags, links, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            note.id, note.title, note.path,
            json.dumps(note.tags), json.dumps(note.links),
            note.created_at, note.updated_at
        ))
        
        # Update backlinks
        for link in note.links:
            # Find target note
            c.execute("SELECT id FROM notes WHERE title = ?", (link,))
            row = c.fetchone()
            if row:
                target_id = row[0]
                c.execute("""
                    INSERT OR REPLACE INTO relations (source, target, type, weight)
                    VALUES (?, ?, 'links_to', 1.0)
                """, (note.id, target_id))
                
        conn.commit()
        conn.close()
        
    def get_note(self, note_id: str) -> Optional[Note]:
        """Get note by ID"""
        conn = sqlite3.connect(self.index_file)
        c = conn.cursor()
        
        c.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            note_path = Path(row[2])
            if note_path.exists():
                content = note_path.read_text()
                # Parse frontmatter
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        content = parts[2].strip()
                        
                return Note(
                    id=row[0], title=row[1], content=content,
                    path=row[2], tags=json.loads(row[3]), links=json.loads(row[4]),
                    created_at=row[5], updated_at=row[6]
                )
        return None
        
    def search_notes(self, query: str) -> List[Note]:
        """Search notes by title or content"""
        conn = sqlite3.connect(self.index_file)
        c = conn.cursor()
        
        c.execute("SELECT * FROM notes WHERE title LIKE ?", (f"%{query}%",))
        rows = c.fetchall()
        conn.close()
        
        return [self.get_note(row[0]) for row in rows if self.get_note(row[0])]
        
    def get_by_tag(self, tag: str) -> List[Note]:
        """Get notes by tag"""
        conn = sqlite3.connect(self.index_file)
        c = conn.cursor()
        
        c.execute("SELECT * FROM notes WHERE tags LIKE ?", (f"%{tag}%",))
        rows = c.fetchall()
        conn.close()
        
        return [self.get_note(row[0]) for row in rows if self.get_note(row[0])]


class KnowledgeGraph:
    """Knowledge graph for entities and relations"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path.home() / ".sentience" / "knowledge.db")
        self._init_db()
        
    def _init_db(self):
        """Initialize graph database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                properties TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT,
                PRIMARY KEY (source, target, type)
            )
        """)
        
        conn.commit()
        conn.close()
        
    def add_entity(self, entity: Entity):
        """Add entity to graph"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR REPLACE INTO nodes (id, type, properties)
            VALUES (?, ?, ?)
        """, (entity.id, entity.type, json.dumps(entity.properties)))
        
        # Add relations
        for rel in entity.relations:
            c.execute("""
                INSERT OR REPLACE INTO edges (source, target, type, properties)
                VALUES (?, ?, ?, ?)
            """, (entity.id, rel.get('target'), rel.get('type'), json.dumps(rel.get('properties', {}))))
            
        conn.commit()
        conn.close()
        
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT * FROM nodes WHERE id = ?", (entity_id,))
        row = c.fetchone()
        
        if row:
            # Get relations
            c.execute("SELECT target, type, properties FROM edges WHERE source = ?", (entity_id,))
            relations = [{"target": r[0], "type": r[1], "properties": json.loads(r[2])} for r in c.fetchall()]
            
            conn.close()
            return Entity(
                id=row[0], type=row[1],
                properties=json.loads(row[2]),
                relations=relations
            )
            
        conn.close()
        return None
        
    def find_path(self, source: str, target: str) -> List[List[str]]:
        """Find paths between entities"""
        # BFS path finding
        paths = []
        queue = [[source]]
        visited = set()
        
        while queue and len(paths) < 10:
            path = queue.pop(0)
            node = path[-1]
            
            if node == target:
                paths.append(path)
                continue
                
            if node in visited:
                continue
            visited.add(node)
            
            # Get connected nodes
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT target FROM edges WHERE source = ?", (node,))
            neighbors = [row[0] for row in c.fetchall()]
            conn.close()
            
            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append(path + [neighbor])
                    
        return paths


class LearningSystem:
    """Self-improvement and learning"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path.home() / ".sentience" / "learning.db")
        self._init_db()
        
    def _init_db(self):
        """Initialize learning database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                input TEXT,
                output TEXT,
                feedback INTEGER,
                metadata TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL UNIQUE,
                count INTEGER DEFAULT 1,
                success_rate REAL DEFAULT 0.5,
                last_seen TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                confidence REAL DEFAULT 1.0
            )
        """)
        
        conn.commit()
        conn.close()
        
    def log_interaction(self, type: str, input: str, output: str, feedback: int = None, metadata: dict = None):
        """Log an interaction"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO interactions (timestamp, type, input, output, feedback, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), type, input, output, feedback, json.dumps(metadata or {})))
        
        conn.commit()
        conn.close()
        
    def learn_pattern(self, pattern: str, success: bool):
        """Learn a pattern"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Check if pattern exists
        c.execute("SELECT count, success_rate FROM patterns WHERE pattern = ?", (pattern,))
        row = c.fetchone()
        
        if row:
            count, rate = row
            new_count = count + 1
            new_rate = (rate * count + (1.0 if success else 0.0)) / new_count
            
            c.execute("""
                UPDATE patterns SET count = ?, success_rate = ?, last_seen = ?
                WHERE pattern = ?
            """, (new_count, new_rate, datetime.now().isoformat(), pattern))
        else:
            c.execute("""
                INSERT INTO patterns (pattern, count, success_rate, last_seen)
                VALUES (?, 1, 1.0 if success else 0.0, ?)
            """, (pattern, datetime.now().isoformat()))
            
        conn.commit()
        conn.close()
        
    def get_preference(self, key: str) -> Optional[Any]:
        """Get learned preference"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT value, confidence FROM preferences WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0]), row[1]
        return None
        
    def set_preference(self, key: str, value: Any, confidence: float = 1.0):
        """Set preference"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR REPLACE INTO preferences (key, value, confidence)
            VALUES (?, ?, ?)
        """, (key, json.dumps(value), confidence))
        
        conn.commit()
        conn.close()
        
    def get_successful_patterns(self, min_success_rate: float = 0.7) -> List[Dict]:
        """Get patterns with high success rate"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            SELECT pattern, success_rate, count FROM patterns
            WHERE success_rate >= ? AND count >= 3
            ORDER BY success_rate DESC, count DESC
        """, (min_success_rate,))
        
        results = [{"pattern": row[0], "success_rate": row[1], "count": row[2]} 
                   for row in c.fetchall()]
        conn.close()
        return results
