#!/usr/bin/env python3
"""Hosting Server - Local web hosting with FastAPI"""
import os
import ssl
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

class HostingServer:
    """Local hosting server similar to zo.space"""
    
    def __init__(self, root_dir: str, port: int = 3000, host: str = "localhost"):
        self.root_dir = Path(root_dir)
        self.port = port
        self.host = host
        self.app = FastAPI()
        self.routes: dict = {}
        self._setup_middleware()
        self._setup_routes()
        
    def _setup_middleware(self):
        """Setup CORS middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
    def _setup_routes(self):
        """Setup default routes"""
        
        @self.app.get("/")
        async def index():
            return {"status": "ok", "message": "Sentience Hosting Server"}
            
        @self.app.get("/health")
        async def health():
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
            
        @self.app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
        async def catch_all(path: str, request: Request):
            # Check if custom route exists
            if path in self.routes:
                route_handler = self.routes[path]
                if callable(route_handler):
                    return await route_handler(request)
                    
            # Check for static file
            file_path = self.root_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
                
            # Check for SPA fallback
            index_path = self.root_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
                
            raise HTTPException(status_code=404, detail="Not found")
            
    def add_route(self, path: str, handler, methods: list = ["GET"]):
        """Add a custom route"""
        self.routes[path.lstrip("/")] = handler
        
        # Also register with FastAPI
        for method in methods:
            self.app.add_api_route(
                f"/{path.lstrip(')(')}",
                handler,
                methods=[method]
            )
            
    def add_static(self, path: str, directory: str):
        """Mount static files directory"""
        self.app.mount(f"/{path.lstrip(')(')}", StaticFiles(directory=directory), name=path)
        
    def add_api_route(self, path: str, handler, methods: list = None):
        """Add API route"""
        self.app.add_api_route(path, handler, methods=methods or ["GET"])
        
    def run(self, ssl_cert: str = None, ssl_key: str = None):
        """Start the server"""
        ssl_config = None
        if ssl_cert and ssl_key:
            ssl_config = {"ssl_certfile": ssl_cert, "ssl_keyfile": ssl_key}
            
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            **(ssl_config or {})
        )


class RouteManager:
    """Manage dynamic routes"""
    
    def __init__(self, server: HostingServer):
        self.server = server
        self.routes_file = Path.home() / ".sentience" / "routes.json"
        self.routes: dict = {}
        self._load_routes()
        
    def _load_routes(self):
        """Load routes from file"""
        if self.routes_file.exists():
            with open(self.routes_file) as f:
                self.routes = json.load(f)
                
    def _save_routes(self):
        """Save routes to file"""
        self.routes_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.routes_file, 'w') as f:
            json.dump(self.routes, f, indent=2)
            
    def create_route(self, path: str, handler_code: str, is_api: bool = False):
        """Create a new route from code"""
        # Compile handler code
        local_vars = {}
        exec(handler_code, {"__builtins__": __builtins__, "request": None}, local_vars)
        
        handler = local_vars.get("handler")
        if handler:
            self.server.add_route(path, handler)
            self.routes[path] = {
                "code": handler_code,
                "is_api": is_api,
                "created": datetime.now().isoformat()
            }
            self._save_routes()
            
    def delete_route(self, path: str):
        """Delete a route"""
        if path in self.routes:
            del self.routes[path]
            self._save_routes()


class DomainManager:
    """Manage custom domains for local hosting"""
    
    def __init__(self):
        self.hosts_file = Path("/etc/hosts") if os.name != 'nt' else Path(os.environ.get("SystemRoot", "C:\\Windows")) / "system32" / "drivers" / "etc" / "hosts"
        self.domains: dict = {}
        
    def add_domain(self, domain: str, port: int, ssl: bool = False):
        """Add a local domain"""
        # Add to hosts file (requires sudo on Unix)
        entry = f"127.0.0.1    {domain}\n"
        
        # Store domain config
        self.domains[domain] = {
            "port": port,
            "ssl": ssl,
            "url": f"{"https" if ssl else "http"}://{domain}:{port}"
        }
        
    def remove_domain(self, domain: str):
        """Remove a local domain"""
        if domain in self.domains:
            del self.domains[domain]
            
    def generate_ssl_cert(self, domain: str):
        """Generate self-signed SSL certificate"""
        import subprocess
        
        cert_file = Path.home() / ".sentience" / "ssl" / f"{domain}.crt"
        key_file = Path.home() / ".sentience" / "ssl" / f"{domain}.key"
        
        cert_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate with openssl
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_file), "-out", str(cert_file),
            "-days", "365", "-nodes",
            "-subj", f"/CN={domain}"
        ], check=True, capture_output=True)
        
        return str(cert_file), str(key_file)


class TunnelManager:
    """Manage external tunnels (ngrok, cloudflare)"""
    
    def __init__(self):
        self.tunnels: dict = {}
        
    def start_ngrok(self, port: int, auth_token: str = None) -> str:
        """Start ngrok tunnel"""
        try:
            from pyngrok import ngrok
            
            if auth_token:
                ngrok.set_auth_token(auth_token)
                
            tunnel = ngrok.connect(port)
            public_url = tunnel.public_url
            self.tunnels["ngrok"] = {
                "url": public_url,
                "port": port,
                "tunnel": tunnel
            }
            return public_url
        except ImportError:
            raise RuntimeError("pyngrok not installed. Run: pip install pyngrok")
            
    def stop_tunnel(self, name: str = "ngrok"):
        """Stop a tunnel"""
        if name in self.tunnels:
            tunnel_info = self.tunnels[name]
            if "tunnel" in tunnel_info:
                try:
                    from pyngrok import ngrok
                    ngrok.disconnect(tunnel_info["tunnel"].public_url)
                except:
                    pass
            del self.tunnels[name]
