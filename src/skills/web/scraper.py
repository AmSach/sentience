"""
Web Scraper Skill
Extract data from web pages.
"""

import os
import re
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

METADATA = {
    "name": "scraper",
    "description": "Extract data from web pages with CSS/XPath selectors",
    "category": "web",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["scrape", "web scrape", "extract data", "crawl"],
    "dependencies": [],
    "tags": ["scraping", "web", "extraction", "html"]
}

SKILL_NAME = "scraper"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "web"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


class SimpleHTMLParser:
    """Simple HTML parser for scraping without external dependencies."""
    
    def __init__(self):
        self.in_tag = False
        self.current_tag = None
        self.current_attrs = {}
        self.tag_stack = []
        self.text_parts = []
    
    def parse(self, html: str) -> Dict[str, Any]:
        """Parse HTML into a simple structure."""
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Parse tags
        result = {'_text': '', '_children': {}}
        
        # Extract text content
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        result['_text'] = text
        
        return result
    
    def find_all(self, html: str, tag: str) -> List[Dict[str, Any]]:
        """Find all instances of a tag."""
        results = []
        
        # Pattern for tag with attributes
        pattern = rf'<{tag}[^>]*>(.*?)</{tag}>'
        matches = re.finditer(pattern, html, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            full_match = match.group(0)
            content = match.group(1)
            
            # Extract attributes
            attrs = self._extract_attrs(full_match, tag)
            
            # Clean content
            clean_content = re.sub(r'<[^>]+>', '', content).strip()
            clean_content = re.sub(r'\s+', ' ', clean_content)
            
            results.append({
                'tag': tag,
                'attributes': attrs,
                'content': clean_content,
                'html': full_match
            })
        
        return results
    
    def find(self, html: str, tag: str) -> Optional[Dict[str, Any]]:
        """Find first instance of a tag."""
        results = self.find_all(html, tag)
        return results[0] if results else None
    
    def _extract_attrs(self, tag_html: str, tag_name: str) -> Dict[str, str]:
        """Extract attributes from tag HTML."""
        attrs = {}
        
        # Get tag opening
        tag_pattern = rf'<{tag_name}([^>]*)>'
        match = re.search(tag_pattern, tag_html, re.IGNORECASE)
        
        if match:
            attr_string = match.group(1)
            
            # Extract attribute pairs
            attr_pattern = r'(\w+)=["\']([^"\']*)["\']|(\w+)=([^\s>]+)|(\w+)'
            
            for m in re.finditer(attr_pattern, attr_string):
                if m.group(1):
                    attrs[m.group(1)] = m.group(2)
                elif m.group(3):
                    attrs[m.group(3)] = m.group(4)
                elif m.group(5):
                    attrs[m.group(5)] = ''
        
        return attrs
    
    def find_by_class(self, html: str, class_name: str) -> List[Dict[str, Any]]:
        """Find elements by class name."""
        pattern = rf'<(\w+)[^>]*class=["\'][^"\']*{class_name}[^"\']*["\'][^>]*>(.*?)</\1>'
        results = []
        
        for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            tag = match.group(1)
            content = match.group(2)
            attrs = self._extract_attrs(match.group(0), tag)
            
            clean_content = re.sub(r'<[^>]+>', '', content).strip()
            
            results.append({
                'tag': tag,
                'attributes': attrs,
                'content': clean_content,
                'html': match.group(0)
            })
        
        return results
    
    def find_by_id(self, html: str, id_value: str) -> Optional[Dict[str, Any]]:
        """Find element by ID."""
        pattern = rf'<(\w+)[^>]*id=["\']?{id_value}["\']?[^>]*>(.*?)</\1>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        
        if match:
            tag = match.group(1)
            content = match.group(2)
            attrs = self._extract_attrs(match.group(0), tag)
            
            clean_content = re.sub(r'<[^>]+>', '', content).strip()
            
            return {
                'tag': tag,
                'attributes': attrs,
                'content': clean_content,
                'html': match.group(0)
            }
        
        return None
    
    def find_links(self, html: str, base_url: str = None) -> List[Dict[str, str]]:
        """Extract all links from HTML."""
        links = []
        
        # Find all anchor tags
        pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
        
        for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            href = match.group(1)
            text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            
            # Resolve relative URLs
            if base_url and href and not href.startswith(('http://', 'https://', '//')):
                href = urljoin(base_url, href)
            
            # Skip fragments and javascript
            if href and not href.startswith(('#', 'javascript:')):
                links.append({
                    'url': href,
                    'text': text
                })
        
        return links
    
    def find_images(self, html: str, base_url: str = None) -> List[Dict[str, str]]:
        """Extract all images from HTML."""
        images = []
        
        # Find all img tags
        pattern = r'<img[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>'
        
        for match in re.finditer(pattern, html, re.IGNORECASE):
            src = match.group(1)
            alt = match.group(2) or ''
            
            if base_url and src and not src.startswith(('http://', 'https://', '//', 'data:')):
                src = urljoin(base_url, src)
            
            images.append({
                'src': src,
                'alt': alt
            })
        
        return images
    
    def find_tables(self, html: str) -> List[Dict[str, Any]]:
        """Extract tables from HTML."""
        tables = []
        
        # Find all table tags
        table_pattern = r'<table[^>]*>(.*?)</table>'
        
        for table_match in re.finditer(table_pattern, html, re.DOTALL | re.IGNORECASE):
            table_html = table_match.group(1)
            table_data = {'headers': [], 'rows': []}
            
            # Extract headers
            header_pattern = r'<th[^>]*>(.*?)</th>'
            headers = re.findall(header_pattern, table_html, re.DOTALL | re.IGNORECASE)
            table_data['headers'] = [re.sub(r'<[^>]+>', '', h).strip() for h in headers]
            
            # Extract rows
            row_pattern = r'<tr[^>]*>(.*?)</tr>'
            for row_match in re.finditer(row_pattern, table_html, re.DOTALL | re.IGNORECASE):
                row_html = row_match.group(1)
                
                # Skip header row
                if '<th' in row_html.lower():
                    continue
                
                cell_pattern = r'<td[^>]*>(.*?)</td>'
                cells = re.findall(cell_pattern, row_html, re.DOTALL | re.IGNORECASE)
                
                row = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                if row:
                    table_data['rows'].append(row)
            
            if table_data['headers'] or table_data['rows']:
                tables.append(table_data)
        
        return tables
    
    def find_meta(self, html: str) -> Dict[str, str]:
        """Extract meta tags from HTML."""
        meta = {}
        
        # Find all meta tags
        pattern = r'<meta\s+([^>]+)>'
        
        for match in re.finditer(pattern, html, re.IGNORECASE):
            attr_string = match.group(1)
            
            # Extract name or property
            name_match = re.search(r'(?:name|property)=["\']([^"\']+)["\']', attr_string, re.IGNORECASE)
            content_match = re.search(r'content=["\']([^"\']*)["\']', attr_string, re.IGNORECASE)
            
            if name_match and content_match:
                meta[name_match.group(1)] = content_match.group(1)
        
        return meta
    
    def find_json_ld(self, html: str) -> List[Dict[str, Any]]:
        """Extract JSON-LD structured data."""
        json_ld_list = []
        
        pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        
        for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(match.group(1))
                json_ld_list.append(data)
            except json.JSONDecodeError:
                pass
        
        return json_ld_list


class WebScraper:
    """Main web scraper class."""
    
    def __init__(self):
        self.parser = SimpleHTMLParser()
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch(self, url: str) -> str:
        """Fetch HTML from URL."""
        import urllib.request
        import urllib.error
        
        request = urllib.request.Request(url, headers=self.session_headers)
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode('utf-8', errors='ignore')
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to fetch {url}: {e}")
    
    def scrape(self, url: str, selectors: Dict[str, str]) -> Dict[str, Any]:
        """Scrape a page with CSS-like selectors."""
        html = self.fetch(url)
        return self.extract(html, selectors, url)
    
    def extract(self, html: str, selectors: Dict[str, str], base_url: str = None) -> Dict[str, Any]:
        """Extract data from HTML using selectors."""
        results = {}
        
        for name, selector in selectors.items():
            # Parse selector
            if selector.startswith('#'):
                # ID selector
                element = self.parser.find_by_id(html, selector[1:])
                results[name] = element['content'] if element else None
            
            elif selector.startswith('.'):
                # Class selector
                elements = self.parser.find_by_class(html, selector[1:])
                results[name] = [e['content'] for e in elements]
            
            elif selector.startswith('a[href]'):
                # Links
                results[name] = self.parser.find_links(html, base_url)
            
            elif selector.startswith('img'):
                # Images
                results[name] = self.parser.find_images(html, base_url)
            
            elif selector.startswith('table'):
                # Tables
                results[name] = self.parser.find_tables(html)
            
            elif selector.startswith('meta'):
                # Meta tags
                results[name] = self.parser.find_meta(html)
            
            elif selector.startswith('json-ld'):
                # JSON-LD
                results[name] = self.parser.find_json_ld(html)
            
            else:
                # Tag selector
                elements = self.parser.find_all(html, selector)
                results[name] = [e['content'] for e in elements]
        
        return results
    
    def crawl(self, start_url: str, max_pages: int = 10, 
              link_selector: str = 'a[href]') -> Dict[str, Any]:
        """Crawl multiple pages starting from a URL."""
        visited = set()
        results = []
        queue = [start_url]
        
        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            
            if url in visited:
                continue
            
            try:
                html = self.fetch(url)
                links = self.parser.find_links(html, url)
                
                results.append({
                    'url': url,
                    'title': self._extract_title(html),
                    'links_count': len(links)
                })
                
                visited.add(url)
                
                # Add new links to queue
                for link in links:
                    link_url = link['url']
                    if link_url not in visited and link_url not in queue:
                        queue.append(link_url)
            
            except Exception as e:
                results.append({
                    'url': url,
                    'error': str(e)
                })
        
        return {
            'pages': results,
            'total_crawled': len(visited)
        }
    
    def _extract_title(self, html: str) -> str:
        """Extract page title."""
        match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ''


def execute(
    url: str = None,
    html: str = None,
    operation: str = "extract",
    selectors: Dict[str, str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Scrape web pages.
    
    Args:
        url: URL to scrape
        html: HTML content (if no URL)
        operation: Operation (extract/fetch/crawl/links/images/tables/meta)
        selectors: CSS-like selectors for extraction
    
    Returns:
        Scraped data
    """
    scraper = WebScraper()
    
    if operation == "fetch":
        if not url:
            return {"success": False, "error": "url required"}
        
        try:
            html = scraper.fetch(url)
            return {
                "success": True,
                "html": html,
                "url": url
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif operation == "extract":
        if url:
            try:
                html = scraper.fetch(url)
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if not html:
            return {"success": False, "error": "url or html required"}
        
        if not selectors:
            return {"success": False, "error": "selectors required"}
        
        results = scraper.extract(html, selectors, url)
        return {
            "success": True,
            "data": results
        }
    
    elif operation == "scrape":
        if not url or not selectors:
            return {"success": False, "error": "url and selectors required"}
        
        try:
            results = scraper.scrape(url, selectors)
            return {
                "success": True,
                "url": url,
                "data": results
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif operation == "links":
        if url:
            try:
                html = scraper.fetch(url)
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if not html:
            return {"success": False, "error": "url or html required"}
        
        links = scraper.parser.find_links(html, url)
        return {
            "success": True,
            "links": links,
            "count": len(links)
        }
    
    elif operation == "images":
        if url:
            try:
                html = scraper.fetch(url)
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if not html:
            return {"success": False, "error": "url or html required"}
        
        images = scraper.parser.find_images(html, url)
        return {
            "success": True,
            "images": images,
            "count": len(images)
        }
    
    elif operation == "tables":
        if url:
            try:
                html = scraper.fetch(url)
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if not html:
            return {"success": False, "error": "url or html required"}
        
        tables = scraper.parser.find_tables(html)
        return {
            "success": True,
            "tables": tables,
            "count": len(tables)
        }
    
    elif operation == "meta":
        if url:
            try:
                html = scraper.fetch(url)
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if not html:
            return {"success": False, "error": "url or html required"}
        
        meta = scraper.parser.find_meta(html)
        return {
            "success": True,
            "meta": meta
        }
    
    elif operation == "crawl":
        if not url:
            return {"success": False, "error": "url required"}
        
        max_pages = kwargs.get('max_pages', 10)
        
        try:
            results = scraper.crawl(url, max_pages)
            return {
                "success": True,
                "crawl_results": results
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
