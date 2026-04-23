"""
Memory Compression - LZ4 compression, embeddings, semantic dedup, summaries.
Compresses and optimizes memory storage for efficiency.
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

# Try to import LZ4, fall back to zlib if not available
try:
    import lz4.frame as lz4
    COMPRESSION_AVAILABLE = 'lz4'
except ImportError:
    import zlib
    COMPRESSION_AVAILABLE = 'zlib'

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
class CompressedMemory:
    """Represents a compressed memory block."""
    id: str
    original_size: int
    compressed_size: int
    compression_ratio: float
    data_type: str  # 'text', 'json', 'binary'
    compression_method: str
    created_at: datetime
    metadata: Dict = field(default_factory=dict)
    hash: str = ""


@dataclass
class Embedding:
    """Represents a vector embedding."""
    id: str
    text_hash: str
    text_preview: str
    vector: List[float]
    dimension: int
    model_name: str
    created_at: datetime


@dataclass
class SemanticCluster:
    """Represents a cluster of semantically similar items."""
    id: str
    centroid: List[float]
    member_ids: List[str]
    member_hashes: List[str]
    summary: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Summary:
    """Represents a generated summary."""
    id: str
    source_ids: List[str]
    source_hashes: List[str]
    summary_type: str  # 'extractive', 'abstractive', 'hierarchical'
    content: str
    key_points: List[str]
    compression_ratio: float
    created_at: datetime


class MemoryCompressor:
    """
    Memory compression system with:
    - LZ4/zlib compression for data storage
    - Vector embeddings for semantic representation
    - Semantic deduplication using embeddings
    - Summary generation for long-term retention
    """
    
    EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2 dimension
    SIMILARITY_THRESHOLD = 0.95  # For deduplication
    MIN_COMPRESSION_RATIO = 1.1  # Only compress if ratio > this
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._load_counters()
    
    def _init_db(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()
        
        # Compressed memories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compressed_memories (
                id TEXT PRIMARY KEY,
                original_size INTEGER NOT NULL,
                compressed_size INTEGER NOT NULL,
                compression_ratio REAL NOT NULL,
                data_type TEXT NOT NULL,
                compression_method TEXT NOT NULL,
                compressed_data BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}',
                hash TEXT NOT NULL
            )
        ''')
        
        # Embeddings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                text_hash TEXT NOT NULL UNIQUE,
                text_preview TEXT,
                vector BLOB NOT NULL,
                dimension INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for vector search
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON embeddings(text_hash)')
        
        # Semantic clusters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS semantic_clusters (
                id TEXT PRIMARY KEY,
                centroid BLOB NOT NULL,
                member_ids TEXT NOT NULL,
                member_hashes TEXT NOT NULL,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Summaries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS summaries (
                id TEXT PRIMARY KEY,
                source_ids TEXT NOT NULL,
                source_hashes TEXT NOT NULL,
                summary_type TEXT NOT NULL,
                content TEXT NOT NULL,
                key_points TEXT DEFAULT '[]',
                compression_ratio REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Deduplication index (maps hash to canonical ID)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dedup_index (
                content_hash TEXT PRIMARY KEY,
                canonical_id TEXT NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                occurrence_count INTEGER DEFAULT 1
            )
        ''')
        
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
        # Map prefix names to counter names
        for name, prefix in [('memory', 'mem'), ('embedding', 'emb'), 
                            ('cluster', 'clu'), ('summary', 'sum')]:
            cursor.execute('SELECT value FROM counters WHERE name = ?', (name,))
            row = cursor.fetchone()
            setattr(self, f'_{prefix}_counter', row['value'] if row else 0)
    
    def _save_counter(self, name: str):
        """Save a counter value."""
        cursor = self.conn.cursor()
        # Map prefix back to full name for storage
        name_map = {'mem': 'memory', 'emb': 'embedding', 'clu': 'cluster', 'sum': 'summary'}
        full_name = name_map.get(name, name)
        value = getattr(self, f'_{name}_counter')
        cursor.execute('INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)',
                      (full_name, value))
        self.conn.commit()
    
    def _generate_id(self, prefix: str) -> str:
        """Generate a unique ID."""
        counter_name = prefix.rstrip('_')
        current = getattr(self, f'_{counter_name}_counter')
        setattr(self, f'_{counter_name}_counter', current + 1)
        self._save_counter(counter_name)
        return f"{prefix}{current + 1:08d}"
    
    def _hash_content(self, content: str) -> str:
        """Generate hash for content."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def compress_data(self, data: str, data_type: str = 'text') -> CompressedMemory:
        """
        Compress data using LZ4 or zlib.
        Only compresses if compression ratio is beneficial.
        """
        original_bytes = data.encode('utf-8')
        original_size = len(original_bytes)
        content_hash = self._hash_content(data)
        
        # Check for existing compression
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM compressed_memories WHERE hash = ?', (content_hash,))
        existing = cursor.fetchone()
        
        if existing:
            return CompressedMemory(
                id=existing['id'],
                original_size=existing['original_size'],
                compressed_size=existing['compressed_size'],
                compression_ratio=existing['compression_ratio'],
                data_type=existing['data_type'],
                compression_method=existing['compression_method'],
                created_at=datetime.fromisoformat(existing['created_at']),
                metadata=json.loads(existing['metadata']),
                hash=content_hash
            )
        
        # Compress data
        if COMPRESSION_AVAILABLE == 'lz4':
            compressed_bytes = lz4.compress(original_bytes, compression_level=3)
            method = 'lz4'
        else:
            compressed_bytes = zlib.compress(original_bytes, level=6)
            method = 'zlib'
        
        compressed_size = len(compressed_bytes)
        ratio = original_size / compressed_size if compressed_size > 0 else 1.0
        
        # Only store if compression is beneficial
        if ratio < self.MIN_COMPRESSION_RATIO:
            # Store uncompressed with marker
            compressed_bytes = original_bytes
            method = 'none'
            ratio = 1.0
            compressed_size = original_size
        
        memory_id = self._generate_id('mem_')
        
        cursor.execute('''
            INSERT INTO compressed_memories 
            (id, original_size, compressed_size, compression_ratio, data_type,
             compression_method, compressed_data, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (memory_id, original_size, compressed_size, ratio, data_type,
              method, compressed_bytes, content_hash))
        
        self.conn.commit()
        
        return CompressedMemory(
            id=memory_id,
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=ratio,
            data_type=data_type,
            compression_method=method,
            created_at=datetime.utcnow(),
            hash=content_hash
        )
    
    def decompress_data(self, memory_id: str) -> Optional[str]:
        """Decompress data by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM compressed_memories WHERE id = ?', (memory_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        compressed_bytes = row['compressed_data']
        method = row['compression_method']
        
        if method == 'none':
            return compressed_bytes.decode('utf-8')
        elif method == 'lz4':
            return lz4.decompress(compressed_bytes).decode('utf-8')
        elif method == 'zlib':
            return zlib.decompress(compressed_bytes).decode('utf-8')
        
        return None
    
    def create_embedding(self, text: str) -> Optional[Embedding]:
        """
        Create a vector embedding for text.
        Returns None if embedding library not available.
        """
        if not EMBEDDING_AVAILABLE:
            return None
        
        text_hash = self._hash_content(text)
        
        # Check for existing embedding
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM embeddings WHERE text_hash = ?', (text_hash,))
        existing = cursor.fetchone()
        
        if existing:
            vector_blob = existing['vector']
            vector = list(struct.unpack(f'{existing["dimension"]}f', vector_blob))
            
            return Embedding(
                id=existing['id'],
                text_hash=text_hash,
                text_preview=existing['text_preview'],
                vector=vector,
                dimension=existing['dimension'],
                model_name=existing['model_name'],
                created_at=datetime.fromisoformat(existing['created_at'])
            )
        
        # Create new embedding
        model = get_embedding_model()
        if model is None:
            return None
        
        vector = model.encode(text).tolist()
        dimension = len(vector)
        
        # Serialize vector
        vector_blob = struct.pack(f'{dimension}f', *vector)
        
        embedding_id = self._generate_id('emb_')
        text_preview = text[:200] + ('...' if len(text) > 200 else '')
        
        cursor.execute('''
            INSERT INTO embeddings (id, text_hash, text_preview, vector, dimension, model_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (embedding_id, text_hash, text_preview, vector_blob, dimension, 'all-MiniLM-L6-v2'))
        
        self.conn.commit()
        
        return Embedding(
            id=embedding_id,
            text_hash=text_hash,
            text_preview=text_preview,
            vector=vector,
            dimension=dimension,
            model_name='all-MiniLM-L6-v2',
            created_at=datetime.utcnow()
        )
    
    def get_embedding(self, text_hash: str) -> Optional[Embedding]:
        """Get embedding by text hash."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM embeddings WHERE text_hash = ?', (text_hash,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        vector_blob = row['vector']
        vector = list(struct.unpack(f'{row["dimension"]}f', vector_blob))
        
        return Embedding(
            id=row['id'],
            text_hash=text_hash,
            text_preview=row['text_preview'],
            vector=vector,
            dimension=row['dimension'],
            model_name=row['model_name'],
            created_at=datetime.fromisoformat(row['created_at'])
        )
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def find_similar(self, text: str, limit: int = 10, 
                     threshold: float = 0.7) -> List[Tuple[Embedding, float]]:
        """
        Find semantically similar texts.
        Returns list of (embedding, similarity_score) tuples.
        """
        if not EMBEDDING_AVAILABLE:
            return []
        
        # Create embedding for query
        model = get_embedding_model()
        if model is None:
            return []
        
        query_vector = model.encode(text).tolist()
        
        # Search all embeddings
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM embeddings')
        
        results = []
        for row in cursor.fetchall():
            stored_vector = list(struct.unpack(f'{row["dimension"]}f', row['vector']))
            similarity = self.cosine_similarity(query_vector, stored_vector)
            
            if similarity >= threshold:
                embedding = Embedding(
                    id=row['id'],
                    text_hash=row['text_hash'],
                    text_preview=row['text_preview'],
                    vector=stored_vector,
                    dimension=row['dimension'],
                    model_name=row['model_name'],
                    created_at=datetime.fromisoformat(row['created_at'])
                )
                results.append((embedding, similarity))
        
        # Sort by similarity and limit
        results.sort(key=lambda x: -x[1])
        return results[:limit]
    
    def deduplicate(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if text is semantically duplicate of existing content.
        Returns (is_duplicate, canonical_id).
        """
        text_hash = self._hash_content(text)
        
        cursor = self.conn.cursor()
        
        # Check exact hash match
        cursor.execute('SELECT canonical_id FROM dedup_index WHERE content_hash = ?', (text_hash,))
        row = cursor.fetchone()
        
        if row:
            # Update occurrence count
            cursor.execute('''
                UPDATE dedup_index SET occurrence_count = occurrence_count + 1
                WHERE content_hash = ?
            ''', (text_hash,))
            self.conn.commit()
            return (True, row['canonical_id'])
        
        # Check semantic similarity if embeddings available
        if EMBEDDING_AVAILABLE:
            similar = self.find_similar(text, limit=1, threshold=self.SIMILARITY_THRESHOLD)
            
            if similar:
                similar_embedding, similarity = similar[0]
                # This is a semantic duplicate
                cursor.execute('''
                    INSERT INTO dedup_index (content_hash, canonical_id)
                    VALUES (?, ?)
                ''', (text_hash, similar_embedding.id))
                self.conn.commit()
                return (True, similar_embedding.id)
        
        # Not a duplicate - add to index
        cursor.execute('''
            INSERT INTO dedup_index (content_hash, canonical_id)
            VALUES (?, ?)
        ''', (text_hash, text_hash))
        self.conn.commit()
        
        return (False, None)
    
    def cluster_embeddings(self, n_clusters: int = 10) -> List[SemanticCluster]:
        """
        Cluster embeddings using k-means-like approach.
        """
        if not EMBEDDING_AVAILABLE:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, vector, dimension FROM embeddings')
        
        embeddings_data = []
        for row in cursor.fetchall():
            vector = list(struct.unpack(f'{row["dimension"]}f', row['vector']))
            embeddings_data.append((row['id'], vector))
        
        if len(embeddings_data) < n_clusters:
            n_clusters = max(1, len(embeddings_data))
        
        if not embeddings_data:
            return []
        
        # Simple k-means implementation
        import random
        
        # Initialize centroids randomly
        random.shuffle(embeddings_data)
        centroids = [e[1][:] for e in embeddings_data[:n_clusters]]
        
        # Iterate k-means
        for iteration in range(20):
            # Assign to clusters
            clusters = defaultdict(list)
            for emb_id, vector in embeddings_data:
                best_cluster = 0
                best_similarity = -1
                
                for i, centroid in enumerate(centroids):
                    sim = self.cosine_similarity(vector, centroid)
                    if sim > best_similarity:
                        best_similarity = sim
                        best_cluster = i
                
                clusters[best_cluster].append((emb_id, vector))
            
            # Update centroids
            for i in range(n_clusters):
                if clusters[i]:
                    # Calculate mean
                    dim = len(centroids[i])
                    new_centroid = [0.0] * dim
                    for _, vec in clusters[i]:
                        for j in range(dim):
                            new_centroid[j] += vec[j]
                    for j in range(dim):
                        new_centroid[j] /= len(clusters[i])
                    centroids[i] = new_centroid
        
        # Create cluster records
        semantic_clusters = []
        
        for cluster_id, members in clusters.items():
            if not members:
                continue
            
            centroid = centroids[cluster_id]
            member_ids = [m[0] for m in members]
            member_hashes = []
            
            # Get hashes
            for mid in member_ids:
                cursor.execute('SELECT text_hash FROM embeddings WHERE id = ?', (mid,))
                row = cursor.fetchone()
                if row:
                    member_hashes.append(row['text_hash'])
            
            # Store cluster
            cluster_uuid = self._generate_id('clu_')
            centroid_blob = struct.pack(f'{len(centroid)}f', *centroid)
            
            cursor.execute('''
                INSERT INTO semantic_clusters 
                (id, centroid, member_ids, member_hashes)
                VALUES (?, ?, ?, ?)
            ''', (cluster_uuid, centroid_blob, json.dumps(member_ids),
                  json.dumps(member_hashes)))
            
            semantic_clusters.append(SemanticCluster(
                id=cluster_uuid,
                centroid=centroid,
                member_ids=member_ids,
                member_hashes=member_hashes,
                summary="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ))
        
        self.conn.commit()
        return semantic_clusters
    
    def generate_extractive_summary(self, texts: List[str], max_length: int = 500) -> Summary:
        """
        Generate an extractive summary by selecting key sentences.
        """
        if not texts:
            raise ValueError("No texts provided for summarization")
        
        # Extract all sentences
        sentences = []
        for i, text in enumerate(texts):
            text_sentences = re.split(r'[.!?]+', text)
            for sent in text_sentences:
                sent = sent.strip()
                if sent and len(sent) > 10:
                    sentences.append((i, sent))
        
        if not sentences:
            return Summary(
                id=self._generate_id('sum_'),
                source_ids=[],
                source_hashes=[self._hash_content(t) for t in texts],
                summary_type='extractive',
                content='No content to summarize.',
                key_points=[],
                compression_ratio=1.0,
                created_at=datetime.utcnow()
            )
        
        # Score sentences by key phrase frequency
        key_phrases = defaultdict(int)
        for _, sent in sentences:
            words = re.findall(r'\b[a-zA-Z]{4,}\b', sent.lower())
            for word in words:
                key_phrases[word] += 1
        
        # Score each sentence
        scored_sentences = []
        for source_idx, sent in sentences:
            words = re.findall(r'\b[a-zA-Z]{4,}\b', sent.lower())
            score = sum(key_phrases.get(w, 0) for w in words) / max(len(words), 1)
            scored_sentences.append((score, source_idx, sent))
        
        # Sort by score and select top sentences
        scored_sentences.sort(reverse=True)
        
        summary_parts = []
        total_length = 0
        seen_sources = set()
        key_points = []
        
        for score, source_idx, sent in scored_sentences:
            if total_length + len(sent) > max_length:
                break
            
            summary_parts.append(sent)
            total_length += len(sent)
            seen_sources.add(source_idx)
            
            # Add as key point if score is high
            if score > 2.0 and len(key_points) < 5:
                key_points.append(sent)
        
        summary_text = '. '.join(summary_parts)
        if summary_text and not summary_text.endswith('.'):
            summary_text += '.'
        
        # Calculate compression ratio
        original_length = sum(len(t) for t in texts)
        compression_ratio = original_length / len(summary_text) if summary_text else 1.0
        
        return Summary(
            id=self._generate_id('sum_'),
            source_ids=[str(i) for i in seen_sources],
            source_hashes=[self._hash_content(texts[i]) for i in seen_sources if i < len(texts)],
            summary_type='extractive',
            content=summary_text,
            key_points=key_points,
            compression_ratio=compression_ratio,
            created_at=datetime.utcnow()
        )
    
    def generate_hierarchical_summary(self, texts: List[str], 
                                      levels: int = 3) -> List[Summary]:
        """
        Generate hierarchical summaries at different compression levels.
        """
        summaries = []
        
        current_texts = texts
        max_lengths = [500, 200, 50]  # Different compression levels
        
        for level in range(min(levels, len(max_lengths))):
            summary = self.generate_extractive_summary(current_texts, max_lengths[level])
            summaries.append(summary)
            current_texts = [summary.content]
        
        return summaries
    
    def compress_and_embed(self, text: str) -> Tuple[CompressedMemory, Optional[Embedding]]:
        """
        Compress and embed text in one operation.
        Returns (compressed_memory, embedding).
        """
        # Check for duplicates first
        is_dup, canonical_id = self.deduplicate(text)
        
        if is_dup:
            # Return existing if duplicate
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM compressed_memories WHERE hash = ?', (canonical_id,))
            row = cursor.fetchone()
            
            if row:
                compressed = CompressedMemory(
                    id=row['id'],
                    original_size=row['original_size'],
                    compressed_size=row['compressed_size'],
                    compression_ratio=row['compression_ratio'],
                    data_type=row['data_type'],
                    compression_method=row['compression_method'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    hash=row['hash']
                )
                
                # Get existing embedding
                embedding = self.get_embedding(canonical_id)
                
                return (compressed, embedding)
        
        # Compress
        compressed = self.compress_data(text)
        
        # Embed
        embedding = self.create_embedding(text) if EMBEDDING_AVAILABLE else None
        
        return (compressed, embedding)
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        # Memory stats
        cursor.execute('SELECT COUNT(*) as count FROM compressed_memories')
        stats['total_memories'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT 
                SUM(original_size) as original,
                SUM(compressed_size) as compressed,
                AVG(compression_ratio) as avg_ratio
            FROM compressed_memories
        ''')
        row = cursor.fetchone()
        stats['total_original_size'] = row['original'] or 0
        stats['total_compressed_size'] = row['compressed'] or 0
        stats['avg_compression_ratio'] = row['avg_ratio'] or 1.0
        stats['space_saved_bytes'] = stats['total_original_size'] - stats['total_compressed_size']
        stats['space_saved_percent'] = (
            (stats['space_saved_bytes'] / stats['total_original_size'] * 100) 
            if stats['total_original_size'] > 0 else 0
        )
        
        # Embedding stats
        cursor.execute('SELECT COUNT(*) as count FROM embeddings')
        stats['total_embeddings'] = cursor.fetchone()['count']
        
        # Cluster stats
        cursor.execute('SELECT COUNT(*) as count FROM semantic_clusters')
        stats['total_clusters'] = cursor.fetchone()['count']
        
        # Dedup stats
        cursor.execute('SELECT COUNT(*) as count FROM dedup_index')
        stats['total_indexed'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT SUM(occurrence_count) as total FROM dedup_index
        ''')
        row = cursor.fetchone()
        total_occurrences = row['total'] or 0
        stats['duplicates_found'] = total_occurrences - stats['total_indexed']
        
        # Summary stats
        cursor.execute('SELECT COUNT(*) as count FROM summaries')
        stats['total_summaries'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT AVG(compression_ratio) as avg FROM summaries')
        stats['avg_summary_compression'] = cursor.fetchone()['avg'] or 1.0
        
        return stats
    
    def cleanup_old_memories(self, days: int = 30, keep_last: int = 100):
        """Clean up old compressed memories while keeping recent ones."""
        cursor = self.conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get IDs to keep (most recent)
        cursor.execute('''
            SELECT id FROM compressed_memories 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (keep_last,))
        keep_ids = {row['id'] for row in cursor.fetchall()}
        
        # Delete old memories not in keep list
        if keep_ids:
            placeholders = ','.join('?' * len(keep_ids))
            cursor.execute(f'''
                DELETE FROM compressed_memories 
                WHERE created_at < ? AND id NOT IN ({placeholders})
            ''', (cutoff.isoformat(), *keep_ids))
        else:
            cursor.execute('''
                DELETE FROM compressed_memories WHERE created_at < ?
            ''', (cutoff.isoformat(),))
        
        deleted = cursor.rowcount
        self.conn.commit()
        
        return deleted
    
    def export_compressed(self, memory_id: str) -> Optional[Dict]:
        """Export a compressed memory with metadata."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM compressed_memories WHERE id = ?', (memory_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            'id': row['id'],
            'original_size': row['original_size'],
            'compressed_size': row['compressed_size'],
            'compression_ratio': row['compression_ratio'],
            'data_type': row['data_type'],
            'compression_method': row['compression_method'],
            'hash': row['hash'],
            'created_at': row['created_at'],
            'metadata': json.loads(row['metadata'])
        }
    
    def close(self):
        """Close database connection."""
        self.conn.close()


if __name__ == '__main__':
    # Example usage
    compressor = MemoryCompressor('/tmp/test_compress.db')
    
    # Compress some text
    text1 = """
    Memory compression is a crucial technique for efficient data storage. 
    It reduces the amount of space required to store information while 
    maintaining the ability to retrieve the original data. Modern compression
    algorithms like LZ4 provide fast compression and decompression speeds,
    making them ideal for real-time applications.
    """ * 10  # Repeat to make it compressible
    
    compressed, embedding = compressor.compress_and_embed(text1)
    print(f"Compressed: {compressed.original_size} -> {compressed.compressed_size} bytes")
    print(f"Compression ratio: {compressed.compression_ratio:.2f}x")
    
    # Test deduplication
    similar_text = text1 + " Extra content."
    is_dup, canonical = compressor.deduplicate(similar_text)
    print(f"Is duplicate: {is_dup}")
    
    # Find similar
    if EMBEDDING_AVAILABLE:
        query = "efficient data storage techniques"
        similar = compressor.find_similar(query, limit=3)
        print(f"Found {len(similar)} similar texts")
        for emb, score in similar:
            print(f"  - Score: {score:.3f}, Preview: {emb.text_preview[:50]}...")
    
    # Generate summary
    texts = [
        "Machine learning is a subset of artificial intelligence.",
        "Deep learning uses neural networks with many layers.",
        "Neural networks are inspired by biological neurons.",
        "Training requires large datasets and computational power."
    ]
    
    summary = compressor.generate_extractive_summary(texts)
    print(f"\nSummary: {summary.content}")
    print(f"Compression ratio: {summary.compression_ratio:.2f}x")
    
    # Get stats
    stats = compressor.get_compression_stats()
    print(f"\nStats: {stats}")
    
    compressor.close()
