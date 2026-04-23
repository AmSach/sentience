"""
Memory Retrieval - Semantic search, time-based retrieval, relevance ranking.
Retrieves relevant memories based on various criteria.
"""

import sqlite3
import json
import hashlib
import struct
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import math
import re

# Try to import embedding libraries
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
    _embedding_model = None
except ImportError:
    EMBEDDING_AVAILABLE = False
    _embedding_model = None


def get_embedding_model():
    """Lazy load the embedding model."""
    global _embedding_model
    if EMBEDDING_AVAILABLE and _embedding_model is None:
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedding_model


@dataclass
class Memory:
    """Represents a stored memory."""
    id: str
    content: str
    content_type: str  # 'text', 'interaction', 'note', 'knowledge'
    importance: float  # 0.0 to 1.0
    created_at: datetime
    accessed_at: datetime
    access_count: int
    tags: List[str]
    metadata: Dict
    embedding_id: Optional[str] = None
    source_id: Optional[str] = None


@dataclass
class RetrievalResult:
    """Represents a memory retrieval result."""
    memory: Memory
    relevance_score: float
    recency_score: float
    importance_score: float
    combined_score: float
    highlights: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class SearchQuery:
    """Represents a search query."""
    text: str
    filters: Dict[str, Any] = field(default_factory=dict)
    time_range: Optional[Tuple[datetime, datetime]] = None
    limit: int = 10
    offset: int = 0
    min_relevance: float = 0.0
    include_context: bool = False
    context_window: int = 0


@dataclass
class Context:
    """Represents retrieved context for a query."""
    query: str
    memories: List[RetrievalResult]
    summary: str
    total_found: int
    retrieval_time_ms: float


