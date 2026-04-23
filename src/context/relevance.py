"""
Relevance Scoring - Score code relevance for context selection

Features:
- TF-IDF for code tokens
- Semantic similarity (using embeddings or heuristics)
- Usage frequency tracking
- Recency weighting
"""

import os
import re
import json
import math
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Document:
    """A document (code file) for TF-IDF."""
    filepath: str
    tokens: List[str]
    token_counts: Dict[str, int]
    content_hash: str
    last_modified: datetime
    language: Optional[str] = None


@dataclass
class RelevanceScore:
    """Relevance score for a file/symbol."""
    filepath: str
    score: float
    tfidf_score: float
    semantic_score: float
    frequency_score: float
    recency_score: float
    combined_score: float
    matched_terms: List[str] = field(default_factory=list)
    highlights: List[Tuple[int, int, str]] = field(default_factory=list)  # (start, end, term)


@dataclass
class UsageRecord:
    """Record of file/symbol usage."""
    filepath: str
    symbol_name: Optional[str]
    timestamp: datetime
    action: str  # edit, view, reference, call
    duration: float = 0.0  # seconds


class Tokenizer:
    """Tokenize code for text analysis."""
    
    # Common programming keywords to filter
    STOPWORDS = {
        'if', 'else', 'elif', 'for', 'while', 'do', 'switch', 'case', 'default',
        'break', 'continue', 'return', 'yield', 'try', 'catch', 'finally', 'throw',
        'class', 'struct', 'interface', 'enum', 'function', 'def', 'fn', 'func',
        'import', 'from', 'export', 'require', 'include', 'using',
        'const', 'let', 'var', 'val', 'var', 'int', 'float', 'string', 'bool',
        'true', 'false', 'null', 'none', 'undefined', 'nan', 'inf',
        'this', 'self', 'super', 'new', 'delete', 'sizeof', 'typeof',
        'public', 'private', 'protected', 'static', 'final', 'abstract',
        'extends', 'implements', 'inherits', 'where', 'as', 'is', 'in',
        'and', 'or', 'not', '!', '&&', '||', '==', '!=', '<', '>', '<=', '>=',
        '+', '-', '*', '/', '%', '=', '+=', '-=', '*=', '/=',
        '{', '}', '(', ')', '[', ']', ';', ':', ',', '.', '->', '=>',
    }
    
    def __init__(self, min_token_length: int = 2, filter_stopwords: bool = True):
        self.min_token_length = min_token_length
        self.filter_stopwords = filter_stopwords
    
    def tokenize(self, code: str, language: Optional[str] = None) -> List[str]:
        """Tokenize code into meaningful tokens."""
        tokens: List[str] = []
        
        # Split on word boundaries and special characters
        # Keep identifiers, strings, and comments together
        
        # Remove comments first (language-aware)
        code = self._remove_comments(code, language)
        
        # Remove string literals but keep their content
        code = re.sub(r'"([^"]*)"', r' \1 ', code)
        code = re.sub(r"'([^']*)'", r' \1 ', code)
        code = re.sub(r'`([^`]*)`', r' \1 ', code)
        
        # Split on non-alphanumeric characters
        raw_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|\d+', code)
        
        for token in raw_tokens:
            token_lower = token.lower()
            
            # Skip short tokens
            if len(token_lower) < self.min_token_length:
                continue
            
            # Skip numbers
            if token.isdigit():
                continue
            
            # Skip stopwords
            if self.filter_stopwords and token_lower in self.STOPWORDS:
                continue
            
            # Split camelCase and snake_case
            subtokens = self._split_identifier(token)
            tokens.extend(subtokens)
        
        return tokens
    
    def _remove_comments(self, code: str, language: Optional[str]) -> str:
        """Remove comments from code."""
        if language == 'Python':
            # Remove single-line comments
            code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
            # Remove multi-line strings (often used as docstrings/comments)
            # Keep them for now as they may contain useful info
        elif language in ('JavaScript', 'TypeScript', 'Java', 'C', 'C++', 'C#'):
            # Remove single-line comments
            code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
            # Remove multi-line comments
            code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        return code
    
    def _split_identifier(self, identifier: str) -> List[str]:
        """Split identifier into subtokens."""
        tokens: List[str] = []
        
        # snake_case
        if '_' in identifier:
            parts = identifier.split('_')
            tokens.extend(p.lower() for p in parts if p and len(p) >= self.min_token_length)
        # camelCase or PascalCase
        else:
            # Split on uppercase letters
            parts = re.findall(r'[a-z]+|[A-Z][a-z]*', identifier)
            for part in parts:
                if len(part) >= self.min_token_length:
                    tokens.append(part.lower())
        
        # Also keep the full identifier
        if identifier.lower() not in tokens:
            tokens.append(identifier.lower())
        
        return tokens
    
    def get_ngrams(self, tokens: List[str], n: int = 2) -> List[str]:
        """Get n-grams from tokens."""
        ngrams: List[str] = []
        for i in range(len(tokens) - n + 1):
            ngram = '_'.join(tokens[i:i+n])
            ngrams.append(ngram)
        return ngrams


