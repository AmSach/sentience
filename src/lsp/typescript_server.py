"""
TypeScript LSP Server - Integration with typescript-language-server.
Provides TypeScript/JavaScript support with refactoring and rename capabilities.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from .client import LSPClient, ServerCapabilities, create_stdio_client
from .manager import LanguageId
from .diagnostics import Diagnostic, DiagnosticSeverity, Range, Position

logger = logging.getLogger(__name__)


@dataclass
class TypeScriptConfig:
    """Configuration for TypeScript LSP."""
    # TypeScript settings
    typescript_version: str = "latest"
    typescript_path: Optional[str] = None
    
    # JavaScript settings
    javascript_format: bool = True
    javascript_suggest: bool = True
    
    # TypeScript settings
    typescript_format: bool = True
    typescript_suggest: bool = True
    typescript_validate: bool = True
    
    # Completion
    include_completions_for_module_exports: bool = True
    include_completions_with_insert_text: bool = True
    include_completions_with_snippet_text: bool = True
    complete_function_calls: bool = True
    
    # Diagnostics
    diagnostic_severity_overrides: Dict[str, str] = field(default_factory=dict)
    
    # Formatting
    format_enable: bool = True
    format_insert_space_after_comma_delimiter: bool = True
    format_insert_space_after_constructor: bool = False
    format_insert_space_after_keywords_in_control_flow_statements: bool = True
    format_insert_space_after_function_keyword_for_anonymous_functions: bool = True
    format_insert_space_after_opening_and_before_closing_nonempty_parenthesis: bool = False
    format_insert_space_after_opening_and_before_closing_nonempty_brackets: bool = False
    format_insert_space_after_opening_and_before_closing_nonempty_braces: bool = True
    format_insert_space_after_opening_and_before_closing_template_string_braces: bool = False
    format_insert_space_after_opening_and_before_closing_jsx_expression_braces: bool = False
    format_insert_space_after_semicolon_in_for_statements: bool = True
    format_insert_space_before_and_after_binary_operators: bool = True
    format_insert_space_before_function_parenthesis: bool = False
    format_insert_space_before_type_annotation: bool = False
    format_place_open_brace_on_new_line_for_control_blocks: bool = False
    format_place_open_brace_on_new_line_for_functions: bool = False
    format_tab_size: int = 4
    format_indent_size: int = 4
    format_convert_tabs_to_spaces: bool = True
    
    # Inlay hints
    inlay_hints_enabled: bool = True
    include_inlay_parameter_name_hints: str = "literals"  # "none", "literals", "all"
    include_inlay_function_parameter_type_hints: bool = True
    include_inlay_variable_type_hints: bool = True
    include_inlay_property_declaration_type_hints: bool = True
    include_inlay_function_like_return_type_hints: bool = True
    include_inlay_enum_member_value_hints: bool = True
    
    # Preferences
    import_module_specifier_preference: str = "relative"  # "relative", "non-relative", "shortest"
    import_module_specifier_ending: str = "auto"  # "auto", "index", "js", "minimal"
    allow_text_changes_in_new_files: bool = True
    disable_suggestions: bool = False
    quote_preference: str = "auto"  # "auto", "double", "single"


class TypeScriptServerAdapter:
    """Adapter for TypeScript Language Server."""
    
    def __init__(self, config: Optional[TypeScriptConfig] = None):
        self.config = config or TypeScriptConfig()
        self.client: Optional[LSPClient] = None
        self._server_version: Optional[str] = None
    
    async def start(self, workspace_root: str) -> bool:
        """Start the TypeScript language server."""
        server_command = self._get_server_command()
        
        if not server_command:
            logger.error("TypeScript language server not found")
            return False
        
        logger.info(f"Starting TypeScript LSP: {server_command}")
        
        # Create client
        self.client = create_stdio_client(
            command=server_command,
            cwd=workspace_root,
            env=self._get_env()
        )
        
        try:
            await self.client.start()
            
            # Initialize with TypeScript-specific initialization options
            init_options = self._build_initialization_options()
            
            capabilities = await self.client.initialize(
                f"file://{workspace_root}",
                init_options
            )
            
            # Configure server
            await self._configure_server()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start TypeScript LSP: {e}")
            await self.stop()
            return False
    
    def _get_server_command(self) -> Optional[List[str]]:
        """Get the command to start typescript-language-server."""
        # Try typescript-language-server
        if self._command_exists("typescript-language-server"):
            return ["typescript-language-server", "--stdio"]
        
        # Try npx
        if self._command_exists("npx"):
            return ["npx", "typescript-language-server", "--stdio"]
        
        # Check node_modules
        local_server = Path.cwd() / "node_modules" / ".bin" / "typescript-language-server"
        if local_server.exists():
            return [str(local_server), "--stdio"]
        
        return None
    
    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists."""
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _get_env(self) -> Dict[str, str]:
        """Get environment for the server."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "NODE_PATH": os.environ.get("NODE_PATH", ""),
        }
        
        if self.config.typescript_path:
            env["TSS_PATH"] = self.config.typescript_path
        
        return env
    
    def _build_initialization_options(self) -> Dict[str, Any]:
        """Build initialization options for TypeScript server."""
        return {
            "hostInfo": "sentience-lsp",
            "preferences": {
                "disableSuggestions": self.config.disable_suggestions,
                "quotePreference": self.config.quote_preference,
                "includeCompletionsForModuleExports": self.config.include_completions_for_module_exports,
                "includeCompletionsWithInsertText": self.config.include_completions_with_insert_text,
                "includeCompletionsWithSnippetText": self.config.include_completions_with_snippet_text,
                "includeCompletionsForImportStatements": True,
                "importModuleSpecifierPreference": self.config.import_module_specifier_preference,
                "importModuleSpecifierEnding": self.config.import_module_specifier_ending,
                "allowTextChangesInNewFiles": self.config.allow_text_changes_in_new_files,
                "providePrefixAndSuffixTextForRename": True,
                "allowRenameOfImportPath": True,
                "includeAutomaticOptionalChainCompletions": True,
                "provideRefactorNotApplicableReason": True,
            },
            "maxTsServerMemory": 4096,
            "typescript": {
                "tsdk": self.config.typescript_path,
                "maxTsServerMemory": 4096,
            }
        }
    
    async def _configure_server(self) -> None:
        """Configure the TypeScript server."""
        if not self.client:
            return
        
        settings = self._build_settings()
        
        await self.client.send_notification("workspace/didChangeConfiguration", {
            "settings": settings
        })
    
    def _build_settings(self) -> Dict[str, Any]:
        """Build settings for TypeScript server."""
        format_options = {
            "tabSize": self.config.format_tab_size,
            "indentSize": self.config.format_indent_size,
            "convertTabsToSpaces": self.config.format_convert_tabs_to_spaces,
            "insertSpaceAfterCommaDelimiter": self.config.format_insert_space_after_comma_delimiter,
            "insertSpaceAfterConstructor": self.config.format_insert_space_after_constructor,
            "insertSpaceAfterKeywordsInControlFlowStatements": self.config.format_insert_space_after_keywords_in_control_flow_statements,
            "insertSpaceAfterFunctionKeywordForAnonymousFunctions": self.config.format_insert_space_after_function_keyword_for_anonymous_functions,
            "insertSpaceAfterOpeningAndBeforeClosingNonemptyParenthesis": self.config.format_insert_space_after_opening_and_before_closing_nonempty_parenthesis,
            "insertSpaceAfterOpeningAndBeforeClosingNonemptyBrackets": self.config.format_insert_space_after_opening_and_before_closing_nonempty_brackets,
            "insertSpaceAfterOpeningAndBeforeClosingNonemptyBraces": self.config.format_insert_space_after_opening_and_before_closing_nonempty_braces,
            "insertSpaceAfterOpeningAndBeforeClosingTemplateStringBraces": self.config.format_insert_space_after_opening_and_before_closing_template_string_braces,
            "insertSpaceAfterOpeningAndBeforeClosingJsxExpressionBraces": self.config.format_insert_space_after_opening_and_before_closing_jsx_expression_braces,
            "insertSpaceAfterSemicolonInForStatements": self.config.format_insert_space_after_semicolon_in_for_statements,
            "insertSpaceBeforeAndAfterBinaryOperators": self.config.format_insert_space_before_and_after_binary_operators,
            "insertSpaceBeforeFunctionParenthesis": self.config.format_insert_space_before_function_parenthesis,
            "insertSpaceBeforeTypeAnnotation": self.config.format_insert_space_before_type_annotation,
            "placeOpenBraceOnNewLineForControlBlocks": self.config.format_place_open_brace_on_new_line_for_control_blocks,
            "placeOpenBraceOnNewLineForFunctions": self.config.format_place_open_brace_on_new_line_for_functions,
        }
        
        return {
            "typescript": {
                "format": format_options,
                "suggest": {
                    "enabled": self.config.typescript_suggest,
                    "completeFunctionCalls": self.config.complete_function_calls,
                },
                "validate": {"enabled": self.config.typescript_validate},
                "inlayHints": {
                    "includeInlayParameterNameHints": self.config.include_inlay_parameter_name_hints,
                    "includeInlayFunctionParameterTypeHints": self.config.include_inlay_function_parameter_type_hints,
                    "includeInlayVariableTypeHints": self.config.include_inlay_variable_type_hints,
                    "includeInlayPropertyDeclarationTypeHints": self.config.include_inlay_property_declaration_type_hints,
                    "includeInlayFunctionLikeReturnTypeHints": self.config.include_inlay_function_like_return_type_hints,
                    "includeInlayEnumMemberValueHints": self.config.include_inlay_enum_member_value_hints,
                },
                "diagnostic": {
                    "severityOverrides": self.config.diagnostic_severity_overrides
                }
            },
            "javascript": {
                "format": format_options,
                "suggest": {
                    "enabled": self.config.javascript_suggest,
                    "completeFunctionCalls": self.config.complete_function_calls,
                },
            }
        }
    
    async def stop(self) -> None:
        """Stop the language server."""
        if self.client:
            try:
                await self.client.shutdown()
            except Exception:
                pass
            finally:
                await self.client.stop()
                self.client = None
    
    async def get_completions(self, uri: str, line: int, character: int, trigger_kind: int = 1) -> List[Dict]:
        """Get completions at position."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/completion", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"triggerKind": trigger_kind}
            })
            
            if isinstance(result, list):
                return result
            return result.get("items", []) if result else []
        except Exception as e:
            logger.error(f"Completion error: {e}")
            return []
    
    async def resolve_completion(self, item: Dict) -> Dict:
        """Resolve additional information for a completion item."""
        if not self.client:
            return item
        
        try:
            return await self.client.send_request("completionItem/resolve", item)
        except Exception:
            return item
    
    async def get_definition(self, uri: str, line: int, character: int) -> List[Dict]:
        """Go to definition at position."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/definition", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "uri" in result:
                return [result]
            return []
        except Exception:
            return []
    
    async def get_type_definition(self, uri: str, line: int, character: int) -> List[Dict]:
        """Go to type definition."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/typeDefinition", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            
            if isinstance(result, list):
                return result
            if result and "uri" in result:
                return [result]
            return []
        except Exception:
            return []
    
    async def get_implementation(self, uri: str, line: int, character: int) -> List[Dict]:
        """Go to implementation."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/implementation", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            
            if isinstance(result, list):
                return result
            if result and "uri" in result:
                return [result]
            return []
        except Exception:
            return []
    
    async def get_references(self, uri: str, line: int, character: int, include_declaration: bool = True) -> List[Dict]:
        """Find all references."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/references", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": include_declaration}
            })
            return result or []
        except Exception:
            return []
    
    async def get_hover(self, uri: str, line: int, character: int) -> Optional[Dict]:
        """Get hover information."""
        if not self.client:
            return None
        
        try:
            return await self.client.send_request("textDocument/hover", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception:
            return None
    
    async def get_signature_help(self, uri: str, line: int, character: int) -> Optional[Dict]:
        """Get signature help."""
        if not self.client:
            return None
        
        try:
            return await self.client.send_request("textDocument/signatureHelp", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception:
            return None
    
    async def get_document_symbols(self, uri: str) -> List[Dict]:
        """Get document symbols."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/documentSymbol", {
                "textDocument": {"uri": uri}
            })
            return result or []
        except Exception:
            return []
    
    async def get_inlay_hints(self, uri: str, start_line: int, end_line: int) -> List[Dict]:
        """Get inlay hints for a range."""
        if not self.client:
            return []
        
        try:
            return await self.client.send_request("textDocument/inlayHint", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": start_line, "character": 0},
                    "end": {"line": end_line, "character": 1000}
                }
            }) or []
        except Exception:
            return []
    
    async def get_code_actions(self, uri: str, line: int, character: int, diagnostics: List[Dict], kinds: Optional[List[str]] = None) -> List[Dict]:
        """Get code actions for a position."""
        if not self.client:
            return []
        
        try:
            return await self.client.send_request("textDocument/codeAction", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": line, "character": character},
                    "end": {"line": line, "character": character + 1}
                },
                "context": {
                    "diagnostics": diagnostics,
                    "only": kinds
                }
            }) or []
        except Exception:
            return []


class TypeScriptRefactoring:
    """TypeScript refactoring operations."""
    
    # Refactoring action kinds
    REFACTOR_EXTRACT_FUNCTION = "refactor.extract.function"
    REFACTOR_EXTRACT_CONSTANT = "refactor.extract.constant"
    REFACTOR_EXTRACT_INTERFACE = "refactor.extract.interface"
    REFACTOR_EXTRACT_TYPE = "refactor.extract.type"
    REFACTOR_MOVE_TO_NEW_FILE = "refactor.move.newFile"
    REFACTOR_MOVE_TO_EXISTING_FILE = "refactor.move.existingFile"
    
    def __init__(self, adapter: TypeScriptServerAdapter):
        self.adapter = adapter
    
    async def get_refactors(self, uri: str, line: int, character: int, end_line: Optional[int] = None, end_char: Optional[int] = None) -> List[Dict]:
        """Get available refactoring actions at a position."""
        if not self.adapter.client:
            return []
        
        range_dict = {
            "start": {"line": line, "character": character},
            "end": {"line": end_line if end_line is not None else line, "character": end_char if end_char is not None else character + 1}
        }
        
        try:
            result = await self.adapter.client.send_request("textDocument/codeAction", {
                "textDocument": {"uri": uri},
                "range": range_dict,
                "context": {
                    "diagnostics": [],
                    "only": ["refactor"]
                }
            })
            return result or []
        except Exception as e:
            logger.error(f"Get refactors error: {e}")
            return []
    
    async def extract_function(self, uri: str, start_line: int, start_char: int, end_line: int, end_char: int, function_name: str = "extracted") -> Optional[Dict]:
        """Extract selection to a function."""
        if not self.adapter.client:
            return None
        
        try:
            # First get the refactor action
            actions = await self.get_refactors(uri, start_line, start_char, end_line, end_char)
            
            extract_actions = [a for a in actions if a.get("kind", "").startswith("refactor.extract.function")]
            
            if not extract_actions:
                return None
            
            # Execute the first extract function action
            action = extract_actions[0]
            
            if action.get("command"):
                return await self.adapter.client.send_request("workspace/executeCommand", {
                    "command": action["command"].get("command"),
                    "arguments": action["command"].get("arguments", [])
                })
            
            if action.get("edit"):
                return action["edit"]
            
            return None
            
        except Exception as e:
            logger.error(f"Extract function error: {e}")
            return None
    
    async def extract_constant(self, uri: str, line: int, character: int, constant_name: str = "extracted") -> Optional[Dict]:
        """Extract to constant."""
        if not self.adapter.client:
            return None
        
        try:
            actions = await self.get_refactors(uri, line, character)
            
            extract_actions = [a for a in actions if a.get("kind", "").startswith("refactor.extract.constant")]
            
            if not extract_actions:
                return None
            
            action = extract_actions[0]
            
            if action.get("command"):
                return await self.adapter.client.send_request("workspace/executeCommand", {
                    "command": action["command"].get("command"),
                    "arguments": action["command"].get("arguments", []) + [constant_name]
                })
            
            return action.get("edit")
            
        except Exception as e:
            logger.error(f"Extract constant error: {e}")
            return None
    
    async def rename(self, uri: str, line: int, character: int, new_name: str) -> Optional[Dict]:
        """Rename a symbol."""
        if not self.adapter.client:
            return None
        
        try:
            return await self.adapter.client.send_request("textDocument/rename", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "newName": new_name
            })
        except Exception as e:
            logger.error(f"Rename error: {e}")
            return None
    
    async def prepare_rename(self, uri: str, line: int, character: int) -> Optional[Dict]:
        """Prepare rename (check if rename is possible and get placeholder)."""
        if not self.adapter.client:
            return None
        
        try:
            return await self.adapter.client.send_request("textDocument/prepareRename", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception:
            return None
    
    async def organize_imports(self, uri: str, skip_destructive_code_actions: bool = False) -> Optional[Dict]:
        """Organize imports in the document."""
        if not self.adapter.client:
            return None
        
        try:
            return await self.adapter.client.send_request("textDocument/codeAction", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 0}
                },
                "context": {
                    "diagnostics": [],
                    "only": ["source.organizeImports"]
                }
            })
        except Exception as e:
            logger.error(f"Organize imports error: {e}")
            return None
    
    async def fix_all(self, uri: str) -> Optional[Dict]:
        """Apply all auto-fixable diagnostics."""
        if not self.adapter.client:
            return None
        
        try:
            return await self.adapter.client.send_request("textDocument/codeAction", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 100000, "character": 0}
                },
                "context": {
                    "diagnostics": [],
                    "only": ["source.fixAll"]
                }
            })
        except Exception as e:
            logger.error(f"Fix all error: {e}")
            return None
    
    async def add_missing_imports(self, uri: str) -> Optional[Dict]:
        """Add all missing imports."""
        if not self.adapter.client:
            return None
        
        try:
            return await self.adapter.client.send_request("textDocument/codeAction", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 0}
                },
                "context": {
                    "diagnostics": [],
                    "only": ["source.addMissingImports"]
                }
            })
        except Exception as e:
            logger.error(f"Add missing imports error: {e}")
            return None
    
    async def move_to_new_file(self, uri: str, line: int, character: int) -> Optional[Dict]:
        """Move symbol to a new file."""
        if not self.adapter.client:
            return None
        
        try:
            actions = await self.get_refactors(uri, line, character)
            
            move_actions = [a for a in actions if a.get("kind") == "refactor.move.newFile"]
            
            if not move_actions:
                return None
            
            action = move_actions[0]
            
            if action.get("command"):
                return await self.adapter.client.send_request("workspace/executeCommand", {
                    "command": action["command"].get("command"),
                    "arguments": action["command"].get("arguments", [])
                })
            
            return None
            
        except Exception as e:
            logger.error(f"Move to new file error: {e}")
            return None


class TypeScriptFormatter:
    """TypeScript/JavaScript formatting using the built-in formatter."""
    
    def __init__(self, adapter: TypeScriptServerAdapter):
        self.adapter = adapter
    
    async def format_document(self, uri: str, options: Optional[Dict] = None) -> List[Dict]:
        """Format an entire document."""
        if not self.adapter.client:
            return []
        
        format_options = options or {
            "tabSize": 4,
            "insertSpaces": True
        }
        
        try:
            return await self.adapter.client.send_request("textDocument/formatting", {
                "textDocument": {"uri": uri},
                "options": format_options
            }) or []
        except Exception as e:
            logger.error(f"Format document error: {e}")
            return []
    
    async def format_range(self, uri: str, start_line: int, start_char: int, end_line: int, end_char: int, options: Optional[Dict] = None) -> List[Dict]:
        """Format a range in a document."""
        if not self.adapter.client:
            return []
        
        format_options = options or {
            "tabSize": 4,
            "insertSpaces": True
        }
        
        try:
            return await self.adapter.client.send_request("textDocument/rangeFormatting", {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": start_line, "character": start_char},
                    "end": {"line": end_line, "character": end_char}
                },
                "options": format_options
            }) or []
        except Exception as e:
            logger.error(f"Format range error: {e}")
            return []
    
    async def format_on_type(self, uri: str, line: int, character: int, typed_char: str, options: Optional[Dict] = None) -> List[Dict]:
        """Format after typing a character."""
        if not self.adapter.client:
            return []
        
        format_options = options or {
            "tabSize": 4,
            "insertSpaces": True
        }
        
        try:
            return await self.adapter.client.send_request("textDocument/onTypeFormatting", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "ch": typed_char,
                "options": format_options
            }) or []
        except Exception as e:
            logger.debug(f"Format on type error (expected for some chars): {e}")
            return []


class TypeScriptCodeLens:
    """TypeScript CodeLens provider."""
    
    def __init__(self, adapter: TypeScriptServerAdapter):
        self.adapter = adapter
    
    async def get_code_lenses(self, uri: str) -> List[Dict]:
        """Get CodeLens items for a document."""
        if not self.adapter.client:
            return []
        
        try:
            return await self.adapter.client.send_request("textDocument/codeLens", {
                "textDocument": {"uri": uri}
            }) or []
        except Exception:
            return []
    
    async def resolve_code_lens(self, code_lens: Dict) -> Dict:
        """Resolve a CodeLens item."""
        if not self.adapter.client:
            return code_lens
        
        try:
            return await self.adapter.client.send_request("codeLens/resolve", code_lens)
        except Exception:
            return code_lens


class TypeScriptCallHierarchy:
    """TypeScript call hierarchy provider."""
    
    def __init__(self, adapter: TypeScriptServerAdapter):
        self.adapter = adapter
    
    async def prepare_call_hierarchy(self, uri: str, line: int, character: int) -> List[Dict]:
        """Prepare call hierarchy at position."""
        if not self.adapter.client:
            return []
        
        try:
            return await self.adapter.client.send_request("textDocument/prepareCallHierarchy", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            }) or []
        except Exception:
            return []
    
    async def get_incoming_calls(self, item: Dict) -> List[Dict]:
        """Get incoming calls to an item."""
        if not self.adapter.client:
            return []
        
        try:
            return await self.adapter.client.send_request("callHierarchy/incomingCalls", {
                "item": item
            }) or []
        except Exception:
            return []
    
    async def get_outgoing_calls(self, item: Dict) -> List[Dict]:
        """Get outgoing calls from an item."""
        if not self.adapter.client:
            return []
        
        try:
            return await self.adapter.client.send_request("callHierarchy/outgoingCalls", {
                "item": item
            }) or []
        except Exception:
            return []


# Test module
if __name__ == "__main__":
    import sys
    
    async def test_typescript_server():
        """Test TypeScript LSP server adapter."""
        print("Testing TypeScript LSP Server Adapter...")
        
        # Test configuration
        print("\n1. Testing configuration...")
        config = TypeScriptConfig(
            typescript_suggest=True,
            typescript_format=True,
            include_inlay_parameter_name_hints="all"
        )
        
        adapter = TypeScriptServerAdapter(config)
        settings = adapter._build_settings()
        
        print(f"  typescript.suggest.enabled: {settings['typescript']['suggest']['enabled']}")
        print(f"  typescript.format.tabSize: {settings['typescript']['format']['tabSize']}")
        print(f"  typescript.inlayHints.includeInlayParameterNameHints: {settings['typescript']['inlayHints']['includeInlayParameterNameHints']}")
        
        # Test initialization options
        print("\n2. Testing initialization options...")
        init_opts = adapter._build_initialization_options()
        
        print(f"  hostInfo: {init_opts['hostInfo']}")
        print(f"  includeCompletionsForModuleExports: {init_opts['preferences']['includeCompletionsForModuleExports']}")
        print(f"  importModuleSpecifierPreference: {init_opts['preferences']['importModuleSpecifierPreference']}")
        
        # Test refactoring
        print("\n3. Testing refactoring...")
        refactor = TypeScriptRefactoring(adapter)
        
        print(f"  REFACTOR_EXTRACT_FUNCTION: {refactor.REFACTOR_EXTRACT_FUNCTION}")
        print(f"  REFACTOR_EXTRACT_CONSTANT: {refactor.REFACTOR_EXTRACT_CONSTANT}")
        print(f"  REFACTOR_MOVE_TO_NEW_FILE: {refactor.REFACTOR_MOVE_TO_NEW_FILE}")
        
        # Test formatter
        print("\n4. Testing formatter...")
        formatter = TypeScriptFormatter(adapter)
        
        format_opts = {"tabSize": 2, "insertSpaces": True}
        print(f"  Format options: {format_opts}")
        
        # Test call hierarchy
        print("\n5. Testing call hierarchy...")
        call_hierarchy = TypeScriptCallHierarchy(adapter)
        
        print("  Call hierarchy methods available:")
        print("    - prepare_call_hierarchy")
        print("    - get_incoming_calls")
        print("    - get_outgoing_calls")
        
        print("\n✓ Tests completed!")
    
    asyncio.run(test_typescript_server())
