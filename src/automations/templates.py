"""
Pre-built automation templates.
Provides ready-to-use automations for common use cases.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .automation_db import Automation, AutomationStatus


@dataclass
class AutomationTemplate:
    """Template for creating automations."""
    id: str
    name: str
    description: str
    trigger_type: str
    trigger_config: Dict[str, Any]
    action_type: str
    action_config: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def create_automation(
        self,
        custom_id: Optional[str] = None,
        custom_name: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Automation:
        """Create an automation from this template."""
        import uuid
        
        # Merge custom config
        trigger_config = dict(self.trigger_config)
        action_config = dict(self.action_config)
        
        if custom_config:
            trigger_config.update(custom_config.get('trigger', {}))
            action_config.update(custom_config.get('action', {}))
        
        return Automation(
            id=custom_id or f"{self.id}_{uuid.uuid4().hex[:8]}",
            name=custom_name or self.name,
            description=self.description,
            trigger_type=self.trigger_type,
            trigger_config=trigger_config,
            action_type=self.action_type,
            action_config=action_config,
            status=AutomationStatus.ACTIVE,
            tags=self.tags.copy(),
            metadata={'template_id': self.id, **self.metadata}
        )


# ==================== Daily Report ====================

DAILY_REPORT_TEMPLATE = AutomationTemplate(
    id="daily_report",
    name="Daily Summary Report",
    description="Generates and sends a daily summary report via email",
    trigger_type="cron",
    trigger_config={
        "expression": "0 9 * * *",  # Every day at 9 AM
        "options": {
            "timezone": "UTC"
        }
    },
    action_type="python_script",
    action_config={
        "script_content": '''
import json
from datetime import datetime, timedelta
from collections import defaultdict

def generate_report(context):
    """
    Generate a daily report.
    
    Customizable report generation function.
    """
    # Example: Aggregate metrics from context
    metrics = context.get('metrics', {})
    events = context.get('events', [])
    
    report_lines = [
        f"# Daily Report - {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Summary",
        f"- Total events: {len(events)}",
        f"- Success rate: {metrics.get('success_rate', 'N/A')}%",
        "",
        "## Details",
    ]
    
    # Add event details
    for event in events[:10]:  # Top 10
        report_lines.append(f"- {event.get('name', 'Unknown')}: {event.get('status', 'N/A')}")
    
    return "\\n".join(report_lines)

def main(context=None):
    if context is None:
        context = {}
    
    report = generate_report(context)
    
    # Store result for email action
    result = {
        'report': report,
        'generated_at': datetime.now().isoformat()
    }
    
    print(report)
    return result
''',
        "function_name": "main"
    },
    tags=["report", "daily", "email"],
    metadata={
        "category": "reporting",
        "requires": ["metrics", "events"]
    }
)

DAILY_REPORT_EMAIL_TEMPLATE = AutomationTemplate(
    id="daily_report_email",
    name="Daily Report Email",
    description="Sends the daily report via email",
    trigger_type="event",
    trigger_config={
        "subscriptions": [
            {"channel": "reports", "pattern": "daily_report_complete"}
        ]
    },
    action_type="email",
    action_config={
        "to": "team@example.com",
        "subject": "Daily Report - {date}",
        "body": "{report}",
        "from_addr": "automation@example.com",
        "html": False,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "automation@example.com",
        "smtp_password": "${SMTP_PASSWORD}",
        "use_tls": True
    },
    tags=["report", "email", "daily"],
    metadata={
        "category": "reporting",
        "requires_env": ["SMTP_PASSWORD"]
    }
)


# ==================== File Backup ====================

FILE_BACKUP_TEMPLATE = AutomationTemplate(
    id="file_backup",
    name="Automated File Backup",
    description="Backs up specified files/directories to a backup location",
    trigger_type="cron",
    trigger_config={
        "expression": "0 2 * * *",  # Every day at 2 AM
        "options": {
            "timezone": "UTC"
        }
    },
    action_type="python_script",
    action_config={
        "script_content": '''
import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

def backup_files(sources, destination, compress=True, retain_days=7):
    """
    Backup files from source directories to destination.
    
    Args:
        sources: List of source paths to backup
        destination: Backup destination directory
        compress: Whether to compress the backup
        retain_days: Number of days to keep old backups
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"backup_{timestamp}"
    
    # Create destination if needed
    dest_path = Path(destination)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    backed_up = []
    errors = []
    
    if compress:
        # Create compressed archive
        archive_path = dest_path / f"{backup_name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            for source in sources:
                source_path = Path(source)
                if source_path.exists():
                    tar.add(source_path, arcname=source_path.name)
                    backed_up.append(str(source_path))
                else:
                    errors.append(f"Source not found: {source}")
    else:
        # Simple copy
        backup_dir = dest_path / backup_name
        backup_dir.mkdir()
        for source in sources:
            source_path = Path(source)
            if source_path.exists():
                dest = backup_dir / source_path.name
                if source_path.is_dir():
                    shutil.copytree(source_path, dest)
                else:
                    shutil.copy2(source_path, dest)
                backed_up.append(str(source_path))
            else:
                errors.append(f"Source not found: {source}")
    
    # Clean old backups
    cutoff = datetime.now() - timedelta(days=retain_days)
    for old_backup in dest_path.iterdir():
        if old_backup.stat().st_mtime < cutoff.timestamp():
            if old_backup.is_dir():
                shutil.rmtree(old_backup)
            else:
                old_backup.unlink()
    
    return {
        'backed_up': backed_up,
        'errors': errors,
        'destination': str(dest_path),
        'archive': str(archive_path) if compress else None
    }

