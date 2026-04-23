#!/usr/bin/env python3
"""
Integration tests for LSP package.
Tests all components together as a package.
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lsp import (
    LSPClient,
    ServerCapabilities,
    StdioTransport,
    TCPTransport,
    TransportType,
    create_stdio_client,
    
    LSPManager,
    LanguageId,
    LanguageConfig,
    Document,
    
    CompletionProvider,
    CompletionItem,
    CompletionItemKind,
    SnippetManager,
    
    Diagnostic,
    DiagnosticSeverity,
    DiagnosticCollection,
    QuickFixProvider,
    SquiggleRenderer,
    
    PythonConfig,
    TypeChecker,
    ImportSorter,
    PythonFormatter,
    
    TypeScriptConfig,
    TypeScriptRefactoring,
)


def test_client():
    """Test LSP client components."""
    print("\n=== Testing LSP Client ===")
    
    # Test transport creation
    print("1. Testing transport creation...")
    transport = StdioTransport(["pylsp"], cwd="/tmp")
    assert transport.command == ["pylsp"]
    print("   ✓ StdioTransport created")
    
    tcp_transport = TCPTransport("localhost", 8080)
    assert tcp_transport.host == "localhost"
    assert tcp_transport.port == 8080
    print("   ✓ TCPTransport created")
    
    # Test client creation
    print("2. Testing client creation...")
    client = create_stdio_client(["pylsp"])
    assert client is not None
    print("   ✓ LSPClient created via factory")
    
    print("✓ Client tests passed")


def test_manager():
    """Test LSP manager components."""
    print("\n=== Testing LSP Manager ===")
    
    # Test language config
    print("1. Testing language configurations...")
    configs = LanguageConfig.get_default_configs()
    assert LanguageId.PYTHON in configs
    assert LanguageId.TYPESCRIPT in configs
    assert LanguageId.GO in configs
    print(f"   ✓ {len(configs)} language configs available")
    
    # Test manager creation
    print("2. Testing manager creation...")
    manager = LSPManager("/tmp")
    assert manager.workspace_root == "/tmp"
    print("   ✓ LSPManager created")
    
    # Test language detection
    print("3. Testing language detection...")
    lang = manager.get_language_for_file("test.py")
    assert lang == LanguageId.PYTHON
    
    lang = manager.get_language_for_file("app.ts")
    assert lang == LanguageId.TYPESCRIPT
    
    lang = manager.get_language_for_file("main.go")
    assert lang == LanguageId.GO
    print("   ✓ Language detection works")
    
    print("✓ Manager tests passed")


def test_completion():
    """Test completion provider."""
    print("\n=== Testing Completion Provider ===")
    
    # Test snippet manager
    print("1. Testing snippets...")
    snippet_mgr = SnippetManager()
    
    py_snippets = snippet_mgr.get_snippets("python")
    assert len(py_snippets) > 0
    print(f"   ✓ {len(py_snippets)} Python snippets")
    
    js_snippets = snippet_mgr.get_snippets("javascript")
    assert len(js_snippets) > 0
    print(f"   ✓ {len(js_snippets)} JavaScript snippets")
    
    # Test snippet expansion
    print("2. Testing snippet expansion...")
    def_snippet = snippet_mgr.find_snippet("python", "def")
    assert def_snippet is not None
    expanded = def_snippet.expand({"name": "hello", "params": "name", "docstring": "Say hello", "pass": "return f'Hello {name}'"})
    assert "def hello" in expanded
    print("   ✓ Snippet expansion works")
    
    # Test completion item
    print("3. Testing completion items...")
    item = CompletionItem(
        label="print",
        kind=CompletionItemKind.FUNCTION,
        detail="Print to stdout",
        documentation="Prints values to standard output"
    )
    assert item.label == "print"
    print("   ✓ CompletionItem created")
    
    print("✓ Completion tests passed")


def test_diagnostics():
    """Test diagnostics components."""
    print("\n=== Testing Diagnostics ===")
    
    # Test diagnostic creation
    print("1. Testing diagnostic creation...")
    diag = Diagnostic.from_lsp({
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
        "message": "Undefined variable 'x'",
        "severity": 1,
        "code": "F821",
        "source": "pyflakes"
    })
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.squiggle_color == "#F44747"
    print("   ✓ Diagnostic created from LSP format")
    
    # Test collection
    print("2. Testing diagnostic collection...")
    collection = DiagnosticCollection()
    
    changes = []
    def listener(uri, diags):
        changes.append(len(diags))
    collection.add_listener(listener)
    
    collection.set("file:///test.py", [
        diag,
        Diagnostic.from_lsp({
            "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 10}},
            "message": "Unused import",
            "severity": 2,
            "source": "pycodestyle"
        })
    ])
    
    counts = collection.count()
    assert counts[DiagnosticSeverity.ERROR] == 1
    assert counts[DiagnosticSeverity.WARNING] == 1
    print("   ✓ Collection tracks diagnostics")
    
    # Test squiggle renderer
    print("3. Testing squiggle rendering...")
    renderer = SquiggleRenderer()
    decorations = renderer.render("file:///test.py", collection.get("file:///test.py"))
    assert len(decorations) == 2
    print("   ✓ Squiggle rendering works")
    
    print("✓ Diagnostics tests passed")


def test_python_server():
    """Test Python server components."""
    print("\n=== Testing Python Server ===")
    
    # Test configuration
    print("1. Testing Python configuration...")
    config = PythonConfig(
        type_checker="mypy",
        formatter="black",
        sort_imports=True,
        format_line_length=100
    )
    assert config.type_checker == "mypy"
    assert config.formatter == "black"
    print("   ✓ PythonConfig created")
    
    # Test import sorter
    print("2. Testing import sorting...")
    sorter = ImportSorter(config)
    
    test_code = '''import sys
import os
from typing import List

def main():
    pass
'''
    
    # Get import blocks
    blocks = sorter.get_import_blocks(test_code)
    assert len(blocks) == 1
    print("   ✓ Import block detection works")
    
    # Test formatter
    print("3. Testing Python formatter...")
    formatter = PythonFormatter(config)
    
    ugly_code = '''x=1+2
y =  {"a":1,"b":2}'''
    
    # Note: Actual formatting requires black/isort installed
    print("   ✓ PythonFormatter created (formatting requires black)")
    
    # Test type checker
    print("4. Testing type checker...")
    checker = TypeChecker(config)
    print("   ✓ TypeChecker created (checking requires mypy)")
    
    print("✓ Python server tests passed")


def test_typescript_server():
    """Test TypeScript server components."""
    print("\n=== Testing TypeScript Server ===")
    
    # Test configuration
    print("1. Testing TypeScript configuration...")
    config = TypeScriptConfig(
        typescript_suggest=True,
        typescript_format=True,
        format_tab_size=2,
        include_inlay_parameter_name_hints="all"
    )
    assert config.format_tab_size == 2
    assert config.include_inlay_parameter_name_hints == "all"
    print("   ✓ TypeScriptConfig created")
    
    # Test initialization options
    print("2. Testing initialization options...")
    adapter = TypeScriptServerAdapter(config)
    init_opts = adapter._build_initialization_options()
    
    assert init_opts["hostInfo"] == "sentience-lsp"
    assert init_opts["preferences"]["includeCompletionsForModuleExports"] == True
    print("   ✓ Initialization options generated")
    
    # Test settings
    print("3. Testing TypeScript settings...")
    settings = adapter._build_settings()
    
    assert settings["typescript"]["suggest"]["enabled"] == True
    assert settings["typescript"]["format"]["tabSize"] == 2
    print("   ✓ Settings generated")
    
    print("✓ TypeScript server tests passed")


def test_document():
    """Test Document class."""
    print("\n=== Testing Document ===")
    
    # Create test file
    test_file = "/tmp/test_doc.py"
    with open(test_file, "w") as f:
        f.write("def hello():\n    return 'world'\n")
    
    # Test document creation
    print("1. Testing document creation from file...")
    doc = Document.from_file(test_file)
    assert doc.language_id == LanguageId.PYTHON
    assert "hello" in doc.text
    print("   ✓ Document created from file")
    
    # Test language detection
    print("2. Testing language detection...")
    
    with open("/tmp/test.ts", "w") as f:
        f.write("const x = 1;\n")
    
    ts_doc = Document.from_file("/tmp/test.ts")
    assert ts_doc.language_id == LanguageId.TYPESCRIPT
    print("   ✓ TypeScript detected")
    
    with open("/tmp/test.go", "w") as f:
        f.write("package main\n")
    
    go_doc = Document.from_file("/tmp/test.go")
    assert go_doc.language_id == LanguageId.GO
    print("   ✓ Go detected")
    
    print("✓ Document tests passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Sentience v3.0 LSP Integration Tests")
    print("=" * 60)
    
    try:
        test_client()
        test_manager()
        test_completion()
        test_diagnostics()
        test_python_server()
        test_typescript_server()
        test_document()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
