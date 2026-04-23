"""
Self-Improvement System - Performance tracking, strategy optimization.
Tracks and improves system performance over time.
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import math
import random


@dataclass
class PerformanceMetric:
    """Represents a performance metric measurement."""
    id: str
    timestamp: datetime
    metric_type: str  # 'accuracy', 'speed', 'quality', 'efficiency'
    metric_name: str
    value: float
    unit: str
    context: Dict = field(default_factory=dict)
    baseline: Optional[float] = None
    improvement: Optional[float] = None


@dataclass
class Strategy:
    """Represents an optimization strategy."""
    id: str
    name: str
    description: str
    strategy_type: str  # 'routing', 'selection', 'processing', 'optimization'
    parameters: Dict = field(default_factory=dict)
    effectiveness: float = 0.5
    usage_count: int = 0
    success_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SkillRecord:
    """Represents a skill and its effectiveness tracking."""
    id: str
    name: str
    skill_type: str
    total_uses: int = 0
    successful_uses: int = 0
    failed_uses: int = 0
    avg_execution_time: float = 0.0
    effectiveness: float = 0.5
    last_used: Optional[datetime] = None
    improvement_history: List[Dict] = field(default_factory=list)


@dataclass
class FeedbackRecord:
    """Represents user feedback on system performance."""
    id: str
    timestamp: datetime
    feedback_type: str  # 'rating', 'correction', 'preference', 'complaint', 'praise'
    target_id: str  # ID of the thing being feedback on
    target_type: str  # 'response', 'action', 'skill', 'strategy'
    rating: Optional[float] = None
    text: Optional[str] = None
    corrections: Dict = field(default_factory=dict)
    user_id: str = "default"
    processed: bool = False


@dataclass
class ImprovementAction:
    """Represents a recommended improvement action."""
    id: str
    action_type: str  # 'parameter_tune', 'strategy_switch', 'skill_update', 'config_change'
    description: str
    rationale: str
    priority: float  # 0.0 to 1.0
    expected_impact: float
    parameters: Dict = field(default_factory=dict)
    status: str = 'pending'  # 'pending', 'implemented', 'rejected', 'testing'
    created_at: datetime = field(default_factory=datetime.utcnow)
    implemented_at: Optional[datetime] = None


class SelfImprovement:
    """
    Self-improvement system with:
    - Performance tracking and metrics
    - Strategy optimization
    - Skill effectiveness tracking
    - User feedback integration
    - Improvement recommendations
    """
    
    PERFORMANCE_WINDOW_DAYS = 30
    MIN_SAMPLES_FOR_STATS = 5
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._load_counters()
    
    def _init_db(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()
        
        # Performance metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metric_type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT DEFAULT '',
                context TEXT DEFAULT '{}',
                baseline REAL,
                improvement REAL
            )
        ''')
        
        # Strategies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                strategy_type TEXT NOT NULL,
                parameters TEXT DEFAULT '{}',
                effectiveness REAL DEFAULT 0.5,
                usage_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Skills table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                skill_type TEXT NOT NULL,
                total_uses INTEGER DEFAULT 0,
                successful_uses INTEGER DEFAULT 0,
                failed_uses INTEGER DEFAULT 0,
                avg_execution_time REAL DEFAULT 0.0,
                effectiveness REAL DEFAULT 0.5,
                last_used TIMESTAMP,
                improvement_history TEXT DEFAULT '[]'
            )
        ''')
        
        # Feedback table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                feedback_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                rating REAL,
                text TEXT,
                corrections TEXT DEFAULT '{}',
                user_id TEXT DEFAULT 'default',
                processed INTEGER DEFAULT 0
            )
        ''')
        
        # Improvement actions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS improvement_actions (
                id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                rationale TEXT,
                priority REAL DEFAULT 0.5,
                expected_impact REAL DEFAULT 0.0,
                parameters TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                implemented_at TIMESTAMP
            )
        ''')
        
        # Strategy usage log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategy_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER DEFAULT 0,
                execution_time REAL,
                context TEXT DEFAULT '{}',
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        ''')
        
        # Skill usage log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skill_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER DEFAULT 0,
                execution_time REAL,
                context TEXT DEFAULT '{}',
                FOREIGN KEY (skill_id) REFERENCES skills(id)
            )
        ''')
        
        # Baselines table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baselines (
                metric_name TEXT PRIMARY KEY,
                baseline_value REAL NOT NULL,
                established_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_type ON performance_metrics(metric_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_target ON feedback(target_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type)')
        
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
        # Map counter names to prefixes
        for name, prefix in [('metric', 'met'), ('strategy', 'str'), ('skill', 'skl'), 
                            ('feedback', 'fdb'), ('action', 'imp')]:
            cursor.execute('SELECT value FROM counters WHERE name = ?', (name,))
            row = cursor.fetchone()
            setattr(self, f'_{prefix}_counter', row['value'] if row else 0)
    
    def _save_counter(self, name: str):
        """Save a counter value."""
        cursor = self.conn.cursor()
        # Map prefix back to full name for storage
        name_map = {'met': 'metric', 'str': 'strategy', 'skl': 'skill', 
                   'fdb': 'feedback', 'imp': 'action'}
        full_name = name_map.get(name, name)
        value = getattr(self, f'_{name}_counter')
        cursor.execute('INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)',
                      (full_name, value))
        self.conn.commit()
    
    def _generate_id(self, prefix: str) -> str:
        """Generate a unique ID."""
        counter_name = prefix.rstrip('_')
        current = getattr(self, f'_{counter_name}_counter')
        setattr(self, f'_{counter_name}_counter', current + 1)
        self._save_counter(counter_name)
        return f"{prefix}{current + 1:08d}"
    
    def record_metric(self, metric_type: str, metric_name: str, value: float,
                      unit: str = '', context: Dict = None) -> PerformanceMetric:
        """Record a performance metric."""
        cursor = self.conn.cursor()
        
        metric_id = self._generate_id('met_')
        
        # Get baseline
        cursor.execute('SELECT baseline_value FROM baselines WHERE metric_name = ?', (metric_name,))
        row = cursor.fetchone()
        baseline = row['baseline_value'] if row else None
        
        # Calculate improvement
        improvement = None
        if baseline is not None and baseline != 0:
            improvement = (value - baseline) / abs(baseline)
        
        cursor.execute('''
            INSERT INTO performance_metrics 
            (id, metric_type, metric_name, value, unit, context, baseline, improvement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (metric_id, metric_type, metric_name, value, unit,
              json.dumps(context or {}), baseline, improvement))
        
        self.conn.commit()
        
        return PerformanceMetric(
            id=metric_id,
            timestamp=datetime.utcnow(),
            metric_type=metric_type,
            metric_name=metric_name,
            value=value,
            unit=unit,
            context=context or {},
            baseline=baseline,
            improvement=improvement
        )
    
    def set_baseline(self, metric_name: str, baseline_value: float):
        """Set or update baseline for a metric."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO baselines (metric_name, baseline_value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (metric_name, baseline_value))
        
        self.conn.commit()
    
    def get_metric_trends(self, metric_name: str, days: int = 30) -> Dict[str, Any]:
        """Get trends for a specific metric."""
        cursor = self.conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        cursor.execute('''
            SELECT value, timestamp, improvement
            FROM performance_metrics
            WHERE metric_name = ? AND timestamp > ?
            ORDER BY timestamp
        ''', (metric_name, cutoff.isoformat()))
        
        values = []
        timestamps = []
        improvements = []
        
        for row in cursor.fetchall():
            values.append(row['value'])
            timestamps.append(row['timestamp'])
            improvements.append(row['improvement'])
        
        if not values:
            return {'metric_name': metric_name, 'count': 0}
        
        # Calculate statistics
        avg_value = sum(values) / len(values)
        min_value = min(values)
        max_value = max(values)
        
        # Calculate trend (simple linear regression)
        if len(values) > 1:
            n = len(values)
            x_sum = sum(range(n))
            y_sum = sum(values)
            xy_sum = sum(i * v for i, v in enumerate(values))
            x2_sum = sum(i * i for i in range(n))
            
            slope = (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum) if n * x2_sum != x_sum * x_sum else 0
            
            if slope > 0:
                trend = 'improving'
            elif slope < 0:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'unknown'
            slope = 0
        
        return {
            'metric_name': metric_name,
            'count': len(values),
            'avg': avg_value,
            'min': min_value,
            'max': max_value,
            'trend': trend,
            'slope': slope,
            'last_value': values[-1] if values else None,
            'values': values[-10:],  # Last 10 values
            'timestamps': timestamps[-10:]
        }
    
    def register_strategy(self, name: str, description: str, strategy_type: str,
                          parameters: Dict = None) -> Strategy:
        """Register a new strategy."""
        cursor = self.conn.cursor()
        
        strategy_id = self._generate_id('str_')
        
        cursor.execute('''
            INSERT INTO strategies (id, name, description, strategy_type, parameters)
            VALUES (?, ?, ?, ?, ?)
        ''', (strategy_id, name, description, strategy_type, json.dumps(parameters or {})))
        
        self.conn.commit()
        
        return Strategy(
            id=strategy_id,
            name=name,
            description=description,
            strategy_type=strategy_type,
            parameters=parameters or {}
        )
    
    def get_strategy(self, strategy_id: str = None, name: str = None) -> Optional[Strategy]:
        """Get a strategy by ID or name."""
        cursor = self.conn.cursor()
        
        if strategy_id:
            cursor.execute('SELECT * FROM strategies WHERE id = ?', (strategy_id,))
        elif name:
            cursor.execute('SELECT * FROM strategies WHERE name = ?', (name,))
        else:
            return None
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return Strategy(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            strategy_type=row['strategy_type'],
            parameters=json.loads(row['parameters']),
            effectiveness=row['effectiveness'],
            usage_count=row['usage_count'],
            success_count=row['success_count'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
    
    def log_strategy_use(self, strategy_id: str, success: bool, 
                         execution_time: float = None, context: Dict = None):
        """Log a strategy usage event."""
        cursor = self.conn.cursor()
        
        # Update strategy stats
        cursor.execute('''
            UPDATE strategies 
            SET usage_count = usage_count + 1,
                success_count = success_count + ?,
                effectiveness = CAST(success_count + ? AS REAL) / (usage_count + 1),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (1 if success else 0, 1 if success else 0, strategy_id))
        
        # Log usage
        cursor.execute('''
            INSERT INTO strategy_log (strategy_id, success, execution_time, context)
            VALUES (?, ?, ?, ?)
        ''', (strategy_id, 1 if success else 0, execution_time, json.dumps(context or {})))
        
        self.conn.commit()
    
    def get_best_strategy(self, strategy_type: str = None, 
                          min_uses: int = 5) -> Optional[Strategy]:
        """Get the best performing strategy."""
        cursor = self.conn.cursor()
        
        query = '''
            SELECT * FROM strategies 
            WHERE usage_count >= ?
        '''
        params = [min_uses]
        
        if strategy_type:
            query += ' AND strategy_type = ?'
            params.append(strategy_type)
        
        query += ' ORDER BY effectiveness DESC LIMIT 1'
        
        cursor.execute(query, params)
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return Strategy(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            strategy_type=row['strategy_type'],
            parameters=json.loads(row['parameters']),
            effectiveness=row['effectiveness'],
            usage_count=row['usage_count'],
            success_count=row['success_count'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
    
    def register_skill(self, name: str, skill_type: str) -> SkillRecord:
        """Register a new skill."""
        cursor = self.conn.cursor()
        
        skill_id = self._generate_id('skl_')
        
        cursor.execute('''
            INSERT INTO skills (id, name, skill_type)
            VALUES (?, ?, ?)
        ''', (skill_id, name, skill_type))
        
        self.conn.commit()
        
        return SkillRecord(
            id=skill_id,
            name=name,
            skill_type=skill_type
        )
    
    def get_skill(self, skill_id: str = None, name: str = None) -> Optional[SkillRecord]:
        """Get a skill by ID or name."""
        cursor = self.conn.cursor()
        
        if skill_id:
            cursor.execute('SELECT * FROM skills WHERE id = ?', (skill_id,))
        elif name:
            cursor.execute('SELECT * FROM skills WHERE name = ?', (name,))
        else:
            return None
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return SkillRecord(
            id=row['id'],
            name=row['name'],
            skill_type=row['skill_type'],
            total_uses=row['total_uses'],
            successful_uses=row['successful_uses'],
            failed_uses=row['failed_uses'],
            avg_execution_time=row['avg_execution_time'],
            effectiveness=row['effectiveness'],
            last_used=datetime.fromisoformat(row['last_used']) if row['last_used'] else None,
            improvement_history=json.loads(row['improvement_history'])
        )
    
    def log_skill_use(self, skill_name: str, success: bool, 
                      execution_time: float = None, context: Dict = None):
        """Log a skill usage event."""
        cursor = self.conn.cursor()
        
        # Get skill
        cursor.execute('SELECT * FROM skills WHERE name = ?', (skill_name,))
        row = cursor.fetchone()
        
        if not row:
            # Auto-register skill
            skill = self.register_skill(skill_name, 'auto')
        else:
            skill_id = row['id']
            
            # Update skill stats
            new_total = row['total_uses'] + 1
            new_success = row['successful_uses'] + (1 if success else 0)
            new_failed = row['failed_uses'] + (0 if success else 1)
            new_effectiveness = new_success / new_total if new_total > 0 else 0.5
            
            # Update average execution time
            old_avg = row['avg_execution_time']
            old_count = row['total_uses']
            if execution_time is not None:
                new_avg = (old_avg * old_count + execution_time) / new_total
            else:
                new_avg = old_avg
            
            cursor.execute('''
                UPDATE skills 
                SET total_uses = ?,
                    successful_uses = ?,
                    failed_uses = ?,
                    effectiveness = ?,
                    avg_execution_time = ?,
                    last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_total, new_success, new_failed, new_effectiveness, new_avg, skill_id))
            
            # Log usage
            cursor.execute('''
                INSERT INTO skill_log (skill_id, success, execution_time, context)
                VALUES (?, ?, ?, ?)
            ''', (skill_id, 1 if success else 0, execution_time, json.dumps(context or {})))
        
        self.conn.commit()
    
    def get_effective_skills(self, min_effectiveness: float = 0.7,
                             min_uses: int = 5, limit: int = 20) -> List[SkillRecord]:
        """Get most effective skills."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT * FROM skills
            WHERE effectiveness >= ? AND total_uses >= ?
            ORDER BY effectiveness DESC, total_uses DESC
            LIMIT ?
        ''', (min_effectiveness, min_uses, limit))
        
        skills = []
        for row in cursor.fetchall():
            skills.append(SkillRecord(
                id=row['id'],
                name=row['name'],
                skill_type=row['skill_type'],
                total_uses=row['total_uses'],
                successful_uses=row['successful_uses'],
                failed_uses=row['failed_uses'],
                avg_execution_time=row['avg_execution_time'],
                effectiveness=row['effectiveness'],
                last_used=datetime.fromisoformat(row['last_used']) if row['last_used'] else None,
                improvement_history=json.loads(row['improvement_history'])
            ))
        
        return skills
    
    def record_feedback(self, feedback_type: str, target_id: str, target_type: str,
                        rating: float = None, text: str = None,
                        corrections: Dict = None, user_id: str = 'default') -> FeedbackRecord:
        """Record user feedback."""
        cursor = self.conn.cursor()
        
        feedback_id = self._generate_id('fdb_')
        
        cursor.execute('''
            INSERT INTO feedback 
            (id, feedback_type, target_id, target_type, rating, text, corrections, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (feedback_id, feedback_type, target_id, target_type, 
              rating, text, json.dumps(corrections or {}), user_id))
        
        self.conn.commit()
        
        return FeedbackRecord(
            id=feedback_id,
            timestamp=datetime.utcnow(),
            feedback_type=feedback_type,
            target_id=target_id,
            target_type=target_type,
            rating=rating,
            text=text,
            corrections=corrections or {},
            user_id=user_id
        )
    
    def process_feedback(self, feedback_id: str) -> Dict:
        """Process unprocessed feedback and extract improvements."""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT * FROM feedback WHERE id = ? AND processed = 0', (feedback_id,))
        row = cursor.fetchone()
        
        if not row:
            return {'processed': False, 'reason': 'Already processed or not found'}
        
        feedback = FeedbackRecord(
            id=row['id'],
            timestamp=datetime.fromisoformat(row['timestamp']),
            feedback_type=row['feedback_type'],
            target_id=row['target_id'],
            target_type=row['target_type'],
            rating=row['rating'],
            text=row['text'],
            corrections=json.loads(row['corrections']),
            user_id=row['user_id']
        )
        
        improvements = []
        
        # Process based on feedback type
        if feedback.feedback_type == 'rating' and feedback.rating is not None:
            # Update target effectiveness based on rating
            if feedback.target_type == 'strategy':
                self._update_strategy_effectiveness(feedback.target_id, feedback.rating)
                improvements.append(f"Updated strategy effectiveness based on rating {feedback.rating}")
            elif feedback.target_type == 'skill':
                self._update_skill_effectiveness(feedback.target_id, feedback.rating)
                improvements.append(f"Updated skill effectiveness based on rating {feedback.rating}")
        
        elif feedback.feedback_type == 'correction' and feedback.corrections:
            # Apply corrections
            improvements.append(f"Applied corrections: {list(feedback.corrections.keys())}")
        
        elif feedback.feedback_type == 'preference':
            # Record preference for future reference
            improvements.append(f"Recorded preference for {feedback.target_type}")
        
        # Mark as processed
        cursor.execute('UPDATE feedback SET processed = 1 WHERE id = ?', (feedback_id,))
        self.conn.commit()
        
        return {
            'processed': True,
            'feedback_id': feedback_id,
            'improvements': improvements
        }
    
    def _update_strategy_effectiveness(self, strategy_id: str, rating: float):
        """Update strategy effectiveness based on rating."""
        cursor = self.conn.cursor()
        
        # Weighted update
        cursor.execute('''
            UPDATE strategies 
            SET effectiveness = effectiveness * 0.8 + ? * 0.2,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (rating / 5.0, strategy_id))  # Assume 5-point scale
        
        self.conn.commit()
    
    def _update_skill_effectiveness(self, skill_id: str, rating: float):
        """Update skill effectiveness based on rating."""
        cursor = self.conn.cursor()
        
        # Weighted update
        cursor.execute('''
            UPDATE skills 
            SET effectiveness = effectiveness * 0.8 + ? * 0.2
            WHERE id = ?
        ''', (rating / 5.0, skill_id))
        
        self.conn.commit()
    
    def get_unprocessed_feedback(self, limit: int = 50) -> List[FeedbackRecord]:
        """Get unprocessed feedback records."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT * FROM feedback 
            WHERE processed = 0 
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        feedbacks = []
        for row in cursor.fetchall():
            feedbacks.append(FeedbackRecord(
                id=row['id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                feedback_type=row['feedback_type'],
                target_id=row['target_id'],
                target_type=row['target_type'],
                rating=row['rating'],
                text=row['text'],
                corrections=json.loads(row['corrections']),
                user_id=row['user_id']
            ))
        
        return feedbacks
    
    def generate_improvement_recommendations(self) -> List[ImprovementAction]:
        """Generate improvement recommendations based on analysis."""
        recommendations = []
        cursor = self.conn.cursor()
        
        # Analyze low-performing strategies
        cursor.execute('''
            SELECT * FROM strategies 
            WHERE effectiveness < 0.5 AND usage_count >= ?
            ORDER BY effectiveness ASC
            LIMIT 5
        ''', (self.MIN_SAMPLES_FOR_STATS,))
        
        for row in cursor.fetchall():
            recommendations.append(ImprovementAction(
                id=self._generate_id('imp_'),
                action_type='strategy_review',
                description=f"Review low-performing strategy: {row['name']}",
                rationale=f"Effectiveness is {row['effectiveness']:.2f} with {row['usage_count']} uses",
                priority=1.0 - row['effectiveness'],
                expected_impact=0.2,
                parameters={'strategy_id': row['id'], 'strategy_name': row['name']}
            ))
        
        # Analyze skills with declining performance
        cursor.execute('''
            SELECT * FROM skills 
            WHERE effectiveness < 0.6 AND total_uses >= ?
            ORDER BY effectiveness ASC
            LIMIT 5
        ''', (self.MIN_SAMPLES_FOR_STATS,))
        
        for row in cursor.fetchall():
            recommendations.append(ImprovementAction(
                id=self._generate_id('imp_'),
                action_type='skill_update',
                description=f"Consider updating skill: {row['name']}",
                rationale=f"Effectiveness is {row['effectiveness']:.2f} with {row['failed_uses']} failures",
                priority=1.0 - row['effectiveness'],
                expected_impact=0.15,
                parameters={'skill_id': row['id'], 'skill_name': row['name']}
            ))
        
        # Analyze metrics with declining trends
        cursor.execute('SELECT DISTINCT metric_name FROM performance_metrics')
        for row in cursor.fetchall():
            trend_data = self.get_metric_trends(row['metric_name'])
            if trend_data.get('trend') == 'declining':
                recommendations.append(ImprovementAction(
                    id=self._generate_id('imp_'),
                    action_type='parameter_tune',
                    description=f"Investigate declining metric: {row['metric_name']}",
                    rationale=f"Metric shows declining trend with slope {trend_data.get('slope', 0):.4f}",
                    priority=0.7,
                    expected_impact=0.1,
                    parameters={'metric_name': row['metric_name']}
                ))
        
        # Sort by priority
        recommendations.sort(key=lambda x: -x.priority)
        
        # Store recommendations
        for rec in recommendations:
            cursor.execute('''
                INSERT INTO improvement_actions 
                (id, action_type, description, rationale, priority, expected_impact, parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (rec.id, rec.action_type, rec.description, rec.rationale,
                  rec.priority, rec.expected_impact, json.dumps(rec.parameters)))
        
        self.conn.commit()
        
        return recommendations
    
    def get_pending_improvements(self, limit: int = 20) -> List[ImprovementAction]:
        """Get pending improvement actions."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT * FROM improvement_actions
            WHERE status = 'pending'
            ORDER BY priority DESC
            LIMIT ?
        ''', (limit,))
        
        actions = []
        for row in cursor.fetchall():
            actions.append(ImprovementAction(
                id=row['id'],
                action_type=row['action_type'],
                description=row['description'],
                rationale=row['rationale'],
                priority=row['priority'],
                expected_impact=row['expected_impact'],
                parameters=json.loads(row['parameters']),
                status=row['status'],
                created_at=datetime.fromisoformat(row['created_at']),
                implemented_at=datetime.fromisoformat(row['implemented_at']) if row['implemented_at'] else None
            ))
        
        return actions
    
    def implement_improvement(self, action_id: str, notes: str = None) -> bool:
        """Mark an improvement as implemented."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            UPDATE improvement_actions 
            SET status = 'implemented', implemented_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
        ''', (action_id,))
        
        self.conn.commit()
        return cursor.rowcount > 0
    
    def reject_improvement(self, action_id: str, reason: str = None) -> bool:
        """Mark an improvement as rejected."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            UPDATE improvement_actions 
            SET status = 'rejected'
            WHERE id = ? AND status = 'pending'
        ''', (action_id,))
        
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_improvement_stats(self) -> Dict[str, Any]:
        """Get improvement system statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        # Metric stats
        cursor.execute('SELECT COUNT(*) as count FROM performance_metrics')
        stats['total_metrics'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT metric_type, COUNT(*) as count
            FROM performance_metrics
            GROUP BY metric_type
        ''')
        stats['metrics_by_type'] = {r['metric_type']: r['count'] for r in cursor.fetchall()}
        
        # Strategy stats
        cursor.execute('SELECT COUNT(*) as count FROM strategies')
        stats['total_strategies'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT AVG(effectiveness) as avg FROM strategies WHERE usage_count > 0')
        stats['avg_strategy_effectiveness'] = cursor.fetchone()['avg'] or 0.5
        
        # Skill stats
        cursor.execute('SELECT COUNT(*) as count FROM skills')
        stats['total_skills'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT AVG(effectiveness) as avg FROM skills WHERE total_uses > 0')
        stats['avg_skill_effectiveness'] = cursor.fetchone()['avg'] or 0.5
        
        cursor.execute('''
            SELECT name, effectiveness FROM skills
            WHERE total_uses >= ?
            ORDER BY effectiveness DESC
            LIMIT 5
        ''', (self.MIN_SAMPLES_FOR_STATS,))
        stats['top_skills'] = [(r['name'], r['effectiveness']) for r in cursor.fetchall()]
        
        # Feedback stats
        cursor.execute('SELECT COUNT(*) as count FROM feedback')
        stats['total_feedback'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM feedback WHERE processed = 0')
        stats['unprocessed_feedback'] = cursor.fetchone()['count']
        
        # Improvement stats
        cursor.execute('SELECT COUNT(*) as count FROM improvement_actions')
        stats['total_improvements'] = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM improvement_actions
            GROUP BY status
        ''')
        stats['improvements_by_status'] = {r['status']: r['count'] for r in cursor.fetchall()}
        
        return stats
    
    def close(self):
        """Close database connection."""
        self.conn.close()


if __name__ == '__main__':
    # Example usage
    improve = SelfImprovement('/tmp/test_improve.db')
    
    # Register strategies
    improve.register_strategy(
        'fast_response',
        'Optimize for quick responses',
        'routing',
        {'priority': 'speed', 'max_time': 2.0}
    )
    
    improve.register_strategy(
        'quality_focus',
        'Optimize for response quality',
        'routing',
        {'priority': 'quality', 'max_iterations': 5}
    )
    
    # Register skills
    improve.register_skill('code_generation', 'coding')
    improve.register_skill('text_analysis', 'analysis')
    improve.register_skill('web_search', 'research')
    
    # Log some usage
    improve.log_strategy_use('fast_response', success=True, execution_time=1.5)
    improve.log_strategy_use('fast_response', success=False, execution_time=3.0)
    improve.log_strategy_use('quality_focus', success=True, execution_time=4.0)
    
    improve.log_skill_use('code_generation', success=True, execution_time=2.5)
    improve.log_skill_use('code_generation', success=True, execution_time=1.8)
    improve.log_skill_use('text_analysis', success=False, execution_time=1.0)
    
    # Record metrics
    improve.set_baseline('response_quality', 0.7)
    improve.record_metric('quality', 'response_quality', 0.85, 'score')
    improve.record_metric('quality', 'response_quality', 0.82, 'score')
    improve.record_metric('quality', 'response_quality', 0.88, 'score')
    
    # Record feedback
    improve.record_feedback(
        feedback_type='rating',
        target_id='str_1',
        target_type='strategy',
        rating=4.0,
        text='Good balance of speed and quality'
    )
    
    # Process feedback
    unprocessed = improve.get_unprocessed_feedback()
    for fb in unprocessed:
        result = improve.process_feedback(fb.id)
        print(f"Processed feedback: {result}")
    
    # Generate recommendations
    recommendations = improve.generate_improvement_recommendations()
    print(f"\nGenerated {len(recommendations)} improvement recommendations")
    for rec in recommendations[:3]:
        print(f"  - [{rec.priority:.2f}] {rec.description}")
    
    # Get stats
    stats = improve.get_improvement_stats()
    print(f"\nImprovement stats: {stats}")
    
    # Get metric trends
    trends = improve.get_metric_trends('response_quality')
    print(f"\nResponse quality trends: {trends['trend']}")
    
    improve.close()
