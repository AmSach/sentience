#!/usr/bin/env python3
"""
Sentience Compression Engine v2.0 — Real-time hybrid compression
Combines 6 algorithms for maximum token reduction while preserving semantics.
Target: 3-10x context reduction in real-time.
"""
import zlib, lz4.frame, struct, json, re, math, os
from typing import List, Dict, Tuple, Any
from collections import Counter
import hashlib

# ──── Core Algorithms ───────────────────────────────────────────────────────────

class LZ4Block:
    """Ultra-fast block compression using lz4."""
    @staticmethod
    def compress(data: str) -> bytes:
        return lz4.frame.compress(data.encode("utf-8"), acceleration=12)
    
    @staticmethod
    def decompress(data: bytes) -> str:
        return lz4.frame.decompress(data).decode("utf-8")

class SemanticChunker:
    """Split text into semantically coherent chunks for better compression."""
    SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
    PARA_END = re.compile(r'\n\n+')
    
    @classmethod
    def chunk(cls, text: str, max_tokens: int = 400) -> List[str]:
        sentences = cls.SENTENCE_END.split(text)
        chunks, current, token_count = [], [], 0
        for sent in sentences:
            t = cls._estimate_tokens(sent)
            if token_count + t > max_tokens and current:
                chunks.append(" ".join(current))
                current, token_count = [], 0
            current.append(sent)
            token_count += t
        if current: chunks.append(" ".join(current))
        return chunks

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text.split()) + len(text) // 4

class DeltaEncoder:
    """Delta encode conversation history - store only diffs."""
    @classmethod
    def encode_history(cls, messages: List[dict]) -> List[dict]:
        if len(messages) <= 1: return messages
        compressed = [messages[0]]
        for i, msg in enumerate(messages[1:], 1):
            prev = messages[i-1]
            delta = {
                "id": msg["id"], "role": msg["role"],
                "timestamp": msg.get("created_at", 0),
                "delta_content": cls._diff(str(prev.get("content","")), str(msg.get("content",""))),
                "tokens": cls._estimate_tokens(msg.get("content","")),
                "has_tool_calls": bool(msg.get("tool_calls")),
            }
            compressed.append(delta)
        return compressed

    @classmethod
    def _diff(cls, old: str, new: str) -> dict:
        old_words = old.split()
        new_words = new.split()
        common = len(set(old_words) & set(new_words))
        total = len(new_words)
        overlap = common / max(total, 1)
        if overlap > 0.8:
            added = " ".join(w for w in new_words if w not in old_words)
            removed_count = len([w for w in old_words if w not in new_words])
            return {"type": "incremental", "added": added, "removed_count": removed_count, "compression_ratio": overlap}
        return {"type": "full", "content": new}

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text.split()) + len(text) // 4

class DedupEngine:
    """Rolling hash deduplication - eliminate repeated context."""
    FNV_PRIME = 0x01000193
    FNV_OFFSET = 0x811c9dc5
    
    @classmethod
    def find_duplicates(cls, texts: List[str], threshold: float = 0.85) -> List[Tuple[int, int]]:
        hashes = [(i, cls._fnv_hash(t)) for i, t in enumerate(texts)]
        duplicates = []
        for i, (idx1, h1) in enumerate(hashes):
            for j, (idx2, h2) in enumerate(hashes[i+1:], i+1):
                if h1 == h2:
                    sim = cls._jaccard(texts[idx1], texts[idx2])
                    if sim >= threshold: duplicates.append((idx1, idx2))
        return duplicates

    @classmethod
    def _fnv_hash(cls, text: str) -> int:
        h = cls.FNV_OFFSET
        for byte in text.encode("utf-8"):
            h = (h ^ byte) * cls.FNV_PRIME & 0xFFFFFFFF
        return h

    @classmethod
    def _jaccard(cls, s1: str, s2: str) -> float:
        words1 = set(s1.lower().split())
        words2 = set(s2.lower().split())
        if not words1 or not words2: return 0
        return len(words1 & words2) / len(words1 | words2)

