"""
Automation persistence layer.
Provides CRUD operations, execution history, error logging, and metrics.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AutomationStatus(Enum):
    """Status of an automation."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"


class ExecutionStatus(Enum):
    """Status of an automation execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class Automation:
    """Represents an automation definition."""
    id: str
    name: str
    description: str = ""
    trigger_type: str = "cron"  # cron, interval, date, rrule, file, email, webhook, event, conditional
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    action_type: str = "python_script"
    action_config: Dict[str, Any] = field(default_factory=dict)
    status: AutomationStatus = AutomationStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'trigger_type': self.trigger_type,
            'trigger_config': json.dumps(self.trigger_config),
            'action_type': self.action_type,
            'action_config': json.dumps(self.action_config),
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'run_count': self.run_count,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'tags': json.dumps(self.tags),
            'metadata': json.dumps(self.metadata)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Automation':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            trigger_type=data.get('trigger_type', 'cron'),
            trigger_config=json.loads(data.get('trigger_config', '{}')),
            action_type=data.get('action_type', 'python_script'),
            action_config=json.loads(data.get('action_config', '{}')),
            status=AutomationStatus(data.get('status', 'active')),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else datetime.now(),
            last_run=datetime.fromisoformat(data['last_run']) if data.get('last_run') else None,
            next_run=datetime.fromisoformat(data['next_run']) if data.get('next_run') else None,
            run_count=data.get('run_count', 0),
            success_count=data.get('success_count', 0),
            failure_count=data.get('failure_count', 0),
            tags=json.loads(data.get('tags', '[]')),
            metadata=json.loads(data.get('metadata', '{}'))
        )


@dataclass
class Execution:
    """Represents an automation execution record."""
    id: str
    automation_id: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    trigger_data: Dict[str, Any] = field(default_factory=dict)
    action_result: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'automation_id': self.automation_id,
            'status': self.status.value,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_ms': self.duration_ms,
            'output': self.output,
            'error': self.error,
            'error_traceback': self.error_traceback,
            'trigger_data': json.dumps(self.trigger_data),
            'action_result': json.dumps(self.action_result),
            'retry_count': self.retry_count,
            'metadata': json.dumps(self.metadata)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Execution':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            automation_id=data['automation_id'],
            status=ExecutionStatus(data.get('status', 'pending')),
            started_at=datetime.fromisoformat(data['started_at']),
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            duration_ms=data.get('duration_ms'),
            output=data.get('output'),
            error=data.get('error'),
            error_traceback=data.get('error_traceback'),
            trigger_data=json.loads(data.get('trigger_data', '{}')),
            action_result=json.loads(data.get('action_result', '{}')),
            retry_count=data.get('retry_count', 0),
            metadata=json.loads(data.get('metadata', '{}'))
        )


@dataclass
class ErrorLog:
    """Represents an error log entry."""
    id: str
    automation_id: str
    execution_id: Optional[str]
    error_type: str
    error_message: str
    error_traceback: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'automation_id': self.automation_id,
            'execution_id': self.execution_id,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'error_traceback': self.error_traceback,
            'timestamp': self.timestamp.isoformat(),
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_note': self.resolution_note
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ErrorLog':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            automation_id=data['automation_id'],
            execution_id=data.get('execution_id'),
            error_type=data['error_type'],
            error_message=data['error_message'],
            error_traceback=data.get('error_traceback'),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else datetime.now(),
            resolved=data.get('resolved', False),
            resolved_at=datetime.fromisoformat(data['resolved_at']) if data.get('resolved_at') else None,
            resolution_note=data.get('resolution_note')
        )


class AutomationDB:
    """
    SQLite-based persistence layer for automations.
    
    Features:
    - Automation CRUD operations
    - Execution history tracking
    - Error logging
    - Success/failure metrics
    """
    
    def __init__(self, db_path: str = "automations/automations.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Automations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS automations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    trigger_type TEXT DEFAULT 'cron',
                    trigger_config TEXT DEFAULT '{}',
                    action_type TEXT DEFAULT 'python_script',
                    action_config TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}'
                )
            ''')
            
            # Executions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    automation_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms REAL,
                    output TEXT,
                    error TEXT,
                    error_traceback TEXT,
                    trigger_data TEXT DEFAULT '{}',
                    action_result TEXT DEFAULT '{}',
                    retry_count INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (automation_id) REFERENCES automations(id)
                )
            ''')
            
            # Error logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_logs (
                    id TEXT PRIMARY KEY,
                    automation_id TEXT NOT NULL,
                    execution_id TEXT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    error_traceback TEXT,
                    timestamp TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0,
                    resolved_at TEXT,
                    resolution_note TEXT,
                    FOREIGN KEY (automation_id) REFERENCES automations(id),
                    FOREIGN KEY (execution_id) REFERENCES executions(id)
                )
            ''')
            
            # Indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_executions_automation ON executions(automation_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_executions_started ON executions(started_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_errors_automation ON error_logs(automation_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON error_logs(timestamp)')
            
            conn.commit()
    
    # ==================== Automation CRUD ====================
    
    def create_automation(self, automation: Automation) -> Automation:
        """Create a new automation."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                data = automation.to_dict()
                
                cursor.execute('''
                    INSERT INTO automations (
                        id, name, description, trigger_type, trigger_config,
                        action_type, action_config, status, created_at, updated_at,
                        last_run, next_run, run_count, success_count, failure_count,
                        tags, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['id'], data['name'], data['description'],
                    data['trigger_type'], data['trigger_config'],
                    data['action_type'], data['action_config'],
                    data['status'], data['created_at'], data['updated_at'],
                    data['last_run'], data['next_run'],
                    data['run_count'], data['success_count'], data['failure_count'],
                    data['tags'], data['metadata']
                ))
                
                conn.commit()
                
        logger.info(f"Created automation: {automation.id}")
        return automation
    
    def get_automation(self, automation_id: str) -> Optional[Automation]:
        """Get an automation by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM automations WHERE id = ?', (automation_id,))
            row = cursor.fetchone()
            
            if row:
                return Automation.from_dict(dict(row))
            return None
    
    def list_automations(
        self,
        status: Optional[AutomationStatus] = None,
        trigger_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Automation]:
        """List automations with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM automations WHERE 1=1'
            params = []
            
            if status:
                query += ' AND status = ?'
                params.append(status.value)
            
            if trigger_type:
                query += ' AND trigger_type = ?'
                params.append(trigger_type)
            
            if tags:
                for tag in tags:
                    query += " AND tags LIKE ?"
                    params.append(f'%"{tag}"%')
            
            query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [Automation.from_dict(dict(row)) for row in rows]
    
    def update_automation(self, automation: Automation) -> Automation:
        """Update an automation."""
        automation.updated_at = datetime.now()
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                data = automation.to_dict()
                
                cursor.execute('''
                    UPDATE automations SET
                        name = ?, description = ?, trigger_type = ?, trigger_config = ?,
                        action_type = ?, action_config = ?, status = ?, updated_at = ?,
                        last_run = ?, next_run = ?, run_count = ?, success_count = ?,
                        failure_count = ?, tags = ?, metadata = ?
                    WHERE id = ?
                ''', (
                    data['name'], data['description'],
                    data['trigger_type'], data['trigger_config'],
                    data['action_type'], data['action_config'],
                    data['status'], data['updated_at'],
                    data['last_run'], data['next_run'],
                    data['run_count'], data['success_count'], data['failure_count'],
                    data['tags'], data['metadata'],
                    data['id']
                ))
                
                conn.commit()
        
        logger.info(f"Updated automation: {automation.id}")
        return automation
    
    def delete_automation(self, automation_id: str) -> bool:
        """Delete an automation and its related records."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete related executions and errors first
                cursor.execute('DELETE FROM error_logs WHERE automation_id = ?', (automation_id,))
                cursor.execute('DELETE FROM executions WHERE automation_id = ?', (automation_id,))
                cursor.execute('DELETE FROM automations WHERE id = ?', (automation_id,))
                
                conn.commit()
                deleted = cursor.rowcount > 0
        
        if deleted:
            logger.info(f"Deleted automation: {automation_id}")
        return deleted
    
    # ==================== Execution History ====================
    
    def create_execution(self, execution: Execution) -> Execution:
        """Create an execution record."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                data = execution.to_dict()
                
                cursor.execute('''
                    INSERT INTO executions (
                        id, automation_id, status, started_at, completed_at,
                        duration_ms, output, error, error_traceback,
                        trigger_data, action_result, retry_count, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['id'], data['automation_id'], data['status'],
                    data['started_at'], data['completed_at'],
                    data['duration_ms'], data['output'], data['error'],
                    data['error_traceback'], data['trigger_data'],
                    data['action_result'], data['retry_count'], data['metadata']
                ))
                
                conn.commit()
        
        logger.debug(f"Created execution: {execution.id}")
        return execution
    
    def get_execution(self, execution_id: str) -> Optional[Execution]:
        """Get an execution by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM executions WHERE id = ?', (execution_id,))
            row = cursor.fetchone()
            
            if row:
                return Execution.from_dict(dict(row))
            return None
    
    def update_execution(self, execution: Execution) -> Execution:
        """Update an execution record."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                data = execution.to_dict()
                
                cursor.execute('''
                    UPDATE executions SET
                        status = ?, completed_at = ?, duration_ms = ?,
                        output = ?, error = ?, error_traceback = ?,
                        trigger_data = ?, action_result = ?,
                        retry_count = ?, metadata = ?
                    WHERE id = ?
                ''', (
                    data['status'], data['completed_at'], data['duration_ms'],
                    data['output'], data['error'], data['error_traceback'],
                    data['trigger_data'], data['action_result'],
                    data['retry_count'], data['metadata'],
                    data['id']
                ))
                
                conn.commit()
        
        return execution
    
    def list_executions(
        self,
        automation_id: Optional[str] = None,
        status: Optional[ExecutionStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Execution]:
        """List executions with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM executions WHERE 1=1'
            params = []
            
            if automation_id:
                query += ' AND automation_id = ?'
                params.append(automation_id)
            
            if status:
                query += ' AND status = ?'
                params.append(status.value)
            
            if start_date:
                query += ' AND started_at >= ?'
                params.append(start_date.isoformat())
            
            if end_date:
                query += ' AND started_at <= ?'
                params.append(end_date.isoformat())
            
            query += ' ORDER BY started_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [Execution.from_dict(dict(row)) for row in rows]
    
    def get_execution_history(
        self,
        automation_id: str,
        limit: int = 50
    ) -> List[Execution]:
        """Get execution history for an automation."""
        return self.list_executions(automation_id=automation_id, limit=limit)
    
    # ==================== Error Logging ====================
    
    def log_error(self, error: ErrorLog) -> ErrorLog:
        """Log an error."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                data = error.to_dict()
                
                cursor.execute('''
                    INSERT INTO error_logs (
                        id, automation_id, execution_id, error_type,
                        error_message, error_traceback, timestamp,
                        resolved, resolved_at, resolution_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['id'], data['automation_id'], data['execution_id'],
                    data['error_type'], data['error_message'],
                    data['error_traceback'], data['timestamp'],
                    data['resolved'], data['resolved_at'], data['resolution_note']
                ))
                
                conn.commit()
        
        logger.warning(f"Logged error: {error.error_type} - {error.error_message}")
        return error
    
    def get_error(self, error_id: str) -> Optional[ErrorLog]:
        """Get an error log by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM error_logs WHERE id = ?', (error_id,))
            row = cursor.fetchone()
            
            if row:
                return ErrorLog.from_dict(dict(row))
            return None
    
    def resolve_error(
        self,
        error_id: str,
        resolution_note: Optional[str] = None
    ) -> Optional[ErrorLog]:
        """Mark an error as resolved."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                cursor.execute('''
                    UPDATE error_logs SET
                        resolved = 1,
                        resolved_at = ?,
                        resolution_note = ?
                    WHERE id = ?
                ''', (now, resolution_note, error_id))
                
                conn.commit()
                
                return self.get_error(error_id)
    
    def list_errors(
        self,
        automation_id: Optional[str] = None,
        resolved: Optional[bool] = None,
        error_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ErrorLog]:
        """List error logs with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM error_logs WHERE 1=1'
            params = []
            
            if automation_id:
                query += ' AND automation_id = ?'
                params.append(automation_id)
            
            if resolved is not None:
                query += ' AND resolved = ?'
                params.append(1 if resolved else 0)
            
            if error_type:
                query += ' AND error_type = ?'
                params.append(error_type)
            
            if start_date:
                query += ' AND timestamp >= ?'
                params.append(start_date.isoformat())
            
            if end_date:
                query += ' AND timestamp <= ?'
                params.append(end_date.isoformat())
            
            query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [ErrorLog.from_dict(dict(row)) for row in rows]
    
    # ==================== Metrics ====================
    
    def get_automation_metrics(self, automation_id: str) -> Dict[str, Any]:
        """Get metrics for an automation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get automation
            automation = self.get_automation(automation_id)
            if not automation:
                return {'error': 'Automation not found'}
            
            # Get execution stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(duration_ms) as avg_duration,
                    MAX(duration_ms) as max_duration,
                    MIN(duration_ms) as min_duration
                FROM executions
                WHERE automation_id = ?
            ''', (automation_id,))
            
            stats = dict(cursor.fetchone())
            
            # Get error count
            cursor.execute('''
                SELECT COUNT(*) as error_count
                FROM error_logs
                WHERE automation_id = ? AND resolved = 0
            ''', (automation_id,))
            
            unresolved_errors = cursor.fetchone()['error_count']
            
            # Calculate success rate
            total = stats.get('total', 0) or 0
            success = stats.get('success', 0) or 0
            success_rate = (success / total * 100) if total > 0 else 0
            
            return {
                'automation_id': automation_id,
                'name': automation.name,
                'status': automation.status.value,
                'run_count': automation.run_count,
                'success_count': automation.success_count,
                'failure_count': automation.failure_count,
                'success_rate': success_rate,
                'total_executions': total,
                'avg_duration_ms': stats.get('avg_duration'),
                'max_duration_ms': stats.get('max_duration'),
                'min_duration_ms': stats.get('min_duration'),
                'unresolved_errors': unresolved_errors,
                'last_run': automation.last_run.isoformat() if automation.last_run else None,
                'next_run': automation.next_run.isoformat() if automation.next_run else None
            }
    
    def get_overall_metrics(self) -> Dict[str, Any]:
        """Get overall system metrics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Count automations by status
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM automations
                GROUP BY status
            ''')
            
            automation_counts = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # Count executions by status
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM executions
                GROUP BY status
            ''')
            
            execution_counts = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # Get recent activity
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM executions
                WHERE started_at >= datetime('now', '-1 day')
            ''')
            
            executions_last_24h = cursor.fetchone()['count']
            
            # Get unresolved errors
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM error_logs
                WHERE resolved = 0
            ''')
            
            unresolved_errors = cursor.fetchone()['count']
            
            return {
                'automations': {
                    'total': sum(automation_counts.values()),
                    'active': automation_counts.get('active', 0),
                    'paused': automation_counts.get('paused', 0),
                    'disabled': automation_counts.get('disabled', 0),
                    'error': automation_counts.get('error', 0)
                },
                'executions': {
                    'total': sum(execution_counts.values()),
                    'success': execution_counts.get('success', 0),
                    'failed': execution_counts.get('failed', 0),
                    'last_24h': executions_last_24h
                },
                'errors': {
                    'unresolved': unresolved_errors
                }
            }
    
    # ==================== Maintenance ====================
    
    def cleanup_old_records(
        self,
        days: int = 30,
        keep_errors: bool = True
    ) -> Dict[str, int]:
        """Clean up old execution records."""
        cutoff = datetime.now() - timedelta(days=days)
        deleted = {'executions': 0}
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete old executions
                cursor.execute('''
                    DELETE FROM executions
                    WHERE started_at < ? AND status IN ('success', 'failed')
                ''', (cutoff.isoformat(),))
                
                deleted['executions'] = cursor.rowcount
                
                if not keep_errors:
                    # Delete old resolved errors
                    cursor.execute('''
                        DELETE FROM error_logs
                        WHERE timestamp < ? AND resolved = 1
                    ''', (cutoff.isoformat(),))
                    
                    deleted['errors'] = cursor.rowcount
                
                conn.commit()
        
        logger.info(f"Cleaned up {deleted} old records")
        return deleted
    
    def vacuum(self):
        """Vacuum the database to reclaim space."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute('VACUUM')
        
        logger.info("Database vacuumed")


# Convenience function
def get_db(db_path: str = "automations/automations.db") -> AutomationDB:
    """Get or create the automation database."""
    return AutomationDB(db_path)
