#!/usr/bin/env python3
"""Automations Scheduler - Full automation system with APScheduler"""
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
import subprocess
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

@dataclass
class Automation:
    id: str
    name: str
    instruction: str
    trigger_type: str  # "cron", "interval", "date", "rrule"
    trigger_config: Dict
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    success_count: int = 0
    error_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
@dataclass 
class ExecutionLog:
    automation_id: str
    started_at: str
    finished_at: Optional[str] = None
    status: str = "running"  # running, success, error
    result: Optional[str] = None
    error: Optional[str] = None

class AutomationDatabase:
    """SQLite persistence for automations"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path.home() / ".sentience" / "automations.db")
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS automations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                instruction TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_config TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_run TEXT,
                next_run TEXT,
                success_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS execution_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                automation_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                result TEXT,
                error TEXT,
                FOREIGN KEY (automation_id) REFERENCES automations(id)
            )
        """)
        
        conn.commit()
        conn.close()
        
    def save_automation(self, automation: Automation):
        """Save or update an automation"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR REPLACE INTO automations 
            (id, name, instruction, trigger_type, trigger_config, enabled, last_run, next_run, success_count, error_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            automation.id, automation.name, automation.instruction,
            automation.trigger_type, json.dumps(automation.trigger_config),
            1 if automation.enabled else 0,
            automation.last_run, automation.next_run,
            automation.success_count, automation.error_count,
            automation.created_at
        ))
        
        conn.commit()
        conn.close()
        
    def get_automation(self, automation_id: str) -> Optional[Automation]:
        """Get an automation by ID"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT * FROM automations WHERE id = ?", (automation_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return Automation(
                id=row[0], name=row[1], instruction=row[2],
                trigger_type=row[3], trigger_config=json.loads(row[4]),
                enabled=bool(row[5]), last_run=row[6], next_run=row[7],
                success_count=row[8], error_count=row[9], created_at=row[10]
            )
        return None
        
    def list_automations(self, enabled_only: bool = False) -> List[Automation]:
        """List all automations"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if enabled_only:
            c.execute("SELECT * FROM automations WHERE enabled = 1 ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM automations ORDER BY created_at DESC")
            
        rows = c.fetchall()
        conn.close()
        
        return [Automation(
            id=row[0], name=row[1], instruction=row[2],
            trigger_type=row[3], trigger_config=json.loads(row[4]),
            enabled=bool(row[5]), last_run=row[6], next_run=row[7],
            success_count=row[8], error_count=row[9], created_at=row[10]
        ) for row in rows]
        
    def delete_automation(self, automation_id: str):
        """Delete an automation"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM automations WHERE id = ?", (automation_id,))
        conn.commit()
        conn.close()
        
    def log_execution(self, log: ExecutionLog):
        """Log an execution"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO execution_logs (automation_id, started_at, finished_at, status, result, error)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (log.automation_id, log.started_at, log.finished_at, log.status, log.result, log.error))
        
        conn.commit()
        conn.close()
        
    def get_logs(self, automation_id: str = None, limit: int = 100) -> List[ExecutionLog]:
        """Get execution logs"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if automation_id:
            c.execute("SELECT * FROM execution_logs WHERE automation_id = ? ORDER BY started_at DESC LIMIT ?", 
                     (automation_id, limit))
        else:
            c.execute("SELECT * FROM execution_logs ORDER BY started_at DESC LIMIT ?", (limit,))
            
        rows = c.fetchall()
        conn.close()
        
        return [ExecutionLog(
            automation_id=row[1], started_at=row[2], finished_at=row[3],
            status=row[4], result=row[5], error=row[6]
        ) for row in rows]


