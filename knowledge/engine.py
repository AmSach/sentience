"""Knowledge base - persistent, searchable, multi-user knowledge system."""
import sqlite3, json, time, uuid, hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime

class KBEntry:
    def __init__(self, id: str, title: str, content: str, tags: List[str], category: str, metadata: Dict = None):
        self.id = id
        self.title = title
        self.content = content
        self.tags = tags
        self.category = category
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.updated_at = time.time()
        self.views = 0
        self.likes = 0
        self.embedding = None
        self.author = "local"
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "category": self.category,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "views": self.views,
            "likes": self.likes,
            "author": self.author,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "KBEntry":
        e = cls(d["id"], d["title"], d["content"], d["tags"], d["category"], d.get("metadata"))
        e.created_at = d.get("created_at", time.time())
        e.updated_at = d.get("updated_at", time.time())
        e.views = d.get("views", 0)
        e.likes = d.get("likes", 0)
        e.author = d.get("author", "local")
        return e

class SearchResult:
    def __init__(self, entry: KBEntry, score: float, highlights: List[str]):
        self.entry = entry
        self.score = score
        self.highlights = highlights

class KnowledgeBase:
    """Persistent vector-like knowledge base with SQLite."""
    
    def __init__(self, db_path: str = "sentience_kb.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()
    
    def _init(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_entries (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT,
                category TEXT DEFAULT 'general',
                metadata TEXT,
                created_at REAL,
                updated_at REAL,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                author TEXT DEFAULT 'local',
                search_text TEXT
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_title ON kb_entries(title)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_category ON kb_entries(category)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_tags ON kb_entries(tags)")
        self.conn.commit()
    
    def add(self, title: str, content: str, tags: List[str] = None, category: str = "general", metadata: Dict = None, author: str = "local") -> str:
        id = str(uuid.uuid4())
        now = time.time()
        search_text = f"{title} {content} {' '.join(tags or [])}".lower()
        self.conn.execute("""
            INSERT INTO kb_entries (id, title, content, tags, category, metadata, created_at, updated_at, search_text, author)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (id, title, content, json.dumps(tags or []), category, json.dumps(metadata or {}), now, now, search_text, author))
        self.conn.commit()
        return id
    
    def get(self, id: str) -> Optional[KBEntry]:
        row = self.conn.execute("SELECT * FROM kb_entries WHERE id = ?", (id,)).fetchone()
        if row:
            r = dict(row)
            r["tags"] = json.loads(r["tags"])
            r["metadata"] = json.loads(r["metadata"])
            entry = KBEntry.from_dict(r)
            self.conn.execute("UPDATE kb_entries SET views = views + 1 WHERE id = ?", (id,))
            self.conn.commit()
            return entry
        return None
    
    def search(self, query: str, category: str = None, tags: List[str] = None, limit: int = 10) -> List[SearchResult]:
        query_lower = query.lower()
        query_words = set(query_lower.split())
        sql = "SELECT * FROM kb_entries WHERE 1=1"
        params = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        if tags:
            for tag in tags:
                sql += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')
        rows = self.conn.execute(sql, params).fetchall()
        scored = []
        for row in rows:
            r = dict(row)
            r["tags"] = json.loads(r["tags"])
            r["metadata"] = json.loads(r["metadata"])
            entry = KBEntry.from_dict(r)
            # Score: title match > tag match > content match
            score = 0.0
            highlights = []
            if query_lower in entry.title.lower():
                score += 10.0
                highlights.append(entry.title)
            common_tags = query_words & set(t.lower() for t in entry.tags)
            score += len(common_tags) * 3.0
            if query_lower in entry.content.lower():
                score += 1.0
                idx = entry.content.lower().find(query_lower)
                highlights.append(entry.content[max(0,idx-50):idx+100])
            if score > 0:
                scored.append(SearchResult(entry, score, highlights))
        scored.sort(key=lambda x: -x.score)
        return scored[:limit]
    
    def update(self, id: str, **kwargs) -> bool:
        sets = []
        params = []
        for k, v in kwargs.items():
            if k in ("tags", "metadata"):
                v = json.dumps(v)
            sets.append(f"{k} = ?")
            params.append(v)
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(id)
        self.conn.execute(f"UPDATE kb_entries SET {', '.join(sets)} WHERE id = ?", params)
        self.conn.commit()
        return self.conn.total_changes > 0
    
    def delete(self, id: str) -> bool:
        self.conn.execute("DELETE FROM kb_entries WHERE id = ?", (id,))
        self.conn.commit()
        return self.total_changes > 0
    
    def list_categories(self) -> List[str]:
        rows = self.conn.execute("SELECT DISTINCT category FROM kb_entries ORDER BY category").fetchall()
        return [r[0] for r in rows]
    
    def list_tags(self) -> List[str]:
        rows = self.conn.execute("SELECT tags FROM kb_entries").fetchall()
        all_tags = []
        for r in rows:
            all_tags.extend(json.loads(r[0]))
        from collections import Counter
        return [t for t, c in Counter(all_tags).most_common(50)]
    
    def get_stats(self) -> Dict:
        total = self.conn.execute("SELECT COUNT(*) FROM kb_entries").fetchone()[0]
        by_category = self.conn.execute("SELECT category, COUNT(*) FROM kb_entries GROUP BY category").fetchall()
        by_author = self.conn.execute("SELECT author, COUNT(*) FROM kb_entries GROUP BY author").fetchall()
        return {
            "total_entries": total,
            "by_category": dict(by_category),
            "by_author": dict(by_author),
            "total_views": self.conn.execute("SELECT SUM(views) FROM kb_entries").fetchone()[0] or 0,
        }