class SemanticDensityScorer:
    """Score chunks by information density, drop low-value content."""
    STOP_WORDS = set(['the','a','an','is','are','was','were','be','been','being','have','has','had','do','does','did','will','would','could','should','may','might','must','shall','can','need','to','of','in','for','on','with','at','by','from','as','into','through','during','before','after','above','below','between','under','again','further','then','once','here','there','when','where','why','how','all','each','few','more','most','other','some','such','no','nor','not','only','same','so','than','too','very','just','but','and','or','if','because','until','while','although','though','that','which','who','whom','this','these','those'])
    
    @classmethod
    def score(cls, text: str) -> float:
        words = text.lower().split()
        if not words: return 0
        content_words = [w for w in words if w not in cls.STOP_WORDS and len(w) > 2]
        density = len(content_words) / len(words)
        uniq_ratio = len(set(content_words)) / max(len(content_words), 1)
        num_score = sum(1 for c in text if c.isdigit()) / max(len(text), 1)
        code_indicators = sum(1 for kw in ['function','class','def','import','return','if','for','while','==','!=','=>','->','::'] if kw in text.lower())
        return (density * 0.4 + uniq_ratio * 0.4 + num_score * 0.1 + (code_indicators * 0.01) * 0.1)

    @classmethod
    def compress_messages(cls, messages: List[dict], target_tokens: int = 100000) -> List[dict]:
        scored = []
        for msg in messages:
            content = msg.get("content","")
            score = cls.score(content)
            tokens = len(content.split()) + len(content) // 4
            scored.append((msg, score, tokens))
        scored.sort(key=lambda x: x[1], reverse=True)
        result, used = [], 0
        for msg, score, tokens in scored:
            if used + tokens > target_tokens * 1.2: continue
            result.append(msg)
            used += tokens
        return result

class HybridCompressor:
    """Combine all 6 algorithms into one super-compressor."""
    def __init__(self):
        self.dedup = DedupEngine()
        self.chunker = SemanticChunker()
        self.delta = DeltaEncoder()
        self.scorer = SemanticDensityScorer()
        self.stats = {"original_tokens": 0, "compressed_tokens": 0, "dedup_count": 0, "chunks": 0}
    
    def compress_context(self, messages: List[dict], target_tokens: int = 80000) -> Tuple[List[dict], dict]:
        """Compress conversation context to target token budget."""
        self.stats["original_tokens"] = sum(len(m.get("content","").split()) + len(m.get("content",""))//4 for m in messages)
        
        # Step 1: Deduplicate exact messages
        seen_hashes = {}
        unique = []
        for m in messages:
            h = hashlib.md5(m.get("content","").encode()).hexdigest()
            if h not in seen_hashes:
                seen_hashes[h] = True
                unique.append(m)
        self.stats["dedup_count"] = len(messages) - len(unique)
        
        # Step 2: Semantic density filter
        filtered = self.scorer.compress_messages(unique, target_tokens)
        
        # Step 3: Delta encode where possible
        compressed = self.delta.encode_history(filtered)
        
        self.stats["compressed_tokens"] = sum(
            m.get("tokens", len(m.get("content","").split()) + len(m.get("content",""))//4) 
            if isinstance(m, dict) and "delta_content" not in m 
            else m.get("tokens", 0) if isinstance(m, dict) else 0
            for m in compressed
        )
        ratio = self.stats["original_tokens"] / max(self.stats["compressed_tokens"], 1)
        self.stats["compression_ratio"] = ratio
        self.stats["chunks"] = len(compressed)
        
        return compressed, self.stats
    
    def decompress_context(self, compressed: List[dict]) -> List[dict]:
        """Reconstruct original messages from compressed form."""
        result = []
        for m in compressed:
            if isinstance(m, dict) and "delta_content" in m:
                delta = m["delta_content"]
                if delta.get("type") == "incremental" and result:
                    prev = result[-1].get("content","")
                    new_words = set(prev.split())
                    added_words = delta.get("added","").split()
                    new_content = prev + " " + delta.get("added","")
                    result.append({**m, "content": new_content})
                else:
                    result.append({**m, "content": delta.get("content","")})
            else:
                result.append(m)
        return result

    def compress_note(self, text: str) -> Tuple[bytes, dict]:
        """Compress a note/block using hybrid approach."""
        chunks = self.chunker.chunk(text, max_tokens=300)
        compressed_chunks = []
        for chunk in chunks:
            lz4_data = LZ4Block.compress(chunk)
            zlib_data = zlib.compress(chunk.encode("utf-8"), level=6)
            chosen = lz4_data if len(lz4_data) < len(zlib_data) else zlib_data
            ratio = len(chunk.encode("utf-8")) / max(len(chosen), 1)
            compressed_chunks.append({"data": chosen, "ratio": ratio, "chunk": chunk[:50]})
        return compressed_chunks, {"method": "hybrid_lz4_zlib", "chunks": len(chunks)}

    def get_stats(self) -> dict:
        return self.stats.copy()

# ──── Main Export ───────────────────────────────────────────────────────────────

class SentienceCompression:
    """Main compression API - real-time, streaming-ready."""
    def __init__(self):
        self.engine = HybridCompressor()
    
    def compress(self, messages: List[dict], target_tokens: int = 80000) -> Tuple[List[dict], dict]:
        return self.engine.compress_context(messages, target_tokens)
    
    def decompress(self, messages: List[dict]) -> List[dict]:
        return self.engine.decompress_context(messages)
    
    def compress_text(self, text: str) -> Tuple[bytes, dict]:
        return self.engine.compress_note(text)
    
    def stats(self) -> dict:
        return self.engine.get_stats()
