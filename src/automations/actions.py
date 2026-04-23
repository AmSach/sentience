"""
Action executor for automation scheduler.
Supports Python scripts, shell commands, API calls, emails, and notifications.
"""

import asyncio
import logging
import os
import sys
import subprocess
import json
import smtplib
import aiohttp
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from enum import Enum
import traceback
import tempfile
import importlib.util

logger = logging.getLogger(__name__)


class ActionStatus(Enum):
    """Status of action execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ActionResult:
    """Result of action execution."""
    action_id: str
    action_type: str
    status: ActionStatus
    output: Optional[str] = None
    error: Optional[str] = None
    return_code: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ActionConfig:
    """Configuration for action execution."""
    timeout: int = 300
    retries: int = 0
    retry_delay: int = 5
    working_dir: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    capture_output: bool = True
    raise_on_error: bool = False


class BaseAction(ABC):
    """Base class for all actions."""
    
    def __init__(
        self,
        action_id: str,
        config: Optional[ActionConfig] = None
    ):
        self.action_id = action_id
        self.config = config or ActionConfig()
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
    
    @property
    @abstractmethod
    def action_type(self) -> str:
        """Get the action type identifier."""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ActionResult:
        """Execute the action."""
        pass
    
    def _create_result(
        self,
        status: ActionStatus,
        output: Optional[str] = None,
        error: Optional[str] = None,
        return_code: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
        """Create an ActionResult with timing info."""
        duration = None
        if self._start_time and self._end_time:
            duration = (self._end_time - self._start_time).total_seconds() * 1000
        
        return ActionResult(
            action_id=self.action_id,
            action_type=self.action_type,
            status=status,
            output=output,
            error=error,
            return_code=return_code,
            data=data,
            duration_ms=duration
        )
    
    async def _run_with_retry(self, func: Callable, **kwargs) -> ActionResult:
        """Run a function with retry logic."""
        attempts = 0
        last_error = None
        
        while attempts <= self.config.retries:
            attempts += 1
            self._start_time = datetime.now()
            
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(
                        func(**kwargs),
                        timeout=self.config.timeout
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(func, **kwargs),
                        timeout=self.config.timeout
                    )
                
                self._end_time = datetime.now()
                return result
            
            except asyncio.TimeoutError:
                self._end_time = datetime.now()
                logger.warning(f"Action {self.action_id} timed out (attempt {attempts})")
                if attempts <= self.config.retries:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                return self._create_result(
                    status=ActionStatus.TIMEOUT,
                    error=f"Action timed out after {self.config.timeout}s"
                )
            
            except Exception as e:
                self._end_time = datetime.now()
                last_error = str(e)
                logger.error(f"Action {self.action_id} error (attempt {attempts}): {e}")
                
                if attempts <= self.config.retries:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
        
        return self._create_result(
            status=ActionStatus.FAILED,
            error=last_error
        )


@dataclass
class PythonScriptConfig:
    """Configuration for Python script action."""
    script_path: Optional[str] = None
    script_content: Optional[str] = None
    module_name: Optional[str] = None
    function_name: str = "main"
    args: List[str] = field(default_factory=list)
    inject_context: bool = True


class PythonScriptAction(BaseAction):
    """Execute Python scripts."""
    
    def __init__(
        self,
        action_id: str,
        script_config: PythonScriptConfig,
        config: Optional[ActionConfig] = None
    ):
        super().__init__(action_id, config)
        self.script_config = script_config
    
    @property
    def action_type(self) -> str:
        return "python_script"
    
    async def execute(self, context: Optional[Dict[str, Any]] = None, **kwargs) -> ActionResult:
        """Execute the Python script."""
        return await self._run_with_retry(self._execute_script, context=context, **kwargs)
    
    async def _execute_script(self, context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Internal script execution."""
        try:
            # Prepare execution environment
            exec_globals = {
                '__name__': '__main__',
                '__file__': self.script_config.script_path or '<inline>',
                'context': context or {},
                'result': None,
                'os': os,
                'sys': sys,
                'json': json,
                'asyncio': asyncio
            }
            
            exec_locals = {}
            
            # Get script content
            if self.script_config.script_path:
                script_path = Path(self.script_config.script_path)
                if not script_path.exists():
                    return self._create_result(
                        status=ActionStatus.FAILED,
                        error=f"Script not found: {script_path}"
                    )
                script_content = script_path.read_text()
            elif self.script_config.script_content:
                script_content = self.script_config.script_content
            else:
                return self._create_result(
                    status=ActionStatus.FAILED,
                    error="No script path or content provided"
                )
            
            # Execute script
            working_dir = self.config.working_dir or os.getcwd()
            old_cwd = os.getcwd()
            os.chdir(working_dir)
            
            try:
                exec(script_content, exec_globals, exec_locals)
                
                # Call function if specified
                if self.script_config.function_name in exec_locals:
                    func = exec_locals[self.script_config.function_name]
                    if asyncio.iscoroutinefunction(func):
                        result = await func(
                            *(context.get('args', self.script_config.args) if self.script_config.inject_context else self.script_config.args)
                        )
                    else:
                        result = func(
                            *(context.get('args', self.script_config.args) if self.script_config.inject_context else self.script_config.args)
                        )
                else:
                    result = exec_globals.get('result')
                
                self._end_time = datetime.now()
                
                return self._create_result(
                    status=ActionStatus.SUCCESS,
                    output=str(result) if result else "Script executed successfully",
                    data={'result': result}
                )
            
            finally:
                os.chdir(old_cwd)
        
        except Exception as e:
            return self._create_result(
                status=ActionStatus.FAILED,
                error=f"{str(e)}\n{traceback.format_exc()}"
            )


