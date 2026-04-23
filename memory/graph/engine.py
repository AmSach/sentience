#!/usr/bin/env python3
"""Sentience Graph - Entity memory with graph traversal."""
import json, hashlib, time, re
from typing import List, Dict, Any, Optional

class SentienceGraph:
    """Build and query entity knowledge graphs from conversations."""
    def __init__(self, storage):
        self.storage = storage
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract named entities from text using patterns."""
        entities = []
        # Simple pattern-based extraction
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
        for name in set(proper_nouns):
            if len(name) > 3 and name not in ('The', 'This', 'That', 'JavaScript', 'TypeScript', 'Python'):
                eid = self.storage.add_entity("person_org", name)
                entities.append({"id": eid, "name": name, "type": "person_org"})
        codes = re.findall(r'\b([A-Z]{2,}[-]?\w*)\b', text)
        for code in set(codes):
            if len(code) > 2 and len(code) < 20:
                eid = self.storage.add_entity("code_slug", code)
                entities.append({"id": eid, "name": code, "type": "code_slug"})
        return entities
    
    def link_entities(self, source_id: str, target_id: str, relationship: str, weight: float = 1.0) -> None:
        self.storage.add_edge(source_id, target_id, relationship, weight)
    
    def build_from_conversation(self, messages: List[dict]) -> None:
        """Auto-build graph from conversation history."""
        for msg in messages:
            content = msg.get("content", "")
            if not content or msg.get("role") == "system": continue
            entities = self.extract_entities(content)
            for i, ent in enumerate(entities):
                if i > 0:
                    self.link_entities(entities[i-1]["id"], ent["id"], "mentioned_near")
    
    def query(self, entity_name: str = None, entity_id: str = None, depth: int = 2, rel_type: str = None) -> Dict:
        if entity_id is None and entity_name:
            all_mem = self.storage.list_memory()
        if entity_id:
            connected = self.storage.get_connected_entities(entity_id, rel_type=rel_type, depth=depth)
            nodes = {}
            for row in connected:
                if len(row) >= 4:
                    nid = row[0]
                    nodes[nid] = {"id": nid, "type": row[1], "name": row[2], "props": json.loads(row[3]) if row[3] else {}, "rels": []}
            edges = []
            for row in connected:
                if len(row) >= 6:
                    edges.append({"from": entity_id, "to": row[0], "rel": row[4], "weight": row[5]})
            return {"center": entity_id, "nodes": list(nodes.values()), "edges": edges}
        return {"nodes": [], "edges": []}
    
    def suggest_links(self, note_content: str, existing_ids: List[str]) -> List[Dict]:
        """Suggest related notes based on content similarity."""
        entities = self.extract_entities(note_content)
        suggestions = []
        for ent in entities:
            connected = self.storage.get_connected_entities(ent["id"], depth=2)
            for row in connected:
                if len(row) >= 4 and row[0] not in existing_ids:
                    suggestions.append({"id": row[0], "name": row[2], "type": row[1], "relevance": row[5] if len(row) > 5 else 1.0})
        suggestions.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return suggestions[:5]
