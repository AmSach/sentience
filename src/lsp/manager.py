"""
LSP Manager - Multi-language support, server lifecycle, and document synchronization.
Manages multiple language servers and coordinates their interactions.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .client import LSPClient, ServerCapabilities, create_stdio_client, create_tcp_client, TransportType

logger = logging.getLogger(__name__)


class LanguageId(Enum):
    """Supported language identifiers."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVASCRIPT_REACT = "javascriptreact"
    TYPESCRIPT_REACT = "typescriptreact"
    GO = "go"
    RUST = "rust"
    HTML = "html"
    CSS = "css"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"


@dataclass
class LanguageConfig:
    """Configuration for a language server."""
    language_id: LanguageId
    extensions: List[str]
    command: List[str]
    transport: TransportType = TransportType.STDIO
    host: Optional[str] = None
    port: Optional[int] = None
    initialization_options: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    
    @classmethod
    def get_default_configs(cls) -> Dict[LanguageId, "LanguageConfig"]:
        """Get default configurations for all supported languages."""
        return {
            LanguageId.PYTHON: cls(
                language_id=LanguageId.PYTHON,
                extensions=[".py", ".pyi", ".pyx"],
                command=["pylsp"],
                settings={
                    "pylsp": {
                        "plugins": {
                            "pycodestyle": {"enabled": True, "maxLineLength": 100},
                            "pyflakes": {"enabled": True},
                            "mccabe": {"enabled": True, "threshold": 15},
                            "jedi_completion": {"enabled": True, "fuzzy": True},
                            "jedi_definition": {"enabled": True},
                            "jedi_hover": {"enabled": True},
                            "jedi_references": {"enabled": True},
                            "jedi_signature": {"enabled": True},
                            "jedi_symbols": {"enabled": True},
                            "mypy": {"enabled": True, "live_mode": True},
                            "isort": {"enabled": True},
                            "black": {"enabled": True, "line_length": 100}
                        }
                    }
                }
            ),
            LanguageId.JAVASCRIPT: cls(
                language_id=LanguageId.JAVASCRIPT,
                extensions=[".js", ".jsx", ".mjs", ".cjs"],
                command=["typescript-language-server", "--stdio"],
                settings={
                    "javascript": {
                        "suggest": {"enabled": True},
                        "format": {"enable": True}
                    }
                }
            ),
            LanguageId.TYPESCRIPT: cls(
                language_id=LanguageId.TYPESCRIPT,
                extensions=[".ts", ".tsx"],
                command=["typescript-language-server", "--stdio"],
                settings={
                    "typescript": {
                        "suggest": {"enabled": True},
                        "format": {"enable": True}
                    }
                }
            ),
            LanguageId.GO: cls(
                language_id=LanguageId.GO,
                extensions=[".go"],
                command=["gopls", "serve"],
                settings={
                    "gopls": {
                        "usePlaceholders": True,
                        "completeUnimported": True,
                        "staticcheck": True
                    }
                }
            ),
            LanguageId.RUST: cls(
                language_id=LanguageId.RUST,
                extensions=[".rs"],
                command=["rust-analyzer"],
                settings={
                    "rust-analyzer": {
                        "cargo": {"loadOutDirsFromCheck": True},
                        "procMacro": {"enabled": True},
                        "checkOnSave": {"enable": True}
                    }
                }
            ),
        }


@dataclass
class Document:
    """Represents a text document."""
    uri: str
    language_id: LanguageId
    version: int = 0
    text: str = ""
    filepath: Optional[str] = None
    
    def __post_init__(self):
        if self.filepath is None:
            parsed = urlparse(self.uri)
            if parsed.scheme == "file":
                self.filepath = parsed.path
    
    @classmethod
    def from_file(cls, filepath: str, language_id: Optional[LanguageId] = None) -> "Document":
        """Create a document from a file."""
        path = Path(filepath)
        
        if language_id is None:
            language_id = cls._detect_language(path.suffix)
        
        uri = f"file://{path.absolute()}"
        
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        
        return cls(uri=uri, language_id=language_id, filepath=str(path.absolute()), text=text)
    
    @staticmethod
    def _detect_language(extension: str) -> LanguageId:
        """Detect language from file extension."""
        extension = extension.lower()
        language_map = {
            ".py": LanguageId.PYTHON,
            ".pyi": LanguageId.PYTHON,
            ".pyx": LanguageId.PYTHON,
            ".js": LanguageId.JAVASCRIPT,
            ".jsx": LanguageId.JAVASCRIPT_REACT,
            ".mjs": LanguageId.JAVASCRIPT,
            ".cjs": LanguageId.JAVASCRIPT,
            ".ts": LanguageId.TYPESCRIPT,
            ".tsx": LanguageId.TYPESCRIPT_REACT,
            ".go": LanguageId.GO,
            ".rs": LanguageId.RUST,
        }
        return language_map.get(extension, LanguageId.PYTHON)