@dataclass
class ShellCommandConfig:
    """Configuration for shell command action."""
    command: str
    shell: bool = True
    split_output: bool = False


class ShellCommandAction(BaseAction):
    """Execute shell commands."""
    
    def __init__(
        self,
        action_id: str,
        shell_config: ShellCommandConfig,
        config: Optional[ActionConfig] = None
    ):
        super().__init__(action_id, config)
        self.shell_config = shell_config
    
    @property
    def action_type(self) -> str:
        return "shell_command"
    
    async def execute(self, **kwargs) -> ActionResult:
        """Execute the shell command."""
        return await self._run_with_retry(self._execute_command)
    
    async def _execute_command(self) -> ActionResult:
        """Internal command execution."""
        try:
            env = os.environ.copy()
            env.update(self.config.env)
            
            process = await asyncio.create_subprocess_shell(
                self.shell_config.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.working_dir,
                env=env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                raise
            
            self._end_time = datetime.now()
            
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace')
            
            if process.returncode == 0:
                return self._create_result(
                    status=ActionStatus.SUCCESS,
                    output=output,
                    return_code=process.returncode,
                    data={
                        'stdout': output,
                        'stderr': error,
                        'return_code': process.returncode
                    }
                )
            else:
                return self._create_result(
                    status=ActionStatus.FAILED,
                    output=output,
                    error=error,
                    return_code=process.returncode,
                    data={
                        'stdout': output,
                        'stderr': error,
                        'return_code': process.returncode
                    }
                )
        
        except asyncio.TimeoutError:
            return self._create_result(
                status=ActionStatus.TIMEOUT,
                error=f"Command timed out after {self.config.timeout}s"
            )
        except Exception as e:
            return self._create_result(
                status=ActionStatus.FAILED,
                error=str(e)
            )


@dataclass
class APICallConfig:
    """Configuration for API call action."""
    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)
    body: Optional[Union[Dict[str, Any], str]] = None
    json_body: bool = True
    auth: Optional[Dict[str, str]] = None
    verify_ssl: bool = True
    follow_redirects: bool = True