def main(context=None):
    # Default configuration - override via context
    sources = context.get('sources', ['/data', '/config']) if context else ['/data', '/config']
    destination = context.get('destination', '/backups') if context else '/backups'
    compress = context.get('compress', True)
    retain_days = context.get('retain_days', 7)
    
    result = backup_files(sources, destination, compress, retain_days)
    
    print(f"Backup complete: {len(result['backed_up'])} items")
    if result['errors']:
        print(f"Errors: {result['errors']}")
    
    return result
''',
        "function_name": "main"
    },
    tags=["backup", "maintenance", "scheduled"],
    metadata={
        "category": "maintenance",
        "configurable": ["sources", "destination", "compress", "retain_days"]
    }
)

FILE_BACKUP_ON_CHANGE_TEMPLATE = AutomationTemplate(
    id="file_backup_on_change",
    name="Backup on File Change",
    description="Triggers backup when important files are modified",
    trigger_type="file",
    trigger_config={
        "path": "/data/important",
        "events": ["modified", "created"],
        "patterns": ["*.conf", "*.yaml", "*.json"],
        "recursive": True,
        "debounce_seconds": 300  # 5 minute debounce
    },
    action_type="shell_command",
    action_config={
        "command": "tar -czf /backups/incremental_$(date +%Y%m%d_%H%M%S).tar.gz -C /data/important ."
    },
    tags=["backup", "file", "real-time"],
    metadata={
        "category": "backup",
        "trigger": "file_change"
    }
)


# ==================== Email Digest ====================

EMAIL_DIGEST_TEMPLATE = AutomationTemplate(
    id="email_digest",
    name="Weekly Email Digest",
    description="Compiles and sends a weekly digest of important emails",
    trigger_type="cron",
    trigger_config={
        "expression": "0 18 * * 5",  # Every Friday at 6 PM
        "options": {
            "timezone": "UTC"
        }
    },
    action_type="python_script",
    action_config={
        "script_content": '''
import json
from datetime import datetime, timedelta
from collections import defaultdict

