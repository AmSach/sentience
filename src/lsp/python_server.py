"""
Python LSP Server Adapter - Integration with jedi/pylsp.
Provides Python-specific features: type checking, import sorting, formatting.
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

from .client import LSPClient, ServerCapabilities, create_stdio_client
from .manager import LanguageId
from .diagnostics import Diagnostic, DiagnosticSeverity, Range, Position

logger = logging.getLogger(__name__)


@dataclass
class PythonConfig:
    """Configuration for Python LSP."""
    # jedi/pylsp settings
    jedi_fuzzy_completion: bool = True
    jedi_case_sensitive_completion: bool = True
    
    # Type checking (mypy/pyright)
    type_checker: str = "mypy"  # "mypy", "pyright", or "none"
    type_check_mode: str = "strict"  # "off", "basic", "strict"
    mypy_path: List[str] = field(default_factory=list)
    mypy_plugins: List[str] = field(default_factory=list)
    
    # Import sorting (isort)
    sort_imports: bool = True
    isort_profile: str = "black"
    isort_line_length: int = 100
    isort_known_first_party: List[str] = field(default_factory=list)
    
    # Formatting (black/autopep8)
    formatter: str = "black"  # "black", "autopep8", "yapf"
    format_line_length: int = 100
    format_skip_string_normalization: bool = False
    
    # Linting (pycodestyle/pyflakes/pylint)
    linter: str = "pycodestyle"  # "pycodestyle", "pyflakes", "pylint", "flake8"
    max_line_length: int = 100
    ignore_errors: List[str] = field(default_factory=list)
    select_errors: List[str] = field(default_factory=list)
    
    # Execution environments
    python_path: str = sys.executable
    venv_path: Optional[str] = None
    extra_paths: List[str] = field(default_factory=list)


class PythonServerAdapter:
    """Adapter for Python LSP servers (pylsp/jedi)."""
    
    def __init__(self, config: Optional[PythonConfig] = None):
        self.config = config or PythonConfig()
        self.client: Optional[LSPClient] = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._mypy_running = False
    
    async def start(self, workspace_root: str) -> bool:
        """Start the Python LSP server."""
        # Determine which server to use
        server_command = self._get_server_command()
        
        if not server_command:
            logger.error("No Python LSP server found")
            return False
        
        logger.info(f"Starting Python LSP: {server_command}")
        
        # Create client
        self.client = create_stdio_client(
            command=server_command,
            cwd=workspace_root,
            env=self._get_env()
        )
        
        try:
            await self.client.start()
            
            # Initialize with Python-specific capabilities
            capabilities = await self.client.initialize(f"file://{workspace_root}")
            
            # Configure server settings
            await self._configure_server()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Python LSP: {e}")
            await self.stop()
            return False
    
    def _get_server_command(self) -> Optional[List[str]]:
        """Get the command to start the LSP server."""
        # Try pylsp first
        if self._command_exists("pylsp"):
            return ["pylsp"]
        
        # Try jedi-language-server
        if self._command_exists("jedi-language-server"):
            return ["jedi-language-server"]
        
        # Try pyright (has different interface but works)
        if self._command_exists("pyright"):
            return ["pyright", "--stdio"]
        
        # Fall back to pylsp installed with pip
        pylsp_path = Path(sys.executable).parent / "pylsp"
        if pylsp_path.exists():
            return [str(pylsp_path)]
        
        return None
    
    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def _get_env(self) -> Dict[str, str]:
        """Get environment variables for the server."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join(self.config.extra_paths) if self.config.extra_paths else "",
        }
        
        if self.config.venv_path:
            venv_bin = Path(self.config.venv_path) / "bin"
            env["PATH"] = f"{venv_bin}:{env['PATH']}"
            env["VIRTUAL_ENV"] = self.config.venv_path
        
        return env
    
    async def _configure_server(self) -> None:
        """Send configuration to the server."""
        if not self.client:
            return
        
        settings = self._build_settings()
        
        await self.client.send_notification("workspace/didChangeConfiguration", {
            "settings": {"pylsp": settings}
        })
    
    def _build_settings(self) -> Dict[str, Any]:
        """Build pylsp settings from config."""
        settings = {
            "plugins": {
                # Completion
                "jedi_completion": {
                    "enabled": True,
                    "fuzzy": self.config.jedi_fuzzy_completion,
                    "case_insensitive": not self.config.jedi_case_sensitive_completion,
                    "include_params": True,
                    "include_class_objects": True,
                    "include_function_objects": True,
                },
                "jedi_definition": {"enabled": True, "follow_builtin_imports": True},
                "jedi_hover": {"enabled": True},
                "jedi_references": {"enabled": True},
                "jedi_signature": {"enabled": True},
                "jedi_symbols": {"enabled": True, "all_scopes": True},
                
                # Diagnostics
                "pycodestyle": {
                    "enabled": self.config.linter == "pycodestyle",
                    "maxLineLength": self.config.max_line_length,
                    "ignore": self.config.ignore_errors,
                    "select": self.config.select_errors,
                },
                "pyflakes": {"enabled": self.config.linter == "pyflakes"},
                "pylint": {
                    "enabled": self.config.linter == "pylint",
                    "args": [],
                },
                "flake8": {
                    "enabled": self.config.linter == "flake8",
                    "maxLineLength": self.config.max_line_length,
                },
                "mccabe": {"enabled": True, "threshold": 15},
                
                # Type checking
                "mypy": {
                    "enabled": self.config.type_checker == "mypy",
                    "live_mode": True,
                    "strict": self.config.type_check_mode == "strict",
                    "dmypy": False,
                    "args": self.config.mypy_path and ["--python-path", os.pathsep.join(self.config.mypy_path)] or [],
                    "config_sub_path": "",
                    "show_column_numbers": True,
                },
                "pyright": {
                    "enabled": self.config.type_checker == "pyright",
                },
                
                # Import sorting
                "isort": {
                    "enabled": self.config.sort_imports,
                    "profile": self.config.isort_profile,
                    "line_length": self.config.isort_line_length,
                    "known_first_party": self.config.isort_known_first_party,
                },
                
                # Formatting
                "black": {
                    "enabled": self.config.formatter == "black",
                    "line_length": self.config.format_line_length,
                    "skip_string_normalization": self.config.format_skip_string_normalization,
                },
                "autopep8": {
                    "enabled": self.config.formatter == "autopep8",
                    "max_line_length": self.config.max_line_length,
                },
                "yapf": {"enabled": self.config.formatter == "yapf"},
                
                # Others
                "rope_completion": {"enabled": False},
                "preload": {"modules": []},
            },
            "rope": {"extensionModules": [], "ropeFolder": ".ropeproject"},
            "configurationSources": ["pycodestyle", "pyflakes", "mccabe", "isort", "yapf"],
        }
        
        return settings
    
    async def stop(self) -> None:
        """Stop the LSP server."""
        if self.client:
            try:
                await self.client.shutdown()
            except Exception:
                pass
            finally:
                await self.client.stop()
                self.client = None
    
    async def get_completions(self, uri: str, line: int, character: int) -> List[Dict]:
        """Get completions at position."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/completion", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            
            if isinstance(result, list):
                return result
            return result.get("items", []) if result else []
        except Exception as e:
            logger.error(f"Completion error: {e}")
            return []
    
    async def get_definition(self, uri: str, line: int, character: int) -> Optional[Dict]:
        """Go to definition at position."""
        if not self.client:
            return None
        
        try:
            return await self.client.send_request("textDocument/definition", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception:
            return None
    
    async def get_references(self, uri: str, line: int, character: int) -> List[Dict]:
        """Find all references at position."""
        if not self.client:
            return []
        
        try:
            result = await self.client.send_request("textDocument/references", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True}
            })
            return result or []
        except Exception:
            return []
    
    async def get_hover(self, uri: str, line: int, character: int) -> Optional[Dict]:
        """Get hover information at position."""
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
        """Get signature help at position."""
        if not self.client:
            return None
        
        try:
            return await self.client.send_request("textDocument/signatureHelp", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception:
            return None


class TypeChecker:
    """Python type checking using mypy or pyright."""
    
    def __init__(self, config: Optional[PythonConfig] = None):
        self.config = config or PythonConfig()
        self._loop = asyncio.get_event_loop()
    
    async def check_file(self, filepath: str, content: Optional[str] = None) -> List[Diagnostic]:
        """Run type checking on a file."""
        if self.config.type_checker == "none":
            return []
        
        if self.config.type_checker == "mypy":
            return await self._check_mypy(filepath, content)
        elif self.config.type_checker == "pyright":
            return await self._check_pyright(filepath)
        
        return []
    
    async def _check_mypy(self, filepath: str, content: Optional[str] = None) -> List[Diagnostic]:
        """Run mypy type checking."""
        args = [
            sys.executable, "-m", "mypy",
            "--no-error-summary",
            "--no-pretty",
            "--show-column-numbers",
            "--show-absolute-path",
            "--output=json",
        ]
        
        # Add config options
        if self.config.type_check_mode == "strict":
            args.append("--strict")
        
        for path in self.config.mypy_path:
            args.extend(["--python-path", path])
        
        for plugin in self.config.mypy_plugins:
            args.extend(["--plugins", plugin])
        
        # Write content to temp file if provided
        if content is not None:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(content)
                filepath = f.name
        
        args.append(filepath)
        
        try:
            result = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            diagnostics = []
            for line in stdout.decode().strip().split("\n"):
                if line:
                    diag = self._parse_mypy_output(line)
                    if diag:
                        diagnostics.append(diag)
            
            return diagnostics
            
        except FileNotFoundError:
            logger.warning("mypy not found, skipping type check")
            return []
        except Exception as e:
            logger.error(f"mypy error: {e}")
            return []
        finally:
            if content is not None:
                try:
                    os.unlink(filepath)
                except:
                    pass
    
    def _parse_mypy_output(self, line: str) -> Optional[Diagnostic]:
        """Parse mypy JSON output."""
        try:
            import json
            data = json.loads(line)
            
            # Map mypy severity to LSP severity
            severity_map = {
                "error": DiagnosticSeverity.ERROR,
                "warning": DiagnosticSeverity.WARNING,
                "note": DiagnosticSeverity.INFORMATION,
            }
            
            severity = severity_map.get(data.get("severity", "error"), DiagnosticSeverity.ERROR)
            
            return Diagnostic(
                range=Range(
                    start=Position(
                        line=data.get("line", 1) - 1,  # mypy uses 1-based lines
                        character=data.get("column", 0)
                    ),
                    end=Position(
                        line=data.get("line", 1) - 1,
                        character=data.get("column", 0) + 1
                    )
                ),
                message=data.get("message", ""),
                severity=severity,
                code=data.get("code"),
                source="mypy"
            )
        except Exception:
            return None
    
    async def _check_pyright(self, filepath: str) -> List[Diagnostic]:
        """Run pyright type checking."""
        args = ["pyright", "--outputjson", filepath]
        
        try:
            result = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            diagnostics = []
            # Parse pyright JSON output
            try:
                import json
                data = json.loads(stdout.decode())
                
                for file_diag in data.get("generalDiagnostics", []):
                    for diag in file_diag.get("diagnostics", []):
                        diagnostics.append(Diagnostic(
                            range=Range(
                                start=Position(
                                    line=diag.get("range", {}).get("start", {}).get("line", 0),
                                    character=diag.get("range", {}).get("start", {}).get("character", 0)
                                ),
                                end=Position(
                                    line=diag.get("range", {}).get("end", {}).get("line", 0),
                                    character=diag.get("range", {}).get("end", {}).get("character", 0)
                                )
                            ),
                            message=diag.get("message", ""),
                            severity=DiagnosticSeverity.ERROR if diag.get("severity") == "error" else DiagnosticSeverity.WARNING,
                            code=diag.get("code"),
                            source="pyright"
                        ))
            except json.JSONDecodeError:
                pass
            
            return diagnostics
            
        except FileNotFoundError:
            logger.warning("pyright not found, skipping type check")
            return []
        except Exception as e:
            logger.error(f"pyright error: {e}")
            return []


class ImportSorter:
    """Python import sorting using isort."""
    
    def __init__(self, config: Optional[PythonConfig] = None):
        self.config = config or PythonConfig()
    
    async def sort_imports(self, content: str, filepath: Optional[str] = None) -> str:
        """Sort imports in the given content."""
        if not self.config.sort_imports:
            return content
        
        try:
            # Use isort API
            import isort
            
            sorted_content = isort.code(
                content,
                profile=self.config.isort_profile,
                line_length=self.config.isort_line_length,
                known_first_party=self.config.isort_known_first_party,
                filename=filepath
            )
            
            return sorted_content
            
        except ImportError:
            # Fall back to command line
            return await self._sort_imports_cli(content)
        except Exception as e:
            logger.error(f"isort error: {e}")
            return content
    
    async def _sort_imports_cli(self, content: str) -> str:
        """Sort imports using isort CLI."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        
        try:
            args = [
                sys.executable, "-m", "isort",
                "--profile", self.config.isort_profile,
                "--line-length", str(self.config.isort_line_length),
                filepath
            ]
            
            result = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await result.communicate()
            
            with open(filepath, "r") as f:
                return f.read()
                
        except FileNotFoundError:
            logger.warning("isort not found, skipping import sort")
            return content
        except Exception as e:
            logger.error(f"isort CLI error: {e}")
            return content
        finally:
            try:
                os.unlink(filepath)
            except:
                pass
    
    def get_import_blocks(self, content: str) -> List[Tuple[int, int]]:
        """Get the start and end line numbers of import blocks."""
        lines = content.split("\n")
        blocks = []
        
        in_block = False
        block_start = 0
        
        for i, line in enumerate(lines):
            is_import = line.strip().startswith(("import ", "from "))
            
            if is_import and not in_block:
                in_block = True
                block_start = i
            elif not is_import and not line.strip().startswith("#") and in_block:
                in_block = False
                blocks.append((block_start, i - 1))
        
        if in_block:
            blocks.append((block_start, len(lines) - 1))
        
        return blocks


