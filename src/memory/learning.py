"""
Learning System - Interaction logging, pattern detection, and preference learning.
Tracks user interactions, detects patterns, learns from errors and successes.
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict, Counter
import re


@dataclass
class Interaction:
    """Represents a user interaction."""
    id: str
    timestamp: datetime
    interaction_type: str  # 'query', 'command', 'feedback', 'correction'
    input_text: str
    output_text: str
    context: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
    user_id: str = "default"
    session_id: str = ""
    outcome: str = "unknown"  # 'success', 'failure', 'partial', 'unknown'
    feedback_score: Optional[float] = None
    feedback_text: Optional[str] = None


@dataclass
class Pattern:
    """Represents a detected pattern in user behavior."""
    id: str
    pattern_type: str  # 'temporal', 'behavioral', 'preference', 'error'
    description: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    confidence: float
    conditions: Dict = field(default_factory=dict)
    actions: Dict = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)


@dataclass
class Preference:
    """Represents a learned user preference."""
    id: str
    category: str  # 'style', 'format', 'language', 'verbosity', etc.
    key: str
    value: Any
    confidence: float
    source: str  # 'explicit', 'implicit', 'inferred'
    evidence: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ErrorRecord:
    """Represents an error learning record."""
    id: str
    timestamp: datetime
    error_type: str
    error_message: str
    context: Dict
    resolution: Optional[str] = None
    resolved: bool = False
    occurrence_count: int = 1
    last_occurrence: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SuccessRecord:
    """Represents a success tracking record."""
    id: str
    timestamp: datetime
    task_type: str
    task_description: str
    approach: str
    metrics: Dict
    context: Dict
    reproducibility_score: float = 1.0


class LearningSystem:
    """
    Comprehensive learning system with:
    - Interaction logging and analysis
    - Pattern detection (temporal, behavioral, preference)
    - Preference learning (explicit and implicit)
    - Error learning and resolution tracking
    - Success tracking and best practices
    """
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._load_counters()
        
    def _init_db(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()
        
        # Interactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                interaction_type TEXT NOT NULL,
                input_text TEXT NOT NULL,
                output_text TEXT,
                context TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                user_id TEXT DEFAULT 'default',
                session_id TEXT DEFAULT '',
                outcome TEXT DEFAULT 'unknown',
                feedback_score REAL,
                feedback_text TEXT,
                input_hash TEXT,
                keywords TEXT DEFAULT '[]'
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_interactions_type ON interactions(interaction_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_interactions_outcome ON interactions(outcome)')
        
        # Patterns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patterns (
                id TEXT PRIMARY KEY,
                pattern_type TEXT NOT NULL,
                description TEXT NOT NULL,
                occurrences INTEGER DEFAULT 1,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence REAL DEFAULT 0.5,
                conditions TEXT DEFAULT '{}',
                actions TEXT DEFAULT '{}',
                examples TEXT DEFAULT '[]'
            )
        ''')
        
        # Preferences table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS preferences (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT DEFAULT 'implicit',
                evidence TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category, key)
            )
        ''')
        
        # Errors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS errors (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                context TEXT DEFAULT '{}',
                resolution TEXT,
                resolved INTEGER DEFAULT 0,
                occurrence_count INTEGER DEFAULT 1,
                last_occurrence TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Successes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS successes (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                task_type TEXT NOT NULL,
                task_description TEXT NOT NULL,
                approach TEXT NOT NULL,
                metrics TEXT DEFAULT '{}',
                context TEXT DEFAULT '{}',
                reproducibility_score REAL DEFAULT 1.0
            )
        ''')
        
        # Pattern-interaction links
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pattern_interactions (
                pattern_id TEXT NOT NULL,
                interaction_id TEXT NOT NULL,
                PRIMARY KEY (pattern_id, interaction_id),
                FOREIGN KEY (pattern_id) REFERENCES patterns(id) ON DELETE CASCADE,
                FOREIGN KEY (interaction_id) REFERENCES interactions(id) ON DELETE CASCADE
            )
        ''')
        
        # Counters
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        ''')
        
        self.conn.commit()
    
    def _load_counters(self):
        """Load ID counters."""
        cursor = self.conn.cursor()
        # Use full counter names that match the prefix used in _generate_id
        for name, full_name in [('interaction', 'int'), ('pattern', 'pat'), 
                                ('preference', 'pref'), ('error', 'err'), ('success', 'suc')]:
            cursor.execute('SELECT value FROM counters WHERE name = ?', (name,))
            row = cursor.fetchone()
            setattr(self, f'_{full_name}_counter', row['value'] if row else 0)
    
    def _save_counter(self, name: str):
        """Save a counter value."""
        cursor = self.conn.cursor()
        value = getattr(self, f'_{name}_counter')
        cursor.execute('INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)',
                      (name, value))
        self.conn.commit()
    
    def _generate_id(self, prefix: str) -> str:
        """Generate a unique ID."""
        counter_name = prefix.rstrip('_')
        current = getattr(self, f'_{counter_name}_counter')
        setattr(self, f'_{counter_name}_counter', current + 1)
        self._save_counter(counter_name)
        return f"{prefix}{current + 1:08d}"
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        # Simple keyword extraction
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                      'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'again', 'further', 'then', 'once',
                      'here', 'there', 'when', 'where', 'why', 'how', 'all',
                      'each', 'few', 'more', 'most', 'other', 'some', 'such',
                      'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
                      'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
                      'until', 'while', 'this', 'that', 'these', 'those', 'i',
                      'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
                      'who', 'whom', 'this', 'that', 'these', 'those'}
        
        # Tokenize and filter
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in stop_words]
        
        # Return top keywords by frequency
        word_counts = Counter(keywords)
        return [w for w, _ in word_counts.most_common(10)]
    
    def log_interaction(self, interaction: Interaction) -> str:
        """Log an interaction to the database."""
        cursor = self.conn.cursor()
        
        interaction_id = interaction.id or self._generate_id('int_')
        input_hash = hashlib.sha256(interaction.input_text.encode()).hexdigest()[:16]
        keywords = self._extract_keywords(interaction.input_text + " " + (interaction.output_text or ""))
        
        cursor.execute('''
            INSERT INTO interactions (
                id, timestamp, interaction_type, input_text, output_text,
                context, metadata, user_id, session_id, outcome,
                feedback_score, feedback_text, input_hash, keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            interaction_id,
            interaction.timestamp.isoformat(),
            interaction.interaction_type,
            interaction.input_text,
            interaction.output_text,
            json.dumps(interaction.context),
            json.dumps(interaction.metadata),
            interaction.user_id,
            interaction.session_id,
            interaction.outcome,
            interaction.feedback_score,
            interaction.feedback_text,
            input_hash,
            json.dumps(keywords)
        ))
        
        self.conn.commit()
        
        # Update patterns and preferences
        self._update_patterns_from_interaction(interaction_id)
        
        return interaction_id
    
    def get_interaction(self, interaction_id: str) -> Optional[Interaction]:
        """Get an interaction by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM interactions WHERE id = ?', (interaction_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return Interaction(
            id=row['id'],
            timestamp=datetime.fromisoformat(row['timestamp']),
            interaction_type=row['interaction_type'],
            input_text=row['input_text'],
            output_text=row['output_text'],
            context=json.loads(row['context']),
            metadata=json.loads(row['metadata']),
            user_id=row['user_id'],
            session_id=row['session_id'],
            outcome=row['outcome'],
            feedback_score=row['feedback_score'],
            feedback_text=row['feedback_text']
        )
    
    def get_recent_interactions(self, limit: int = 100, user_id: str = None,
                                interaction_type: str = None) -> List[Interaction]:
        """Get recent interactions, optionally filtered."""
        cursor = self.conn.cursor()
        
        query = 'SELECT * FROM interactions WHERE 1=1'
        params = []
        
        if user_id:
            query += ' AND user_id = ?'
            params.append(user_id)
        
        if interaction_type:
            query += ' AND interaction_type = ?'
            params.append(interaction_type)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        interactions = []
        for row in cursor.fetchall():
            interactions.append(Interaction(
                id=row['id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                interaction_type=row['interaction_type'],
                input_text=row['input_text'],
                output_text=row['output_text'],
                context=json.loads(row['context']),
                metadata=json.loads(row['metadata']),
                user_id=row['user_id'],
                session_id=row['session_id'],
                outcome=row['outcome'],
                feedback_score=row['feedback_score'],
                feedback_text=row['feedback_text']
            ))
        
        return interactions
    
    def add_feedback(self, interaction_id: str, score: float, text: str = None):
        """Add feedback to an interaction."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            UPDATE interactions 
            SET feedback_score = ?, feedback_text = ?, outcome = ?
            WHERE id = ?
        ''', (score, text, 'success' if score > 0.5 else 'failure', interaction_id))
        
        self.conn.commit()
        
        # Update preferences based on feedback
        interaction = self.get_interaction(interaction_id)
        if interaction:
            self._update_preferences_from_feedback(interaction, score, text)
    
    def detect_patterns(self, time_window_hours: int = 24) -> List[Pattern]:
        """
        Detect patterns in recent interactions.
        Returns list of detected patterns.
        """
        cursor = self.conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(hours=time_window_hours)
        cursor.execute('''
            SELECT * FROM interactions 
            WHERE timestamp > ? 
            ORDER BY timestamp
        ''', (cutoff.isoformat(),))
        
        interactions = []
        for row in cursor.fetchall():
            interactions.append({
                'id': row['id'],
                'timestamp': datetime.fromisoformat(row['timestamp']),
                'type': row['interaction_type'],
                'input': row['input_text'],
                'output': row['output_text'],
                'outcome': row['outcome'],
                'keywords': json.loads(row['keywords']),
                'context': json.loads(row['context'])
            })
        
        patterns = []
        
        # Detect temporal patterns
        temporal_patterns = self._detect_temporal_patterns(interactions)
        patterns.extend(temporal_patterns)
        
        # Detect behavioral patterns
        behavioral_patterns = self._detect_behavioral_patterns(interactions)
        patterns.extend(behavioral_patterns)
        
        # Detect error patterns
        error_patterns = self._detect_error_patterns(interactions)
        patterns.extend(error_patterns)
        
        return patterns
    
    def _detect_temporal_patterns(self, interactions: List[Dict]) -> List[Pattern]:
        """Detect time-based patterns in interactions."""
        patterns = []
        
        if len(interactions) < 3:
            return patterns
        
        # Analyze hour distribution
        hour_counts = Counter(i['timestamp'].hour for i in interactions)
        peak_hours = [h for h, c in hour_counts.most_common(3) if c > len(interactions) / 6]
        
        if peak_hours:
            patterns.append(Pattern(
                id=self._generate_id('pat_'),
                pattern_type='temporal',
                description=f"User is most active during hours: {peak_hours}",
                occurrences=sum(hour_counts[h] for h in peak_hours),
                first_seen=interactions[0]['timestamp'],
                last_seen=interactions[-1]['timestamp'],
                confidence=len(peak_hours) * sum(hour_counts[h] for h in peak_hours) / len(interactions),
                conditions={'hours': peak_hours},
                actions={'suggest': 'schedule_important_tasks'}
            ))
        
        # Analyze day of week distribution
        dow_counts = Counter(i['timestamp'].strftime('%A') for i in interactions)
        peak_days = [d for d, c in dow_counts.most_common(3) if c > len(interactions) / 4]
        
        if peak_days:
            patterns.append(Pattern(
                id=self._generate_id('pat_'),
                pattern_type='temporal',
                description=f"User is most active on: {', '.join(peak_days)}",
                occurrences=sum(dow_counts[d] for d in peak_days),
                first_seen=interactions[0]['timestamp'],
                last_seen=interactions[-1]['timestamp'],
                confidence=0.7,
                conditions={'days': peak_days},
                actions={}
            ))
        
        return patterns
    
    def _detect_behavioral_patterns(self, interactions: List[Dict]) -> List[Pattern]:
        """Detect behavioral patterns in interactions."""
        patterns = []
        
        # Analyze interaction types
        type_counts = Counter(i['type'] for i in interactions)
        
        for itype, count in type_counts.most_common(3):
            if count > len(interactions) / 4:
                patterns.append(Pattern(
                    id=self._generate_id('pat_'),
                    pattern_type='behavioral',
                    description=f"User frequently performs {itype} interactions ({count} times)",
                    occurrences=count,
                    first_seen=interactions[0]['timestamp'],
                    last_seen=interactions[-1]['timestamp'],
                    confidence=count / len(interactions),
                    conditions={'interaction_type': itype},
                    actions={}
                ))
        
        # Analyze keyword patterns
        all_keywords = []
        for i in interactions:
            all_keywords.extend(i['keywords'])
        
        keyword_counts = Counter(all_keywords)
        frequent_keywords = [k for k, c in keyword_counts.most_common(5) if c > len(interactions) / 5]
        
        if frequent_keywords:
            patterns.append(Pattern(
                id=self._generate_id('pat_'),
                pattern_type='behavioral',
                description=f"User frequently discusses: {', '.join(frequent_keywords)}",
                occurrences=sum(keyword_counts[k] for k in frequent_keywords),
                first_seen=interactions[0]['timestamp'],
                last_seen=interactions[-1]['timestamp'],
                confidence=0.6,
                conditions={'keywords': frequent_keywords},
                actions={}
            ))
        
        return patterns
    
    def _detect_error_patterns(self, interactions: List[Dict]) -> List[Pattern]:
        """Detect patterns in errors and failures."""
        patterns = []
        
        failures = [i for i in interactions if i['outcome'] == 'failure']
        
        if len(failures) < 2:
            return patterns
        
        # Analyze failure keywords
        failure_keywords = []
        for f in failures:
            failure_keywords.extend(f['keywords'])
        
        keyword_counts = Counter(failure_keywords)
        common_issues = [k for k, c in keyword_counts.most_common(3) if c >= 2]
        
        if common_issues:
            patterns.append(Pattern(
                id=self._generate_id('pat_'),
                pattern_type='error',
                description=f"Common issues related to: {', '.join(common_issues)}",
                occurrences=sum(keyword_counts[k] for k in common_issues),
                first_seen=failures[0]['timestamp'],
                last_seen=failures[-1]['timestamp'],
                confidence=len(failures) / len(interactions),
                conditions={'keywords': common_issues},
                actions={'suggest': 'provide_guidance'}
            ))
        
        return patterns
    
    def _update_patterns_from_interaction(self, interaction_id: str):
        """Update patterns based on new interaction."""
        # Get similar interactions
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM interactions 
            WHERE id != ? AND input_hash = (
                SELECT input_hash FROM interactions WHERE id = ?
            )
        ''', (interaction_id, interaction_id))
        
        similar = cursor.fetchall()
        
        if similar:
            # Check for existing pattern
            cursor.execute('''
                SELECT * FROM patterns 
                WHERE pattern_type = 'behavioral' 
                AND description LIKE '%repeated query%'
            ''')
            existing = cursor.fetchone()
            
            if existing:
                # Update existing pattern
                cursor.execute('''
                    UPDATE patterns 
                    SET occurrences = occurrences + 1, last_seen = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (existing['id'],))
            else:
                # Create new pattern
                pattern_id = self._generate_id('pat_')
                cursor.execute('''
                    INSERT INTO patterns (id, pattern_type, description, occurrences, confidence)
                    VALUES (?, 'behavioral', 'Repeated similar queries', ?, 0.8)
                ''', (pattern_id, len(similar) + 1))
        
        self.conn.commit()
    
    def _update_preferences_from_feedback(self, interaction: Interaction, 
                                         score: float, text: str):
        """Update preferences based on user feedback."""
        # Analyze what aspects the user liked/disliked
        cursor = self.conn.cursor()
        
        # Extract potential preference signals from keywords
        keywords = self._extract_keywords(interaction.input_text)
        
        for keyword in keywords:
            # Check if preference exists
            cursor.execute('''
                SELECT * FROM preferences WHERE category = 'topic_preference' AND key = ?
            ''', (keyword,))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update confidence based on feedback
                old_conf = existing['confidence']
                new_conf = old_conf * 0.8 + score * 0.2
                
                cursor.execute('''
                    UPDATE preferences 
                    SET confidence = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_conf, existing['id']))
            else:
                # Create new preference
                pref_id = self._generate_id('pref_')
                cursor.execute('''
                    INSERT INTO preferences (id, category, key, value, confidence, source)
                    VALUES (?, 'topic_preference', ?, 'relevant', ?, 'implicit')
                ''', (pref_id, keyword, score))
        
        self.conn.commit()
    
    def set_preference(self, category: str, key: str, value: Any, 
                       source: str = 'explicit') -> str:
        """Explicitly set a user preference."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT * FROM preferences WHERE category = ? AND key = ?
        ''', (category, key))
        
        existing = cursor.fetchone()
        
        if existing:
            pref_id = existing['id']
            evidence = json.loads(existing['evidence'])
            evidence.append(f"Explicitly set at {datetime.utcnow().isoformat()}")
            
            cursor.execute('''
                UPDATE preferences 
                SET value = ?, confidence = 1.0, source = ?, 
                    evidence = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(value), source, json.dumps(evidence[-10:]), pref_id))
        else:
            pref_id = self._generate_id('pref_')
            cursor.execute('''
                INSERT INTO preferences (id, category, key, value, confidence, source, evidence)
                VALUES (?, ?, ?, ?, 1.0, ?, ?)
            ''', (pref_id, category, key, json.dumps(value), source, 
                  json.dumps([f"Explicitly set at {datetime.utcnow().isoformat()}"])))
        
        self.conn.commit()
        return pref_id
    
    def get_preference(self, category: str, key: str) -> Optional[Preference]:
        """Get a specific preference."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM preferences WHERE category = ? AND key = ?
        ''', (category, key))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return Preference(
            id=row['id'],
            category=row['category'],
            key=row['key'],
            value=json.loads(row['value']),
            confidence=row['confidence'],
            source=row['source'],
            evidence=json.loads(row['evidence']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
    
    def get_preferences_by_category(self, category: str) -> List[Preference]:
        """Get all preferences in a category."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM preferences WHERE category = ? ORDER BY confidence DESC
        ''', (category,))
        
        preferences = []
        for row in cursor.fetchall():
            preferences.append(Preference(
                id=row['id'],
                category=row['category'],
                key=row['key'],
                value=json.loads(row['value']),
                confidence=row['confidence'],
                source=row['source'],
                evidence=json.loads(row['evidence']),
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at'])
            ))
        
        return preferences
    
    def get_all_preferences(self) -> Dict[str, Dict[str, Any]]:
        """Get all preferences grouped by category."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM preferences ORDER BY category, key')
        
        result = defaultdict(dict)
        for row in cursor.fetchall():
            result[row['category']][row['key']] = {
                'value': json.loads(row['value']),
                'confidence': row['confidence'],
                'source': row['source']
            }
        
        return dict(result)
    
    def log_error(self, error_type: str, error_message: str, 
                  context: Dict, resolution: str = None) -> str:
        """Log an error occurrence."""
        cursor = self.conn.cursor()
        
        # Check for similar existing error
        cursor.execute('''
            SELECT * FROM errors 
            WHERE error_type = ? AND error_message = ?
        ''', (error_type, error_message))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing error
            error_id = existing['id']
            cursor.execute('''
                UPDATE errors 
                SET occurrence_count = occurrence_count + 1,
                    last_occurrence = CURRENT_TIMESTAMP,
                    resolution = COALESCE(?, resolution)
                WHERE id = ?
            ''', (resolution, error_id))
        else:
            # Create new error record
            error_id = self._generate_id('err_')
            cursor.execute('''
                INSERT INTO errors (id, error_type, error_message, context, resolution)
                VALUES (?, ?, ?, ?, ?)
            ''', (error_id, error_type, error_message, json.dumps(context), resolution))
        
        self.conn.commit()
        return error_id
    
    def resolve_error(self, error_id: str, resolution: str):
        """Mark an error as resolved with resolution."""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE errors 
            SET resolved = 1, resolution = ?
            WHERE id = ?
        ''', (resolution, error_id))
        self.conn.commit()
    
    def get_unresolved_errors(self, limit: int = 50) -> List[ErrorRecord]:
        """Get unresolved errors."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM errors 
            WHERE resolved = 0 
            ORDER BY occurrence_count DESC, last_occurrence DESC
            LIMIT ?
        ''', (limit,))
        
        errors = []
        for row in cursor.fetchall():
            errors.append(ErrorRecord(
                id=row['id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                error_type=row['error_type'],
                error_message=row['error_message'],
                context=json.loads(row['context']),
                resolution=row['resolution'],
                resolved=bool(row['resolved']),
                occurrence_count=row['occurrence_count'],
                last_occurrence=datetime.fromisoformat(row['last_occurrence'])
            ))
        
        return errors
    
    def get_error_resolution(self, error_type: str, error_message: str) -> Optional[str]:
        """Get resolution for a similar error if known."""
        cursor = self.conn.cursor()
        
        # Try exact match first
        cursor.execute('''
            SELECT resolution FROM errors 
            WHERE error_type = ? AND error_message = ? AND resolved = 1
        ''', (error_type, error_message))
        
        row = cursor.fetchone()
        if row:
            return row['resolution']
        
        # Try partial match
        cursor.execute('''
            SELECT resolution FROM errors 
            WHERE error_type = ? AND error_message LIKE ? AND resolved = 1
            ORDER BY occurrence_count DESC
            LIMIT 1
        ''', (error_type, f'%{error_message[:50]}%'))
        
        row = cursor.fetchone()
        return row['resolution'] if row else None
    
    def log_success(self, task_type: str, task_description: str, 
                    approach: str, metrics: Dict, context: Dict) -> str:
        """Log a successful task completion."""
        cursor = self.conn.cursor()
        
        success_id = self._generate_id('suc_')
        
        cursor.execute('''
            INSERT INTO successes (id, task_type, task_description, approach, metrics, context)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (success_id, task_type, task_description, approach, 
              json.dumps(metrics), json.dumps(context)))
        
        self.conn.commit()
        return success_id
    
    def get_successful_approaches(self, task_type: str, limit: int = 10) -> List[SuccessRecord]:
        """Get successful approaches for a task type."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM successes 
            WHERE task_type = ? 
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (task_type, limit))
        
        successes = []
        for row in cursor.fetchall():
            successes.append(SuccessRecord(
                id=row['id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                task_type=row['task_type'],
                task_description=row['task_description'],
                approach=row['approach'],
                metrics=json.loads(row['metrics']),
                context=json.loads(row['context']),
                reproducibility_score=row['reproducibility_score']
            ))
        
        return successes
    
    def get_best_practices(self) -> Dict[str, List[str]]:
        """Get best practices derived from successful tasks."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT task_type, approach, COUNT(*) as count
            FROM successes
            GROUP BY task_type, approach
            HAVING count > 1
            ORDER BY task_type, count DESC
        ''')
        
        practices = defaultdict(list)
        for row in cursor.fetchall():
            if len(practices[row['task_type']]) < 3:
                practices[row['task_type']].append(row['approach'])
        
        return dict(practices)
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get learning system statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        # Interaction stats
        cursor.execute('SELECT COUNT(*) as count FROM interactions')
        stats['total_interactions'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT interaction_type, COUNT(*) as count 
            FROM interactions 
            GROUP BY interaction_type
        ''')
        stats['interactions_by_type'] = {r['interaction_type']: r['count'] for r in cursor.fetchall()}
        
        cursor.execute('''
            SELECT outcome, COUNT(*) as count 
            FROM interactions 
            GROUP BY outcome
        ''')
        stats['outcomes'] = {r['outcome']: r['count'] for r in cursor.fetchall()}
        
        # Pattern stats
        cursor.execute('SELECT COUNT(*) as count FROM patterns')
        stats['total_patterns'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT pattern_type, COUNT(*) as count 
            FROM patterns 
            GROUP BY pattern_type
        ''')
        stats['patterns_by_type'] = {r['pattern_type']: r['count'] for r in cursor.fetchall()}
        
        # Preference stats
        cursor.execute('SELECT COUNT(*) as count FROM preferences')
        stats['total_preferences'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM preferences 
            GROUP BY category
        ''')
        stats['preferences_by_category'] = {r['category']: r['count'] for r in cursor.fetchall()}
        
        # Error stats
        cursor.execute('SELECT COUNT(*) as count FROM errors')
        stats['total_errors'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM errors WHERE resolved = 1')
        stats['resolved_errors'] = cursor.fetchone()['count']
        
        # Success stats
        cursor.execute('SELECT COUNT(*) as count FROM successes')
        stats['total_successes'] = cursor.fetchone()['count']
        
        return stats
    
    def export_learning_data(self) -> Dict[str, Any]:
        """Export all learning data for backup or transfer."""
        cursor = self.conn.cursor()
        
        # Export interactions
        cursor.execute('SELECT * FROM interactions ORDER BY timestamp')
        interactions = []
        for row in cursor.fetchall():
            interactions.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'type': row['interaction_type'],
                'input': row['input_text'],
                'output': row['output_text'],
                'outcome': row['outcome'],
                'feedback_score': row['feedback_score']
            })
        
        # Export patterns
        cursor.execute('SELECT * FROM patterns')
        patterns = [dict(row) for row in cursor.fetchall()]
        
        # Export preferences
        cursor.execute('SELECT * FROM preferences')
        preferences = [dict(row) for row in cursor.fetchall()]
        
        # Export errors
        cursor.execute('SELECT * FROM errors')
        errors = [dict(row) for row in cursor.fetchall()]
        
        # Export successes
        cursor.execute('SELECT * FROM successes')
        successes = [dict(row) for row in cursor.fetchall()]
        
        return {
            'interactions': interactions,
            'patterns': patterns,
            'preferences': preferences,
            'errors': errors,
            'successes': successes,
            'exported_at': datetime.utcnow().isoformat()
        }
    
    def import_learning_data(self, data: Dict[str, Any]):
        """Import learning data from backup."""
        cursor = self.conn.cursor()
        
        # Import preferences
        for pref in data.get('preferences', []):
            cursor.execute('''
                INSERT OR REPLACE INTO preferences 
                (id, category, key, value, confidence, source, evidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (pref['id'], pref['category'], pref['key'], pref['value'],
                  pref['confidence'], pref['source'], pref['evidence'],
                  pref['created_at'], pref['updated_at']))
        
        # Import patterns
        for pattern in data.get('patterns', []):
            cursor.execute('''
                INSERT OR REPLACE INTO patterns 
                (id, pattern_type, description, occurrences, first_seen, last_seen,
                 confidence, conditions, actions, examples)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (pattern['id'], pattern['pattern_type'], pattern['description'],
                  pattern['occurrences'], pattern['first_seen'], pattern['last_seen'],
                  pattern['confidence'], pattern['conditions'], pattern['actions'],
                  pattern['examples']))
        
        self.conn.commit()
    
    def close(self):
        """Close database connection."""
        self.conn.close()


if __name__ == '__main__':
    # Example usage
    learning = LearningSystem('/tmp/test_learning.db')
    
    # Log some interactions
    interactions = [
        Interaction(
            id='',
            timestamp=datetime.utcnow(),
            interaction_type='query',
            input_text='How do I create a Python class?',
            output_text='You can create a Python class using the class keyword...',
            outcome='success',
            user_id='user1'
        ),
        Interaction(
            id='',
            timestamp=datetime.utcnow() - timedelta(hours=2),
            interaction_type='command',
            input_text='Create a new file called test.py',
            output_text='Created file test.py',
            outcome='success',
            user_id='user1'
        ),
        Interaction(
            id='',
            timestamp=datetime.utcnow() - timedelta(hours=4),
            interaction_type='query',
            input_text='Explain async/await in Python',
            output_text='Async/await is used for asynchronous programming...',
            outcome='failure',
            user_id='user1'
        )
    ]
    
    for i in interactions:
        learning.log_interaction(i)
    
    # Add feedback
    # learning.add_feedback(interactions[0].id, 0.9, "Very helpful!")
    
    # Detect patterns
    patterns = learning.detect_patterns(time_window_hours=24)
    print(f"Detected {len(patterns)} patterns")
    for p in patterns:
        print(f"  - {p.description}")
    
    # Set preference
    learning.set_preference('language', 'python', True, source='explicit')
    
    # Get stats
    stats = learning.get_learning_stats()
    print(f"\nLearning stats: {stats}")
    
    learning.close()