def compile_digest(emails, categories=None):
    """
    Compile a digest from emails.
    
    Args:
        emails: List of email data
        categories: Optional category filters
    """
    if categories is None:
        categories = ['important', 'urgent', 'action_required']
    
    # Group by category
    grouped = defaultdict(list)
    for email in emails:
        category = email.get('category', 'other')
        if category in categories or 'other' in categories:
            grouped[category].append(email)
    
    # Build digest
    lines = [
        "# Weekly Email Digest",
        f"Period: {(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}",
        ""
    ]
    
    for category, items in grouped.items():
        lines.append(f"## {category.title()} ({len(items)} emails)")
        for item in items[:5]:  # Top 5 per category
            lines.append(f"- **{item.get('subject', 'No Subject')}**")
            lines.append(f"  From: {item.get('sender', 'Unknown')}")
            lines.append(f"  Date: {item.get('date', 'Unknown')}")
        lines.append("")
    
    return "\\n".join(lines)

def main(context=None):
    # Would fetch emails from context or API
    emails = context.get('emails', []) if context else []
    categories = context.get('categories') if context else None
    
    digest = compile_digest(emails, categories)
    
    return {
        'digest': digest,
        'email_count': sum(len(items) for items in emails),
        'generated_at': datetime.now().isoformat()
    }
''',
        "function_name": "main"
    },
    tags=["email", "digest", "weekly"],
    metadata={
        "category": "communication",
        "requires": ["emails"]
    }
)

EMAIL_DIGEST_SEND_TEMPLATE = AutomationTemplate(
    id="email_digest_send",
    name="Send Email Digest",
    description="Sends the compiled email digest",
    trigger_type="event",
    trigger_config={
        "subscriptions": [
            {"channel": "digests", "pattern": "email_digest_complete"}
        ]
    },
    action_type="email",
    action_config={
        "to": "user@example.com",
        "subject": "Weekly Email Digest",
        "body": "{digest}",
        "html": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587
    },
    tags=["email", "digest"],
    metadata={
        "category": "communication"
    }
)


# ==================== System Cleanup ====================

SYSTEM_CLEANUP_TEMPLATE = AutomationTemplate(
    id="system_cleanup",
    name="Automated System Cleanup",
    description="Cleans up temporary files, logs, and cache",
    trigger_type="cron",
    trigger_config={
        "expression": "0 3 * * 0",  # Every Sunday at 3 AM
        "options": {
            "timezone": "UTC"
        }
    },
    action_type="python_script",
    action_config={
        "script_content": '''
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

def cleanup_system(directories, max_age_days=7, min_free_space_gb=10):
    """
    Clean up system directories.
    
    Args:
        directories: Dict of directory path -> cleanup config
        max_age_days: Default max age for files
        min_free_space_gb: Minimum free space to maintain
    """
    cleaned = []
    errors = []
    space_freed = 0
    
    now = datetime.now()
    cutoff = now - timedelta(days=max_age_days)
    
    for dir_path, config in directories.items():
        path = Path(dir_path)
        if not path.exists():
            errors.append(f"Directory not found: {dir_path}")
            continue
        
        dir_max_age = config.get('max_age_days', max_age_days)
        patterns = config.get('patterns', ['*'])
        recursive = config.get('recursive', True)
        
        dir_cutoff = now - timedelta(days=dir_max_age)
        
        # Walk directory
        for pattern in patterns:
            if recursive:
                files = path.rglob(pattern)
            else:
                files = path.glob(pattern)
            
            for file in files:
                if not file.is_file():
                    continue
                
                # Check age
                mtime = datetime.fromtimestamp(file.stat().st_mtime)
                if mtime > dir_cutoff:
                    continue
                
                # Check size
                size = file.stat().st_size
                
                try:
                    file.unlink()
                    cleaned.append(str(file))
                    space_freed += size
                except Exception as e:
                    errors.append(f"Failed to delete {file}: {e}")
    
    # Check disk space
    disk_usage = shutil.disk_usage('/')
    free_gb = disk_usage.free / (1024**3)
    
    if free_gb < min_free_space_gb:
        errors.append(f"Low disk space: {free_gb:.2f} GB free")
    
    return {
        'cleaned_count': len(cleaned),
        'space_freed_mb': space_freed / (1024**2),
        'errors': errors,
        'free_space_gb': free_gb
    }

