#!/usr/bin/env python3
"""
Sentience RAG Engine - Hybrid Search + GraphRAG
Based on: UltraRAG, RagClaw, ObsidianRAG, Local_RAG
"""
import os
import re
import json
import sqlite3
import hashlib
import math
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Callable
from dataclasses import dataclass, field
import logging
import sqlite3

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False
    logger.warning("sentence-transformers not installed, embeddings disabled")

try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


@dataclass
class Document:
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    chunks: List['Chunk'] = field(default_factory=list)


@dataclass  
class Chunk:
    id: str
    document_id: str
    content: str
    embedding: Optional[List[float]] = None
    start_char: int = 0
    end_char: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    chunk: Chunk
    score: float
    source: str  # 'vector', 'bm25', or 'hybrid'


class BM25Index:
    """Simple BM25 implementation for keyword search"""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths = {}
        self.avg_doc_length = 0
        self.doc_freqs = {}  # term -> number of docs containing term
        self.term_freqs = {}  # doc_id -> term -> frequency
        self.doc_count = 0
        self.idf = {}
        
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return [t for t in text.split() if len(t) > 1]
    
    def index(self, doc_id: str, content: str):
        """Add document to index"""
        tokens = self._tokenize(content)
        self.doc_lengths[doc_id] = len(tokens)
        self.doc_count += 1
        
        # Calculate term frequencies
        term_freq = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
            
        self.term_freqs[doc_id] = term_freq
        
        # Update document frequencies
        for token in set(tokens):
            self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1
            
        # Update average doc length
        self.avg_doc_length = sum(self.doc_lengths.values()) / self.doc_count
        
        # Recalculate IDF
        for term, df in self.doc_freqs.items():
            self.idf[term] = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search with BM25 scoring"""
        query_tokens = self._tokenize(query)
        scores = {}
        
        for doc_id, term_freq in self.term_freqs.items():
            score = 0
            doc_len = self.doc_lengths[doc_id]
            
            for token in query_tokens:
                if token not in term_freq:
                    continue
                    
                tf = term_freq[token]
                idf = self.idf.get(token, 0)
                
                # BM25 formula
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
                score += idf * numerator / denominator
                
            if score > 0:
                scores[doc_id] = score
                
        # Sort and return top_k
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]


class RAGEngine:
    """
    Hybrid RAG Engine with:
    - Vector search (sentence-transformers)
    - BM25 keyword search
    - Graph traversal (wikilinks)
    - SQLite persistence
    """
    
    def __init__(self, 
                 db_path: Path,
                 embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                 chunk_size: int = 512,
                 chunk_overlap: int = 50,
                 use_chroma: bool = False):
        
        self.db_path = Path(db_path)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_model_name = embedding_model
        
        # Initialize embedding model
        self.embedding_model = None
        self.embedding_dim = 384  # Default for MiniLM
        if HAS_EMBEDDINGS:
            try:
                self.embedding_model = SentenceTransformer(embedding_model)
                self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
                logger.info(f"Loaded embedding model: {embedding_model}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
        
        # BM25 index for keyword search
        self.bm25 = BM25Index()
        
        # ChromaDB (optional)
        self.chroma_client = None
        self.chroma_collection = None
        if use_chroma and HAS_CHROMA:
            try:
                self.chroma_client = chromadb.Client()
                self.chroma_collection = self.chroma_client.get_or_create_collection("sentience_rag")
                logger.info("ChromaDB initialized")
            except Exception as e:
                logger.error(f"ChromaDB init failed: {e}")
        
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    source TEXT,
                    title TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    indexed_at TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT,
                    content TEXT NOT NULL,
                    start_char INTEGER,
                    end_char INTEGER,
                    metadata TEXT,
                    embedding BLOB,
                    created_at TEXT,
                    FOREIGN KEY (document_id) REFERENCES documents(id)
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)")
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, content='chunks', content_rowid='rowid')")
            conn.commit()
            
    def _chunk_text(self, text: str, source: str = "") -> List[Chunk]:
        """Split text into overlapping chunks"""
        chunks = []
        start = 0
        chunk_id_base = hashlib.sha256(source.encode()).hexdigest()[:8] if source else ""
        
        # Split by paragraphs first, then by size
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_start = 0
        
        for para in paragraphs:
            if len(current_chunk) + len(para) > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_id = f"{chunk_id_base}_{len(chunks)}"
                chunks.append(Chunk(
                    id=chunk_id,
                    document_id="",
                    content=current_chunk.strip(),
                    start_char=current_start,
                    end_char=current_start + len(current_chunk)
                ))
                
                # Start new chunk with overlap
                overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                current_chunk = current_chunk[overlap_start:] + "\n\n" + para
                current_start += overlap_start
            else:
                current_chunk += "\n\n" + para if current_chunk else para
                
        # Don't forget the last chunk
        if current_chunk.strip():
            chunk_id = f"{chunk_id_base}_{len(chunks)}"
            chunks.append(Chunk(
                id=chunk_id,
                document_id="",
                content=current_chunk.strip(),
                start_char=current_start,
                end_char=current_start + len(current_chunk)
            ))
            
        return chunks
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text"""
        if not self.embedding_model:
            return None
        try:
            emb = self.embedding_model.encode(text, convert_to_numpy=True)
            return emb.tolist()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None
            
    def index_document(self, content: str, source: str = "", metadata: Dict = None) -> Document:
        """Index a document"""
        doc_id = hashlib.sha256((source + content[:100]).encode()).hexdigest()[:16]
        now = datetime.utcnow().isoformat()
        
        # Create document
        doc = Document(
            id=doc_id,
            content=content,
            source=source,
            metadata=metadata or {}
        )
        
        # Chunk the document
        chunks = self._chunk_text(content, source)
        
        with sqlite3.connect(self.db_path) as conn:
            # Store document
            conn.execute("""
                INSERT INTO documents (id, source, title, metadata, created_at, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET indexed_at = excluded.indexed_at
            """, (doc_id, source, metadata.get('title', ''), json.dumps(metadata or {}), now, now))
            
            # Store chunks
            for chunk in chunks:
                chunk.document_id = doc_id
                chunk.metadata = {'source': source}
                
                # Get embedding
                embedding = self._get_embedding(chunk.content)
                embedding_blob = None
                if embedding:
                    import struct
                    embedding_blob = struct.pack(f'{len(embedding)}f', *embedding)
                
                conn.execute("""
                    INSERT INTO chunks (id, document_id, content, start_char, end_char, metadata, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (chunk.id, doc_id, chunk.content, chunk.start_char, chunk.end_char, 
                      json.dumps(chunk.metadata), embedding_blob, now))
                
                # Index in BM25
                self.bm25.index(chunk.id, chunk.content)
                
                # Store in ChromaDB if available
                if self.chroma_collection and embedding:
                    self.chroma_collection.add(
                        ids=[chunk.id],
                        embeddings=[embedding],
                        documents=[chunk.content],
                        metadatas=[{'document_id': doc_id, 'source': source}]
                    )
                    
            conn.commit()
            
        doc.chunks = chunks
        return doc
    
    def index_file(self, file_path: Path, metadata: Dict = None) -> Document:
        """Index a file"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        meta = metadata or {}
        meta['file_path'] = str(file_path)
        meta['file_name'] = file_path.name
        meta['extension'] = file_path.suffix
        
        return self.index_document(content, source=str(file_path), metadata=meta)
    
    def index_directory(self, dir_path: Path, extensions: List[str] = None) -> List[Document]:
        """Index all files in directory"""
        extensions = extensions or ['.md', '.txt', '.py', '.js', '.ts', '.json', '.yaml', '.yml']
        documents = []
        
        for ext in extensions:
            for file_path in Path(dir_path).rglob(f'*{ext}'):
                try:
                    doc = self.index_file(file_path)
                    documents.append(doc)
                    logger.info(f"Indexed: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to index {file_path}: {e}")
                    
        return documents
    
    def search_vector(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Vector similarity search"""
        if not self.embedding_model:
            return []
            
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []
            
        results = []
        
        # Use ChromaDB if available
        if self.chroma_collection:
            chroma_results = self.chroma_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            for i, chunk_id in enumerate(chroma_results['ids'][0]):
                chunk = Chunk(
                    id=chunk_id,
                    document_id=chroma_results['metadatas'][0][i].get('document_id', ''),
                    content=chroma_results['documents'][0][i],
                    metadata=chroma_results['metadatas'][0][i]
                )
                results.append(SearchResult(chunk=chunk, score=1 - chroma_results['distances'][0][i], source='vector'))
                
        else:
            # SQLite search
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM chunks WHERE embedding IS NOT NULL").fetchall()
                
                # Simple cosine similarity
                import struct
                for row in rows:
                    emb_blob = row['embedding']
                    if not emb_blob:
                        continue
                    chunk_emb = list(struct.unpack(f'{len(emb_blob)//4}f', emb_blob))
                    
                    # Cosine similarity
                    dot = sum(a * b for a, b in zip(query_embedding, chunk_emb))
                    norm_a = math.sqrt(sum(a * a for a in query_embedding))
                    norm_b = math.sqrt(sum(b * b for b in chunk_emb))
                    similarity = dot / (norm_a * norm_b) if norm_a and norm_b else 0
                    
                    if similarity > 0.1:  # Threshold
                        chunk = Chunk(
                            id=row['id'],
                            document_id=row['document_id'],
                            content=row['content'],
                            metadata=json.loads(row['metadata']) if row['metadata'] else {}
                        )
                        results.append(SearchResult(chunk=chunk, score=similarity, source='vector'))
                        
            results.sort(key=lambda x: x.score, reverse=True)
            results = results[:top_k]
            
        return results
    
    def search_bm25(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """BM25 keyword search"""
        bm25_results = self.bm25.search(query, top_k)
        
        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for chunk_id, score in bm25_results:
                row = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
                if row:
                    chunk = Chunk(
                        id=row['id'],
                        document_id=row['document_id'],
                        content=row['content'],
                        metadata=json.loads(row['metadata']) if row['metadata'] else {}
                    )
                    results.append(SearchResult(chunk=chunk, score=score, source='bm25'))
                    
        return results
    
    def search_hybrid(self, query: str, top_k: int = 10, alpha: float = 0.5) -> List[SearchResult]:
        """
        Hybrid search: alpha * vector_score + (1-alpha) * bm25_score
        alpha=1.0: pure vector, alpha=0.0: pure BM25
        """
        vector_results = self.search_vector(query, top_k * 2)
        bm25_results = self.search_bm25(query, top_k * 2)
        
        # Normalize scores
        max_vec = max((r.score for r in vector_results), default=1)
        max_bm25 = max((r.score for r in bm25_results), default=1)
        
        # Combine scores
        combined = {}
        
        for r in vector_results:
            r.score = r.score / max_vec if max_vec else 0
            combined[r.chunk.id] = r
            
        for r in bm25_results:
            normalized_score = r.score / max_bm25 if max_bm25 else 0
            if r.chunk.id in combined:
                # Hybrid score
                combined[r.chunk.id].score = alpha * combined[r.chunk.id].score + (1 - alpha) * normalized_score
                combined[r.chunk.id].source = 'hybrid'
            else:
                r.score = (1 - alpha) * normalized_score
                combined[r.chunk.id] = r
                
        # Sort by combined score
        results = sorted(combined.values(), key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def query(self, query: str, top_k: int = 5, mode: str = 'hybrid') -> List[Dict]:
        """Query the RAG system"""
        if mode == 'vector':
            results = self.search_vector(query, top_k)
        elif mode == 'bm25':
            results = self.search_bm25(query, top_k)
        else:
            results = self.search_hybrid(query, top_k)
            
        return [
            {
                'content': r.chunk.content,
                'score': r.score,
                'source': r.source,
                'metadata': r.chunk.metadata
            }
            for r in results
        ]
    
    def get_context(self, query: str, max_tokens: int = 4000) -> str:
        """Get context for a query, fitting within token budget"""
        results = self.search_hybrid(query, top_k=20)
        
        context_parts = []
        current_length = 0
        
        for r in results:
            # Rough token estimate (4 chars per token)
            chunk_tokens = len(r.chunk.content) // 4
            
            if current_length + chunk_tokens > max_tokens:
                break
                
            context_parts.append(f"[Source: {r.chunk.metadata.get('source', 'unknown')}]\n{r.chunk.content}\n")
            current_length += chunk_tokens
            
        return "\n---\n".join(context_parts)


__all__ = ['RAGEngine', 'Document', 'Chunk', 'SearchResult']
