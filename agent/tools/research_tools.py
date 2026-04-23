"""Research tools - web research, deep analysis, multi-source synthesis."""
import json
from typing import Dict, List
from ..research.engine import ResearchEngine

def register_tools(registry):
    engine = ResearchEngine()
    
    @registry.tool("web_research", "Quick web search.", {"query": "Search query", "num_results": "Number of results"})
    def quick_research(query: str, num_results: int = 5) -> Dict:
        return engine.quick_research(query)
    
    @registry.tool("deep_research", "Deep multi-source research on a topic.", {"topic": "Research topic", "depth": "Research depth (1-5)"})
    def deep_research(topic: str, depth: int = 3) -> Dict:
        return engine.deep_research(topic, depth)
    
    @registry.tool("compare_topics", "Research and compare multiple topics side by side.")
    def compare_topics(topics: List[str]) -> Dict:
        return engine.compare_topics(topics)
    
    @registry.tool("extract_facts", "Extract factual claims from text.")
    def extract(text: str) -> List:
        return engine.extract_facts(text)
