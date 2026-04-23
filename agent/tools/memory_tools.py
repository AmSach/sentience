"""Memory tools - vault, graph, compression access."""
import json, time, hashlib
from .registry import tool, ToolContext, ToolResult

def get_compression():
    from memory.compression import SentienceCompression
    return SentienceCompression()

def get_vault():
    from memory.vault import SentienceVault
    return SentienceVault()

def get_graph():
    from memory.graph import SentienceGraph
    return SentienceGraph()

@tool("vault_write", "Write to Obsidian-like vault",
      {"path": {"type": "string"}, "content": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}, "optional": True}})
def vault_write(ctx: ToolContext, path: str, content: str, tags: list = None) -> ToolResult:
    v = get_vault()
    note_id = v.write_note(path, content, tags or [])
    return ToolResult(success=True, output=f"Written to vault: {path}", metadata={"note_id": note_id})

@tool("vault_read", "Read from vault",
      {"path": {"type": "string"}})
def vault_read(ctx: ToolContext, path: str) -> ToolResult:
    v = get_vault()
    note = v.get_note(path)
    if not note:
        return ToolResult(success=False, error=f"Note not found: {path}")
    return ToolResult(success=True, output=note["content"], metadata={"path": path})

@tool("vault_search", "Search vault notes",
      {"query": {"type": "string"}, "limit": {"type": "integer", "optional": True}})
def vault_search(ctx: ToolContext, query: str, limit: int = 10) -> ToolResult:
    v = get_vault()
    results = v.search_notes(query, limit)
    return ToolResult(success=True, output=json.dumps(results, indent=2), metadata={"count": len(results)})

@tool("vault_links", "Get bidirectional links for a note",
      {"path": {"type": "string"}})
def vault_links(ctx: ToolContext, path: str) -> ToolResult:
    v = get_vault()
    links = v.get_links(path)
    return ToolResult(success=True, output=json.dumps(links, indent=2), metadata={"links": links})

@tool("vault_graph", "Get vault as graph JSON",
      {})
def vault_graph(ctx: ToolContext) -> ToolResult:
    v = get_vault()
    g = v.get_graph()
    return ToolResult(success=True, output=json.dumps(g))

@tool("compress", "Compress text using Sentience algorithm",
      {"text": {"type": "string"}, "level": {"type": "string", "optional": True}})
def compress(ctx: ToolContext, text: str, level: str = "smart") -> ToolResult:
    c = get_compression()
    result = c.compress(text, level)
    return ToolResult(success=True, output=result["compressed"], metadata={"ratio": result["ratio"], "original_len": result["original_len"]})

@tool("decompress", "Decompress Sentience compressed text",
      {"compressed": {"type": "string"}})
def decompress(ctx: ToolContext, compressed: str) -> ToolResult:
    c = get_compression()
    result = c.decompress(compressed)
    return ToolResult(success=True, output=result, metadata={})

@tool("graph_query", "Query entity graph",
      {"entity": {"type": "string"}, "depth": {"type": "integer", "optional": True}})
def graph_query(ctx: ToolContext, entity: str, depth: int = 1) -> ToolResult:
    g = get_graph()
    results = g.traverse(entity, depth)
    return ToolResult(success=True, output=json.dumps(results, indent=2), metadata={"entity": entity, "depth": depth})

@tool("graph_add", "Add entity to graph",
      {"entity": {"type": "string"}, "relations": {"type": "array", "optional": True}, "props": {"type": "object", "optional": True}})
def graph_add(ctx: ToolContext, entity: str, relations: list = None, props: dict = None) -> ToolResult:
    g = get_graph()
    g.add_entity(entity, relations or [], props or {})
    return ToolResult(success=True, output=f"Added to graph: {entity}", metadata={"entity": entity})