class TFIDFCalculator:
    """Calculate TF-IDF scores for code documents."""
    
    def __init__(self, tokenizer: Optional[Tokenizer] = None):
        self.tokenizer = tokenizer or Tokenizer()
        self.documents: Dict[str, Document] = {}
        self.document_frequency: Dict[str, int] = defaultdict(int)
        self.idf_cache: Dict[str, float] = {}
        self._corpus_size = 0
    
    def add_document(self, filepath: str, content: str, 
                     language: Optional[str] = None) -> Document:
        """Add a document to the corpus."""
        tokens = self.tokenizer.tokenize(content, language)
        token_counts = Counter(tokens)
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        last_modified = datetime.utcnow()
        
        try:
            stat = os.stat(filepath)
            last_modified = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            pass
        
        doc = Document(
            filepath=filepath,
            tokens=tokens,
            token_counts=token_counts,
            content_hash=content_hash,
            last_modified=last_modified,
            language=language
        )
        
        # Update document frequency
        unique_tokens = set(tokens)
        for token in unique_tokens:
            self.document_frequency[token] += 1
        
        self.documents[filepath] = doc
        self._corpus_size = len(self.documents)
        
        # Clear IDF cache
        self.idf_cache.clear()
        
        return doc
    
    def remove_document(self, filepath: str) -> None:
        """Remove a document from the corpus."""
        if filepath not in self.documents:
            return
        
        doc = self.documents[filepath]
        
        # Update document frequency
        unique_tokens = set(doc.tokens)
        for token in unique_tokens:
            self.document_frequency[token] -= 1
            if self.document_frequency[token] <= 0:
                del self.document_frequency[token]
        
        del self.documents[filepath]
        self._corpus_size = len(self.documents)
        self.idf_cache.clear()
    
    def get_idf(self, token: str) -> float:
        """Get inverse document frequency for a token."""
        if token in self.idf_cache:
            return self.idf_cache[token]
        
        df = self.document_frequency.get(token, 0)
        
        if df == 0:
            idf = 0.0
        else:
            # Smooth IDF
            idf = math.log((self._corpus_size + 1) / (df + 1)) + 1
        
        self.idf_cache[token] = idf
        return idf
    
    def get_tf(self, doc: Document, token: str) -> float:
        """Get term frequency for a token in a document."""
        if not doc.tokens:
            return 0.0
        
        count = doc.token_counts.get(token, 0)
        # Log-normalized TF
        return 1 + math.log(count) if count > 0 else 0.0
    
    def get_tfidf(self, doc: Document, token: str) -> float:
        """Get TF-IDF score for a token in a document."""
        tf = self.get_tf(doc, token)
        idf = self.get_idf(token)
        return tf * idf
    
    def get_document_vector(self, doc: Document) -> Dict[str, float]:
        """Get TF-IDF vector for a document."""
        vector: Dict[str, float] = {}
        
        for token, count in doc.token_counts.items():
            vector[token] = self.get_tfidf(doc, token)
        
        # Normalize
        magnitude = math.sqrt(sum(v * v for v in vector.values()))
        if magnitude > 0:
            for token in vector:
                vector[token] /= magnitude
        
        return vector
    
    def search(self, query: str, top_k: int = 10, 
               language: Optional[str] = None) -> List[Tuple[str, float, List[str]]]:
        """Search for documents matching a query."""
        if not self.documents:
            return []
        
        # Tokenize query
        query_tokens = self.tokenizer.tokenize(query, language)
        query_counts = Counter(query_tokens)
        
        # Calculate query vector
        query_vector: Dict[str, float] = {}
        for token, count in query_counts.items():
            tf = 1 + math.log(count) if count > 0 else 0.0
            idf = self.get_idf(token)
            query_vector[token] = tf * idf
        
        # Normalize query vector
        magnitude = math.sqrt(sum(v * v for v in query_vector.values()))
        if magnitude > 0:
            for token in query_vector:
                query_vector[token] /= magnitude
        
        # Calculate similarity with each document
        scores: List[Tuple[str, float, List[str]]] = []
        
        for filepath, doc in self.documents.items():
            doc_vector = self.get_document_vector(doc)
            
            # Cosine similarity
            score = 0.0
            matched_terms: List[str] = []
            
            for token, query_weight in query_vector.items():
                if token in doc_vector:
                    doc_weight = doc_vector[token]
                    score += query_weight * doc_weight
                    matched_terms.append(token)
            
            if score > 0:
                scores.append((filepath, score, matched_terms))
        
        # Sort by score
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]


