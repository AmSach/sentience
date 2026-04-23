"""
Knowledge Vault - Obsidian-like note management with bi-directional linking.
SQLite-backed markdown notes with tags, graph view, and full-text search.
"""

import sqlite3
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set, Tuple
from dataclasses import dataclass, field, asdict
import unicodedata
import uuid


@dataclass
class Note:
    """Represents a markdown note in the vault."""
    id: str
    title: str
    content: str
    tags: Set[str] = field(default_factory=set)
    links: Set[str] = field(default_factory=set)
    backlinks: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'tags': list(self.tags),
            'links': list(self.links),
            'backlinks': list(self.backlinks),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Note':
        return cls(
            id=data['id'],
            title=data['title'],
            content=data['content'],
            tags=set(data.get('tags', [])),
            links=set(data.get('links', [])),
            backlinks=set(data.get('backlinks', [])),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            metadata=data.get('metadata', {})
        )


@dataclass
class SearchResult:
    """Represents a search result with relevance score."""
    note: Note
    score: float
    highlights: List[Tuple[int, int]] = field(default_factory=list)


class KnowledgeVault:
    """
    Obsidian-like knowledge vault with:
    - Markdown notes with frontmatter
    - Bi-directional linking [[note-name]]
    - Tag system #tag
    - Graph view generation
    - Full-text search with SQLite FTS5
    """
    
    # Pattern for wiki-style links [[note-name]]
    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    # Pattern for tags #tag
    TAG_PATTERN = re.compile(r'(?<!\w)#[\w/\-]+')
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema with FTS5 for full-text search."""
        cursor = self.conn.cursor()
        
        # Main notes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # Tags table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                count INTEGER DEFAULT 0
            )
        ''')
        
        # Note-tags junction table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS note_tags (
                note_id TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (note_id, tag_id),
                FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        ''')
        
        # Links table (forward links)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                link_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES notes(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES notes(id) ON DELETE CASCADE,
                UNIQUE(source_id, target_id)
            )
        ''')
        
        # FTS5 virtual table for full-text search
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                id,
                title,
                content,
                content='notes',
                content_rowid='rowid'
            )
        ''')
        
        # Triggers to keep FTS in sync
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                INSERT INTO notes_fts(rowid, id, title, content)
                VALUES (new.rowid, new.id, new.title, new.content);
            END
        ''')
        
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, id, title, content)
                VALUES('delete', old.rowid, old.id, old.title, old.content);
            END
        ''')
        
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, id, title, content)
                VALUES('delete', old.rowid, old.id, old.title, old.content);
                INSERT INTO notes_fts(rowid, id, title, content)
                VALUES (new.rowid, new.id, new.title, new.content);
            END
        ''')
        
        self.conn.commit()
    
    def _generate_id(self, title: str) -> str:
        """Generate a unique ID for a note from title."""
        # Slugify the title
        slug = unicodedata.normalize('NFKD', title.lower())
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug).strip('-')
        
        # Add short hash for uniqueness
        hash_part = hashlib.md5(f"{title}{datetime.utcnow().isoformat()}".encode()).hexdigest()[:8]
        return f"{slug}-{hash_part}"
    
    def _extract_tags(self, content: str) -> Set[str]:
        """Extract hashtags from content."""
        tags = set()
        for match in self.TAG_PATTERN.finditer(content):
            tag = match.group(0)[1:]  # Remove # prefix
            tags.add(tag.lower())
        return tags
    
    def _extract_links(self, content: str) -> Set[str]:
        """Extract wiki-style links from content."""
        links = set()
        for match in self.WIKI_LINK_PATTERN.finditer(content):
            link = match.group(1).strip()
            links.add(link.lower())
        return links
    
    def _resolve_link(self, link: str) -> Optional[str]:
        """Resolve a link text to a note ID."""
        cursor = self.conn.cursor()
        
        # Try exact title match first
        cursor.execute('SELECT id FROM notes WHERE LOWER(title) = ?', (link.lower(),))
        row = cursor.fetchone()
        if row:
            return row['id']
        
        # Try partial match
        cursor.execute('SELECT id FROM notes WHERE LOWER(title) LIKE ?', (f'%{link.lower()}%',))
        row = cursor.fetchone()
        if row:
            return row['id']
        
        # Try ID match
        cursor.execute('SELECT id FROM notes WHERE id = ?', (link,))
        row = cursor.fetchone()
        if row:
            return row['id']
        
        return None
    
    def _update_tags(self, note_id: str, tags: Set[str]):
        """Update tags for a note."""
        cursor = self.conn.cursor()
        
        # Remove existing tags
        cursor.execute('DELETE FROM note_tags WHERE note_id = ?', (note_id,))
        
        # Decrement old tag counts
        cursor.execute('''
            UPDATE tags SET count = count - 1 
            WHERE id IN (SELECT tag_id FROM note_tags WHERE note_id = ?)
        ''', (note_id,))
        
        # Add new tags
        for tag in tags:
            cursor.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
            cursor.execute('SELECT id FROM tags WHERE name = ?', (tag,))
            tag_id = cursor.fetchone()['id']
            cursor.execute('INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)',
                          (note_id, tag_id))
            cursor.execute('UPDATE tags SET count = count + 1 WHERE name = ?', (tag,))
        
        self.conn.commit()
    
    def _update_links(self, note_id: str, links: Set[str]):
        """Update forward links and backlinks."""
        cursor = self.conn.cursor()
        
        # Remove existing forward links
        cursor.execute('DELETE FROM links WHERE source_id = ?', (note_id,))
        
        # Add new forward links
        for link in links:
            target_id = self._resolve_link(link)
            if target_id and target_id != note_id:
                cursor.execute('''
                    INSERT OR IGNORE INTO links (source_id, target_id, link_text)
                    VALUES (?, ?, ?)
                ''', (note_id, target_id, link))
        
        self.conn.commit()
    
    def create_note(self, title: str, content: str, metadata: Dict = None) -> Note:
        """Create a new note with automatic tag and link extraction."""
        note_id = self._generate_id(title)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        cursor = self.conn.cursor()
        
        # Check for duplicate content
        cursor.execute('SELECT id FROM notes WHERE content_hash = ?', (content_hash,))
        if cursor.fetchone():
            raise ValueError(f"Note with identical content already exists")
        
        # Insert note
        cursor.execute('''
            INSERT INTO notes (id, title, content, content_hash, metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (note_id, title, content, content_hash, json.dumps(metadata or {})))
        
        self.conn.commit()
        
        # Extract and store tags
        tags = self._extract_tags(content)
        self._update_tags(note_id, tags)
        
        # Extract and store links
        links = self._extract_links(content)
        self._update_links(note_id, links)
        
        return self.get_note(note_id)
    
    def get_note(self, note_id: str) -> Optional[Note]:
        """Retrieve a note by ID with tags and links."""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT * FROM notes WHERE id = ?', (note_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        # Get tags
        cursor.execute('''
            SELECT t.name FROM tags t
            JOIN note_tags nt ON t.id = nt.tag_id
            WHERE nt.note_id = ?
        ''', (note_id,))
        tags = {r['name'] for r in cursor.fetchall()}
        
        # Get forward links
        cursor.execute('SELECT target_id FROM links WHERE source_id = ?', (note_id,))
        links = {r['target_id'] for r in cursor.fetchall()}
        
        # Get backlinks
        cursor.execute('SELECT source_id FROM links WHERE target_id = ?', (note_id,))
        backlinks = {r['source_id'] for r in cursor.fetchall()}
        
        return Note(
            id=row['id'],
            title=row['title'],
            content=row['content'],
            tags=tags,
            links=links,
            backlinks=backlinks,
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            metadata=json.loads(row['metadata'])
        )
    
    def update_note(self, note_id: str, title: str = None, content: str = None, 
                    metadata: Dict = None) -> Optional[Note]:
        """Update a note's content, recalculating tags and links."""
        cursor = self.conn.cursor()
        
        # Get existing note
        existing = self.get_note(note_id)
        if not existing:
            return None
        
        # Update fields
        new_title = title if title is not None else existing.title
        new_content = content if content is not None else existing.content
        new_metadata = metadata if metadata is not None else existing.metadata
        new_hash = hashlib.sha256(new_content.encode()).hexdigest()
        
        cursor.execute('''
            UPDATE notes 
            SET title = ?, content = ?, content_hash = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (new_title, new_content, new_hash, json.dumps(new_metadata), note_id))
        
        self.conn.commit()
        
        # Update tags and links
        tags = self._extract_tags(new_content)
        self._update_tags(note_id, tags)
        
        links = self._extract_links(new_content)
        self._update_links(note_id, links)
        
        return self.get_note(note_id)
    
    def delete_note(self, note_id: str) -> bool:
        """Delete a note and clean up references."""
        cursor = self.conn.cursor()
        
        # Update tag counts
        cursor.execute('''
            UPDATE tags SET count = count - 1 
            WHERE id IN (SELECT tag_id FROM note_tags WHERE note_id = ?)
        ''', (note_id,))
        
        # Remove links
        cursor.execute('DELETE FROM links WHERE source_id = ? OR target_id = ?', 
                      (note_id, note_id))
        
        # Delete note (cascade will handle note_tags)
        cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        
        self.conn.commit()
        return cursor.rowcount > 0
    
    def search(self, query: str, limit: int = 50, offset: int = 0) -> List[SearchResult]:
        """
        Full-text search using SQLite FTS5.
        Supports boolean operators, phrase queries, and ranking.
        """
        cursor = self.conn.cursor()
        
        # Escape special FTS5 characters and build query
        fts_query = query.replace('"', '""')
        
        # Search with ranking
        cursor.execute('''
            SELECT n.id, n.title, n.content, n.created_at, n.updated_at, n.metadata,
                   bm25(notes_fts) as score
            FROM notes n
            JOIN notes_fts fts ON n.id = fts.id
            WHERE notes_fts MATCH ?
            ORDER BY score
            LIMIT ? OFFSET ?
        ''', (fts_query, limit, offset))
        
        results = []
        for row in cursor.fetchall():
            note = Note(
                id=row['id'],
                title=row['title'],
                content=row['content'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                metadata=json.loads(row['metadata'])
            )
            
            # Calculate highlights (simple implementation)
            highlights = []
            query_terms = query.lower().split()
            content_lower = note.content.lower()
            for term in query_terms:
                idx = content_lower.find(term)
                if idx != -1:
                    highlights.append((idx, idx + len(term)))
            
            results.append(SearchResult(
                note=note,
                score=-row['score'],  # BM25 returns negative scores
                highlights=highlights
            ))
        
        return results
    
    def search_by_tag(self, tags: List[str], limit: int = 50) -> List[Note]:
        """Search notes by tags (AND logic)."""
        cursor = self.conn.cursor()
        
        placeholders = ','.join('?' * len(tags))
        cursor.execute(f'''
            SELECT DISTINCT n.id, n.title, n.content, n.created_at, n.updated_at, n.metadata
            FROM notes n
            JOIN note_tags nt ON n.id = nt.note_id
            JOIN tags t ON nt.tag_id = t.id
            WHERE t.name IN ({placeholders})
            GROUP BY n.id
            HAVING COUNT(DISTINCT t.id) = ?
            ORDER BY n.updated_at DESC
            LIMIT ?
        ''', (*tags, len(tags), limit))
        
        notes = []
        for row in cursor.fetchall():
            notes.append(Note(
                id=row['id'],
                title=row['title'],
                content=row['content'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                metadata=json.loads(row['metadata'])
            ))
        
        return notes
    
    def get_all_tags(self) -> List[Tuple[str, int]]:
        """Get all tags with their usage counts."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT name, count FROM tags WHERE count > 0 ORDER BY count DESC')
        return [(row['name'], row['count']) for row in cursor.fetchall()]
    
    def get_linked_notes(self, note_id: str, depth: int = 2) -> Dict[str, List[str]]:
        """
        Get all notes linked to/from a note up to specified depth.
        Returns adjacency list for graph visualization.
        """
        cursor = self.conn.cursor()
        visited = set()
        adjacency = {}
        
        def traverse(current_id: str, current_depth: int):
            if current_depth > depth or current_id in visited:
                return
            visited.add(current_id)
            
            # Get forward links
            cursor.execute('SELECT target_id FROM links WHERE source_id = ?', (current_id,))
            forward = [r['target_id'] for r in cursor.fetchall()]
            
            # Get backlinks
            cursor.execute('SELECT source_id FROM links WHERE target_id = ?', (current_id,))
            backward = [r['source_id'] for r in cursor.fetchall()]
            
            all_linked = list(set(forward + backward))
            adjacency[current_id] = all_linked
            
            for linked_id in all_linked:
                traverse(linked_id, current_depth + 1)
        
        traverse(note_id, 0)
        return adjacency
    
    def get_graph(self) -> Dict[str, Dict]:
        """
        Generate full graph representation for visualization.
        Returns nodes and edges suitable for D3.js or similar.
        """
        cursor = self.conn.cursor()
        
        # Get all notes as nodes
        cursor.execute('SELECT id, title, created_at FROM notes')
        nodes = []
        for row in cursor.fetchall():
            # Get tags for this note
            cursor.execute('''
                SELECT t.name FROM tags t
                JOIN note_tags nt ON t.id = nt.tag_id
                WHERE nt.note_id = ?
            ''', (row['id'],))
            tags = [r['name'] for r in cursor.fetchall()]
            
            nodes.append({
                'id': row['id'],
                'title': row['title'],
                'created': row['created_at'],
                'tags': tags,
                'size': 1  # Will be updated based on connections
            })
        
        # Get all links as edges
        cursor.execute('SELECT source_id, target_id FROM links')
        edges = []
        link_counts = {}
        
        for row in cursor.fetchall():
            edges.append({
                'source': row['source_id'],
                'target': row['target_id']
            })
            link_counts[row['source_id']] = link_counts.get(row['source_id'], 0) + 1
            link_counts[row['target_id']] = link_counts.get(row['target_id'], 0) + 1
        
        # Update node sizes based on connections
        for node in nodes:
            node['size'] = link_counts.get(node['id'], 1)
        
        return {
            'nodes': nodes,
            'edges': edges,
            'stats': {
                'total_notes': len(nodes),
                'total_links': len(edges),
                'orphan_notes': sum(1 for n in nodes if n['id'] not in link_counts)
            }
        }
    
    def get_recent_notes(self, limit: int = 20) -> List[Note]:
        """Get recently updated notes."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, title, content, created_at, updated_at, metadata
            FROM notes
            ORDER BY updated_at DESC
            LIMIT ?
        ''', (limit,))
        
        notes = []
        for row in cursor.fetchall():
            notes.append(Note(
                id=row['id'],
                title=row['title'],
                content=row['content'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                metadata=json.loads(row['metadata'])
            ))
        
        return notes
    
    def export_note(self, note_id: str, format: str = 'markdown') -> str:
        """Export a note to various formats."""
        note = self.get_note(note_id)
        if not note:
            raise ValueError(f"Note not found: {note_id}")
        
        if format == 'markdown':
            # Generate frontmatter
            frontmatter = ['---']
            frontmatter.append(f'id: {note.id}')
            frontmatter.append(f'title: {note.title}')
            frontmatter.append(f'created: {note.created_at.isoformat()}')
            frontmatter.append(f'updated: {note.updated_at.isoformat()}')
            if note.tags:
                frontmatter.append(f'tags: [{", ".join(sorted(note.tags))}]')
            for key, value in note.metadata.items():
                frontmatter.append(f'{key}: {value}')
            frontmatter.append('---')
            frontmatter.append('')
            
            return '\n'.join(frontmatter) + note.content
        
        elif format == 'json':
            return json.dumps(note.to_dict(), indent=2)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def import_note(self, content: str, format: str = 'markdown') -> Note:
        """Import a note from various formats."""
        if format == 'markdown':
            # Parse frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1].strip()
                    body = parts[2].strip()
                    
                    metadata = {}
                    title = None
                    tags = set()
                    
                    for line in frontmatter.split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            if key == 'title':
                                title = value
                            elif key == 'tags':
                                # Parse tag list
                                value = value.strip('[]')
                                tags = {t.strip() for t in value.split(',') if t.strip()}
                            else:
                                metadata[key] = value
                    
                    if not title:
                        # Extract title from first heading
                        for line in body.split('\n'):
                            if line.startswith('#'):
                                title = line.lstrip('#').strip()
                                break
                        if not title:
                            title = 'Untitled'
                    
                    return self.create_note(title, body, metadata)
            
            # No frontmatter, treat as plain markdown
            title = None
            for line in content.split('\n'):
                if line.startswith('#'):
                    title = line.lstrip('#').strip()
                    break
            if not title:
                title = 'Untitled'
            
            return self.create_note(title, content)
        
        elif format == 'json':
            data = json.loads(content)
            note = self.create_note(
                data['title'],
                data['content'],
                data.get('metadata', {})
            )
            return note
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_stats(self) -> Dict:
        """Get vault statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        cursor.execute('SELECT COUNT(*) as count FROM notes')
        stats['total_notes'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM tags WHERE count > 0')
        stats['total_tags'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM links')
        stats['total_links'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT name, count FROM tags ORDER BY count DESC LIMIT 10')
        stats['top_tags'] = [(r['name'], r['count']) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT n.id, n.title, COUNT(l.id) as link_count
            FROM notes n
            LEFT JOIN links l ON n.id = l.target_id
            GROUP BY n.id
            ORDER BY link_count DESC
            LIMIT 5
        ''')
        stats['most_linked'] = [(r['title'], r['link_count']) for r in cursor.fetchall()]
        
        return stats
    
    def close(self):
        """Close database connection."""
        self.conn.close()


# Convenience function for creating vault from directory of markdown files
def import_from_directory(vault: KnowledgeVault, directory: str) -> int:
    """Import all markdown files from a directory."""
    path = Path(directory)
    count = 0
    
    for md_file in path.glob('**/*.md'):
        try:
            content = md_file.read_text()
            vault.import_note(content, format='markdown')
            count += 1
        except Exception as e:
            print(f"Error importing {md_file}: {e}")
    
    return count


if __name__ == '__main__':
    # Example usage
    vault = KnowledgeVault('/tmp/test_vault.db')
    
    # Create some notes
    note1 = vault.create_note(
        "Introduction to Memory Systems",
        "# Introduction to Memory Systems\n\n"
        "Memory systems are crucial for #AI and #cognition.\n\n"
        "See also [[Knowledge Graphs]] and [[Embedding Models]]."
    )
    
    note2 = vault.create_note(
        "Knowledge Graphs",
        "# Knowledge Graphs\n\n"
        "Knowledge graphs represent #information as nodes and edges.\n\n"
        "Related to [[Introduction to Memory Systems]]."
    )
    
    note3 = vault.create_note(
        "Embedding Models",
        "# Embedding Models\n\n"
        "Embeddings convert text to vectors for #semantic #search.\n\n"
        "References [[Introduction to Memory Systems]]."
    )
    
    # Search
    results = vault.search("memory")
    print(f"Found {len(results)} results for 'memory'")
    
    # Get graph
    graph = vault.get_graph()
    print(f"Graph has {graph['stats']['total_notes']} nodes and {graph['stats']['total_links']} edges")
    
    # Get stats
    stats = vault.get_stats()
    print(f"Vault stats: {stats}")
    
    vault.close()