class MemoryRetrieval:
    """
    Memory retrieval system with:
    - Semantic search using embeddings
    - Time-based retrieval
    - Relevance ranking (semantic + recency + importance)
    - Context injection for augmented queries
    """
    
    EMBEDDING_DIMENSION = 384
    DEFAULT_WEIGHTS = {
        'relevance': 0.5,
        'recency': 0.3,
        'importance': 0.2
    }
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._load_counters()
    
    def _init_db(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()
        
        # Memories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text',
                importance REAL DEFAULT 0.5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                embedding_id TEXT,
                source_id TEXT,
                content_hash TEXT
            )
        ''')
        
        # Embeddings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                memory_id TEXT,
                vector BLOB NOT NULL,
                dimension INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        ''')
        
        # Access log for tracking usage patterns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                query_hash TEXT,
                context_type TEXT,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        ''')
        
        # FTS5 virtual table for full-text search
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                id,
                content,
                tags,
                content='memories',
                content_rowid='rowid'
            )
        ''')
        
        # Triggers to keep FTS in sync
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, id, content, tags)
                VALUES (new.rowid, new.id, new.content, new.tags);
            END
        ''')
        
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, id, content, tags)
                VALUES('delete', old.rowid, old.id, old.content, old.tags);
            END
        ''')
        
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, id, content, tags)
                VALUES('delete', old.rowid, old.id, old.content, old.tags);
                INSERT INTO memories_fts(rowid, id, content, tags)
                VALUES (new.rowid, new.id, new.content, new.tags);
            END
        ''')
        
        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(accessed_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(content_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_access_log_memory ON access_log(memory_id)')
        
        # Counters
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        ''')
        
        self.conn.commit()
    
    def _load_counters(self):
        """Load ID counters."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM counters WHERE name = "memory"')
        row = cursor.fetchone()
        self._memory_counter = row['value'] if row else 0
    
    def _save_counter(self):
        """Save counter value."""
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)',
                      ('memory', self._memory_counter))
        self.conn.commit()
    
    def _generate_id(self) -> str:
        """Generate a unique ID."""
        self._memory_counter += 1
        self._save_counter()
        return f"mem_{self._memory_counter:08d}"
    
    def _hash_content(self, content: str) -> str:
        """Generate hash for content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _create_embedding(self, content: str) -> Optional[str]:
        """Create embedding for content."""
        if not EMBEDDING_AVAILABLE:
            return None
        
        model = get_embedding_model()
        if model is None:
            return None
        
        vector = model.encode(content).tolist()
        dimension = len(vector)
        
        cursor = self.conn.cursor()
        embedding_id = f"emb_{self._hash_content(content)}"
        
        # Serialize vector
        vector_blob = struct.pack(f'{dimension}f', *vector)
        
        cursor.execute('''
            INSERT OR IGNORE INTO embeddings (id, vector, dimension, model_name)
            VALUES (?, ?, ?, ?)
        ''', (embedding_id, vector_blob, dimension, 'all-MiniLM-L6-v2'))
        
        self.conn.commit()
        return embedding_id
    
    def store_memory(self, content: str, content_type: str = 'text',
                     importance: float = 0.5, tags: List[str] = None,
                     metadata: Dict = None, source_id: str = None) -> Memory:
        """Store a new memory."""
        cursor = self.conn.cursor()
        
        memory_id = self._generate_id()
        content_hash = self._hash_content(content)
        tags_json = json.dumps(tags or [])
        metadata_json = json.dumps(metadata or {})
        
        # Create embedding
        embedding_id = self._create_embedding(content)
        
        cursor.execute('''
            INSERT INTO memories 
            (id, content, content_type, importance, tags, metadata, embedding_id, source_id, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (memory_id, content, content_type, importance, tags_json, 
              metadata_json, embedding_id, source_id, content_hash))
        
        self.conn.commit()
        
        return Memory(
            id=memory_id,
            content=content,
            content_type=content_type,
            importance=importance,
            created_at=datetime.utcnow(),
            accessed_at=datetime.utcnow(),
            access_count=0,
            tags=tags or [],
            metadata=metadata or {},
            embedding_id=embedding_id,
            source_id=source_id
        )
    
    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM memories WHERE id = ?', (memory_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return Memory(
            id=row['id'],
            content=row['content'],
            content_type=row['content_type'],
            importance=row['importance'],
            created_at=datetime.fromisoformat(row['created_at']),
            accessed_at=datetime.fromisoformat(row['accessed_at']),
            access_count=row['access_count'],
            tags=json.loads(row['tags']),
            metadata=json.loads(row['metadata']),
            embedding_id=row['embedding_id'],
            source_id=row['source_id']
        )
    
    def update_memory(self, memory_id: str, **kwargs) -> Optional[Memory]:
        """Update memory fields."""
        cursor = self.conn.cursor()
        
        # Build update query
        updates = []
        params = []
        
        if 'content' in kwargs:
            updates.append('content = ?')
            params.append(kwargs['content'])
            # Update embedding
            embedding_id = self._create_embedding(kwargs['content'])
            if embedding_id:
                updates.append('embedding_id = ?')
                params.append(embedding_id)
        
        if 'importance' in kwargs:
            updates.append('importance = ?')
            params.append(kwargs['importance'])
        
        if 'tags' in kwargs:
            updates.append('tags = ?')
            params.append(json.dumps(kwargs['tags']))
        
        if 'metadata' in kwargs:
            updates.append('metadata = ?')
            params.append(json.dumps(kwargs['metadata']))
        
        if not updates:
            return self.get_memory(memory_id)
        
        params.append(memory_id)
        
        cursor.execute(f'''
            UPDATE memories SET {', '.join(updates)}, accessed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', params)
        
        self.conn.commit()
        return self.get_memory(memory_id)
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM memories WHERE id = ?', (memory_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def _record_access(self, memory_id: str, query_hash: str = None, context_type: str = None):
        """Record memory access."""
        cursor = self.conn.cursor()
        
        # Update memory access info
        cursor.execute('''
            UPDATE memories 
            SET accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1
            WHERE id = ?
        ''', (memory_id,))
        
        # Log access
        cursor.execute('''
            INSERT INTO access_log (memory_id, query_hash, context_type)
            VALUES (?, ?, ?)
        ''', (memory_id, query_hash, context_type))
        
        self.conn.commit()
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between vectors."""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _compute_recency_score(self, accessed_at: datetime) -> float:
        """Compute recency score (exponential decay)."""
        age_hours = (datetime.utcnow() - accessed_at).total_seconds() / 3600
        # Decay: 1.0 at 0 hours, 0.5 at 24 hours, approaching 0 over time
        return math.exp(-age_hours / 24.0)
    
    def _get_embedding_vector(self, embedding_id: str) -> Optional[List[float]]:
        """Get embedding vector by ID."""
        if not embedding_id:
            return None
        
        cursor = self.conn.cursor()
        cursor.execute('SELECT vector, dimension FROM embeddings WHERE id = ?', (embedding_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return list(struct.unpack(f'{row["dimension"]}f', row['vector']))
    
    def semantic_search(self, query: SearchQuery) -> List[RetrievalResult]:
        """
        Perform semantic search using embeddings.
        Returns ranked results by combined score.
        """
        start_time = datetime.utcnow()
        
        if not EMBEDDING_AVAILABLE:
            # Fall back to keyword search
            return self.keyword_search(query)
        
        # Create query embedding
        model = get_embedding_model()
        if model is None:
            return self.keyword_search(query)
        
        query_vector = model.encode(query.text).tolist()
        query_hash = self._hash_content(query.text)
        
        # Get all embeddings
        cursor = self.conn.cursor()
        
        sql = 'SELECT * FROM memories WHERE 1=1'
        params = []
        
        # Apply filters
        if 'content_type' in query.filters:
            sql += ' AND content_type = ?'
            params.append(query.filters['content_type'])
        
        if 'tags' in query.filters:
            for tag in query.filters['tags']:
                sql += ' AND tags LIKE ?'
                params.append(f'%{tag}%')
        
        if 'min_importance' in query.filters:
            sql += ' AND importance >= ?'
            params.append(query.filters['min_importance'])
        
        if query.time_range:
            sql += ' AND created_at BETWEEN ? AND ?'
            params.extend([query.time_range[0].isoformat(), query.time_range[1].isoformat()])
        
        cursor.execute(sql, params)
        
        results = []
        weights = query.filters.get('weights', self.DEFAULT_WEIGHTS)
        
        for row in cursor.fetchall():
            # Get embedding vector
            if not row['embedding_id']:
                continue
            
            memory_vector = self._get_embedding_vector(row['embedding_id'])
            if not memory_vector:
                continue
            
            # Calculate relevance score
            relevance = self.cosine_similarity(query_vector, memory_vector)
            
            if relevance < query.min_relevance:
                continue
            
            # Calculate recency score
            accessed_at = datetime.fromisoformat(row['accessed_at'])
            recency = self._compute_recency_score(accessed_at)
            
            # Get importance score
            importance = row['importance']
            
            # Calculate combined score
            combined = (
                weights['relevance'] * relevance +
                weights['recency'] * recency +
                weights['importance'] * importance
            )
            
            memory = Memory(
                id=row['id'],
                content=row['content'],
                content_type=row['content_type'],
                importance=importance,
                created_at=datetime.fromisoformat(row['created_at']),
                accessed_at=accessed_at,
                access_count=row['access_count'],
                tags=json.loads(row['tags']),
                metadata=json.loads(row['metadata']),
                embedding_id=row['embedding_id'],
                source_id=row['source_id']
            )
            
            # Calculate highlights
            highlights = self._calculate_highlights(query.text, row['content'])
            
            results.append(RetrievalResult(
                memory=memory,
                relevance_score=relevance,
                recency_score=recency,
                importance_score=importance,
                combined_score=combined,
                highlights=highlights
            ))
        
        # Sort by combined score
        results.sort(key=lambda r: -r.combined_score)
        
        # Record access for top results
        for result in results[:query.limit]:
            self._record_access(result.memory.id, query_hash, 'semantic_search')
        
        return results[query.offset:query.offset + query.limit]
    
    def keyword_search(self, query: SearchQuery) -> List[RetrievalResult]:
        """
        Perform full-text keyword search.
        """
        start_time = datetime.utcnow()
        query_hash = self._hash_content(query.text)
        
        cursor = self.conn.cursor()
        
        # Use FTS5 for full-text search
        fts_query = query.text.replace('"', '""')
        
        sql = '''
            SELECT m.*, bm25(memories_fts) as score
            FROM memories m
            JOIN memories_fts fts ON m.id = fts.id
            WHERE memories_fts MATCH ?
        '''
        params = [fts_query]
        
        # Apply additional filters
        if 'content_type' in query.filters:
            sql += ' AND m.content_type = ?'
            params.append(query.filters['content_type'])
        
        if 'min_importance' in query.filters:
            sql += ' AND m.importance >= ?'
            params.append(query.filters['min_importance'])
        
        if query.time_range:
            sql += ' AND m.created_at BETWEEN ? AND ?'
            params.extend([query.time_range[0].isoformat(), query.time_range[1].isoformat()])
        
        sql += f' ORDER BY score LIMIT {query.limit + query.offset}'
        
        cursor.execute(sql, params)
        
        results = []
        weights = query.filters.get('weights', self.DEFAULT_WEIGHTS)
        
        for row in cursor.fetchall():
            # BM25 returns negative scores
            relevance = min(1.0, max(0.0, -row['score'] / 10.0))
            
            if relevance < query.min_relevance:
                continue
            
            accessed_at = datetime.fromisoformat(row['accessed_at'])
            recency = self._compute_recency_score(accessed_at)
            importance = row['importance']
            
            combined = (
                weights['relevance'] * relevance +
                weights['recency'] * recency +
                weights['importance'] * importance
            )
            
            memory = Memory(
                id=row['id'],
                content=row['content'],
                content_type=row['content_type'],
                importance=importance,
                created_at=datetime.fromisoformat(row['created_at']),
                accessed_at=accessed_at,
                access_count=row['access_count'],
                tags=json.loads(row['tags']),
                metadata=json.loads(row['metadata']),
                embedding_id=row['embedding_id'],
                source_id=row['source_id']
            )
            
            highlights = self._calculate_highlights(query.text, row['content'])
            
            results.append(RetrievalResult(
                memory=memory,
                relevance_score=relevance,
                recency_score=recency,
                importance_score=importance,
                combined_score=combined,
                highlights=highlights
            ))
        
        # Record access
        for result in results[:query.limit]:
            self._record_access(result.memory.id, query_hash, 'keyword_search')
        
        return results[query.offset:query.offset + query.limit]
    
    def _calculate_highlights(self, query: str, content: str) -> List[Tuple[int, int]]:
        """Calculate highlight positions in content."""
        highlights = []
        query_terms = set(query.lower().split())
        content_lower = content.lower()
        
        for term in query_terms:
            start = 0
            while True:
                idx = content_lower.find(term, start)
                if idx == -1:
                    break
                highlights.append((idx, idx + len(term)))
                start = idx + 1
        
        return highlights
    
    def time_based_retrieval(self, time_range: Tuple[datetime, datetime],
                             content_type: str = None, limit: int = 50) -> List[Memory]:
        """
        Retrieve memories within a time range.
        """
        cursor = self.conn.cursor()
        
        sql = '''
            SELECT * FROM memories 
            WHERE created_at BETWEEN ? AND ?
        '''
        params = [time_range[0].isoformat(), time_range[1].isoformat()]
        
        if content_type:
            sql += ' AND content_type = ?'
            params.append(content_type)
        
        sql += ' ORDER BY importance DESC, created_at DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(sql, params)
        
        memories = []
        for row in cursor.fetchall():
            memories.append(Memory(
                id=row['id'],
                content=row['content'],
                content_type=row['content_type'],
                importance=row['importance'],
                created_at=datetime.fromisoformat(row['created_at']),
                accessed_at=datetime.fromisoformat(row['accessed_at']),
                access_count=row['access_count'],
                tags=json.loads(row['tags']),
                metadata=json.loads(row['metadata']),
                embedding_id=row['embedding_id'],
                source_id=row['source_id']
            ))
        
        return memories
    
    def recent_memories(self, hours: int = 24, limit: int = 20) -> List[Memory]:
        """Get recent memories from last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return self.time_based_retrieval((cutoff, datetime.utcnow()), limit=limit)
    
    def important_memories(self, min_importance: float = 0.7, limit: int = 20) -> List[Memory]:
        """Get memories above importance threshold."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT * FROM memories 
            WHERE importance >= ?
            ORDER BY importance DESC, accessed_at DESC
            LIMIT ?
        ''', (min_importance, limit))
        
        memories = []
        for row in cursor.fetchall():
            memories.append(Memory(
                id=row['id'],
                content=row['content'],
                content_type=row['content_type'],
                importance=row['importance'],
                created_at=datetime.fromisoformat(row['created_at']),
                accessed_at=datetime.fromisoformat(row['accessed_at']),
                access_count=row['access_count'],
                tags=json.loads(row['tags']),
                metadata=json.loads(row['metadata']),
                embedding_id=row['embedding_id'],
                source_id=row['source_id']
            ))
        
        return memories
    
    def frequently_accessed(self, limit: int = 20, days: int = 30) -> List[Memory]:
        """Get most frequently accessed memories."""
        cursor = self.conn.cursor()
        
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        cursor.execute('''
            SELECT m.*, COUNT(a.id) as access_freq
            FROM memories m
            JOIN access_log a ON m.id = a.memory_id
            WHERE a.accessed_at > ?
            GROUP BY m.id
            ORDER BY access_freq DESC
            LIMIT ?
        ''', (cutoff, limit))
        
        memories = []
        for row in cursor.fetchall():
            memories.append(Memory(
                id=row['id'],
                content=row['content'],
                content_type=row['content_type'],
                importance=row['importance'],
                created_at=datetime.fromisoformat(row['created_at']),
                accessed_at=datetime.fromisoformat(row['accessed_at']),
                access_count=row['access_count'],
                tags=json.loads(row['tags']),
                metadata=json.loads(row['metadata']),
                embedding_id=row['embedding_id'],
                source_id=row['source_id']
            ))
        
        return memories
    
    def search_by_tags(self, tags: List[str], limit: int = 50) -> List[Memory]:
        """Search memories by tags (AND logic)."""
        cursor = self.conn.cursor()
        
        placeholders = ','.join('?' * len(tags))
        
        cursor.execute(f'''
            SELECT * FROM memories
            WHERE id IN (
                SELECT id FROM memories_fts WHERE memories_fts MATCH ?
            )
            ORDER BY importance DESC, accessed_at DESC
            LIMIT ?
        ''', (f'tags:({" AND ".join(tags)})', limit))
        
        memories = []
        for row in cursor.fetchall():
            memories.append(Memory(
                id=row['id'],
                content=row['content'],
                content_type=row['content_type'],
                importance=row['importance'],
                created_at=datetime.fromisoformat(row['created_at']),
                accessed_at=datetime.fromisoformat(row['accessed_at']),
                access_count=row['access_count'],
                tags=json.loads(row['tags']),
                metadata=json.loads(row['metadata']),
                embedding_id=row['embedding_id'],
                source_id=row['source_id']
            ))
        
        return memories
    
    def inject_context(self, query: str, max_context: int = 5,
                       max_length: int = 2000) -> Context:
        """
        Inject relevant context for a query.
        Returns augmented context for use in response generation.
        """
        start_time = datetime.utcnow()
        
        # Create search query
        search = SearchQuery(
            text=query,
            limit=max_context,
            min_relevance=0.3,
            include_context=True
        )
        
        # Perform semantic search
        results = self.semantic_search(search)
        
        # Build context
        context_parts = []
        total_length = 0
        
        for result in results:
            content = result.memory.content
            if total_length + len(content) > max_length:
                # Truncate if needed
                remaining = max_length - total_length
                if remaining > 50:
                    content = content[:remaining] + '...'
                else:
                    break
            
            context_parts.append(content)
            total_length += len(content)
        
        # Generate summary
        summary = self._generate_context_summary(context_parts, query)
        
        retrieval_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return Context(
            query=query,
            memories=results,
            summary=summary,
            total_found=len(results),
            retrieval_time_ms=retrieval_time
        )
    
    def _generate_context_summary(self, context_parts: List[str], query: str) -> str:
        """Generate a summary of context for query."""
        if not context_parts:
            return "No relevant context found."
        
        if len(context_parts) == 1:
            return context_parts[0]
        
        # Combine with relevance markers
        summary_parts = ["Relevant context:"]
        for i, part in enumerate(context_parts[:5], 1):
            preview = part[:200] + ('...' if len(part) > 200 else '')
            summary_parts.append(f"{i}. {preview}")
        
        return '\n'.join(summary_parts)
    
    def get_related_memories(self, memory_id: str, limit: int = 5) -> List[RetrievalResult]:
        """Get memories related to a specific memory."""
        memory = self.get_memory(memory_id)
        if not memory:
            return []
        
        # Use the memory content as query
        query = SearchQuery(
            text=memory.content,
            limit=limit + 1,  # Get one extra to exclude self
            min_relevance=0.5
        )
        
        results = self.semantic_search(query)
        
        # Filter out the original memory
        return [r for r in results if r.memory.id != memory_id][:limit]
    
    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval system statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        # Memory stats
        cursor.execute('SELECT COUNT(*) as count FROM memories')
        stats['total_memories'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT content_type, COUNT(*) as count 
            FROM memories GROUP BY content_type
        ''')
        stats['memories_by_type'] = {r['content_type']: r['count'] for r in cursor.fetchall()}
        
        cursor.execute('SELECT AVG(importance) as avg FROM memories')
        stats['avg_importance'] = cursor.fetchone()['avg'] or 0.5
        
        cursor.execute('SELECT AVG(access_count) as avg FROM memories')
        stats['avg_access_count'] = cursor.fetchone()['avg'] or 0
        
        # Embedding stats
        cursor.execute('SELECT COUNT(*) as count FROM embeddings')
        stats['total_embeddings'] = cursor.fetchone()['count']
        
        # Access stats
        cursor.execute('SELECT COUNT(*) as count FROM access_log')
        stats['total_accesses'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT COUNT(DISTINCT DATE(accessed_at)) as days
            FROM access_log
            WHERE accessed_at > datetime('now', '-30 days')
        ''')
        stats['active_days_last_30'] = cursor.fetchone()['days']
        
        return stats
    
    def close(self):
        """Close database connection."""
        self.conn.close()


if __name__ == '__main__':
    # Example usage
    retrieval = MemoryRetrieval('/tmp/test_retrieval.db')
    
    # Store some memories
    memories = [
        retrieval.store_memory(
            "Python is a high-level programming language known for its readability.",
            content_type='knowledge',
            importance=0.8,
            tags=['python', 'programming']
        ),
        retrieval.store_memory(
            "Machine learning algorithms learn patterns from data.",
            content_type='knowledge',
            importance=0.9,
            tags=['ml', 'ai', 'algorithms']
        ),
        retrieval.store_memory(
            "The user prefers concise responses over detailed explanations.",
            content_type='preference',
            importance=0.7,
            tags=['user', 'preferences']
        ),
        retrieval.store_memory(
            "Neural networks are inspired by biological neurons in the brain.",
            content_type='knowledge',
            importance=0.6,
            tags=['neural-networks', 'ai']
        )
    ]
    
    print(f"Stored {len(memories)} memories")
    
    # Semantic search
    query = SearchQuery(text="programming languages", limit=3)
    results = retrieval.semantic_search(query)
    
    print(f"\nSemantic search for '{query.text}':")
    for result in results:
        print(f"  - [{result.combined_score:.3f}] {result.memory.content[:50]}...")
    
    # Keyword search
    query = SearchQuery(text="python", limit=3)
    results = retrieval.keyword_search(query)
    
    print(f"\nKeyword search for '{query.text}':")
    for result in results:
        print(f"  - [{result.combined_score:.3f}] {result.memory.content[:50]}...")
    
    # Time-based retrieval
    recent = retrieval.recent_memories(hours=24)
    print(f"\nRecent memories: {len(recent)}")
    
    # Context injection
    context = retrieval.inject_context("artificial intelligence")
    print(f"\nInjected context: {context.summary[:100]}...")
    
    # Stats
    stats = retrieval.get_retrieval_stats()
    print(f"\nStats: {stats}")
    
    retrieval.close()