class AutomationScheduler:
    """Main automation scheduler"""
    
    def __init__(self, db: AutomationDatabase = None):
        self.db = db or AutomationDatabase()
        
        # Setup scheduler with persistence
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{self.db.db_path.replace(".db", "_jobs.db")}')
        }
        executors = {
            'default': ThreadPoolExecutor(20)
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            timezone='UTC'
        )
        
        self.action_handlers: Dict[str, Callable] = {
            'python': self._execute_python,
            'shell': self._execute_shell,
            'api': self._execute_api,
            'email': self._execute_email,
            'notification': self._execute_notification
        }
        
        self._load_automations()
        
    def start(self):
        """Start the scheduler"""
        self.scheduler.start()
        
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        
    def _load_automations(self):
        """Load and schedule all enabled automations"""
        for automation in self.db.list_automations(enabled_only=True):
            self._schedule_automation(automation)
            
    def _schedule_automation(self, automation: Automation):
        """Schedule an automation"""
        try:
            trigger = self._create_trigger(automation.trigger_type, automation.trigger_config)
            
            self.scheduler.add_job(
                self._run_automation,
                trigger=trigger,
                id=automation.id,
                args=[automation.id],
                replace_existing=True
            )
            
            # Update next_run
            job = self.scheduler.get_job(automation.id)
            if job:
                automation.next_run = job.next_run_time.isoformat() if job.next_run_time else None
                self.db.save_automation(automation)
                
        except Exception as e:
            print(f"Failed to schedule automation {automation.id}: {e}")
            
    def _create_trigger(self, trigger_type: str, config: Dict):
        """Create a trigger from configuration"""
        if trigger_type == "cron":
            return CronTrigger(**config)
        elif trigger_type == "interval":
            return IntervalTrigger(**config)
        elif trigger_type == "date":
            return DateTrigger(**config)
        elif trigger_type == "rrule":
            # Parse rrule and convert to cron
            # Simplified - would use dateutil.rrule in production
            return CronTrigger(**config)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
            
    def _run_automation(self, automation_id: str):
        """Execute an automation"""
        automation = self.db.get_automation(automation_id)
        if not automation:
            return
            
        log = ExecutionLog(
            automation_id=automation_id,
            started_at=datetime.now().isoformat()
        )
        
        try:
            # Parse instruction and execute
            result = self._execute_instruction(automation.instruction)
            
            log.finished_at = datetime.now().isoformat()
            log.status = "success"
            log.result = str(result)[:1000]
            
            automation.success_count += 1
            automation.last_run = log.finished_at
            
        except Exception as e:
            log.finished_at = datetime.now().isoformat()
            log.status = "error"
            log.error = str(e)
            
            automation.error_count += 1
            
        finally:
            self.db.log_execution(log)
            self.db.save_automation(automation)
            
    def _execute_instruction(self, instruction: str) -> Any:
        """Execute an automation instruction"""
        # Parse instruction type
        if instruction.startswith("python:"):
            code = instruction[7:]
            return self._execute_python(code)
        elif instruction.startswith("shell:"):
            cmd = instruction[6:]
            return self._execute_shell(cmd)
        elif instruction.startswith("api:"):
            url = instruction[4:]
            return self._execute_api(url)
        else:
            # Default to shell
            return self._execute_shell(instruction)
            
    def _execute_python(self, code: str) -> Any:
        """Execute Python code"""
        local_vars = {}
        exec(code, {"__builtins__": __builtins__}, local_vars)
        return local_vars.get("result")
        
    def _execute_shell(self, command: str) -> str:
        """Execute shell command"""
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return result.stdout
        
    def _execute_api(self, url: str, method: str = "GET", data: dict = None) -> dict:
        """Make API call"""
        import requests
        resp = requests.request(method, url, json=data)
        return resp.json()
        
    def _execute_email(self, to: str, subject: str, body: str) -> dict:
        """Send email"""
        # Would use GmailClient
        return {"status": "would send email", "to": to}
        
    def _execute_notification(self, message: str, title: str = "Sentience") -> dict:
        """Send notification"""
        # Would use system notifications
        return {"status": "would notify", "message": message}
        
    def create_automation(self, name: str, instruction: str, trigger_type: str, 
                         trigger_config: Dict, enabled: bool = True) -> Automation:
        """Create a new automation"""
        import uuid
        
        automation = Automation(
            id=str(uuid.uuid4()),
            name=name,
            instruction=instruction,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            enabled=enabled
        )
        
        self.db.save_automation(automation)
        
        if enabled:
            self._schedule_automation(automation)
            
        return automation
        
    def update_automation(self, automation_id: str, **kwargs) -> Optional[Automation]:
        """Update an automation"""
        automation = self.db.get_automation(automation_id)
        if not automation:
            return None
            
        for key, value in kwargs.items():
            if hasattr(automation, key):
                setattr(automation, key, value)
                
        self.db.save_automation(automation)
        
        # Reschedule if needed
        if "trigger_type" in kwargs or "trigger_config" in kwargs:
            self.scheduler.remove_job(automation_id)
            self._schedule_automation(automation)
            
        return automation
        
    def delete_automation(self, automation_id: str):
        """Delete an automation"""
        self.scheduler.remove_job(automation_id)
        self.db.delete_automation(automation_id)
        
    def enable_automation(self, automation_id: str):
        """Enable an automation"""
        self.update_automation(automation_id, enabled=True)
        
    def disable_automation(self, automation_id: str):
        """Disable an automation"""
        self.scheduler.remove_job(automation_id)
        self.update_automation(automation_id, enabled=False)
        
    def run_now(self, automation_id: str):
        """Run an automation immediately"""
        self._run_automation(automation_id)


# Trigger templates
TRIGGER_TEMPLATES = {
    "daily_9am": {"trigger_type": "cron", "trigger_config": {"hour": 9, "minute": 0}},
    "hourly": {"trigger_type": "interval", "trigger_config": {"hours": 1}},
    "every_5_min": {"trigger_type": "interval", "trigger_config": {"minutes": 5}},
    "weekly_monday_9am": {"trigger_type": "cron", "trigger_config": {"day_of_week": "mon", "hour": 9}},
    "monthly_first": {"trigger_type": "cron", "trigger_config": {"day": 1, "hour": 9}},
}

# Automation templates
AUTOMATION_TEMPLATES = {
    "daily_report": {
        "name": "Daily Report",
        "instruction": "python:print('Daily report generated')",
        "trigger": TRIGGER_TEMPLATES["daily_9am"]
    },
    "backup_files": {
        "name": "Backup Files",
        "instruction": "shell:cp -r ~/Documents ~/backups/$(date +%Y%m%d)",
        "trigger": TRIGGER_TEMPLATES["daily_9am"]
    },
    "check_updates": {
        "name": "Check for Updates",
        "instruction": "shell:apt list --upgradable",
        "trigger": TRIGGER_TEMPLATES["daily_9am"]
    }
}
