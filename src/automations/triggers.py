"""
Custom triggers for automation scheduler.
Includes file system, email, webhook, event-based, and conditional triggers.
"""

import asyncio
import logging
import os
import re
import json
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union
from dataclasses import dataclass, field
from enum import Enum
import threading
from queue import Queue, Empty

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent
)

logger = logging.getLogger(__name__)


class TriggerState(Enum):
    """State of a trigger."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    TRIGGERED = "triggered"
    ERROR = "error"


@dataclass
class TriggerEvent:
    """Event generated when a trigger fires."""
    trigger_id: str
    trigger_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseTrigger(ABC):
    """Base class for all triggers."""
    
    def __init__(self, trigger_id: str):
        self.trigger_id = trigger_id
        self.state = TriggerState.INACTIVE
        self._callbacks: List[Callable[[TriggerEvent], None]] = []
        self._last_triggered: Optional[datetime] = None
        self._trigger_count: int = 0
        self._error: Optional[str] = None
    
    def on_trigger(self, callback: Callable[[TriggerEvent], None]):
        """Register a callback for when the trigger fires."""
        self._callbacks.append(callback)
    
    def off_trigger(self, callback: Callable[[TriggerEvent], None]):
        """Unregister a callback."""
        self._callbacks.remove(callback)
    
    def _fire(self, data: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None):
        """Fire the trigger and call all registered callbacks."""
        event = TriggerEvent(
            trigger_id=self.trigger_id,
            trigger_type=self.__class__.__name__,
            data=data or {},
            metadata=metadata or {}
        )
        
        self._last_triggered = datetime.now()
        self._trigger_count += 1
        self.state = TriggerState.TRIGGERED
        
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Callback error for trigger {self.trigger_id}: {e}")
        
        # Reset to active after firing
        self.state = TriggerState.ACTIVE
    
    @abstractmethod
    def start(self):
        """Start monitoring for trigger conditions."""
        pass
    
    @abstractmethod
    def stop(self):
        """Stop monitoring."""
        pass
    
    def reset(self):
        """Reset trigger state."""
        self.state = TriggerState.INACTIVE
        self._error = None


class FileEventType(Enum):
    """Types of file events to watch."""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass
class FileTriggerConfig:
    """Configuration for file system trigger."""
    path: str
    event_types: List[FileEventType] = field(default_factory=lambda: [FileEventType.MODIFIED])
    patterns: List[str] = field(default_factory=lambda: ["*"])
    ignore_patterns: List[str] = field(default_factory=list)
    recursive: bool = True
    debounce_seconds: float = 1.0


class FileSystemTrigger(BaseTrigger):
    """
    File system trigger using watchdog.
    
    Fires when files are created, modified, deleted, or moved.
    Supports pattern matching and debouncing.
    """
    
    def __init__(
        self,
        trigger_id: str,
        config: FileTriggerConfig
    ):
        super().__init__(trigger_id)
        self.config = config
        self._observer: Optional[Observer] = None
        self._handler: Optional[FileSystemEventHandler] = None
        self._pending_events: Dict[str, datetime] = {}
        self._debounce_task: Optional[asyncio.Task] = None
    
    def start(self):
        """Start watching the file system."""
        if self.state == TriggerState.ACTIVE:
            return
        
        path = Path(self.config.path)
        if not path.exists():
            logger.warning(f"Watch path does not exist: {self.config.path}")
        
        self._handler = _FileEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            self.config.path,
            recursive=self.config.recursive
        )
        self._observer.start()
        self.state = TriggerState.ACTIVE
        
        logger.info(f"Started file trigger {self.trigger_id} watching {self.config.path}")
    
    def stop(self):
        """Stop watching the file system."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self.state = TriggerState.INACTIVE
        logger.info(f"Stopped file trigger {self.trigger_id}")
    
    def _handle_event(self, event_type: FileEventType, src_path: str, dest_path: Optional[str] = None):
        """Handle a file system event."""
        # Check pattern match
        filename = os.path.basename(src_path)
        matches_pattern = any(
            fnmatch.fnmatch(filename, pattern)
            for pattern in self.config.patterns
        )
        if not matches_pattern:
            return
        
        # Check ignore pattern
        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return
        
        # Check event type
        if event_type not in self.config.event_types:
            return
        
        # Debounce
        key = f"{src_path}:{event_type.value}"
        now = datetime.now()
        
        if key in self._pending_events:
            last_time = self._pending_events[key]
            if (now - last_time).total_seconds() < self.config.debounce_seconds:
                return
        
        self._pending_events[key] = now
        
        # Fire trigger
        data = {
            'event_type': event_type.value,
            'src_path': src_path
        }
        if dest_path:
            data['dest_path'] = dest_path
        
        self._fire(data)
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get trigger statistics."""
        return {
            'trigger_id': self.trigger_id,
            'state': self.state.value,
            'watch_path': self.config.path,
            'last_triggered': self._last_triggered.isoformat() if self._last_triggered else None,
            'trigger_count': self._trigger_count
        }


class _FileEventHandler(FileSystemEventHandler):
    """Internal handler for watchdog events."""
    
    def __init__(self, trigger: FileSystemTrigger):
        self.trigger = trigger
        super().__init__()
    
    def on_created(self, event):
        if not event.is_directory:
            self.trigger._handle_event(FileEventType.CREATED, event.src_path)
    
    def on_modified(self, event):
        if not event.is_directory:
            self.trigger._handle_event(FileEventType.MODIFIED, event.src_path)
    
    def on_deleted(self, event):
        if not event.is_directory:
            self.trigger._handle_event(FileEventType.DELETED, event.src_path)
    
    def on_moved(self, event):
        if not event.is_directory:
            self.trigger._handle_event(FileEventType.MOVED, event.src_path, event.dest_path)


import fnmatch


@dataclass
class EmailTriggerConfig:
    """Configuration for email trigger."""
    inbox_path: Optional[str] = None
    sender_filter: Optional[str] = None
    subject_filter: Optional[str] = None
    body_pattern: Optional[str] = None
    has_attachment: Optional[bool] = None
    folder: str = "INBOX"
    poll_interval: int = 60


class EmailTrigger(BaseTrigger):
    """
    Email trigger that monitors inbox for matching emails.
    
    Filters by sender, subject, body pattern, and attachments.
    """
    
    def __init__(
        self,
        trigger_id: str,
        config: EmailTriggerConfig,
        email_client: Optional[Any] = None
    ):
        super().__init__(trigger_id)
        self.config = config
        self.email_client = email_client
        self._poll_task: Optional[asyncio.Task] = None
        self._seen_ids: Set[str] = set()
    
    def start(self):
        """Start polling for emails."""
        if self.state == TriggerState.ACTIVE:
            return
        
        self.state = TriggerState.ACTIVE
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"Started email trigger {self.trigger_id}")
    
    def stop(self):
        """Stop polling for emails."""
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        self.state = TriggerState.INACTIVE
        logger.info(f"Stopped email trigger {self.trigger_id}")
    
    async def _poll_loop(self):
        """Polling loop for email checking."""
        while self.state == TriggerState.ACTIVE:
            try:
                await self._check_emails()
            except Exception as e:
                logger.error(f"Email trigger {self.trigger_id} error: {e}")
                self._error = str(e)
            
            await asyncio.sleep(self.config.poll_interval)
    
    async def _check_emails(self):
        """Check for new matching emails."""
        if not self.email_client:
            logger.warning(f"Email trigger {self.trigger_id} has no email client configured")
            return
        
        # This would integrate with actual email client
        # Placeholder for email fetching logic
        emails = await self._fetch_emails()
        
        for email in emails:
            email_id = email.get('id')
            if email_id in self._seen_ids:
                continue
            
            if self._matches_filters(email):
                self._seen_ids.add(email_id)
                self._fire({
                    'email_id': email_id,
                    'sender': email.get('sender'),
                    'subject': email.get('subject'),
                    'body': email.get('body', '')[:500],
                    'has_attachments': email.get('has_attachments', False),
                    'received_at': email.get('date')
                })
    
    async def _fetch_emails(self) -> List[Dict[str, Any]]:
        """Fetch emails from the configured inbox."""
        # Placeholder - would integrate with IMAP/Gmail API
        return []
    
    def _matches_filters(self, email: Dict[str, Any]) -> bool:
        """Check if email matches configured filters."""
        if self.config.sender_filter:
            if not re.search(self.config.sender_filter, email.get('sender', '')):
                return False
        
        if self.config.subject_filter:
            if not re.search(self.config.subject_filter, email.get('subject', '')):
                return False
        
        if self.config.body_pattern:
            if not re.search(self.config.body_pattern, email.get('body', '')):
                return False
        
        if self.config.has_attachment is not None:
            if email.get('has_attachments', False) != self.config.has_attachment:
                return False
        
        return True


@dataclass
class WebhookTriggerConfig:
    """Configuration for webhook trigger."""
    endpoint: str
    secret: Optional[str] = None
    allowed_ips: List[str] = field(default_factory=list)
    http_methods: List[str] = field(default_factory=lambda: ["POST"])
    require_auth: bool = False
    auth_header: Optional[str] = None


class WebhookTrigger(BaseTrigger):
    """
    Webhook trigger that fires on HTTP requests.
    
    Supports IP whitelisting, secret verification, and authentication.
    """
    
    def __init__(
        self,
        trigger_id: str,
        config: WebhookTriggerConfig
    ):
        super().__init__(trigger_id)
        self.config = config
        self._request_queue: Queue = Queue()
    
    def start(self):
        """Mark webhook as active (actual serving is handled by HTTP server)."""
        self.state = TriggerState.ACTIVE
        logger.info(f"Webhook trigger {self.trigger_id} active at {self.config.endpoint}")
    
    def stop(self):
        """Deactivate webhook."""
        self.state = TriggerState.INACTIVE
        logger.info(f"Webhook trigger {self.trigger_id} deactivated")
    
    def process_request(
        self,
        method: str,
        headers: Dict[str, str],
        body: str,
        client_ip: str
    ) -> Dict[str, Any]:
        """
        Process an incoming HTTP request.
        
        Returns:
            Response dict with 'status' and 'message'
        """
        # Check method
        if method.upper() not in [m.upper() for m in self.config.http_methods]:
            return {'status': 405, 'message': 'Method not allowed'}
        
        # Check IP
        if self.config.allowed_ips and client_ip not in self.config.allowed_ips:
            return {'status': 403, 'message': 'Forbidden'}
        
        # Check auth
        if self.config.require_auth:
            auth_header = headers.get('authorization', '')
            if not auth_header or auth_header != self.config.auth_header:
                return {'status': 401, 'message': 'Unauthorized'}
        
        # Verify secret (HMAC signature)
        if self.config.secret:
            signature = headers.get('x-webhook-signature', '')
            expected = self._compute_signature(body)
            if signature != expected:
                return {'status': 401, 'message': 'Invalid signature'}
        
        # Fire trigger
        self._fire({
            'method': method,
            'endpoint': self.config.endpoint,
            'headers': headers,
            'body': body,
            'client_ip': client_ip
        })
        
        return {'status': 200, 'message': 'OK'}
    
    def _compute_signature(self, body: str) -> str:
        """Compute HMAC signature for body."""
        import hmac
        return hmac.new(
            self.config.secret.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()


@dataclass
class EventSubscription:
    """Subscription to an event channel."""
    channel: str
    event_pattern: str = "*"
    priority: int = 0


class EventTrigger(BaseTrigger):
    """
    Event-based trigger that fires on custom events.
    
    Supports pub/sub pattern with channels and event patterns.
    """
    
    _channels: Dict[str, List['EventTrigger']] = {}
    
    def __init__(
        self,
        trigger_id: str,
        subscriptions: List[EventSubscription]
    ):
        super().__init__(trigger_id)
        self.subscriptions = subscriptions
        self._event_history: List[Dict[str, Any]] = []
    
    def start(self):
        """Subscribe to configured channels."""
        for sub in self.subscriptions:
            if sub.channel not in EventTrigger._channels:
                EventTrigger._channels[sub.channel] = []
            EventTrigger._channels[sub.channel].append(self)
        
        self.state = TriggerState.ACTIVE
        logger.info(f"Event trigger {self.trigger_id} subscribed to {[s.channel for s in self.subscriptions]}")
    
    def stop(self):
        """Unsubscribe from channels."""
        for sub in self.subscriptions:
            if sub.channel in EventTrigger._channels:
                if self in EventTrigger._channels[sub.channel]:
                    EventTrigger._channels[sub.channel].remove(self)
        
        self.state = TriggerState.INACTIVE
        logger.info(f"Event trigger {self.trigger_id} unsubscribed")
    
    @classmethod
    def emit(cls, channel: str, event_name: str, data: Optional[Dict[str, Any]] = None):
        """Emit an event to all subscribers on a channel."""
        if channel not in cls._channels:
            return
        
        for trigger in cls._channels[channel]:
            for sub in trigger.subscriptions:
                if sub.channel != channel:
                    continue
                
                # Match event pattern
                if not fnmatch.fnmatch(event_name, sub.event_pattern):
                    continue
                
                # Fire trigger
                trigger._fire({
                    'channel': channel,
                    'event_name': event_name,
                    'data': data or {}
                })
                
                # Store in history
                trigger._event_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'channel': channel,
                    'event_name': event_name,
                    'data': data
                })
    
    @property
    def history(self) -> List[Dict[str, Any]]:
        """Get event history."""
        return self._event_history.copy()


@dataclass
class Condition:
    """A condition to evaluate."""
    field: str
    operator: str  # eq, ne, gt, gte, lt, lte, contains, matches, in, not_in
    value: Any


class ConditionalTrigger(BaseTrigger):
    """
    Trigger that fires when conditions are met.
    
    Evaluates conditions against provided context.
    """
    
    def __init__(
        self,
        trigger_id: str,
        conditions: List[Condition],
        mode: str = "all"  # "all" or "any"
    ):
        super().__init__(trigger_id)
        self.conditions = conditions
        self.mode = mode
        self._evaluation_count: int = 0
        self._match_count: int = 0
    
    def start(self):
        """Activate the trigger."""
        self.state = TriggerState.ACTIVE
        logger.info(f"Conditional trigger {self.trigger_id} active")
    
    def stop(self):
        """Deactivate the trigger."""
        self.state = TriggerState.INACTIVE
        logger.info(f"Conditional trigger {self.trigger_id} inactive")
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Evaluate conditions against context.
        
        Returns True and fires if conditions match.
        """
        if self.state != TriggerState.ACTIVE:
            return False
        
        self._evaluation_count += 1
        results = []
        
        for condition in self.conditions:
            result = self._evaluate_condition(condition, context)
            results.append(result)
        
        matched = all(results) if self.mode == "all" else any(results)
        
        if matched:
            self._match_count += 1
            self._fire({
                'context': context,
                'conditions_matched': [
                    {'field': c.field, 'operator': c.operator, 'value': c.value}
                    for i, c in enumerate(self.conditions) if results[i]
                ]
            })
        
        return matched
    
    def _evaluate_condition(self, condition: Condition, context: Dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        # Get field value from context (supports nested access)
        value = self._get_nested_value(context, condition.field)
        
        if value is None:
            return False
        
        op = condition.operator.lower()
        target = condition.value
        
        if op == 'eq':
            return value == target
        elif op == 'ne':
            return value != target
        elif op == 'gt':
            return value > target
        elif op == 'gte':
            return value >= target
        elif op == 'lt':
            return value < target
        elif op == 'lte':
            return value <= target
        elif op == 'contains':
            return target in value
        elif op == 'matches':
            return bool(re.search(target, str(value)))
        elif op == 'in':
            return value in target
        elif op == 'not_in':
            return value not in target
        elif op == 'is_none':
            return value is None
        elif op == 'is_not_none':
            return value is not None
        elif op == 'is_true':
            return bool(value)
        elif op == 'is_false':
            return not bool(value)
        else:
            logger.warning(f"Unknown operator: {op}")
            return False
    
    def _get_nested_value(self, context: Dict[str, Any], path: str) -> Any:
        """Get a nested value from context using dot notation."""
        parts = path.split('.')
        value = context
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                idx = int(part)
                value = value[idx] if 0 <= idx < len(value) else None
            else:
                return None
        
        return value
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get trigger statistics."""
        return {
            'trigger_id': self.trigger_id,
            'state': self.state.value,
            'conditions_count': len(self.conditions),
            'mode': self.mode,
            'evaluation_count': self._evaluation_count,
            'match_count': self._match_count,
            'match_rate': self._match_count / self._evaluation_count if self._evaluation_count > 0 else 0,
            'last_triggered': self._last_triggered.isoformat() if self._last_triggered else None
        }


class TriggerManager:
    """Manager for all triggers."""
    
    def __init__(self):
        self._triggers: Dict[str, BaseTrigger] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
    
    def register(self, trigger: BaseTrigger, callback: Optional[Callable] = None):
        """Register a trigger with optional callback."""
        self._triggers[trigger.trigger_id] = trigger
        
        if callback:
            if trigger.trigger_id not in self._callbacks:
                self._callbacks[trigger.trigger_id] = []
            self._callbacks[trigger.trigger_id].append(callback)
            trigger.on_trigger(callback)
    
    def unregister(self, trigger_id: str):
        """Unregister a trigger."""
        if trigger_id in self._triggers:
            trigger = self._triggers[trigger_id]
            trigger.stop()
            
            if trigger_id in self._callbacks:
                for callback in self._callbacks[trigger_id]:
                    trigger.off_trigger(callback)
                del self._callbacks[trigger_id]
            
            del self._triggers[trigger_id]
    
    def get(self, trigger_id: str) -> Optional[BaseTrigger]:
        """Get a trigger by ID."""
        return self._triggers.get(trigger_id)
    
    def start_all(self):
        """Start all registered triggers."""
        for trigger in self._triggers.values():
            trigger.start()
    
    def stop_all(self):
        """Stop all registered triggers."""
        for trigger in self._triggers.values():
            trigger.stop()
    
    def list_triggers(self) -> List[Dict[str, Any]]:
        """List all triggers with their status."""
        result = []
        for trigger in self._triggers.values():
            result.append({
                'id': trigger.trigger_id,
                'type': trigger.__class__.__name__,
                'state': trigger.state.value,
                'last_triggered': trigger._last_triggered.isoformat() if trigger._last_triggered else None
            })
        return result