@dataclass
class WorkspaceFolder:
    """Represents a workspace folder."""
    uri: str
    name: str
    
    @classmethod
    def from_path(cls, path: str) -> "WorkspaceFolder":
        """Create a workspace folder from a path."""
        abs_path = Path(path).absolute()
        return cls(uri=f"file://{abs_path}", name=abs_path.name)


class LSPManager:
    """Manages multiple LSP clients for different languages."""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.workspace_folder = WorkspaceFolder.from_path(workspace_root)
        
        self._clients: Dict[LanguageId, LSPClient] = {}
        self._configs: Dict[LanguageId, LanguageConfig] = LanguageConfig.get_default_configs()
        self._documents: Dict[str, Document] = {}
        self._language_to_extensions: Dict[LanguageId, List[str]] = {
            config.language_id: config.extensions for config in self._configs.values()
        }
        
        self._notification_handlers: Dict[str, List[Callable]] = {
            "textDocument/publishDiagnostics": [],
            "textDocument/didOpen": [],
            "textDocument/didClose": [],
            "textDocument/didSave": [],
        }
        
        self._state_lock = asyncio.Lock()
    
    async def start(self, languages: Optional[List[LanguageId]] = None) -> None:
        """Start LSP servers for specified languages (or all enabled languages)."""
        if languages is None:
            languages = [lang for lang, config in self._configs.items() if config.enabled]
        
        for language in languages:
            if language in self._clients:
                continue
            
            config = self._configs.get(language)
            if not config or not config.enabled:
                logger.warning(f"Language {language.value} not configured or disabled")
                continue
            
            try:
                await self._start_server(config)
            except Exception as e:
                logger.error(f"Failed to start server for {language.value}: {e}")
    
    async def _start_server(self, config: LanguageConfig) -> None:
        """Start a language server from configuration."""
        logger.info(f"Starting LSP server for {config.language_id.value}: {config.command}")
        
        if config.transport == TransportType.STDIO:
            client = create_stdio_client(
                command=config.command,
                cwd=self.workspace_root,
                env={"PATH": os.environ.get("PATH", "")}
            )
        elif config.transport == TransportType.TCP:
            if not config.host or not config.port:
                raise ValueError("TCP transport requires host and port")
            client = create_tcp_client(config.host, config.port)
        else:
            raise ValueError(f"Unknown transport type: {config.transport}")
        
        # Set up notification forwarding
        client.on_notification("textDocument/publishDiagnostics", self._on_diagnostics)
        client.on_notification("window/showMessage", self._on_window_message)
        client.on_notification("window/logMessage", self._on_log_message)
        
        await client.start()
        
        # Initialize with workspace configuration
        init_options = config.initialization_options.copy()
        init_options["settings"] = config.settings
        
        server_caps = await client.initialize(self.workspace_folder.uri)
        
        self._clients[config.language_id] = client
        logger.info(f"LSP server for {config.language_id.value} initialized successfully")
        
        # Send workspace configuration
        if config.settings:
            await self._send_configuration(config)
    
    async def _send_configuration(self, config: LanguageConfig) -> None:
        """Send workspace/configuration to the server."""
        client = self._clients.get(config.language_id)
        if not client:
            return
        
        # Send didChangeConfiguration notification
        await client.send_notification("workspace/didChangeConfiguration", {
            "settings": config.settings
        })
    
    async def stop(self, language: Optional[LanguageId] = None) -> None:
        """Stop LSP server(s)."""
        if language:
            if language in self._clients:
                await self._shutdown_server(language)
        else:
            for lang in list(self._clients.keys()):
                await self._shutdown_server(lang)
    
    async def _shutdown_server(self, language: LanguageId) -> None:
        """Shutdown a specific language server."""
        client = self._clients.get(language)
        if client:
            try:
                await client.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down {language.value}: {e}")
            finally:
                await client.stop()
                del self._clients[language]
    
    async def open_document(self, filepath: str, language_id: Optional[LanguageId] = None) -> Document:
        """Open a document in the appropriate language server."""
        doc = Document.from_file(filepath, language_id)
        
        async with self._state_lock:
            self._documents[doc.uri] = doc
        
        client = self._clients.get(doc.language_id)
        if client and client.initialized:
            await client.send_notification("textDocument/didOpen", {
                "textDocument": {
                    "uri": doc.uri,
                    "languageId": doc.language_id.value,
                    "version": doc.version,
                    "text": doc.text
                }
            })
            
            # Notify handlers
            await self._notify_handlers("textDocument/didOpen", {"document": doc})
        
        return doc
    
    async def close_document(self, uri: str) -> None:
        """Close a document in the language server."""
        doc = self._documents.get(uri)
        if not doc:
            return
        
        client = self._clients.get(doc.language_id)
        if client and client.initialized:
            await client.send_notification("textDocument/didClose", {
                "textDocument": {"uri": uri}
            })
            
            await self._notify_handlers("textDocument/didClose", {"document": doc})
        
        async with self._state_lock:
            self._documents.pop(uri, None)
    
    async def update_document(self, uri: str, text: str, version: Optional[int] = None) -> None:
        """Update document content (full sync)."""
        async with self._state_lock:
            doc = self._documents.get(uri)
            if not doc:
                return
            
            doc.text = text
            doc.version = version if version is not None else doc.version + 1
        
        client = self._clients.get(doc.language_id)
        if client and client.initialized:
            sync_kind = client.server_capabilities.text_document_sync if client.server_capabilities else 1
            
            if sync_kind == 2:
                # Incremental sync - calculate changes
                # For simplicity, we'll do full sync
                pass
            
            # Full sync
            await client.send_notification("textDocument/didChange", {
                "textDocument": {
                    "uri": uri,
                    "version": doc.version
                },
                "contentChanges": [{"text": text}]
            })
    
    async def update_document_incremental(self, uri: str, changes: List[Dict[str, Any]], version: Optional[int] = None) -> None:
        """Update document with incremental changes."""
        async with self._state_lock:
            doc = self._documents.get(uri)
            if not doc:
                return
            
            doc.version = version if version is not None else doc.version + 1
            
            # Apply changes to local document text
            for change in changes:
                doc.text = self._apply_text_change(doc.text, change)
        
        client = self._clients.get(doc.language_id)
        if client and client.initialized:
            await client.send_notification("textDocument/didChange", {
                "textDocument": {
                    "uri": uri,
                    "version": doc.version
                },
                "contentChanges": changes
            })
    
    def _apply_text_change(self, text: str, change: Dict[str, Any]) -> str:
        """Apply a text change to document content."""
        if "range" not in change:
            return change.get("text", text)
        
        lines = text.split("\n")
        range_info = change["range"]
        start_line = range_info["start"]["line"]
        start_char = range_info["start"]["character"]
        end_line = range_info["end"]["line"]
        end_char = range_info["end"]["character"]
        
        # Get content before and after the change
        before = "\n".join(lines[:start_line])
        if start_line < len(lines):
            before += ("\n" if start_line > 0 else "") + lines[start_line][:start_char]
        
        after_lines = lines[end_line:]
        if after_lines:
            after = lines[end_line][end_char:] + "\n".join("\n" + l for l in after_lines[1:])
        else:
            after = ""
        
        new_text = change.get("text", "")
        return before + new_text + after
    
    async def save_document(self, uri: str, include_text: bool = False) -> None:
        """Notify server that document was saved."""
        doc = self._documents.get(uri)
        if not doc:
            return
        
        client = self._clients.get(doc.language_id)
        if client and client.initialized:
            params = {"textDocument": {"uri": uri}}
            if include_text:
                params["text"] = doc.text
            
            await client.send_notification("textDocument/didSave", params)
            await self._notify_handlers("textDocument/didSave", {"document": doc})
    
    def get_document(self, uri: str) -> Optional[Document]:
        """Get a document by URI."""
        return self._documents.get(uri)
    
    def get_client(self, language: LanguageId) -> Optional[LSPClient]:
        """Get LSP client for a language."""
        return self._clients.get(language)
    
    def get_language_for_file(self, filepath: str) -> Optional[LanguageId]:
        """Determine language for a file."""
        ext = Path(filepath).suffix.lower()
        for lang, extensions in self._language_to_extensions.items():
            if ext in extensions:
                return lang
        return None
    
    async def request_completion(self, uri: str, line: int, character: int, context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Request completion items from the server."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        }
        
        if context:
            params["context"] = context
        
        try:
            result = await client.send_request("textDocument/completion", params)
            
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get("items", [])
            return []
        except Exception as e:
            logger.error(f"Completion request failed: {e}")
            return []
    
    async def request_hover(self, uri: str, line: int, character: int) -> Optional[Dict[str, Any]]:
        """Request hover information."""
        doc = self._documents.get(uri)
        if not doc:
            return None
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return None
        
        try:
            return await client.send_request("textDocument/hover", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception as e:
            logger.error(f"Hover request failed: {e}")
            return None
    
    async def request_definition(self, uri: str, line: int, character: int) -> List[Dict[str, Any]]:
        """Request go-to-definition."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        try:
            result = await client.send_request("textDocument/definition", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "uri" in result:
                return [result]
            return []
        except Exception as e:
            logger.error(f"Definition request failed: {e}")
            return []
    
    async def request_references(self, uri: str, line: int, character: int, include_declaration: bool = True) -> List[Dict[str, Any]]:
        """Request find references."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        try:
            result = await client.send_request("textDocument/references", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": include_declaration}
            })
            return result or []
        except Exception as e:
            logger.error(f"References request failed: {e}")
            return []
    
    async def request_signature_help(self, uri: str, line: int, character: int) -> Optional[Dict[str, Any]]:
        """Request signature help."""
        doc = self._documents.get(uri)
        if not doc:
            return None
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return None
        
        try:
            return await client.send_request("textDocument/signatureHelp", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception as e:
            logger.error(f"Signature help request failed: {e}")
            return None
    
    async def request_document_symbols(self, uri: str) -> List[Dict[str, Any]]:
        """Request document symbols."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        try:
            result = await client.send_request("textDocument/documentSymbol", {
                "textDocument": {"uri": uri}
            })
            return result or []
        except Exception as e:
            logger.error(f"Document symbols request failed: {e}")
            return []
    
    async def request_workspace_symbols(self, query: str = "") -> List[Dict[str, Any]]:
        """Request workspace symbols."""
        # Use the first available client
        for client in self._clients.values():
            if client.initialized:
                try:
                    result = await client.send_request("workspace/symbol", {"query": query})
                    return result or []
                except Exception as e:
                    logger.error(f"Workspace symbols request failed: {e}")
        return []
    
    async def request_formatting(self, uri: str, options: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Request document formatting."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        format_options = options or {
            "tabSize": 4,
            "insertSpaces": True,
            "trimTrailingWhitespace": True,
            "insertFinalNewline": True,
            "trimFinalNewlines": True
        }
        
        try:
            return await client.send_request("textDocument/formatting", {
                "textDocument": {"uri": uri},
                "options": format_options
            }) or []
        except Exception as e:
            logger.error(f"Formatting request failed: {e}")
            return []
    
    async def request_range_formatting(self, uri: str, start_line: int, start_char: int, end_line: int, end_char: int, options: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Request range formatting."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        format_options = options or {"tabSize": 4, "insertSpaces": True}
        
        try:
            return await client.send_request("textDocument/rangeFormatting", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": start_line, "character": start_char},
                    "end": {"line": end_line, "character": end_char}
                },
                "options": format_options
            }) or []
        except Exception as e:
            logger.error(f"Range formatting request failed: {e}")
            return []
    
    async def request_rename(self, uri: str, line: int, character: int, new_name: str) -> Optional[Dict[str, Any]]:
        """Request rename."""
        doc = self._documents.get(uri)
        if not doc:
            return None
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return None
        
        try:
            return await client.send_request("textDocument/rename", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "newName": new_name
            })
        except Exception as e:
            logger.error(f"Rename request failed: {e}")
            return None
    
    async def request_code_actions(self, uri: str, diagnostics: List[Dict], start_line: int, start_char: int, end_line: int, end_char: int, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Request code actions."""
        doc = self._documents.get(uri)
        if not doc:
            return []
        
        client = self._clients.get(doc.language_id)
        if not client or not client.initialized:
            return []
        
        context = {
            "diagnostics": diagnostics,
            "only": kinds if kinds else None
        }
        
        try:
            result = await client.send_request("textDocument/codeAction", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": start_line, "character": start_char},
                    "end": {"line": end_line, "character": end_char}
                },
                "context": context
            })
            return result or []
        except Exception as e:
            logger.error(f"Code action request failed: {e}")
            return []
    
    async def execute_command(self, command: str, arguments: Optional[List] = None) -> Any:
        """Execute a workspace command."""
        for client in self._clients.values():
            if client.initialized:
                try:
                    return await client.send_request("workspace/executeCommand", {
                        "command": command,
                        "arguments": arguments or []
                    })
                except Exception as e:
                    logger.error(f"Execute command failed: {e}")
        return None
    
    def on_diagnostics(self, handler: Callable) -> None:
        """Register a handler for diagnostics."""
        self._notification_handlers["textDocument/publishDiagnostics"].append(handler)
    
    def on_document_opened(self, handler: Callable) -> None:
        """Register a handler for document open events."""
        self._notification_handlers["textDocument/didOpen"].append(handler)
    
    def on_document_closed(self, handler: Callable) -> None:
        """Register a handler for document close events."""
        self._notification_handlers["textDocument/didClose"].append(handler)
    
    def on_document_saved(self, handler: Callable) -> None:
        """Register a handler for document save events."""
        self._notification_handlers["textDocument/didSave"].append(handler)
    
    async def _on_diagnostics(self, params: Dict[str, Any]) -> None:
        """Handle diagnostics notification from server."""
        await self._notify_handlers("textDocument/publishDiagnostics", params)
    
    async def _on_window_message(self, params: Dict[str, Any]) -> None:
        """Handle window/showMessage notification."""
        message = params.get("message", "")
        msg_type = params.get("type", 3)  # 3 = Info
        type_names = {1: "Error", 2: "Warning", 3: "Info", 4: "Log"}
        logger.log(
            logging.ERROR if msg_type == 1 else logging.WARNING if msg_type == 2 else logging.INFO,
            f"[LSP] {type_names.get(msg_type, 'Message')}: {message}"
        )
    
    async def _on_log_message(self, params: Dict[str, Any]) -> None:
        """Handle window/logMessage notification."""
        logger.debug(f"[LSP Log] {params.get('message', '')}")
    
    async def _notify_handlers(self, event: str, params: Dict[str, Any]) -> None:
        """Notify all registered handlers for an event."""
        handlers = self._notification_handlers.get(event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(params)
                else:
                    handler(params)
            except Exception as e:
                logger.error(f"Error in handler for {event}: {e}")
    
    def update_config(self, language: LanguageId, settings: Dict[str, Any]) -> None:
        """Update language configuration."""
        if language in self._configs:
            self._configs[language].settings.update(settings)
    
    def is_language_enabled(self, language: LanguageId) -> bool:
        """Check if a language server is running."""
        return language in self._clients and self._clients[language].initialized
    
    def get_supported_languages(self) -> List[LanguageId]:
        """Get list of configured languages."""
        return list(self._configs.keys())
    
    def get_active_documents(self) -> List[Document]:
        """Get all active documents."""
        return list(self._documents.values())


# Test module
if __name__ == "__main__":
    import sys
    
    async def test_manager():
        """Test the LSP Manager."""
        print("Testing LSP Manager...")
        
        # Create manager for current directory
        manager = LSPManager("/tmp")
        
        # Register diagnostic handler
        def on_diagnostics(params):
            print(f"Diagnostics for {params.get('uri')}: {len(params.get('diagnostics', []))} issues")
        
        manager.on_diagnostics(on_diagnostics)
        
        try:
            # Start Python server
            print("Starting Python LSP...")
            await manager.start([LanguageId.PYTHON])
            
            # Open a test document
            print("Opening document...")
            test_file = "/tmp/test.py"
            with open(test_file, "w") as f:
                f.write("import os\nprint('hello')\n")
            
            doc = await manager.open_document(test_file)
            print(f"Opened: {doc.uri}")
            
            # Wait for diagnostics
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("Stopping manager...")
            await manager.stop()
    
    asyncio.run(test_manager())