class APICallAction(BaseAction):
    """Make HTTP API calls."""
    
    def __init__(
        self,
        action_id: str,
        api_config: APICallConfig,
        config: Optional[ActionConfig] = None
    ):
        super().__init__(action_id, config)
        self.api_config = api_config
    
    @property
    def action_type(self) -> str:
        return "api_call"
    
    async def execute(self, context: Optional[Dict[str, Any]] = None, **kwargs) -> ActionResult:
        """Execute the API call."""
        return await self._run_with_retry(self._execute_call, context=context)
    
    async def _execute_call(self, context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Internal API call execution."""
        try:
            # Merge context into params/body
            params = dict(self.api_config.params)
            body = self.api_config.body
            
            if context:
                if isinstance(context, dict):
                    params.update(context.get('params', {}))
                    if 'body' in context:
                        body = context['body']
            
            headers = dict(self.api_config.headers)
            if self.api_config.auth:
                if 'bearer' in self.api_config.auth:
                    headers['Authorization'] = f"Bearer {self.api_config.auth['bearer']}"
                elif 'basic' in self.api_config.auth:
                    import base64
                    credentials = base64.b64encode(
                        self.api_config.auth['basic'].encode()
                    ).decode()
                    headers['Authorization'] = f"Basic {credentials}"
            
            async with aiohttp.ClientSession() as session:
                kwargs = {
                    'headers': headers,
                    'params': params,
                    'timeout': aiohttp.ClientTimeout(total=self.config.timeout),
                    'ssl': self.api_config.verify_ssl,
                    'allow_redirects': self.api_config.follow_redirects
                }
                
                if body:
                    if self.api_config.json_body and isinstance(body, dict):
                        kwargs['json'] = body
                    else:
                        kwargs['data'] = body
                
                async with session.request(
                    self.api_config.method.upper(),
                    self.api_config.url,
                    **kwargs
                ) as response:
                    response_text = await response.text()
                    
                    try:
                        response_data = await response.json()
                    except:
                        response_data = None
                    
                    self._end_time = datetime.now()
                    
                    data = {
                        'url': str(response.url),
                        'status_code': response.status,
                        'headers': dict(response.headers),
                        'body': response_text,
                        'json': response_data
                    }
                    
                    if 200 <= response.status < 300:
                        return self._create_result(
                            status=ActionStatus.SUCCESS,
                            output=response_text,
                            data=data
                        )
                    else:
                        return self._create_result(
                            status=ActionStatus.FAILED,
                            output=response_text,
                            error=f"HTTP {response.status}",
                            data=data
                        )
        
        except asyncio.TimeoutError:
            return self._create_result(
                status=ActionStatus.TIMEOUT,
                error=f"API call timed out after {self.config.timeout}s"
            )
        except Exception as e:
            return self._create_result(
                status=ActionStatus.FAILED,
                error=str(e)
            )


@dataclass
class EmailConfig:
    """Configuration for email action."""
    to: Union[str, List[str]]
    subject: str
    body: str
    from_addr: Optional[str] = None
    cc: Optional[Union[str, List[str]]] = None
    bcc: Optional[Union[str, List[str]]] = None
    html: bool = False
    attachments: List[str] = field(default_factory=list)
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    use_tls: bool = True


class EmailAction(BaseAction):
    """Send emails."""
    
    def __init__(
        self,
        action_id: str,
        email_config: EmailConfig,
        config: Optional[ActionConfig] = None
    ):
        super().__init__(action_id, config)
        self.email_config = email_config
    
    @property
    def action_type(self) -> str:
        return "email"
    
    async def execute(self, context: Optional[Dict[str, Any]] = None, **kwargs) -> ActionResult:
        """Execute email sending."""
        return await self._run_with_retry(self._send_email, context=context)
    
    async def _send_email(self, context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Internal email sending."""
        try:
            # Prepare email
            msg = MIMEMultipart('alternative') if self.email_config.html else MIMEText(self.email_config.body)
            
            if self.email_config.html:
                msg.attach(MIMEText(self.email_config.body, 'html'))
            
            msg['Subject'] = self.email_config.subject
            
            # Merge context into subject/body
            if context:
                for key, value in context.items():
                    msg['Subject'] = msg['Subject'].replace(f'{{{key}}}', str(value))
                    if self.email_config.html:
                        for part in msg.walk():
                            if part.get_content_type() == 'text/html':
                                part.set_payload(part.get_payload().replace(f'{{{key}}}', str(value)))
                    else:
                        msg.set_payload(msg.get_payload().replace(f'{{{key}}}', str(value)))
            
            # Recipients
            to_list = self.email_config.to if isinstance(self.email_config.to, list) else [self.email_config.to]
            msg['To'] = ', '.join(to_list)
            
            if self.email_config.cc:
                cc_list = self.email_config.cc if isinstance(self.email_config.cc, list) else [self.email_config.cc]
                msg['Cc'] = ', '.join(cc_list)
                to_list.extend(cc_list)
            
            if self.email_config.bcc:
                bcc_list = self.email_config.bcc if isinstance(self.email_config.bcc, list) else [self.email_config.bcc]
                to_list.extend(bcc_list)
            
            if self.email_config.from_addr:
                msg['From'] = self.email_config.from_addr
            
            # Attachments
            for attachment_path in self.email_config.attachments:
                path = Path(attachment_path)
                if path.exists():
                    with open(path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            'attachment',
                            filename=path.name
                        )
                        msg.attach(part)
            
            # Send
            def send_sync():
                with smtplib.SMTP(self.email_config.smtp_host, self.email_config.smtp_port) as server:
                    if self.email_config.use_tls:
                        server.starttls()
                    
                    if self.email_config.smtp_user:
                        server.login(
                            self.email_config.smtp_user,
                            self.email_config.smtp_password or ''
                        )
                    
                    server.send_message(msg, to_addrs=to_list)
            
            await asyncio.to_thread(send_sync)
            
            self._end_time = datetime.now()
            
            return self._create_result(
                status=ActionStatus.SUCCESS,
                output=f"Email sent to {', '.join(to_list)}",
                data={
                    'recipients': to_list,
                    'subject': self.email_config.subject
                }
            )
        
        except Exception as e:
            return self._create_result(
                status=ActionStatus.FAILED,
                error=str(e)
            )


@dataclass
class NotificationConfig:
    """Configuration for notification action."""
    title: str
    message: str
    level: str = "info"  # info, warning, error, success
    channels: List[str] = field(default_factory=lambda: ["default"])
    sound: bool = False
    actions: List[Dict[str, str]] = field(default_factory=list)
    icon: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None


class NotificationAction(BaseAction):
    """Send notifications to various channels."""
    
    # Registry of notification handlers by channel
    _handlers: Dict[str, Callable] = {}
    
    def __init__(
        self,
        action_id: str,
        notification_config: NotificationConfig,
        config: Optional[ActionConfig] = None
    ):
        super().__init__(action_id, config)
        self.notification_config = notification_config
    
    @property
    def action_type(self) -> str:
        return "notification"
    
    @classmethod
    def register_handler(cls, channel: str, handler: Callable):
        """Register a notification handler for a channel."""
        cls._handlers[channel] = handler
    
    @classmethod
    def unregister_handler(cls, channel: str):
        """Unregister a notification handler."""
        if channel in cls._handlers:
            del cls._handlers[channel]
    
    async def execute(self, context: Optional[Dict[str, Any]] = None, **kwargs) -> ActionResult:
        """Execute notification sending."""
        return await self._run_with_retry(self._send_notification, context=context)
    
    async def _send_notification(self, context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Internal notification sending."""
        title = self.notification_config.title
        message = self.notification_config.message
        
        # Merge context
        if context:
            for key, value in context.items():
                title = title.replace(f'{{{key}}}', str(value))
                message = message.replace(f'{{{key}}}', str(value))
        
        results = {}
        successful = []
        failed = []
        
        for channel in self.notification_config.channels:
            if channel in self._handlers:
                try:
                    result = await asyncio.to_thread(
                        self._handlers[channel],
                        title=title,
                        message=message,
                        level=self.notification_config.level,
                        sound=self.notification_config.sound,
                        actions=self.notification_config.actions,
                        icon=self.notification_config.icon,
                        image=self.notification_config.image,
                        url=self.notification_config.url
                    )
                    results[channel] = result
                    successful.append(channel)
                except Exception as e:
                    logger.error(f"Notification handler error for channel {channel}: {e}")
                    results[channel] = {'error': str(e)}
                    failed.append(channel)
            else:
                # Default handler - just log
                logger.info(f"[{self.notification_config.level.upper()}] {title}: {message}")
                results[channel] = {'status': 'logged'}
                successful.append(channel)
        
        self._end_time = datetime.now()
        
        status = ActionStatus.SUCCESS if successful else ActionStatus.FAILED
        
        return self._create_result(
            status=status,
            output=f"Notification sent to {len(successful)} channel(s)",
            error=f"Failed for channels: {', '.join(failed)}" if failed else None,
            data={
                'title': title,
                'message': message,
                'level': self.notification_config.level,
                'channels': {
                    'successful': successful,
                    'failed': failed,
                    'results': results
                }
            }
        )


class ActionExecutor:
    """Executor for running actions with orchestration."""
    
    def __init__(self, default_config: Optional[ActionConfig] = None):
        self.default_config = default_config or ActionConfig()
        self._actions: Dict[str, BaseAction] = {}
        self._results: Dict[str, List[ActionResult]] = {}
        self._running: Dict[str, asyncio.Task] = {}
    
    def register(self, action: BaseAction):
        """Register an action."""
        self._actions[action.action_id] = action
    
    def unregister(self, action_id: str):
        """Unregister an action."""
        if action_id in self._actions:
            del self._actions[action_id]
    
    def get(self, action_id: str) -> Optional[BaseAction]:
        """Get an action by ID."""
        return self._actions.get(action_id)
    
    async def execute(
        self,
        action_id: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ActionResult:
        """Execute an action by ID."""
        action = self._actions.get(action_id)
        if not action:
            return ActionResult(
                action_id=action_id,
                action_type="unknown",
                status=ActionStatus.FAILED,
                error=f"Action not found: {action_id}"
            )
        
        result = await action.execute(context=context, **kwargs)
        
        # Store result history
        if action_id not in self._results:
            self._results[action_id] = []
        self._results[action_id].append(result)
        
        return result
    
    async def execute_sequential(
        self,
        action_ids: List[str],
        context: Optional[Dict[str, Any]] = None,
        stop_on_failure: bool = True
    ) -> List[ActionResult]:
        """Execute multiple actions in sequence."""
        results = []
        
        for action_id in action_ids:
            result = await self.execute(action_id, context)
            results.append(result)
            
            if stop_on_failure and result.status != ActionStatus.SUCCESS:
                break
        
        return results
    
    async def execute_parallel(
        self,
        action_ids: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[ActionResult]:
        """Execute multiple actions in parallel."""
        tasks = [self.execute(action_id, context) for action_id in action_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed results
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(ActionResult(
                    action_id=action_ids[i],
                    action_type="unknown",
                    status=ActionStatus.FAILED,
                    error=str(result)
                ))
            else:
                processed.append(result)
        
        return processed
    
    async def execute_conditional(
        self,
        condition_action_id: str,
        true_action_ids: List[str],
        false_action_ids: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute actions based on condition result."""
        condition_result = await self.execute(condition_action_id, context)
        
        if condition_result.status == ActionStatus.SUCCESS:
            if condition_result.data and condition_result.data.get('result'):
                actions_to_run = true_action_ids
            else:
                actions_to_run = false_action_ids
        else:
            actions_to_run = false_action_ids
        
        results = await self.execute_sequential(actions_to_run, context)
        
        return {
            'condition': condition_result,
            'branch': 'true' if actions_to_run == true_action_ids else 'false',
            'results': results
        }
    
    def get_results(self, action_id: str) -> List[ActionResult]:
        """Get all results for an action."""
        return self._results.get(action_id, [])
    
    def get_last_result(self, action_id: str) -> Optional[ActionResult]:
        """Get the last result for an action."""
        results = self._results.get(action_id, [])
        return results[-1] if results else None
    
    def clear_results(self, action_id: Optional[str] = None):
        """Clear stored results."""
        if action_id:
            self._results.pop(action_id, None)
        else:
            self._results.clear()
    
    @property
    def registered_actions(self) -> List[str]:
        """Get list of registered action IDs."""
        return list(self._actions.keys())


def create_action_from_config(
    action_id: str,
    action_type: str,
    config_dict: Dict[str, Any],
    execution_config: Optional[ActionConfig] = None
) -> BaseAction:
    """Factory function to create actions from config dicts."""
    if action_type == "python_script":
        script_config = PythonScriptConfig(**config_dict)
        return PythonScriptAction(action_id, script_config, execution_config)
    
    elif action_type == "shell_command":
        shell_config = ShellCommandConfig(**config_dict)
        return ShellCommandAction(action_id, shell_config, execution_config)
    
    elif action_type == "api_call":
        api_config = APICallConfig(**config_dict)
        return APICallAction(action_id, api_config, execution_config)
    
    elif action_type == "email":
        email_config = EmailConfig(**config_dict)
        return EmailAction(action_id, email_config, execution_config)
    
    elif action_type == "notification":
        notification_config = NotificationConfig(**config_dict)
        return NotificationAction(action_id, notification_config, execution_config)
    
    else:
        raise ValueError(f"Unknown action type: {action_type}")
