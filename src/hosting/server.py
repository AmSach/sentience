#!/usr/bin/env python3
"""Hosting Server - Local web server for hosting sites and APIs"""
import asyncio
import json
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from datetime import datetime
import socket
import threading

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None  # type: ignore

try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False


class HostingServer:
    """Local web server for hosting sites, APIs, and websockets"""
    
    def __init__(self, host: str = "localhost", port: int = 8080,
                 static_dir: str = None):
        self.host = host
        self.port = port
        self.static_dir = Path(static_dir or (Path.home() / ".sentience" / "public"))
        self.static_dir.mkdir(parents=True, exist_ok=True)
        
        self.app = None
        self.runner = None
        self.site = None
        self.routes: Dict[str, Callable] = {}
        self.is_running = False
        self._ws_clients = set()
    
    def route(self, path: str, method: str = "GET"):
        """Decorator to register a route"""
        def decorator(func):
            self.routes[f"{method}:{path}"] = func
            return func
        return decorator
    
    def add_route(self, path: str, handler: Callable, method: str = "GET"):
        """Programmatically add a route"""
        self.routes[f"{method}:{path}"] = handler
    
    def remove_route(self, path: str, method: str = "GET"):
        """Remove a route"""
        key = f"{method}:{path}"
        if key in self.routes:
            del self.routes[key]
    
    async def _handle_request(self, request) -> "web.Response":
        """Handle incoming HTTP request"""
        if not AIOHTTP_AVAILABLE or web is None:
            return {"success": False, "error": "aiohttp not available"}  # type: ignore
        method = request.method
        path = request.path
        key = f"{method}:{path}"
        
        # Check for exact route match
        if key in self.routes:
            try:
                result = await self.routes[key](request) if asyncio.iscoroutinefunction(self.routes[key]) else self.routes[key](request)
                if isinstance(result, dict):
                    return web.json_response(result)
                elif isinstance(result, str):
                    return web.Response(text=result, content_type="text/html")
                return result
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        
        # Check for path parameters (simple matching)
        for route_key, handler in self.routes.items():
            route_method, route_path = route_key.split(":", 1)
            if route_method != method:
                continue
            
            # Simple param matching: /api/users/:id
            if ":" in route_path:
                route_parts = route_path.split("/")
                path_parts = path.split("/")
                
                if len(route_parts) != len(path_parts):
                    continue
                
                params = {}
                match = True
                for rp, pp in zip(route_parts, path_parts):
                    if rp.startswith(":"):
                        params[rp[1:]] = pp
                    elif rp != pp:
                        match = False
                        break
                
                if match:
                    request.path_params = params
                    try:
                        result = await handler(request) if asyncio.iscoroutinefunction(handler) else handler(request)
                        if isinstance(result, dict):
                            return web.json_response(result)
                        return result
                    except Exception as e:
                        return web.json_response({"error": str(e)}, status=500)
        
        # Serve static files
        if method == "GET":
            static_path = self.static_dir / path.lstrip("/")
            if static_path.exists() and static_path.is_file():
                return web.FileResponse(static_path)
            
            # Try index.html for directories
            if static_path.exists() and static_path.is_dir():
                index_path = static_path / "index.html"
                if index_path.exists():
                    return web.FileResponse(index_path)
        
        return web.json_response({"error": "Not found"}, status=404)
    
    async def start(self) -> Dict:
        """Start the server"""
        if not AIOHTTP_AVAILABLE:
            return {"success": False, "error": "aiohttp not installed. Run: pip install aiohttp"}
        
        try:
            self.app = web.Application()
            
            # Add routes
            for route_key in self.routes:
                method, path = route_key.split(":", 1)
                self.app.router.add_route(method, path, self._handle_request)
            
            # Add catch-all for static files and unmatched routes
            self.app.router.add_route("*", "/{path:.*}", self._handle_request)
            
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            self.is_running = True
            return {
                "success": True,
                "url": f"http://{self.host}:{self.port}",
                "message": f"Server running on port {self.port}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def stop(self) -> Dict:
        """Stop the server"""
        try:
            if self.runner:
                await self.runner.cleanup()
            self.is_running = False
            return {"success": True, "message": "Server stopped"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_url(self, path: str = "") -> str:
        """Get full URL for a path"""
        return f"http://{self.host}:{self.port}{path}"
    
    def is_port_available(self) -> bool:
        """Check if port is available"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.host, self.port))
                return True
        except:
            return False
    
    def find_available_port(self, start: int = 8080, max_tries: int = 100) -> int:
        """Find an available port"""
        for port in range(start, start + max_tries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((self.host, port))
                    return port
            except:
                continue
        return -1
    
    # Convenience methods for common routes
    
    def api_endpoint(self, path: str, method: str = "GET"):
        """Decorator for API endpoints"""
        return self.route(f"/api{path}", method)
    
    def static_file(self, filename: str, content: str) -> Dict:
        """Create a static file"""
        try:
            filepath = self.static_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
            return {"success": True, "url": self.get_url(f"/{filename}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def serve_directory(self, directory: str) -> Dict:
        """Serve files from a directory"""
        try:
            import shutil
            dir_path = Path(directory)
            if dir_path.exists():
                # Copy to static dir
                for item in dir_path.iterdir():
                    if item.is_file():
                        shutil.copy(item, self.static_dir / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, self.static_dir / item.name, dirs_exist_ok=True)
                return {"success": True, "url": self.get_url()}
            return {"success": False, "error": "Directory not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Tool definitions for AI
HOSTING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "server_start",
            "description": "Start local hosting server",
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Port number (default: 8080)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "server_stop",
            "description": "Stop the hosting server",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "server_add_route",
            "description": "Add an API route",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Route path (e.g., /api/hello)"},
                    "response": {"type": "object", "description": "JSON response"}
                },
                "required": ["path", "response"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "server_serve_file",
            "description": "Serve a static file",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name"},
                    "content": {"type": "string", "description": "File content"}
                },
                "required": ["filename", "content"]
            }
        }
    }
]

# Singleton
_hosting_server: Optional[HostingServer] = None

def get_hosting_server() -> HostingServer:
    """Get or create hosting server"""
    global _hosting_server
    if _hosting_server is None:
        _hosting_server = HostingServer()
    return _hosting_server

async def execute_hosting_tool(name: str, args: Dict) -> Dict:
    """Execute hosting tool by name"""
    server = get_hosting_server()
    
    if name == "server_start":
        if args.get("port"):
            server.port = args["port"]
        if not server.is_port_available():
            server.port = server.find_available_port()
        return await server.start()
    elif name == "server_stop":
        return await server.stop()
    elif name == "server_add_route":
        response = args.get("response", {})
        server.add_route(args.get("path", "/"), lambda r: response)
        return {"success": True, "url": server.get_url(args.get("path", "/"))}
    elif name == "server_serve_file":
        return server.static_file(args.get("filename", ""), args.get("content", ""))
    else:
        return {"success": False, "error": f"Unknown hosting tool: {name}"}

def run_server_sync(port: int = 8080) -> Dict:
    """Run server synchronously (blocking)"""
    async def run():
        server = get_hosting_server()
        server.port = port
        if not server.is_port_available():
            server.port = server.find_available_port()
        result = await server.start()
        if result["success"]:
            print(f"Server running at {result['url']}")
            # Keep running
            while server.is_running:
                await asyncio.sleep(1)
        return result
    
    return asyncio.run(run())
