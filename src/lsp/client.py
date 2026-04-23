"""
LSP Client - Transport and protocol handling for Language Server Protocol.
Supports TCP and STDIO transports with full request/response and notification handling.
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from concurrent.futures import Future

logger = logging.getLogger(__name__)


class TransportType(Enum):
    STDIO = "stdio"
    TCP = "tcp"


@dataclass
class LSPCapabilities:
    """Client capabilities sent during initialization."""
    text_document_sync: int = 1
    completion_support: bool = True
    completion_trigger_characters: List[str] = field(default_factory=lambda: [".", "(", ","])
    hover_support: bool = True
    signature_help_support: bool = True
    definition_support: bool = True
    references_support: bool = True
    document_symbol_support: bool = True
    workspace_symbol_support: bool = True
    code_action_support: bool = True
    code_lens_support: bool = False
    document_formatting_support: bool = True
    document_range_formatting_support: bool = True
    rename_support: bool = True
    execute_command_support: bool = True


@dataclass
class ServerCapabilities:
    """Server capabilities received during initialization."""
    text_document_sync: Optional[int] = None
    completion_provider: Optional[Dict[str, Any]] = None
    hover_provider: Optional[bool] = None
    signature_help_provider: Optional[Dict[str, Any]] = None
    definition_provider: Optional[bool] = None
    references_provider: Optional[bool] = None
    document_symbol_provider: Optional[bool] = None
    workspace_symbol_provider: Optional[bool] = None
    code_action_provider: Optional[Union[bool, Dict]] = None
    code_lens_provider: Optional[Dict] = None
    document_formatting_provider: Optional[bool] = None
    document_range_formatting_provider: Optional[bool] = None
    rename_provider: Optional[Union[bool, Dict]] = None
    execute_command_provider: Optional[Dict[str, List[str]]] = None


class Transport(ABC):
    """Abstract base class for LSP transports."""
    
    @abstractmethod
    async def start(self) -> None:
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        pass
    
    @abstractmethod
    async def send(self, data: bytes) -> None:
        pass
    
    @abstractmethod
    async def receive(self) -> Optional[bytes]:
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        pass


class StdioTransport(Transport):
    """STDIO transport for LSP communication."""
    
    def __init__(self, command: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None):
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.env = {**os.environ, **(env or {})}
        self.process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._buffer = ""
        self._running = False
    
    async def start(self) -> None:
        logger.info(f"Starting LSP server: {' '.join(self.command)}")
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env
        )
        self._running = True
        self._reader_task = asyncio.create_task(self._read_messages())
        asyncio.create_task(self._read_stderr())
    
    async def stop(self) -> None:
        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self.process:
            try:
                self.process.stdin.close()
                await self.process.wait()
            except Exception as e:
                logger.warning(f"Error stopping process: {e}")
                self.process.kill()
    
    async def send(self, data: bytes) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("Transport not started")
        try:
            self.process.stdin.write(data)
            await self.process.stdin.drain()
        except Exception as e:
            logger.error(f"Error sending data: {e}")
            raise
    
    async def receive(self) -> Optional[bytes]:
        if not self._running:
            return None
        try:
            return await self._message_queue.get()
        except asyncio.CancelledError:
            return None
    
    def is_running(self) -> bool:
        return self._running and (self.process is not None and self.process.returncode is None)
    
    async def _read_messages(self) -> None:
        while self._running and self.process and self.process.stdout:
            try:
                data = await self.process.stdout.read(4096)
                if not data:
                    logger.warning("Server closed stdout")
                    self._running = False
                    break
                self._buffer += data.decode("utf-8", errors="replace")
                while "\r\n\r\n" in self._buffer:
                    header_end = self._buffer.index("\r\n\r\n")
                    headers = self._buffer[:header_end]
                    self._buffer = self._buffer[header_end + 4:]
                    content_length = 0
                    for line in headers.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break
                    while len(self._buffer) < content_length:
                        more_data = await self.process.stdout.read(4096)
                        if not more_data:
                            break
                        self._buffer += more_data.decode("utf-8", errors="replace")
                    if len(self._buffer) >= content_length:
                        content = self._buffer[:content_length]
                        self._buffer = self._buffer[content_length:]
                        await self._message_queue.put(content.encode("utf-8"))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading messages: {e}")
                break
    
    async def _read_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return
        while self._running:
            try:
                line = await self.process.stderr.readline()
                if not line:
                    break
                logger.debug(f"[LSP stderr] {line.decode().strip()}")
            except Exception:
                break


class TCPTransport(Transport):
    """TCP transport for LSP communication."""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._buffer = ""
        self._running = False
    
    async def start(self) -> None:
        logger.info(f"Connecting to LSP server at {self.host}:{self.port}")
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self._running = True
        self._reader_task = asyncio.create_task(self._read_messages())
    
    async def stop(self) -> None:
        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
    
    async def send(self, data: bytes) -> None:
        if not self.writer:
            raise RuntimeError("Transport not started")
        self.writer.write(data)
        await self.writer.drain()
    
    async def receive(self) -> Optional[bytes]:
        if not self._running:
            return None
        try:
            return await self._message_queue.get()
        except asyncio.CancelledError:
            return None
    
    def is_running(self) -> bool:
        return self._running and self.writer is not None and not self.writer.is_closing()
    
    async def _read_messages(self) -> None:
        while self._running and self.reader:
            try:
                data = await self.reader.read(4096)
                if not data:
                    logger.warning("Server closed connection")
                    self._running = False
                    break
                self._buffer += data.decode("utf-8", errors="replace")
                while "\r\n\r\n" in self._buffer:
                    header_end = self._buffer.index("\r\n\r\n")
                    headers = self._buffer[:header_end]
                    self._buffer = self._buffer[header_end + 4:]
                    content_length = 0
                    for line in headers.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break
                    while len(self._buffer) < content_length:
                        more_data = await self.reader.read(4096)
                        if not more_data:
                            break
                        self._buffer += more_data.decode("utf-8", errors="replace")
                    if len(self._buffer) >= content_length:
                        content = self._buffer[:content_length]
                        self._buffer = self._buffer[content_length:]
                        await self._message_queue.put(content.encode("utf-8"))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading TCP messages: {e}")
                break


class LSPClient:
    """Main LSP client handling requests, responses, and notifications."""
    
    def __init__(self, transport: Transport, client_name: str = "sentience-lsp", client_version: str = "3.0.0"):
        self.transport = transport
        self.client_name = client_name
        self.client_version = client_version
        self._request_id = 0
        self._pending_requests: Dict[int, Future] = {}
        self._notification_handlers: Dict[str, List[Callable]] = {}
        self._response_handlers: Dict[str, Callable] = {}
        self.server_capabilities: Optional[ServerCapabilities] = None
        self.initialized = False
        self._message_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        await self.transport.start()
        self._message_task = asyncio.create_task(self._process_messages())
        logger.info("LSP client started")
    
    async def stop(self) -> None:
        if self._message_task:
            self._message_task.cancel()
            try:
                await self._message_task
            except asyncio.CancelledError:
                pass
        await self.transport.stop()
        self.initialized = False
        logger.info("LSP client stopped")
    
    def _get_next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    
    def _encode_message(self, data: Dict[str, Any]) -> bytes:
        content = json.dumps(data, separators=(",", ":"))
        header = f"Content-Length: {len(content)}\r\n\r\n"
        return (header + content).encode("utf-8")
    
    def _decode_message(self, data: bytes) -> Dict[str, Any]:
        return json.loads(data.decode("utf-8"))
    
    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        request_id = self._get_next_id()
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        future: Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        try:
            await self.transport.send(self._encode_message(message))
            logger.debug(f"Sent request: {method} (id={request_id})")
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out after {timeout}s")
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise
    
    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        await self.transport.send(self._encode_message(message))
        logger.debug(f"Sent notification: {method}")
    
    def on_notification(self, method: str, handler: Callable) -> None:
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(handler)
    
    async def initialize(self, root_uri: str, capabilities: Optional[LSPCapabilities] = None) -> ServerCapabilities:
        caps = capabilities or LSPCapabilities()
        init_params = {
            "processId": os.getpid(),
            "clientInfo": {
                "name": self.client_name,
                "version": self.client_version
            },
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": False, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "completion": {
                        "dynamicRegistration": False,
                        "completionItem": {"snippetSupport": True, "commitCharactersSupport": True, "documentationFormat": ["markdown", "plaintext"], "deprecatedSupport": True, "preselectSupport": True},
                        "completionItemKind": {"valueSet": list(range(1, 26))},
                        "contextSupport": True
                    },
                    "hover": {"dynamicRegistration": False, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": False, "signatureInformation": {"documentationFormat": ["markdown", "plaintext"], "parameterInformation": {"labelOffsetSupport": True}}},
                    "declaration": {"dynamicRegistration": False, "linkSupport": True},
                    "definition": {"dynamicRegistration": False, "linkSupport": True},
                    "typeDefinition": {"dynamicRegistration": False, "linkSupport": True},
                    "implementation": {"dynamicRegistration": False, "linkSupport": True},
                    "references": {"dynamicRegistration": False},
                    "documentHighlight": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False, "symbolKind": {"valueSet": list(range(1, 27))}, "hierarchicalDocumentSymbolSupport": True},
                    "codeAction": {"dynamicRegistration": False, "codeActionLiteralSupport": {"codeActionKind": {"valueSet": ["", "quickfix", "refactor", "refactor.extract", "refactor.inline", "refactor.rewrite", "source", "source.organizeImports"]}}},
                    "formatting": {"dynamicRegistration": False},
                    "rangeFormatting": {"dynamicRegistration": False},
                    "onTypeFormatting": {"dynamicRegistration": False},
                    "rename": {"dynamicRegistration": False, "prepareSupport": True}
                },
                "workspace": {"workspaceFolders": True, "configuration": True, "symbol": {"dynamicRegistration": False, "symbolKind": {"valueSet": list(range(1, 27))}}, "executeCommand": {}}
            },
            "trace": "off",
            "workspaceFolders": [{"uri": root_uri, "name": "workspace"}]
        }
        response = await self.send_request("initialize", init_params)
        self.server_capabilities = self._parse_capabilities(response.get("capabilities", {}))
        await self.send_notification("initialized", {})
        self.initialized = True
        logger.info(f"LSP initialized. Server capabilities: {response.get('capabilities', {}).keys()}")
        return self.server_capabilities
    
    def _parse_capabilities(self, caps: Dict[str, Any]) -> ServerCapabilities:
        return ServerCapabilities(
            text_document_sync=caps.get("textDocumentSync", {}).get("change") if isinstance(caps.get("textDocumentSync"), dict) else caps.get("textDocumentSync"),
            completion_provider=caps.get("completionProvider"),
            hover_provider=caps.get("hoverProvider"),
            signature_help_provider=caps.get("signatureHelpProvider"),
            definition_provider=caps.get("definitionProvider"),
            references_provider=caps.get("referencesProvider"),
            document_symbol_provider=caps.get("documentSymbolProvider"),
            workspace_symbol_provider=caps.get("workspaceSymbolProvider"),
            code_action_provider=caps.get("codeActionProvider"),
            code_lens_provider=caps.get("codeLensProvider"),
            document_formatting_provider=caps.get("documentFormattingProvider"),
            document_range_formatting_provider=caps.get("documentRangeFormattingProvider"),
            rename_provider=caps.get("renameProvider"),
            execute_command_provider=caps.get("executeCommandProvider")
        )
    
    async def shutdown(self) -> None:
        if self.initialized:
            try:
                await self.send_request("shutdown", timeout=5.0)
                await self.send_notification("exit", {})
            except Exception as e:
                logger.warning(f"Error during shutdown: {e}")
            self.initialized = False
    
    async def _process_messages(self) -> None:
        while self.transport.is_running():
            try:
                data = await self.transport.receive()
                if not data:
                    continue
                message = self._decode_message(data)
                logger.debug(f"Received message: {message.get('method', 'response')}")
                if "id" in message and "method" not in message:
                    self._handle_response(message)
                elif "method" in message:
                    if "id" in message:
                        await self._handle_server_request(message)
                    else:
                        self._handle_notification(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    def _handle_response(self, message: Dict[str, Any]) -> None:
        request_id = message["id"]
        future = self._pending_requests.pop(request_id, None)
        if future and not future.done():
            if "error" in message:
                error = message["error"]
                future.set_exception(Exception(f"LSP error {error.get('code')}: {error.get('message')}"))
            else:
                future.set_result(message.get("result"))
    
    def _handle_notification(self, message: Dict[str, Any]) -> None:
        method = message.get("method", "")
        params = message.get("params", {})
        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(params))
                else:
                    handler(params)
            except Exception as e:
                logger.error(f"Error in notification handler for {method}: {e}")
    
    async def _handle_server_request(self, message: Dict[str, Any]) -> None:
        method = message.get("method", "")
        params = message.get("params", {})
        request_id = message["id"]
        response = {"jsonrpc": "2.0", "id": request_id}
        try:
            if method == "workspace/configuration":
                result = await self._handle_configuration_request(params)
                response["result"] = result
            elif method == "window/showMessageRequest":
                result = await self._handle_message_request(params)
                response["result"] = result
            else:
                response["result"] = None
        except Exception as e:
            response["error"] = {"code": -32603, "message": str(e)}
        await self.transport.send(self._encode_message(response))
    
    async def _handle_configuration_request(self, params: Dict[str, Any]) -> List[Any]:
        items = params.get("items", [])
        results = []
        for item in items:
            results.append({"settings": item.get("section", {})})
        return results
    
    async def _handle_message_request(self, params: Dict[str, Any]) -> Optional[Dict]:
        actions = params.get("actions", [])
        return actions[0] if actions else None


def create_stdio_client(command: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> LSPClient:
    transport = StdioTransport(command, cwd, env)
    return LSPClient(transport)


def create_tcp_client(host: str, port: int) -> LSPClient:
    transport = TCPTransport(host, port)
    return LSPClient(transport)


if __name__ == "__main__":
    import sys
    async def test_client():
        print("Testing LSP Client...")
        client = create_stdio_client(["pylsp"], cwd="/tmp")
        client.on_notification("textDocument/publishDiagnostics", lambda p: print(f"Diagnostics: {p}"))
        client.on_notification("window/showMessage", lambda p: print(f"Server message: {p}"))
        try:
            await client.start()
            print("Client started")
            capabilities = await client.initialize("file:///tmp")
            print(f"Server capabilities: {capabilities}")
            await client.shutdown()
            print("Shutdown complete")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await client.stop()
    asyncio.run(test_client())
