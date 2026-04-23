"""
Persistent automation agent.
Background worker with self-healing, retry logic, and result notifications.
"""

import asyncio
import logging
import signal
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import uuid
import json

from .scheduler import Scheduler, SchedulerConfig
from .actions import (
    ActionExecutor, ActionStatus, ActionResult,
    create_action_from_config, ActionConfig
)
from .automation_db import (
    AutomationDB, Automation, AutomationStatus,
    Execution, ExecutionStatus, ErrorLog
)
from .triggers import TriggerManager, BaseTrigger

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """State of the automation agent."""
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    RECOVERING = "recovering"


@dataclass
class AgentConfig:
    """Configuration for the automation agent."""
    db_path: str = "automations/automations.db"
    max_concurrent_executions: int = 10
    health_check_interval: int = 60
    retry_delay: int = 30
    max_retries: int = 3
    notification_channels: List[str] = field(default_factory=lambda: ["log"])
    auto_recover: bool = True
    recovery_delay: int = 60


@dataclass
class ExecutionTask:
    """Represents a scheduled execution task."""
    task_id: str
    automation_id: str
    trigger_data: Dict[str, Any] = field(default_factory=dict)
    scheduled_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    priority: int = 0


class AutomationAgent:
    """
    Persistent automation agent that manages automations lifecycle.
    
    Features:
    - Background worker process
    - Self-healing on errors
    - Retry logic with exponential backoff
    - Result notifications
    - Health monitoring
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.state = AgentState.INITIALIZING
        
        # Core components
        self.db = AutomationDB(self.config.db_path)
        self.scheduler = Scheduler()
        self.executor = ActionExecutor()
        self.trigger_manager = TriggerManager()
        
        # Execution management
        self._task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_executions)
        
        # Tracking
        self._processed_tasks: Set[str] = set()
        self._health_status: Dict[str, Any] = {}
        self._start_time: Optional[datetime] = None
        self._last_activity: Optional[datetime] = None
        
        # Callbacks
        self._on_execution_complete: List[Callable] = []
        self._on_error: List[Callable] = []
        self._on_recovery: List[Callable] = []
        
        # Shutdown handling
        self._shutdown_event = asyncio.Event()
        
        logger.info("Automation agent initialized")
    
    # ==================== Lifecycle ====================
    
    async def start(self):
        """Start the automation agent."""
        if self.state == AgentState.RUNNING:
            logger.warning("Agent already running")
            return
        
        self.state = AgentState.STARTING
        self._start_time = datetime.now()
        
        try:
            # Load automations from database
            await self._load_automations()
            
            # Start scheduler
            self.scheduler.start()
            
            # Start health check loop
            asyncio.create_task(self._health_check_loop())
            
            # Start task processor
            asyncio.create_task(self._process_tasks_loop())
            
            self.state = AgentState.RUNNING
            logger.info("Automation agent started")
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"Failed to start agent: {e}")
            raise
    
    async def stop(self, wait: bool = True):
        """Stop the automation agent."""
        if self.state == AgentState.STOPPED:
            return
        
        self.state = AgentState.STOPPING
        self._shutdown_event.set()
        
        # Cancel running tasks
        for task_id, task in list(self._running_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Stop scheduler
        self.scheduler.stop(wait=wait)
        
        # Stop all triggers
        self.trigger_manager.stop_all()
        
        self.state = AgentState.STOPPED
        logger.info("Automation agent stopped")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self._handle_signal(s))
            )
    
    async def _handle_signal(self, sig):
        """Handle shutdown signal."""
        logger.info(f"Received signal {sig.name}, shutting down...")
        await self.stop()
    
    # ==================== Automation Management ====================
    
    async def _load_automations(self):
        """Load automations from database and schedule them."""
        automations = self.db.list_automations(status=AutomationStatus.ACTIVE)
        
        for automation in automations:
            try:
                await self._schedule_automation(automation)
            except Exception as e:
                logger.error(f"Failed to schedule automation {automation.id}: {e}")
                self._log_automation_error(automation, e)
        
        logger.info(f"Loaded {len(automations)} automations")
    
    async def _schedule_automation(self, automation: Automation):
        """Schedule an automation based on its trigger type."""
        trigger_type = automation.trigger_type
        trigger_config = automation.trigger_config
        
        # Create action from config
        action = create_action_from_config(
            automation.id,
            automation.action_type,
            automation.action_config
        )
        self.executor.register(action)
        
        # Schedule based on trigger type
        if trigger_type == "cron":
            self.scheduler.add_cron_job(
                self._create_job_func(automation.id),
                automation.id,
                trigger_config.get("expression", "* * * * *"),
                name=automation.name,
                **trigger_config.get("options", {})
            )
        
        elif trigger_type == "interval":
            self.scheduler.add_interval_job(
                self._create_job_func(automation.id),
                automation.id,
                seconds=trigger_config.get("seconds"),
                minutes=trigger_config.get("minutes"),
                hours=trigger_config.get("hours"),
                days=trigger_config.get("days"),
                name=automation.name,
                **trigger_config.get("options", {})
            )
        
        elif trigger_type == "date":
            run_date = datetime.fromisoformat(trigger_config.get("datetime"))
            self.scheduler.add_date_job(
                self._create_job_func(automation.id),
                automation.id,
                run_date,
                name=automation.name
            )
        
        elif trigger_type == "rrule":
            self.scheduler.add_rrule_job(
                self._create_job_func(automation.id),
                automation.id,
                trigger_config.get("rrule"),
                name=automation.name,
                **trigger_config.get("options", {})
            )
        
        elif trigger_type in ("file", "email", "webhook", "event", "conditional"):
            # Create trigger and register with manager
            trigger = self._create_trigger(automation)
            if trigger:
                trigger.on_trigger(lambda e: asyncio.create_task(
                    self._enqueue_execution(automation.id, e.data)
                ))
                self.trigger_manager.register(trigger)
                trigger.start()
        
        # Update next run time
        job = self.scheduler.get_job(automation.id)
        if job:
            automation.next_run = datetime.fromisoformat(job['next_run_time']) if job['next_run_time'] else None
            self.db.update_automation(automation)
        
        logger.info(f"Scheduled automation: {automation.id} ({trigger_type})")
    
    def _create_job_func(self, automation_id: str) -> Callable:
        """Create a job function for the scheduler."""
        async def job_func():
            await self._enqueue_execution(automation_id)
        return job_func
    
    def _create_trigger(self, automation: Automation) -> Optional[BaseTrigger]:
        """Create a trigger from automation config."""
        # This would create the appropriate trigger type
        # Implementation depends on trigger types defined in triggers.py
        from .triggers import (
            FileSystemTrigger, FileTriggerConfig, FileEventType,
            EmailTrigger, EmailTriggerConfig,
            WebhookTrigger, WebhookTriggerConfig,
            EventTrigger, EventSubscription,
            ConditionalTrigger, Condition
        )
        
        trigger_type = automation.trigger_type
        config = automation.trigger_config
        
        if trigger_type == "file":
            file_config = FileTriggerConfig(
                path=config.get("path", "."),
                event_types=[FileEventType(e) for e in config.get("events", ["modified"])],
                patterns=config.get("patterns", ["*"]),
                recursive=config.get("recursive", True)
            )
            return FileSystemTrigger(automation.id, file_config)
        
        elif trigger_type == "webhook":
            webhook_config = WebhookTriggerConfig(
                endpoint=config.get("endpoint", "/webhook"),
                secret=config.get("secret"),
                http_methods=config.get("methods", ["POST"])
            )
            return WebhookTrigger(automation.id, webhook_config)
        
        elif trigger_type == "event":
            subscriptions = [
                EventSubscription(
                    channel=sub.get("channel", "default"),
                    event_pattern=sub.get("pattern", "*")
                )
                for sub in config.get("subscriptions", [])
            ]
            return EventTrigger(automation.id, subscriptions)
        
        elif trigger_type == "conditional":
            conditions = [
                Condition(
                    field=c.get("field"),
                    operator=c.get("operator", "eq"),
                    value=c.get("value")
                )
                for c in config.get("conditions", [])
            ]
            return ConditionalTrigger(
                automation.id,
                conditions,
                mode=config.get("mode", "all")
            )
        
        return None
    
    async def add_automation(self, automation: Automation) -> Automation:
        """Add a new automation."""
        automation = self.db.create_automation(automation)
        
        if automation.status == AutomationStatus.ACTIVE:
            await self._schedule_automation(automation)
        
        return automation
    
    async def update_automation(self, automation: Automation) -> Automation:
        """Update an existing automation."""
        # Remove old scheduling
        self.scheduler.remove_job(automation.id)
        
        # Update database
        automation = self.db.update_automation(automation)
        
        # Reschedule if active
        if automation.status == AutomationStatus.ACTIVE:
            await self._schedule_automation(automation)
        
        return automation
    
    async def remove_automation(self, automation_id: str) -> bool:
        """Remove an automation."""
        self.scheduler.remove_job(automation_id)
        return self.db.delete_automation(automation_id)
    
    async def pause_automation(self, automation_id: str) -> Optional[Automation]:
        """Pause an automation."""
        automation = self.db.get_automation(automation_id)
        if automation:
            automation.status = AutomationStatus.PAUSED
            self.scheduler.pause_job(automation_id)
            return self.db.update_automation(automation)
        return None
    
    async def resume_automation(self, automation_id: str) -> Optional[Automation]:
        """Resume a paused automation."""
        automation = self.db.get_automation(automation_id)
        if automation:
            automation.status = AutomationStatus.ACTIVE
            self.scheduler.resume_job(automation_id)
            return self.db.update_automation(automation)
        return None
    
    # ==================== Execution ====================
    
    async def _enqueue_execution(
        self,
        automation_id: str,
        trigger_data: Optional[Dict[str, Any]] = None
    ):
        """Enqueue an execution task."""
        task_id = f"{automation_id}:{uuid.uuid4()}"
        
        task = ExecutionTask(
            task_id=task_id,
            automation_id=automation_id,
            trigger_data=trigger_data or {},
            scheduled_at=datetime.now()
        )
        
        await self._task_queue.put((task.priority, task.scheduled_at, task))
        self._last_activity = datetime.now()
        
        logger.debug(f"Enqueued execution: {task_id}")
    
    async def _process_tasks_loop(self):
        """Main loop for processing execution tasks."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for task with timeout
                try:
                    priority, scheduled_at, task = await asyncio.wait_for(
                        self._task_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Execute task
                asyncio.create_task(self._execute_task(task))
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Task processing error: {e}")
    
    async def _execute_task(self, task: ExecutionTask):
        """Execute an automation task."""
        async with self._semaphore:
            task_id = task.task_id
            automation_id = task.automation_id
            
            if task_id in self._processed_tasks:
                return
            
            self._processed_tasks.add(task_id)
            
            automation = self.db.get_automation(automation_id)
            if not automation:
                logger.error(f"Automation not found: {automation_id}")
                return
            
            # Create execution record
            execution = Execution(
                id=str(uuid.uuid4()),
                automation_id=automation_id,
                status=ExecutionStatus.RUNNING,
                started_at=datetime.now(),
                trigger_data=task.trigger_data,
                retry_count=task.retry_count
            )
            self.db.create_execution(execution)
            
            try:
                # Execute action
                result = await self.executor.execute(
                    automation_id,
                    context={
                        'automation': automation.to_dict(),
                        'trigger_data': task.trigger_data,
                        'execution_id': execution.id
                    }
                )
                
                # Update execution record
                execution.completed_at = datetime.now()
                execution.duration_ms = result.duration_ms
                execution.output = result.output
                execution.action_result = result.data or {}
                
                if result.status == ActionStatus.SUCCESS:
                    execution.status = ExecutionStatus.SUCCESS
                    automation.success_count += 1
                else:
                    execution.status = ExecutionStatus.FAILED
                    execution.error = result.error
                    automation.failure_count += 1
                    
                    # Log error
                    self._log_execution_error(automation, execution, result.error)
                    
                    # Retry logic
                    if task.retry_count < self.config.max_retries:
                        await self._schedule_retry(task, automation)
                
                automation.run_count += 1
                automation.last_run = datetime.now()
                self.db.update_automation(automation)
                
            except Exception as e:
                execution.status = ExecutionStatus.FAILED
                execution.error = str(e)
                execution.error_traceback = traceback.format_exc()
                execution.completed_at = datetime.now()
                
                self._log_execution_error(automation, execution, str(e))
            
            finally:
                self.db.update_execution(execution)
                
                # Notify callbacks
                await self._notify_execution_complete(execution)
                
                self._last_activity = datetime.now()
    
    async def _schedule_retry(self, task: ExecutionTask, automation: Automation):
        """Schedule a retry for failed execution."""
        retry_task = ExecutionTask(
            task_id=f"{task.automation_id}:{uuid.uuid4()}",
            automation_id=task.automation_id,
            trigger_data=task.trigger_data,
            scheduled_at=datetime.now() + timedelta(
                seconds=self.config.retry_delay * (2 ** task.retry_count)
            ),
            retry_count=task.retry_count + 1,
            priority=10  # Higher priority for retries
        )
        
        delay = (retry_task.scheduled_at - datetime.now()).total_seconds()
        await asyncio.sleep(delay)
        await self._task_queue.put((
            retry_task.priority,
            retry_task.scheduled_at,
            retry_task
        ))
        
        logger.info(f"Scheduled retry {retry_task.retry_count} for {task.automation_id}")
    
    # ==================== Health & Recovery ====================
    
    async def _health_check_loop(self):
        """Periodic health check loop."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def _perform_health_check(self):
        """Perform health check and recovery if needed."""
        self._health_status = {
            'timestamp': datetime.now().isoformat(),
            'state': self.state.value,
            'uptime_seconds': (datetime.now() - self._start_time).total_seconds() if self._start_time else 0,
            'scheduler_running': self.scheduler.running,
            'queue_size': self._task_queue.qsize(),
            'active_tasks': len(self._running_tasks),
            'last_activity': self._last_activity.isoformat() if self._last_activity else None
        }
        
        # Check for stalled tasks
        stalled = self._check_stalled_tasks()
        if stalled:
            logger.warning(f"Found {len(stalled)} stalled tasks")
            if self.config.auto_recover:
                await self._recover_stalled_tasks(stalled)
        
        # Check scheduler health
        if not self.scheduler.running and self.state == AgentState.RUNNING:
            logger.error("Scheduler not running, attempting recovery")
            if self.config.auto_recover:
                await self._recover_scheduler()
        
        # Update agent state
        if self.state == AgentState.RECOVERING:
            if self._health_status['scheduler_running']:
                self.state = AgentState.RUNNING
    
    def _check_stalled_tasks(self) -> List[str]:
        """Check for tasks that have been running too long."""
        stalled = []
        for task_id, task in self._running_tasks.items():
            if task.done():
                continue
            # Tasks running longer than 10 minutes are considered stalled
            # This would need actual timing tracking
        return stalled
    
    async def _recover_stalled_tasks(self, stalled: List[str]):
        """Recover stalled tasks."""
        for task_id in stalled:
            task = self._running_tasks.get(task_id)
            if task and not task.done():
                task.cancel()
                logger.info(f"Cancelled stalled task: {task_id}")
    
    async def _recover_scheduler(self):
        """Recover the scheduler."""
        self.state = AgentState.RECOVERING
        
        try:
            self.scheduler.stop(wait=False)
            await asyncio.sleep(1)
            self.scheduler.start()
            
            await self._notify_recovery("scheduler")
            self.state = AgentState.RUNNING
            logger.info("Scheduler recovered")
            
        except Exception as e:
            logger.error(f"Scheduler recovery failed: {e}")
            self.state = AgentState.ERROR
    
    # ==================== Error Handling ====================
    
    def _log_automation_error(self, automation: Automation, error: Exception):
        """Log an automation error."""
        error_log = ErrorLog(
            id=str(uuid.uuid4()),
            automation_id=automation.id,
            execution_id=None,
            error_type=type(error).__name__,
            error_message=str(error),
            error_traceback=traceback.format_exc()
        )
        self.db.log_error(error_log)
    
    def _log_execution_error(
        self,
        automation: Automation,
        execution: Execution,
        error: str
    ):
        """Log an execution error."""
        error_log = ErrorLog(
            id=str(uuid.uuid4()),
            automation_id=automation.id,
            execution_id=execution.id,
            error_type="ExecutionError",
            error_message=error,
            error_traceback=execution.error_traceback
        )
        self.db.log_error(error_log)
    
    # ==================== Notifications ====================
    
    def on_execution_complete(self, callback: Callable):
        """Register callback for execution completion."""
        self._on_execution_complete.append(callback)
    
    def on_error(self, callback: Callable):
        """Register callback for errors."""
        self._on_error.append(callback)
    
    def on_recovery(self, callback: Callable):
        """Register callback for recovery events."""
        self._on_recovery.append(callback)
    
    async def _notify_execution_complete(self, execution: Execution):
        """Notify callbacks of execution completion."""
        for callback in self._on_execution_complete:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(execution)
                else:
                    callback(execution)
            except Exception as e:
                logger.error(f"Execution callback error: {e}")
    
    async def _notify_error(self, error_log: ErrorLog):
        """Notify callbacks of errors."""
        for callback in self._on_error:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error_log)
                else:
                    callback(error_log)
            except Exception as e:
                logger.error(f"Error callback error: {e}")
    
    async def _notify_recovery(self, component: str):
        """Notify callbacks of recovery."""
        for callback in self._on_recovery:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(component)
                else:
                    callback(component)
            except Exception as e:
                logger.error(f"Recovery callback error: {e}")
    
    # ==================== Status & Metrics ====================
    
    @property
    def status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            'state': self.state.value,
            'uptime': (datetime.now() - self._start_time).total_seconds() if self._start_time else 0,
            'scheduler': self.scheduler.state,
            'queue_size': self._task_queue.qsize(),
            'active_tasks': len(self._running_tasks),
            'health': self._health_status,
            'db_metrics': self.db.get_overall_metrics()
        }
    
    async def run_now(self, automation_id: str) -> Optional[str]:
        """Execute an automation immediately."""
        automation = self.db.get_automation(automation_id)
        if automation:
            await self._enqueue_execution(automation_id)
            return automation_id
        return None
    
    def get_automation_status(self, automation_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific automation."""
        automation = self.db.get_automation(automation_id)
        if not automation:
            return None
        
        job = self.scheduler.get_job(automation_id)
        metrics = self.db.get_automation_metrics(automation_id)
        
        return {
            'automation': automation.to_dict(),
            'scheduled': job is not None,
            'next_run': job.get('next_run_time') if job else None,
            'metrics': metrics
        }


async def run_agent(config: Optional[AgentConfig] = None):
    """Run the automation agent as a standalone process."""
    agent = AutomationAgent(config)
    
    try:
        await agent.start()
        
        # Keep running until shutdown
        while agent.state != AgentState.STOPPED:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        await agent.stop()
    except Exception as e:
        logger.error(f"Agent error: {e}")
        await agent.stop()
        raise


def main():
    """Main entry point for standalone agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Automation Agent")
    parser.add_argument("--db", default="automations/automations.db", help="Database path")
    parser.add_argument("--max-concurrent", type=int, default=10, help="Max concurrent executions")
    parser.add_argument("--health-interval", type=int, default=60, help="Health check interval")
    parser.add_argument("--no-auto-recover", action="store_true", help="Disable auto recovery")
    
    args = parser.parse_args()
    
    config = AgentConfig(
        db_path=args.db,
        max_concurrent_executions=args.max_concurrent,
        health_check_interval=args.health_interval,
        auto_recover=not args.no_auto_recover
    )
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(run_agent(config))


if __name__ == "__main__":
    main()
