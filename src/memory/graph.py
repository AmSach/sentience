"""
Knowledge Graph - Entity extraction, relation detection, and graph analytics.
SQLite-based graph database with path finding and community detection.
"""

import sqlite3
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import math


@dataclass
class Entity:
    """Represents an entity in the knowledge graph."""
    id: str
    name: str
    entity_type: str
    aliases: Set[str] = field(default_factory=set)
    properties: Dict = field(default_factory=dict)
    confidence: float = 1.0
    source_ids: Set[str] = field(default_factory=set)
    

@dataclass
class Relation:
    """Represents a relation between entities."""
    id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict = field(default_factory=dict)
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)


@dataclass
class Path:
    """Represents a path in the graph."""
    nodes: List[str]
    edges: List[str]
    length: int
    weight: float


class KnowledgeGraph:
    """
    SQLite-based knowledge graph with:
    - Entity extraction from text
    - Relation detection
    - Path finding (Dijkstra, BFS)
    - Community detection (label propagation)
    - Centrality measures
    """
    
    # Entity patterns for extraction
    ENTITY_PATTERNS = {
        'person': [
            r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b',  # First Last
            r'\b(Dr\.|Mr\.|Ms\.|Mrs\.)\s+([A-Z][a-z]+)\b',  # Title + Name
        ],
        'organization': [
            r'\b([A-Z][A-Za-z]+ (?:Inc|Corp|LLC|Ltd|Company|Co)\.?)\b',
            r'\b([A-Z][A-Za-z]+ (?:University|Institute|College|School))\b',
        ],
        'location': [
            r'\b([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)\b',  # City, Country
            r'\b([A-Z]{2,})\b',  # Acronyms like USA, UK
        ],
        'date': [
            r'\b(\d{4}-\d{2}-\d{2})\b',
            r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',
            r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b',
        ],
        'money': [
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars|USD)',
        ],
        'email': [
            r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',
        ],
        'url': [
            r'\b(https?://[^\s<>"{}|\\^`\[\]]+)\b',
        ],
    }
    
    # Relation patterns
    RELATION_PATTERNS = {
        'works_for': [
            r'(\w+)\s+works\s+(?:at|for)\s+(\w+)',
            r'(\w+)\s+(?:is|was)\s+(?:employed|hired)\s+(?:at|by)\s+(\w+)',
        ],
        'located_in': [
            r'(\w+)\s+(?:is|was)?\s*(?:located|based|headquartered)\s+in\s+(\w+)',
            r'(\w+)\s+in\s+(\w+)',
        ],
        'part_of': [
            r'(\w+)\s+(?:is|was)?\s*(?:a\s+)?part\s+of\s+(\w+)',
            r'(\w+)\s+belongs\s+to\s+(\w+)',
        ],
        'related_to': [
            r'(\w+)\s+(?:is|was)?\s*related\s+to\s+(\w+)',
            r'(\w+)\s+and\s+(\w+)\s+are\s+related',
        ],
        'created_by': [
            r'(\w+)\s+(?:was|is)?\s*(?:created|founded|established|built)\s+(?:by|in)\s+(\w+)',
        ],
        'knows': [
            r'(\w+)\s+(?:knows|knew|met)\s+(\w+)',
        ],
    }
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._load_entity_id_counter()
        
    def _init_db(self):
        """Initialize graph database schema."""
        cursor = self.conn.cursor()
        
        # Entities table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                aliases TEXT DEFAULT '[]',
                properties TEXT DEFAULT '{}',
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Relations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                confidence REAL DEFAULT 1.0,
                evidence TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            )
        ''')
        
        # Entity sources (link entities to their source documents)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entity_sources (
                entity_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                mention_count INTEGER DEFAULT 1,
                PRIMARY KEY (entity_id, source_id),
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(type)')
        
        # Graph metadata
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS graph_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        self.conn.commit()
    
    def _load_entity_id_counter(self):
        """Load or initialize entity ID counter."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM graph_meta WHERE key = "entity_counter"')
        row = cursor.fetchone()
        self._entity_counter = int(row['value']) if row else 0
    
    def _save_entity_id_counter(self):
        """Save entity ID counter."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO graph_meta (key, value) VALUES ("entity_counter", ?)
        ''', (str(self._entity_counter),))
        self.conn.commit()
    
    def _generate_entity_id(self) -> str:
        """Generate a unique entity ID."""
        self._entity_counter += 1
        self._save_entity_id_counter()
        return f"ent_{self._entity_counter:08d}"
    
    def _generate_relation_id(self) -> str:
        """Generate a unique relation ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM graph_meta WHERE key = "relation_counter"')
        row = cursor.fetchone()
        counter = int(row['value']) if row else 0
        counter += 1
        cursor.execute('''
            INSERT OR REPLACE INTO graph_meta (key, value) VALUES ("relation_counter", ?)
        ''', (str(counter),))
        self.conn.commit()
        return f"rel_{counter:08d}"
    
    def extract_entities(self, text: str, source_id: str = None) -> List[Entity]:
        """
        Extract entities from text using pattern matching.
        Returns list of extracted entities.
        """
        entities = []
        seen = set()
        
        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    entity_name = match.group(0) if match.lastindex is None else match.group(1)
                    
                    # Normalize entity name
                    entity_name = entity_name.strip()
                    if not entity_name or len(entity_name) < 2:
                        continue
                    
                    # Skip duplicates
                    key = (entity_name.lower(), entity_type)
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    entity = Entity(
                        id=self._generate_entity_id(),
                        name=entity_name,
                        entity_type=entity_type,
                        confidence=0.8,  # Pattern match confidence
                        source_ids={source_id} if source_id else set()
                    )
                    entities.append(entity)
        
        return entities
    
    def extract_relations(self, text: str, entities: List[Entity], source_id: str = None) -> List[Relation]:
        """
        Extract relations between entities from text.
        """
        relations = []
        
        # Create entity lookup
        entity_names = {e.name.lower(): e for e in entities}
        
        for relation_type, patterns in self.RELATION_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    source_name = match.group(1).strip()
                    target_name = match.group(2).strip()
                    
                    # Find matching entities
                    source_entity = entity_names.get(source_name.lower())
                    target_entity = entity_names.get(target_name.lower())
                    
                    if source_entity and target_entity and source_entity.id != target_entity.id:
                        relation = Relation(
                            id=self._generate_relation_id(),
                            source_id=source_entity.id,
                            target_id=target_entity.id,
                            relation_type=relation_type,
                            confidence=0.7,
                            evidence=[text[max(0, match.start()-50):match.end()+50]]
                        )
                        relations.append(relation)
        
        return relations
    
    def add_entity(self, entity: Entity) -> str:
        """Add an entity to the graph."""
        cursor = self.conn.cursor()
        
        # Check if entity with same name exists
        cursor.execute('''
            SELECT id FROM entities WHERE LOWER(name) = LOWER(?) AND type = ?
        ''', (entity.name, entity.entity_type))
        
        existing = cursor.fetchone()
        if existing:
            # Update existing entity
            entity_id = existing['id']
            cursor.execute('''
                UPDATE entities 
                SET confidence = (confidence + ?) / 2,
                    aliases = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (entity.confidence, json.dumps(list(entity.aliases)), entity_id))
        else:
            # Insert new entity
            entity_id = entity.id
            cursor.execute('''
                INSERT INTO entities (id, name, type, aliases, properties, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (entity_id, entity.name, entity.entity_type, 
                  json.dumps(list(entity.aliases)), json.dumps(entity.properties), entity.confidence))
        
        # Add source references
        for src_id in entity.source_ids:
            cursor.execute('''
                INSERT OR IGNORE INTO entity_sources (entity_id, source_id, mention_count)
                VALUES (?, ?, 1)
            ''', (entity_id, src_id))
        
        self.conn.commit()
        return entity_id
    
    def add_relation(self, relation: Relation) -> str:
        """Add a relation to the graph."""
        cursor = self.conn.cursor()
        
        # Check if similar relation exists
        cursor.execute('''
            SELECT id, evidence FROM relations 
            WHERE source_id = ? AND target_id = ? AND type = ?
        ''', (relation.source_id, relation.target_id, relation.relation_type))
        
        existing = cursor.fetchone()
        if existing:
            # Merge evidence
            relation_id = existing['id']
            existing_evidence = json.loads(existing['evidence'])
            new_evidence = existing_evidence + relation.evidence
            cursor.execute('''
                UPDATE relations 
                SET evidence = ?, confidence = (confidence + ?) / 2
                WHERE id = ?
            ''', (json.dumps(new_evidence[:10]), relation.confidence, relation_id))
        else:
            # Insert new relation
            relation_id = relation.id
            cursor.execute('''
                INSERT INTO relations (id, source_id, target_id, type, properties, confidence, evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (relation_id, relation.source_id, relation.target_id,
                  relation.relation_type, json.dumps(relation.properties),
                  relation.confidence, json.dumps(relation.evidence)))
        
        self.conn.commit()
        return relation_id
    
    def process_text(self, text: str, source_id: str = None) -> Tuple[List[Entity], List[Relation]]:
        """
        Process text to extract and store entities and relations.
        Returns extracted entities and relations.
        """
        # Extract entities
        entities = self.extract_entities(text, source_id)
        
        # Store entities
        entity_ids = {}
        for entity in entities:
            entity_id = self.add_entity(entity)
            entity_ids[entity.name.lower()] = entity_id
            entity.id = entity_id
        
        # Extract relations
        relations = self.extract_relations(text, entities, source_id)
        
        # Store relations
        for relation in relations:
            relation.id = self.add_relation(relation)
        
        return entities, relations
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM entities WHERE id = ?', (entity_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        # Get source IDs
        cursor.execute('SELECT source_id FROM entity_sources WHERE entity_id = ?', (entity_id,))
        source_ids = {r['source_id'] for r in cursor.fetchall()}
        
        return Entity(
            id=row['id'],
            name=row['name'],
            entity_type=row['type'],
            aliases=set(json.loads(row['aliases'])),
            properties=json.loads(row['properties']),
            confidence=row['confidence'],
            source_ids=source_ids
        )
    
    def get_entity_by_name(self, name: str, entity_type: str = None) -> Optional[Entity]:
        """Get an entity by name."""
        cursor = self.conn.cursor()
        
        if entity_type:
            cursor.execute('''
                SELECT * FROM entities WHERE LOWER(name) = LOWER(?) AND type = ?
            ''', (name, entity_type))
        else:
            cursor.execute('SELECT * FROM entities WHERE LOWER(name) = LOWER(?)', (name,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return self.get_entity(row['id'])
    
    def get_relations(self, entity_id: str = None, relation_type: str = None, 
                      limit: int = 100) -> List[Relation]:
        """Get relations, optionally filtered by entity or type."""
        cursor = self.conn.cursor()
        
        query = 'SELECT * FROM relations WHERE 1=1'
        params = []
        
        if entity_id:
            query += ' AND (source_id = ? OR target_id = ?)'
            params.extend([entity_id, entity_id])
        
        if relation_type:
            query += ' AND type = ?'
            params.append(relation_type)
        
        query += f' ORDER BY confidence DESC LIMIT {limit}'
        
        cursor.execute(query, params)
        relations = []
        
        for row in cursor.fetchall():
            relations.append(Relation(
                id=row['id'],
                source_id=row['source_id'],
                target_id=row['target_id'],
                relation_type=row['type'],
                properties=json.loads(row['properties']),
                confidence=row['confidence'],
                evidence=json.loads(row['evidence'])
            ))
        
        return relations
    
    def get_neighbors(self, entity_id: str, depth: int = 1, 
                      relation_types: List[str] = None) -> Dict[str, List[Tuple[str, str]]]:
        """
        Get neighboring entities up to specified depth.
        Returns dict mapping entity_id -> [(neighbor_id, relation_type), ...]
        """
        cursor = self.conn.cursor()
        visited = {entity_id}
        neighbors = defaultdict(list)
        current_level = {entity_id}
        
        for _ in range(depth):
            next_level = set()
            
            for ent_id in current_level:
                # Get outgoing relations
                query = 'SELECT target_id, type FROM relations WHERE source_id = ?'
                params = [ent_id]
                
                if relation_types:
                    placeholders = ','.join('?' * len(relation_types))
                    query += f' AND type IN ({placeholders})'
                    params.extend(relation_types)
                
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    if row['target_id'] not in visited:
                        neighbors[ent_id].append((row['target_id'], row['type']))
                        next_level.add(row['target_id'])
                        visited.add(row['target_id'])
                
                # Get incoming relations
                query = 'SELECT source_id, type FROM relations WHERE target_id = ?'
                params = [ent_id]
                
                if relation_types:
                    placeholders = ','.join('?' * len(relation_types))
                    query += f' AND type IN ({placeholders})'
                    params.extend(relation_types)
                
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    if row['source_id'] not in visited:
                        neighbors[ent_id].append((row['source_id'], row['type']))
                        next_level.add(row['source_id'])
                        visited.add(row['source_id'])
            
            current_level = next_level
        
        return dict(neighbors)
    
    def find_path(self, source_id: str, target_id: str, 
                  max_depth: int = 5, relation_types: List[str] = None) -> Optional[Path]:
        """
        Find shortest path between two entities using BFS.
        """
        if source_id == target_id:
            return Path(nodes=[source_id], edges=[], length=0, weight=0.0)
        
        cursor = self.conn.cursor()
        
        # BFS
        queue = deque([(source_id, [source_id], [])])
        visited = {source_id}
        
        while queue:
            current_id, path_nodes, path_edges = queue.popleft()
            
            if len(path_nodes) > max_depth:
                continue
            
            # Get neighbors
            query = 'SELECT target_id, id FROM relations WHERE source_id = ?'
            params = [current_id]
            
            if relation_types:
                placeholders = ','.join('?' * len(relation_types))
                query += f' AND type IN ({placeholders})'
                params.extend(relation_types)
            
            cursor.execute(query, params)
            
            for row in cursor.fetchall():
                neighbor_id = row['target_id']
                edge_id = row['id']
                
                if neighbor_id == target_id:
                    # Found path
                    final_nodes = path_nodes + [neighbor_id]
                    final_edges = path_edges + [edge_id]
                    return Path(
                        nodes=final_nodes,
                        edges=final_edges,
                        length=len(final_edges),
                        weight=float(len(final_edges))
                    )
                
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((
                        neighbor_id,
                        path_nodes + [neighbor_id],
                        path_edges + [edge_id]
                    ))
        
        return None  # No path found
    
    def find_all_paths(self, source_id: str, target_id: str, 
                       max_depth: int = 4, limit: int = 10) -> List[Path]:
        """
        Find all paths up to max_depth between two entities.
        """
        cursor = self.conn.cursor()
        
        paths = []
        stack = [(source_id, [source_id], [])]
        
        while stack and len(paths) < limit:
            current_id, path_nodes, path_edges = stack.pop()
            
            if current_id == target_id and len(path_nodes) > 1:
                paths.append(Path(
                    nodes=path_nodes,
                    edges=path_edges,
                    length=len(path_edges),
                    weight=float(len(path_edges))
                ))
                continue
            
            if len(path_nodes) >= max_depth:
                continue
            
            # Get neighbors
            cursor.execute('SELECT target_id, id FROM relations WHERE source_id = ?', 
                          (current_id,))
            
            for row in cursor.fetchall():
                neighbor_id = row['target_id']
                edge_id = row['id']
                
                if neighbor_id not in path_nodes:  # Avoid cycles
                    stack.append((
                        neighbor_id,
                        path_nodes + [neighbor_id],
                        path_edges + [edge_id]
                    ))
        
        # Sort by path length
        paths.sort(key=lambda p: p.length)
        return paths[:limit]
    
    def detect_communities(self, iterations: int = 10) -> Dict[str, int]:
        """
        Detect communities using label propagation algorithm.
        Returns dict mapping entity_id -> community_id.
        """
        cursor = self.conn.cursor()
        
        # Get all entities
        cursor.execute('SELECT id FROM entities')
        entities = [row['id'] for row in cursor.fetchall()]
        
        # Initialize each entity with unique label
        labels = {ent: i for i, ent in enumerate(entities)}
        
        # Build adjacency list
        cursor.execute('SELECT source_id, target_id FROM relations')
        adj = defaultdict(set)
        for row in cursor.fetchall():
            adj[row['source_id']].add(row['target_id'])
            adj[row['target_id']].add(row['source_id'])
        
        # Label propagation
        for _ in range(iterations):
            changed = False
            for entity in entities:
                neighbors = adj.get(entity, set())
                if not neighbors:
                    continue
                
                # Count neighbor labels
                label_counts = defaultdict(int)
                for neighbor in neighbors:
                    label_counts[labels[neighbor]] += 1
                
                # Find most common label
                if label_counts:
                    max_count = max(label_counts.values())
                    best_labels = [l for l, c in label_counts.items() if c == max_count]
                    new_label = min(best_labels)  # Deterministic tie-breaking
                    
                    if labels[entity] != new_label:
                        labels[entity] = new_label
                        changed = True
            
            if not changed:
                break
        
        # Normalize community IDs
        unique_labels = sorted(set(labels.values()))
        label_to_community = {l: i for i, l in enumerate(unique_labels)}
        
        return {ent: label_to_community[labels[ent]] for ent in entities}
    
    def compute_centrality(self, method: str = 'pagerank', 
                          damping: float = 0.85, iterations: int = 20) -> Dict[str, float]:
        """
        Compute centrality measures for entities.
        Supports: pagerank, degree, betweenness (approximate)
        """
        cursor = self.conn.cursor()
        
        # Get all entities
        cursor.execute('SELECT id FROM entities')
        entities = [row['id'] for row in cursor.fetchall()]
        n = len(entities)
        
        if n == 0:
            return {}
        
        # Build adjacency list
        cursor.execute('SELECT source_id, target_id FROM relations')
        adj = defaultdict(set)
        out_degree = defaultdict(int)
        
        for row in cursor.fetchall():
            adj[row['target_id']].add(row['source_id'])  # Incoming links
            out_degree[row['source_id']] += 1
        
        if method == 'degree':
            # Degree centrality
            centrality = {}
            for entity in entities:
                in_degree = len(adj.get(entity, set()))
                out_degree_count = out_degree.get(entity, 0)
                centrality[entity] = (in_degree + out_degree_count) / (2 * (n - 1)) if n > 1 else 0
            return centrality
        
        elif method == 'pagerank':
            # PageRank
            scores = {ent: 1.0 / n for ent in entities}
            
            for _ in range(iterations):
                new_scores = {}
                for entity in entities:
                    incoming = adj.get(entity, set())
                    rank_sum = sum(scores[src] / out_degree.get(src, 1) for src in incoming)
                    new_scores[entity] = (1 - damping) / n + damping * rank_sum
                scores = new_scores
            
            # Normalize
            total = sum(scores.values())
            return {ent: s / total for ent, s in scores.items()} if total > 0 else scores
        
        elif method == 'betweenness':
            # Approximate betweenness (sample-based for large graphs)
            centrality = {ent: 0.0 for ent in entities}
            sample_size = min(100, n)
            import random
            sample = random.sample(entities, sample_size) if sample_size < n else entities
            
            for source in sample:
                # BFS from source
                stack = []
                predecessors = defaultdict(list)
                distances = {source: 0}
                sigma = {source: 1}
                queue = deque([source])
                
                while queue:
                    v = queue.popleft()
                    stack.append(v)
                    
                    for w in adj.get(v, set()) | {u for u, outs in adj.items() if v in outs}:
                        if w not in distances:
                            distances[w] = distances[v] + 1
                            queue.append(w)
                        
                        if distances[w] == distances[v] + 1:
                            sigma[w] = sigma.get(w, 0) + sigma.get(v, 0)
                            predecessors[w].append(v)
                
                # Back-propagation
                delta = {ent: 0.0 for ent in entities}
                while stack:
                    w = stack.pop()
                    for v in predecessors[w]:
                        delta[v] += (sigma.get(v, 0) / max(sigma.get(w, 1), 1)) * (1 + delta[w])
                    if w != source:
                        centrality[w] += delta[w]
            
            # Normalize
            scale = 2.0 / ((n - 1) * (n - 2)) if n > 2 else 1.0
            return {ent: c * scale for ent, c in centrality.items()}
        
        return {}
    
    def get_entity_types(self) -> List[Tuple[str, int]]:
        """Get all entity types with counts."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT type, COUNT(*) as count FROM entities GROUP BY type ORDER BY count DESC')
        return [(row['type'], row['count']) for row in cursor.fetchall()]
    
    def get_relation_types(self) -> List[Tuple[str, int]]:
        """Get all relation types with counts."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT type, COUNT(*) as count FROM relations GROUP BY type ORDER BY count DESC')
        return [(row['type'], row['count']) for row in cursor.fetchall()]
    
    def get_subgraph(self, entity_ids: List[str]) -> Dict[str, Any]:
        """
        Extract a subgraph containing specified entities and their relations.
        """
        cursor = self.conn.cursor()
        
        # Get entities
        placeholders = ','.join('?' * len(entity_ids))
        cursor.execute(f'SELECT * FROM entities WHERE id IN ({placeholders})', entity_ids)
        
        nodes = []
        for row in cursor.fetchall():
            nodes.append({
                'id': row['id'],
                'name': row['name'],
                'type': row['type'],
                'confidence': row['confidence']
            })
        
        # Get relations between these entities
        cursor.execute(f'''
            SELECT * FROM relations 
            WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
        ''', entity_ids + entity_ids)
        
        edges = []
        for row in cursor.fetchall():
            edges.append({
                'id': row['id'],
                'source': row['source_id'],
                'target': row['target_id'],
                'type': row['type'],
                'confidence': row['confidence']
            })
        
        return {'nodes': nodes, 'edges': edges}
    
    def export_graph(self, format: str = 'json') -> str:
        """Export entire graph in various formats."""
        cursor = self.conn.cursor()
        
        if format == 'json':
            cursor.execute('SELECT * FROM entities')
            entities = []
            for row in cursor.fetchall():
                entities.append({
                    'id': row['id'],
                    'name': row['name'],
                    'type': row['type'],
                    'aliases': json.loads(row['aliases']),
                    'properties': json.loads(row['properties']),
                    'confidence': row['confidence']
                })
            
            cursor.execute('SELECT * FROM relations')
            relations = []
            for row in cursor.fetchall():
                relations.append({
                    'id': row['id'],
                    'source': row['source_id'],
                    'target': row['target_id'],
                    'type': row['type'],
                    'properties': json.loads(row['properties']),
                    'confidence': row['confidence'],
                    'evidence': json.loads(row['evidence'])
                })
            
            return json.dumps({'entities': entities, 'relations': relations}, indent=2)
        
        elif format == 'gexf':
            # GEXF format for Gephi
            xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
            xml_parts.append('<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">')
            xml_parts.append('<graph mode="static" defaultedgetype="directed">')
            
            # Nodes
            xml_parts.append('<nodes>')
            cursor.execute('SELECT id, name, type, confidence FROM entities')
            for row in cursor.fetchall():
                xml_parts.append(f'''<node id="{row['id']}" label="{row['name']}">
                    <attvalues>
                        <attvalue for="type" value="{row['type']}"/>
                        <attvalue for="confidence" value="{row['confidence']}"/>
                    </attvalues>
                </node>''')
            xml_parts.append('</nodes>')
            
            # Edges
            xml_parts.append('<edges>')
            cursor.execute('SELECT id, source_id, target_id, type FROM relations')
            for row in cursor.fetchall():
                xml_parts.append(f'''<edge id="{row['id']}" source="{row['source_id']}" 
                    target="{row['target_id']}" label="{row['type']}"/>''')
            xml_parts.append('</edges>')
            
            xml_parts.append('</graph></gexf>')
            return '\n'.join(xml_parts)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        cursor.execute('SELECT COUNT(*) as count FROM entities')
        stats['total_entities'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM relations')
        stats['total_relations'] = cursor.fetchone()['count']
        
        stats['entity_types'] = self.get_entity_types()
        stats['relation_types'] = self.get_relation_types()
        
        # Density
        n = stats['total_entities']
        max_edges = n * (n - 1) if n > 1 else 0
        stats['density'] = stats['total_relations'] / max_edges if max_edges > 0 else 0
        
        # Average degree
        cursor.execute('SELECT AVG(cnt) FROM (SELECT COUNT(*) as cnt FROM relations GROUP BY source_id)')
        row = cursor.fetchone()
        stats['avg_out_degree'] = row[0] if row[0] else 0
        
        return stats
    
    def merge_entities(self, entity_id_1: str, entity_id_2: str, keep_id: str = None) -> str:
        """
        Merge two entities, keeping one and updating all relations.
        Returns the ID of the kept entity.
        """
        if keep_id is None:
            keep_id = entity_id_1
        
        other_id = entity_id_2 if keep_id == entity_id_1 else entity_id_1
        
        cursor = self.conn.cursor()
        
        # Get both entities
        cursor.execute('SELECT * FROM entities WHERE id IN (?, ?)', (entity_id_1, entity_id_2))
        rows = cursor.fetchall()
        if len(rows) != 2:
            raise ValueError("Both entities must exist")
        
        entities = {row['id']: row for row in rows}
        
        # Merge aliases
        merged_aliases = set(json.loads(entities[keep_id]['aliases']))
        merged_aliases.update(json.loads(entities[other_id]['aliases']))
        
        # Merge properties
        merged_properties = json.loads(entities[keep_id]['properties'])
        merged_properties.update(json.loads(entities[other_id]['properties']))
        
        # Update kept entity
        cursor.execute('''
            UPDATE entities 
            SET aliases = ?, properties = ?, confidence = ?
            WHERE id = ?
        ''', (json.dumps(list(merged_aliases)), json.dumps(merged_properties),
              (entities[keep_id]['confidence'] + entities[other_id]['confidence']) / 2,
              keep_id))
        
        # Update relations pointing to other entity
        cursor.execute('UPDATE relations SET source_id = ? WHERE source_id = ?', 
                      (keep_id, other_id))
        cursor.execute('UPDATE relations SET target_id = ? WHERE target_id = ?', 
                      (keep_id, other_id))
        
        # Delete duplicate relations
        cursor.execute('''
            DELETE FROM relations WHERE rowid NOT IN (
                SELECT MIN(rowid) FROM relations GROUP BY source_id, target_id, type
            )
        ''')
        
        # Delete other entity
        cursor.execute('DELETE FROM entities WHERE id = ?', (other_id,))
        
        self.conn.commit()
        return keep_id
    
    def close(self):
        """Close database connection."""
        self.conn.close()


if __name__ == '__main__':
    # Example usage
    graph = KnowledgeGraph('/tmp/test_graph.db')
    
    # Process some text
    text = """
    John Smith works at Google Inc in Mountain View.
    Google Inc was founded by Larry Page.
    John Smith knows Jane Doe who works at Apple Inc.
    """
    
    entities, relations = graph.process_text(text, source_id="doc1")
    
    print(f"Extracted {len(entities)} entities:")
    for e in entities:
        print(f"  - {e.name} ({e.entity_type})")
    
    print(f"\nExtracted {len(relations)} relations:")
    for r in relations:
        print(f"  - {r.source_id} --[{r.relation_type}]--> {r.target_id}")
    
    # Get stats
    stats = graph.get_stats()
    print(f"\nGraph stats: {stats}")
    
    # Find communities
    communities = graph.detect_communities()
    print(f"Detected {len(set(communities.values()))} communities")
    
    # Compute centrality
    centrality = graph.compute_centrality('pagerank')
    top_entities = sorted(centrality.items(), key=lambda x: -x[1])[:5]
    print(f"Top entities by PageRank: {top_entities}")
    
    graph.close()