def main(context=None):
    directories = context.get('directories') if context else {
        '/tmp': {'max_age_days': 1, 'recursive': True},
        '/var/log': {'max_age_days': 30, 'patterns': ['*.log', '*.log.*']},
        '/var/cache': {'max_age_days': 7, 'recursive': True}
    }
    max_age_days = context.get('max_age_days', 7) if context else 7
    min_free_space_gb = context.get('min_free_space_gb', 10) if context else 10
    
    result = cleanup_system(directories, max_age_days, min_free_space_gb)
    
    print(f"Cleanup complete: {result['cleaned_count']} files, {result['space_freed_mb']:.2f} MB freed")
    
    return result
''',
        "function_name": "main"
    },
    tags=["cleanup", "maintenance", "scheduled"],
    metadata={
        "category": "maintenance",
        "configurable": ["directories", "max_age_days", "min_free_space_gb"]
    }
)

LOG_ROTATION_TEMPLATE = AutomationTemplate(
    id="log_rotation",
    name="Log Rotation",
    description="Rotates and compresses log files",
    trigger_type="cron",
    trigger_config={
        "expression": "0 0 * * *",  # Every day at midnight
        "options": {
            "timezone": "UTC"
        }
    },
    action_type="shell_command",
    action_config={
        "command": "find /var/log -name '*.log' -size +100M -exec gzip {} \\;"
    },
    tags=["logs", "maintenance", "daily"],
    metadata={
        "category": "maintenance"
    }
)


# ==================== API Monitoring ====================

API_HEALTH_CHECK_TEMPLATE = AutomationTemplate(
    id="api_health_check",
    name="API Health Check",
    description="Monitors API endpoints and sends alerts on failure",
    trigger_type="interval",
    trigger_config={
        "minutes": 5,
        "options": {
            "misfire_grace_time": 60
        }
    },
    action_type="python_script",
    action_config={
        "script_content": '''
import json
from datetime import datetime

def check_api_health(endpoints):
    """
    Check health of API endpoints.
    
    Args:
        endpoints: List of endpoint configs with url, method, expected_status
    """
    import urllib.request
    import urllib.error
    
    results = []
    failures = []
    
    for endpoint in endpoints:
        url = endpoint.get('url')
        method = endpoint.get('method', 'GET')
        expected_status = endpoint.get('expected_status', 200)
        timeout = endpoint.get('timeout', 10)
        
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = response.status
                healthy = status == expected_status
                
                results.append({
                    'url': url,
                    'status': status,
                    'healthy': healthy,
                    'response_time_ms': 0  # Would need timing
                })
                
                if not healthy:
                    failures.append({
                        'url': url,
                        'expected': expected_status,
                        'actual': status
                    })
        
        except urllib.error.URLError as e:
            results.append({
                'url': url,
                'status': None,
                'healthy': False,
                'error': str(e)
            })
            failures.append({
                'url': url,
                'error': str(e)
            })
        
        except Exception as e:
            results.append({
                'url': url,
                'status': None,
                'healthy': False,
                'error': str(e)
            })
            failures.append({
                'url': url,
                'error': str(e)
            })
    
    return {
        'results': results,
        'failures': failures,
        'healthy_count': len([r for r in results if r.get('healthy')]),
        'total_count': len(endpoints),
        'timestamp': datetime.now().isoformat()
    }

