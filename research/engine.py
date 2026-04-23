"""Research engine - web research, deep analysis, multi-source synthesis."""
import json, re, urllib.request, urllib.parse, time, html
from typing import Dict, List, Any, Optional
from collections import defaultdict

class WebResearcher:
    """Web search and content extraction."""
    
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0 (compatible; Sentience/1.0)"}
    
    def search(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search the web using multiple free sources."""
        results = []
        # DuckDuckGo
        try:
            url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}&kl=en-us"
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                html_content = resp.read().decode("utf-8", errors="ignore")
            # Parse results
            for match in re.finditer(r'<a class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>', html_content):
                results.append({"url": match.group(1), "title": html.unescape(match.group(2).strip()), "source": "duckduckgo"})
            for match in re.finditer(r'<a class="result__snippet" href="([^"]+)">([^<]+)', html_content):
                if len(results) < num_results * 2:
                    snippet = html.unescape(match.group(2).strip()).replace("<b>","").replace("</b>","")
                    if not any(r.get("url") == match.group(1) for r in results):
                        results.append({"url": match.group(1), "snippet": snippet[:300], "source": "duckduckgo"})
        except Exception as e:
            pass
        return results[:num_results]
    
    def fetch_page(self, url: str, timeout: int = 10) -> Dict:
        """Fetch and parse a web page."""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                title = re.search(r'<title>([^<]+)</title>', content, re.IGNORECASE)
                text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                return {
                    "url": url,
                    "title": html.unescape(title.group(1).strip()) if title else "",
                    "content": text[:5000],
                    "content_length": len(content),
                }
        except Exception as e:
            return {"url": url, "error": str(e)}

class DeepResearcher:
    """Multi-source deep research with synthesis."""
    
    def __init__(self, researcher: WebResearcher):
        self.researcher = researcher
    
    def research(self, topic: str, depth: int = 3) -> Dict:
        """Deep research on a topic across multiple sources."""
        # Phase 1: Initial search
        search_results = self.researcher.search(topic, num_results=depth * 3)
        sources = []
        all_content = []
        
        # Phase 2: Fetch top sources
        for result in search_results[:depth]:
            page = self.researcher.fetch_page(result["url"])
            if "content" in page:
                sources.append({"url": result["url"], "title": result.get("title",""), "snippet": result.get("snippet","")})
                all_content.append(page["content"][:2000])
        
        # Phase 3: Synthesize
        combined = " ".join(all_content)
        return {
            "topic": topic,
            "depth": depth,
            "sources_found": len(sources),
            "sources": sources,
            "combined_content": combined[:10000],
            "key_findings": self._extract_findings(combined),
        }
    
    def _extract_findings(self, content: str) -> List[str]:
        sentences = re.split(r'[.!?]\s+', content)
        important = [s.strip() for s in sentences if len(s) > 50 and any(w in s.lower() for w in ["result", "found", "showed", "revealed", "discovered", "according", "studies", "research"])]
        return important[:10]

class ResearchEngine:
    """Full research system."""
    
    def __init__(self):
        self.web = WebResearcher()
        self.deep = DeepResearcher(self.web)
    
    def quick_research(self, query: str) -> Dict:
        """Quick web search."""
        results = self.web.search(query, 5)
        return {"query": query, "results": results}
    
    def deep_research(self, topic: str, depth: int = 3) -> Dict:
        """Deep multi-source research."""
        return self.deep.research(topic, depth)
    
    def compare_topics(self, topics: List[str]) -> Dict:
        """Research and compare multiple topics."""
        results = {}
        for topic in topics:
            results[topic] = self.deep.research(topic, depth=2)
        return results
    
    def extract_facts(self, text: str) -> List[Dict]:
        """Extract factual claims from text."""
        facts = []
        sentences = re.split(r'[.!?]\s+', text)
        for s in sentences:
            s = s.strip()
            if len(s) > 30 and any(w in s.lower() for w in ["is", "are", "was", "were", "has", "have", "will", "can", "should", "may"]):
                # Look for quantifiable claims
                numbers = re.findall(r'\d+(?:\.\d+)?(?:%|million|billion|thousand|\$)?

', s, re.IGNORECASE)
                if numbers:
                    facts.append({"statement": s, "data_points": numbers})
        return facts