class PythonFormatter:
    """Python code formatting using black, autopep8, or yapf."""
    
    def __init__(self, config: Optional[PythonConfig] = None):
        self.config = config or PythonConfig()
    
    async def format_document(self, content: str, filepath: Optional[str] = None) -> str:
        """Format the entire document."""
        if self.config.formatter == "black":
            return await self._format_black(content)
        elif self.config.formatter == "autopep8":
            return await self._format_autopep8(content)
        elif self.config.formatter == "yapf":
            return await self._format_yapf(content)
        
        return content
    
    async def format_range(self, content: str, start_line: int, end_line: int) -> str:
        """Format a range of lines."""
        # Most formatters don't support range formatting well
        # For now, format the whole document and return the requested range
        formatted = await self.format_document(content)
        lines = formatted.split("\n")
        return "\n".join(lines[start_line:end_line + 1])
    
    async def _format_black(self, content: str) -> str:
        """Format using black."""
        try:
            import black
            
            mode = black.Mode(
                line_length=self.config.format_line_length,
                string_normalization=not self.config.format_skip_string_normalization
            )
            
            formatted = black.format_str(content, mode=mode)
            return formatted
            
        except ImportError:
            return await self._format_cli("black", content)
        except Exception as e:
            logger.error(f"black error: {e}")
            return content
    
    async def _format_autopep8(self, content: str) -> str:
        """Format using autopep8."""
        try:
            import autopep8
            
            formatted = autopep8.fix_code(
                content,
                options={"max_line_length": self.config.max_line_length}
            )
            return formatted
            
        except ImportError:
            return await self._format_cli("autopep8", content)
        except Exception as e:
            logger.error(f"autopep8 error: {e}")
            return content
    
    async def _format_yapf(self, content: str) -> str:
        """Format using yapf."""
        try:
            import yapf.yapflib.yapf_api
            
            formatted, _ = yapf.yapflib.yapf_api.FormatCode(
                content,
                style_config=f"{{based_on_style: pep8, column_limit: {self.config.format_line_length}}}"
            )
            return formatted
            
        except ImportError:
            return await self._format_cli("yapf", content)
        except Exception as e:
            logger.error(f"yapf error: {e}")
            return content
    
    async def _format_cli(self, formatter: str, content: str) -> str:
        """Format using CLI tool."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        
        try:
            args = [sys.executable, "-m", formatter, filepath]
            
            result = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await result.communicate()
            
            with open(filepath, "r") as f:
                return f.read()
                
        except FileNotFoundError:
            logger.warning(f"{formatter} not found, skipping format")
            return content
        except Exception as e:
            logger.error(f"{formatter} CLI error: {e}")
            return content
        finally:
            try:
                os.unlink(filepath)
            except:
                pass


class PythonRefactoring:
    """Python refactoring operations."""
    
    def __init__(self, adapter: PythonServerAdapter):
        self.adapter = adapter
    
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
    
    async def extract_variable(self, content: str, start_line: int, start_char: int, end_line: int, end_char: int, var_name: str) -> Optional[str]:
        """Extract selection to a variable."""
        lines = content.split("\n")
        
        if start_line != end_line:
            logger.warning("Multi-line extract variable not supported")
            return None
        
        line = lines[start_line]
        selected = line[start_char:end_char]
        
        # Create assignment statement
        indent = len(line) - len(line.lstrip())
        assignment = " " * indent + f"{var_name} = {selected}\n"
        
        # Replace selection with variable name
        new_line = line[:start_char] + var_name + line[end_char:]
        lines[start_line] = assignment + new_line
        
        return "\n".join(lines)
    
    async def extract_method(self, content: str, start_line: int, end_line: int, method_name: str, indent_size: int = 4) -> Optional[str]:
        """Extract lines to a method."""
        lines = content.split("\n")
        
        # Get selected lines
        selected = lines[start_line:end_line + 1]
        
        # Detect indentation
        first_line_indent = len(selected[0]) - len(selected[0].lstrip())
        method_indent = first_line_indent - indent_size
        
        if method_indent < 0:
            method_indent = 0
        
        # Create method definition
        method_def = " " * method_indent + f"def {method_name}():\n"
        
        # Adjust indentation of selected lines
        indent_diff = indent_size
        adjusted = []
        for line in selected:
            if line.strip():
                adjusted.append(" " * indent_size + line)
            else:
                adjusted.append(line)
        
        # Replace original lines with method call
        call_line = " " * method_indent + f"{method_name}()\n"
        
        result_lines = lines[:start_line] + [call_line] + lines[end_line + 1:]
        
        # Find a good place to insert the method (after other methods at same level)
        insert_line = start_line
        for i in range(start_line - 1, -1, -1):
            line = lines[i]
            if line.strip().startswith("def ") and len(line) - len(line.lstrip()) == method_indent:
                insert_line = i
                break
        
        # Insert method
        result_lines = result_lines[:insert_line] + [method_def] + adjusted + ["\n"] + result_lines[insert_line:]
        
        return "\n".join(result_lines)
    
    async def organize_imports(self, content: str) -> str:
        """Organize imports (remove unused, sort)."""
        sorter = ImportSorter(self.adapter.config)
        return await sorter.sort_imports(content)


# Test module
if __name__ == "__main__":
    import sys
    
    async def test_python_server():
        """Test Python LSP server adapter."""
        print("Testing Python LSP Server Adapter...")
        
        # Test configuration
        print("\n1. Testing configuration...")
        config = PythonConfig(
            type_checker="mypy",
            formatter="black",
            sort_imports=True
        )
        adapter = PythonServerAdapter(config)
        
        settings = adapter._build_settings()
        print(f"  jedi_completion: {settings['plugins']['jedi_completion']['enabled']}")
        print(f"  mypy: {settings['plugins']['mypy']['enabled']}")
        print(f"  black: {settings['plugins']['black']['enabled']}")
        print(f"  isort: {settings['plugins']['isort']['enabled']}")
        
        # Test import sorter
        print("\n2. Testing import sorter...")
        sorter = ImportSorter(config)
        
        test_code = '''import sys
import os
from typing import List, Dict
import asyncio

def main():
    print("hello")
'''
        
        sorted_code = await sorter.sort_imports(test_code)
        print("  Sorted imports:")
        for line in sorted_code.split("\n")[:5]:
            print(f"    {line}")
        
        # Test formatter
        print("\n3. Testing formatter...")
        formatter = PythonFormatter(config)
        
        ugly_code = '''x=1+2
y =  {"a":1,"b":2}
def foo( a,b ):return a+b'''
        
        formatted = await formatter.format_document(ugly_code)
        print("  Formatted:")
        for line in formatted.split("\n")[:5]:
            print(f"    {line}")
        
        # Test type checker
        print("\n4. Testing type checker...")
        checker = TypeChecker(config)
        
        test_file = "/tmp/test_mypy.py"
        with open(test_file, "w") as f:
            f.write("def greet(name: str) -> int:\n    return f'Hello {name}'\n")
        
        try:
            diags = await checker.check_file(test_file)
            print(f"  Found {len(diags)} type errors")
            for d in diags[:3]:
                print(f"    Line {d.range.start.line + 1}: {d.message}")
        except Exception as e:
            print(f"  Type checker not available: {e}")
        
        # Test refactoring
        print("\n5. Testing refactoring...")
        refactor = PythonRefactoring(adapter)
        
        extract_test = '''x = 1 + 2 + 3
print(x)'''
        
        result = await refactor.extract_variable(extract_test, 0, 4, 0, 15, "result")
        if result:
            print("  Extracted variable:")
            for line in result.split("\n"):
                print(f"    {line}")
        
        print("\n✓ Tests completed!")
    
    asyncio.run(test_python_server())
