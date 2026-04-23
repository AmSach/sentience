"""Analysis tools - data analysis, document comparison, fact extraction."""
import json
from typing import Dict, List
from ..analysis.engine import SentienceAnalysis

def register_tools(registry):
    analyzer = SentienceAnalysis()
    
    @registry.tool("analyze_document", "Analyze a document for structure, entities, sentiment, readability.", {"text": "Text content to analyze", "mode": "full or quick"})
    def analyze_doc(text: str, mode: str = "full") -> Dict:
        return analyzer.analyze_document(text, mode)
    
    @registry.tool("compare_documents", "Compare two documents for similarity and differences.")
    def compare_docs(doc1: str, doc2: str) -> Dict:
        return analyzer.compare_documents(doc1, doc2)
    
    @registry.tool("generate_summary", "Generate a summary of text.", {"text": "Text to summarize", "max_length": "Max summary length in characters"})
    def summarize(text: str, max_length: int = 500) -> str:
        return analyzer.generate_summary(text, max_length)
    
    @registry.tool("extract_tables", "Extract table data from text.")
    def extract_tables(text: str) -> List:
        return analyzer.extract_tables(text)
    
    @registry.tool("extract_facts", "Extract factual claims and data points from text.")
    def extract_facts(text: str) -> List:
        return analyzer.extract_facts(text)