def main(context=None):
    endpoints = context.get('endpoints') if context else [
        {'url': 'http://localhost:8000/health', 'expected_status': 200},
        {'url': 'http://localhost:8000/api/status', 'expected_status': 200}
    ]
    
    result = check_api_health(endpoints)
    
    if result['failures']:
        print(f"ALERT: {len(result['failures'])} endpoints failing!")
        for failure in result['failures']:
            print(f"  - {failure}")
    else:
        print(f"All {result['healthy_count']} endpoints healthy")
    
    return result
''',
        "function_name": "main"
    },
    tags=["monitoring", "api", "health"],
    metadata={
        "category": "monitoring",
        "configurable": ["endpoints"]
    }
)

API_ALERT_TEMPLATE = AutomationTemplate(
    id="api_alert",
    name="API Failure Alert",
    description="Sends alert when API health check fails",
    trigger_type="conditional",
    trigger_config={
        "conditions": [
            {"field": "failures", "operator": "is_not_none"},
            {"field": "failures", "operator": "contains", "value": "url"}
        ],
        "mode": "all"
    },
    action_type="notification",
    action_config={
        "title": "API Health Alert",
        "message": "{failures_count} endpoints are failing",
        "level": "error",
        "channels": ["default"],
        "sound": True
    },
    tags=["monitoring", "alert", "api"],
    metadata={
        "category": "monitoring"
    }
)

API_DOWNTIME_REPORT_TEMPLATE = AutomationTemplate(
    id="api_downtime_report",
    name="API Downtime Report",
    description="Generates daily report of API downtime incidents",
    trigger_type="cron",
    trigger_config={
        "expression": "0 8 * * *",  # Every day at 8 AM
        "options": {
            "timezone": "UTC"
        }
    },
    action_type="api_call",
    action_config={
        "url": "http://localhost:8000/api/metrics/downtime",
        "method": "GET",
        "headers": {
            "Accept": "application/json"
        }
    },
    tags=["monitoring", "api", "report"],
    metadata={
        "category": "monitoring"
    }
)


# ==================== Template Registry ====================

TEMPLATE_REGISTRY = {
    "daily_report": DAILY_REPORT_TEMPLATE,
    "daily_report_email": DAILY_REPORT_EMAIL_TEMPLATE,
    "file_backup": FILE_BACKUP_TEMPLATE,
    "file_backup_on_change": FILE_BACKUP_ON_CHANGE_TEMPLATE,
    "email_digest": EMAIL_DIGEST_TEMPLATE,
    "email_digest_send": EMAIL_DIGEST_SEND_TEMPLATE,
    "system_cleanup": SYSTEM_CLEANUP_TEMPLATE,
    "log_rotation": LOG_ROTATION_TEMPLATE,
    "api_health_check": API_HEALTH_CHECK_TEMPLATE,
    "api_alert": API_ALERT_TEMPLATE,
    "api_downtime_report": API_DOWNTIME_REPORT_TEMPLATE
}


def get_template(template_id: str) -> Optional[AutomationTemplate]:
    """Get a template by ID."""
    return TEMPLATE_REGISTRY.get(template_id)


def list_templates(category: Optional[str] = None) -> List[AutomationTemplate]:
    """List available templates, optionally filtered by category."""
    templates = list(TEMPLATE_REGISTRY.values())
    
    if category:
        templates = [t for t in templates if t.metadata.get('category') == category]
    
    return templates


def create_from_template(
    template_id: str,
    custom_id: Optional[str] = None,
    custom_name: Optional[str] = None,
    custom_config: Optional[Dict[str, Any]] = None
) -> Optional[Automation]:
    """Create an automation from a template."""
    template = get_template(template_id)
    if template:
        return template.create_automation(custom_id, custom_name, custom_config)
    return None


def get_template_categories() -> List[str]:
    """Get list of template categories."""
    categories = set()
    for template in TEMPLATE_REGISTRY.values():
        if 'category' in template.metadata:
            categories.add(template.metadata['category'])
    return list(categories)