class SemanticSimilarity:
    """Calculate semantic similarity between code snippets."""
    
    def __init__(self):
        self._embeddings_cache: Dict[str, List[float]] = {}
        self._use_embeddings = False
        
        # Try to import sentence transformers
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            self._use_embeddings = True
        except ImportError:
            self._model = None
            logger.info("sentence-transformers not available, using heuristic similarity")
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text."""
        if not self._use_embeddings or not self._model:
            return []
        
        # Check cache
        cache_key = hashlib.sha256(text.encode()).hexdigest()[:16]
        if cache_key in self._embeddings_cache:
            return self._embeddings_cache[cache_key]
        
        # Generate embedding
        embedding = self._model.encode(text).tolist()
        self._embeddings_cache[cache_key] = embedding
        
        return embedding
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0
        
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts."""
        if self._use_embeddings:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)
            return self.cosine_similarity(emb1, emb2)
        else:
            return self._heuristic_similarity(text1, text2)
    
    def _heuristic_similarity(self, text1: str, text2: str) -> float:
        """Calculate heuristic similarity when embeddings not available."""
        # Jaccard similarity on words
        words1 = set(re.findall(r'\b\w+\b', text1.lower()))
        words2 = set(re.findall(r'\b\w+\b', text2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def find_similar(self, query: str, documents: Dict[str, str], 
                     top_k: int = 10) -> List[Tuple[str, float]]:
        """Find documents similar to query."""
        if not self._use_embeddings:
            # Use TF-IDF-like scoring as fallback
            tokenizer = Tokenizer()
            query_tokens = set(tokenizer.tokenize(query))
            
            scores: List[Tuple[str, float]] = []
            for filepath, content in documents.items():
                doc_tokens = set(tokenizer.tokenize(content))
                
                if not query_tokens or not doc_tokens:
                    continue
                
                intersection = query_tokens & doc_tokens
                jaccard = len(intersection) / len(query_tokens | doc_tokens)
                
                if jaccard > 0:
                    scores.append((filepath, jaccard))
            
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:top_k]
        
        # Use embeddings
        query_embedding = self.get_embedding(query)
        
        scores: List[Tuple[str, float]] = []
        for filepath, content in documents.items():
            doc_embedding = self.get_embedding(content)
            sim = self.cosine_similarity(query_embedding, doc_embedding)
            
            if sim > 0:
                scores.append((filepath, sim))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class UsageTracker:
    """Track usage frequency of files and symbols."""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self._usage_records: List[UsageRecord] = []
        self._file_frequency: Dict[str, int] = defaultdict(int)
        self._symbol_frequency: Dict[str, int] = defaultdict(int)
        self._recent_usage: Dict[str, datetime] = {}
        self._max_records = 10000
    
    def record(self, filepath: str, action: str,
               symbol_name: Optional[str] = None,
               duration: float = 0.0) -> None:
        """Record a usage event."""
        record = UsageRecord(
            filepath=filepath,
            symbol_name=symbol_name,
            timestamp=datetime.utcnow(),
            action=action,
            duration=duration
        )
        
        self._usage_records.append(record)
        
        # Update frequency
        self._file_frequency[filepath] += 1
        if symbol_name:
            key = f"{filepath}::{symbol_name}"
            self._symbol_frequency[key] += 1
        
        # Update recent usage
        self._recent_usage[filepath] = record.timestamp
        
        # Trim records if needed
        if len(self._usage_records) > self._max_records:
            self._trim_records()
    
    def _trim_records(self) -> None:
        """Trim old usage records."""
        # Keep only recent records
        cutoff = datetime.utcnow() - timedelta(days=30)
        self._usage_records = [r for r in self._usage_records if r.timestamp >= cutoff]
        
        # Rebuild frequency counts
        self._file_frequency.clear()
        self._symbol_frequency.clear()
        
        for record in self._usage_records:
            self._file_frequency[record.filepath] += 1
            if record.symbol_name:
                key = f"{record.filepath}::{record.symbol_name}"
                self._symbol_frequency[key] += 1
    
    def get_file_frequency(self, filepath: str) -> int:
        """Get usage frequency for a file."""
        return self._file_frequency.get(filepath, 0)
    
    def get_symbol_frequency(self, filepath: str, symbol_name: str) -> int:
        """Get usage frequency for a symbol."""
        key = f"{filepath}::{symbol_name}"
        return self._symbol_frequency.get(key, 0)
    
    def get_most_used_files(self, top_k: int = 10) -> List[Tuple[str, int]]:
        """Get most frequently used files."""
        sorted_files = sorted(
            self._file_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_files[:top_k]
    
    def get_most_used_symbols(self, top_k: int = 10) -> List[Tuple[str, int]]:
        """Get most frequently used symbols."""
        sorted_symbols = sorted(
            self._symbol_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_symbols[:top_k]
    
    def get_recently_used(self, minutes: int = 60) -> List[str]:
        """Get files used in the last N minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent = [
            filepath for filepath, timestamp in self._recent_usage.items()
            if timestamp >= cutoff
        ]
        return recent
    
    def save(self) -> None:
        """Save usage data to storage."""
        if not self.storage_path:
            return
        
        data = {
            'records': [
                {
                    'filepath': r.filepath,
                    'symbol_name': r.symbol_name,
                    'timestamp': r.timestamp.isoformat(),
                    'action': r.action,
                    'duration': r.duration
                }
                for r in self._usage_records
            ],
            'file_frequency': dict(self._file_frequency),
            'symbol_frequency': dict(self._symbol_frequency)
        }
        
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(data, f)
    
    def load(self) -> None:
        """Load usage data from storage."""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            self._usage_records = [
                UsageRecord(
                    filepath=r['filepath'],
                    symbol_name=r.get('symbol_name'),
                    timestamp=datetime.fromisoformat(r['timestamp']),
                    action=r['action'],
                    duration=r.get('duration', 0.0)
                )
                for r in data.get('records', [])
            ]
            
            self._file_frequency = defaultdict(int, data.get('file_frequency', {}))
            self._symbol_frequency = defaultdict(int, data.get('symbol_frequency', {}))
            
            # Rebuild recent usage
            for record in self._usage_records:
                if record.filepath not in self._recent_usage or \
                   record.timestamp > self._recent_usage[record.filepath]:
                    self._recent_usage[record.filepath] = record.timestamp
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Error loading usage data: {e}")


class RecencyWeighting:
    """Calculate recency-based weights for files."""
    
    def __init__(self, half_life_hours: float = 24.0):
        """
        Initialize with half-life for exponential decay.
        
        Args:
            half_life_hours: Time in hours for weight to decay to 0.5
        """
        self.half_life_hours = half_life_hours
        self.half_life_seconds = half_life_hours * 3600
        self.decay_constant = math.log(2) / self.half_life_seconds
    
    def calculate_weight(self, last_modified: datetime, 
                         reference_time: Optional[datetime] = None) -> float:
        """Calculate recency weight with exponential decay."""
        if reference_time is None:
            reference_time = datetime.utcnow()
        
        age_seconds = (reference_time - last_modified).total_seconds()
        
        if age_seconds < 0:
            age_seconds = 0
        
        weight = math.exp(-self.decay_constant * age_seconds)
        
        return weight
    
    def calculate_weight_from_age(self, age_seconds: float) -> float:
        """Calculate weight from age in seconds."""
        return math.exp(-self.decay_constant * age_seconds)
    
    def get_weight_threshold(self, min_weight: float = 0.1) -> float:
        """Get maximum age in seconds for minimum weight."""
        # t = -ln(w) / decay_constant
        max_age_seconds = -math.log(min_weight) / self.decay_constant
        return max_age_seconds


class RelevanceScorer:
    """Combine multiple relevance factors into a single score."""
    
    def __init__(self, 
                 tfidf_weight: float = 0.4,
                 semantic_weight: float = 0.3,
                 frequency_weight: float = 0.15,
                 recency_weight: float = 0.15):
        self.tfidf_weight = tfidf_weight
        self.semantic_weight = semantic_weight
        self.frequency_weight = frequency_weight
        self.recency_weight = recency_weight
        
        self.tfidf = TFIDFCalculator()
        self.semantic = SemanticSimilarity()
        self.usage = UsageTracker()
        self.recency = RecencyWeighting()
    
    def index_file(self, filepath: str, content: str,
                   language: Optional[str] = None) -> None:
        """Index a file for relevance scoring."""
        self.tfidf.add_document(filepath, content, language)
    
    def remove_file(self, filepath: str) -> None:
        """Remove a file from the index."""
        self.tfidf.remove_document(filepath)
    
    def score_query(self, query: str, filepath: str,
                    content: Optional[str] = None,
                    language: Optional[str] = None) -> RelevanceScore:
        """Calculate relevance score for a file given a query."""
        # TF-IDF score
        tfidf_results = self.tfidf.search(query, top_k=100, language=language)
        tfidf_score = 0.0
        matched_terms: List[str] = []
        
        for fp, score, terms in tfidf_results:
            if fp == filepath:
                tfidf_score = score
                matched_terms = terms
                break
        
        # Semantic score
        semantic_score = 0.0
        if content:
            semantic_score = self.semantic.similarity(query, content)
        
        # Frequency score (normalized)
        freq = self.usage.get_file_frequency(filepath)
        max_freq = max(self.usage._file_frequency.values()) if self.usage._file_frequency else 1
        frequency_score = freq / max_freq if max_freq > 0 else 0.0
        
        # Recency score
        doc = self.tfidf.documents.get(filepath)
        recency_score = 0.0
        if doc:
            recency_score = self.recency.calculate_weight(doc.last_modified)
        
        # Combined score
        combined = (
            self.tfidf_weight * tfidf_score +
            self.semantic_weight * semantic_score +
            self.frequency_weight * frequency_score +
            self.recency_weight * recency_score
        )
        
        return RelevanceScore(
            filepath=filepath,
            score=combined,
            tfidf_score=tfidf_score,
            semantic_score=semantic_score,
            frequency_score=frequency_score,
            recency_score=recency_score,
            combined_score=combined,
            matched_terms=matched_terms
        )
    
    def search(self, query: str, top_k: int = 10,
               language: Optional[str] = None,
               content_map: Optional[Dict[str, str]] = None) -> List[RelevanceScore]:
        """Search for relevant files given a query."""
        # Get TF-IDF results
        tfidf_results = self.tfidf.search(query, top_k=top_k * 2, language=language)
        
        scores: List[RelevanceScore] = []
        
        for filepath, tfidf_score, matched_terms in tfidf_results:
            # Get content if provided
            content = content_map.get(filepath) if content_map else None
            
            # Semantic score
            semantic_score = 0.0
            if content:
                semantic_score = self.semantic.similarity(query, content)
            
            # Frequency score
            freq = self.usage.get_file_frequency(filepath)
            max_freq = max(self.usage._file_frequency.values()) if self.usage._file_frequency else 1
            frequency_score = freq / max_freq if max_freq > 0 else 0.0
            
            # Recency score
            doc = self.tfidf.documents.get(filepath)
            recency_score = 0.0
            if doc:
                recency_score = self.recency.calculate_weight(doc.last_modified)
            
            # Combined score
            combined = (
                self.tfidf_weight * tfidf_score +
                self.semantic_weight * semantic_score +
                self.frequency_weight * frequency_score +
                self.recency_weight * recency_score
            )
            
            scores.append(RelevanceScore(
                filepath=filepath,
                score=combined,
                tfidf_score=tfidf_score,
                semantic_score=semantic_score,
                frequency_score=frequency_score,
                recency_score=recency_score,
                combined_score=combined,
                matched_terms=matched_terms
            ))
        
        # Sort by combined score
        scores.sort(key=lambda s: s.combined_score, reverse=True)
        
        return scores[:top_k]
    
    def get_highlights(self, content: str, terms: List[str],
                       context_chars: int = 50) -> List[Tuple[int, int, str]]:
        """Find highlighted matches in content."""
        highlights: List[Tuple[int, int, str]] = []
        
        content_lower = content.lower()
        
        for term in terms:
            term_lower = term.lower()
            start = 0
            
            while True:
                pos = content_lower.find(term_lower, start)
                if pos == -1:
                    break
                
                # Get context
                context_start = max(0, pos - context_chars)
                context_end = min(len(content), pos + len(term) + context_chars)
                
                # Find word boundaries
                while context_start > 0 and not content[context_start-1].isspace():
                    context_start -= 1
                while context_end < len(content) and not content[context_end].isspace():
                    context_end += 1
                
                highlights.append((pos, pos + len(term), term))
                start = pos + 1
        
        return highlights
    
    def save_index(self, filepath: str) -> None:
        """Save relevance index to file."""
        data = {
            'documents': {
                fp: {
                    'tokens': doc.tokens[:1000],  # Truncate for storage
                    'token_counts': dict(doc.token_counts),
                    'content_hash': doc.content_hash,
                    'last_modified': doc.last_modified.isoformat(),
                    'language': doc.language
                }
                for fp, doc in self.tfidf.documents.items()
            },
            'document_frequency': dict(self.tfidf.document_frequency),
            'corpus_size': self.tfidf._corpus_size
        }
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f)
    
    def load_index(self, filepath: str) -> None:
        """Load relevance index from file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.tfidf.documents = {}
            
            for fp, doc_data in data.get('documents', {}).items():
                doc = Document(
                    filepath=fp,
                    tokens=doc_data.get('tokens', []),
                    token_counts=Counter(doc_data.get('token_counts', {})),
                    content_hash=doc_data.get('content_hash', ''),
                    last_modified=datetime.fromisoformat(doc_data.get('last_modified', datetime.utcnow().isoformat())),
                    language=doc_data.get('language')
                )
                self.tfidf.documents[fp] = doc
            
            self.tfidf.document_frequency = defaultdict(int, data.get('document_frequency', {}))
            self.tfidf._corpus_size = data.get('corpus_size', 0)
            self.tfidf.idf_cache.clear()
            
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Error loading relevance index: {e}")


def create_relevance_scorer(root_path: str, 
                            index_path: Optional[str] = None) -> RelevanceScorer:
    """Create and optionally load a relevance scorer."""
    scorer = RelevanceScorer()
    
    if index_path and os.path.exists(index_path):
        scorer.load_index(index_path)
    
    return scorer


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        scorer = RelevanceScorer()
        
        # Index directory
        root = sys.argv[1]
        for root_dir, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'venv', '__pycache__')]
            
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.jsx', '.tsx')):
                    filepath = os.path.join(root_dir, f)
                    try:
                        with open(filepath, 'r') as file:
                            content = file.read()
                        scorer.index_file(filepath, content)
                    except IOError:
                        pass
        
        # Search
        if len(sys.argv) > 2:
            query = sys.argv[2]
            results = scorer.search(query, top_k=5)
            
            for result in results:
                print(f"{result.filepath}: {result.combined_score:.3f}")
                print(f"  Terms: {result.matched_terms}")
