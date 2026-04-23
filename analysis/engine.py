"""Analysis engine - deep data analysis, pattern recognition, insights."""
import json, re, os
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime

class SentienceAnalysis:
    """Multi-mode analysis engine."""
    
    def __init__(self):
        self.cache = {}
    
    def analyze_document(self, text: str, mode: str = "full") -> Dict:
        """Analyze document structure and content."""
        if mode == "full":
            return {
                "word_count": len(text.split()),
                "char_count": len(text),
                "sentence_count": len(re.split(r'[.!?]+', text)),
                "paragraph_count": len(text.split("\n\n")),
                "avg_word_length": sum(len(w) for w in text.split()) / max(1, len(text.split())),
                "language_hints": self._detect_language(text),
                "entities": self._extract_entities(text),
                "topics": self._extract_topics(text),
                "sentiment": self._analyze_sentiment(text),
                "readability_score": self._readability_score(text),
            }
        elif mode == "quick":
            return {
                "word_count": len(text.split()),
                "char_count": len(text),
                "language_hints": self._detect_language(text),
            }
    
    def _detect_language(self, text: str) -> Dict:
        common_words = {
            "en": ["the", "is", "at", "which", "on", "and", "a", "an", "in", "with", "for", "to", "of", "by"],
            "hi": ["है", "के", "में", "की", "को", "से", "पर", "यह", "और", "हैं"],
            "es": ["el", "la", "de", "que", "es", "en", "un", "una", "y", "los", "las"],
            "fr": ["le", "la", "les", "de", "du", "un", "une", "et", "est", "que", "en"],
            "de": ["der", "die", "das", "und", "ist", "in", "von", "mit", "für", "auf"],
            "zh": ["的", "是", "在", "了", "和", "有", "我", "他", "这", "个"],
            "ja": ["の", "は", "を", "た", "が", "で", "て", "と", "し", "れ"],
        }
        words = text.lower().split()
        lang_scores = {}
        for lang, keywords in common_words.items():
            score = sum(1 for w in words[:50] if w in keywords)
            if score > 0:
                lang_scores[lang] = score / len(keywords)
        return {"detected": max(lang_scores, key=lang_scores.get) if lang_scores else "unknown", "scores": lang_scores}
    
    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Simple named entity extraction."""
        entities = {"persons": [], "organizations": [], "locations": [], "dates": [], "emails": [], "urls": [], "phones": []}
        # Dates
        date_patterns = [r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}']
        for p in date_patterns:
            entities["dates"].extend(re.findall(p, text, re.IGNORECASE))
        # Emails
        entities["emails"] = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        # URLs
        entities["urls"] = re.findall(r'https?://[^\s]+', text)
        # Phones
        entities["phones"] = re.findall(r'\+?[\d\s\-()]{10,}', text)
        # Capitalized words (simple heuristic)
        words = re.findall(r'(?:[A-Z][a-z]+){2,}', text)
        for w in words:
            if len(w) > 3 and w not in ["The", "This", "That", "With"]:
                entities["organizations"].append(w)
        return {k: list(set(v))[:20] for k, v in entities.items()}
    
    def _extract_topics(self, text: str) -> List[str]:
        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        stopwords = {"that", "this", "with", "have", "from", "they", "been", "were", "will", "would", "could", "their", "what", "about", "which", "when", "make", "just", "over", "such", "into", "than", "more", "them", "then", "some", "her", "all", "can", "had", "has", "have", "each", "other", "some", "these", "those", "very"}
        filtered = [w for w in words if w not in stopwords]
        counter = Counter(filtered)
        return [w for w, c in counter.most_common(10)]
    
    def _analyze_sentiment(self, text: str) -> Dict:
        positive = ["good", "great", "excellent", "amazing", "wonderful", "fantastic", "happy", "love", "best", "beautiful", "perfect", "success", "successful", "profit", "growth", "increase", "improve", "achieved", "won", "positive"]
        negative = ["bad", "poor", "terrible", "awful", "horrible", "sad", "hate", "worst", "ugly", "fail", "failure", "loss", "decrease", "decline", "problem", "issue", "error", "crash", "bug", "negative"]
        words = text.lower().split()
        pos = sum(1 for w in words if w in positive)
        neg = sum(1 for w in words if w in negative)
        total = pos + neg
        if total == 0:
            return {"score": 0, "label": "neutral", "positive_count": 0, "negative_count": 0}
        score = (pos - neg) / total
        return {"score": round(score, 3), "label": "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral", "positive_count": pos, "negative_count": neg}
    
    def _readability_score(self, text: str) -> Dict:
        words = text.split()
        sentences = len(re.split(r'[.!?]+', text))
        syllables = sum(self._count_syllables(w) for w in words)
        if not words or not sentences:
            return {"score": 0, "grade": "N/A"}
        avg_words_per_sentence = len(words) / sentences
        avg_syllables_per_word = syllables / len(words)
        # Flesch Reading Ease
        score = 206.835 - 1.015 * avg_words_per_sentence - 84.6 * avg_syllables_per_word
        score = max(0, min(100, score))
        grade = "College Graduate" if score > 80 else "College" if score > 60 else "High School" if score > 40 else "Middle School" if score > 20 else "Elementary"
        return {"score": round(score, 1), "grade": grade, "avg_words_per_sentence": round(avg_words_per_sentence, 1), "avg_syllables_per_word": round(avg_syllables_per_word, 2)}
    
    def _count_syllables(self, word: str) -> int:
        word = word.lower()
        vowels = "aeiouy"
        count = 0
        prev_vowel = False
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel
        return max(1, count)
    
    def compare_documents(self, doc1: str, doc2: str) -> Dict:
        """Compare two documents for similarity and differences."""
        text1 = self._load_doc(doc1)
        text2 = self._load_doc(doc2)
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        intersection = words1 & words2
        union = words1 | words2
        jaccard = len(intersection) / len(union) if union else 0
        return {
            "jaccard_similarity": round(jaccard, 3),
            "unique_to_doc1": list(words1 - words2)[:50],
            "unique_to_doc2": list(words2 - words1)[:50],
            "common_words": list(intersection)[:50],
            "length_diff": abs(len(text1) - len(text2)),
        }
    
    def _load_doc(self, path: str) -> str:
        try:
            if path.endswith(".pdf"):
                from PyPDF2 import PdfReader
                return " ".join([p.extract_text() for p in PdfReader(path).pages])
            elif path.endswith(".docx"):
                from docx import Document
                return " ".join([p.text for p in Document(path).paragraphs])
            return open(path).read()
        except:
            return path  # treat as raw text
    
    def extract_tables(self, text: str) -> List[List[str]]:
        """Extract table data from text."""
        tables = []
        lines = text.split("\n")
        current_table = []
        for line in lines:
            if "\t" in line or " | " in line:
                cols = [c.strip() for c in re.split(r'\t|\|', line) if c.strip()]
                if len(cols) >= 2:
                    current_table.append(cols)
            elif current_table and not line.strip():
                if current_table:
                    tables.append(current_table)
                    current_table = []
        if current_table:
            tables.append(current_table)
        return tables
    
    def generate_summary(self, text: str, max_length: int = 500) -> str:
        """Generate a summary of the text."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s for s in sentences if len(s) > 20]
        if not sentences:
            return text[:max_length]
        # Score sentences by word importance
        words = set(re.findall(r'\b[a-z]{5,}\b', text.lower()))
        scored = []
        for s in sentences:
            s_words = re.findall(r'\b[a-z]{5,}\b', s.lower())
            score = sum(1 for w in s_words if w in words)
            scored.append((score, len(s), s))
        scored.sort(key=lambda x: (-x[0], x[1]))
        result = ""
        for score, length, s in scored:
            if len(result) + len(s) + 1 <= max_length:
                result += " " + s
        return result.strip()
