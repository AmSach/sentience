"""
Sentience v3.0 - Tunnel Management
External access via ngrok, cloudflare tunnel, and localtunnel.
"""

import os
import re
import sys
import json
import logging
import asyncio
import subprocess
import signal
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import socket


logger = logging.getLogger("sentience.tunnel")


class TunnelProvider(str, Enum):
    """Tunnel provider types."""
    NGROK = "ngrok"
    CLOUDFLARE = "cloudflare"
    LOCALTUNNEL = "localtunnel"


@dataclass
class TunnelConfig:
    """Tunnel configuration."""
    provider: TunnelProvider = TunnelProvider.NGROK
    local_port: int = 8000
    local_host: str = "localhost"
    subdomain: Optional[str] = None
    region: Optional[str] = None
    auth_token: Optional[str] = None
    hostname: Optional[str] = None
    
    # Options
    inspect_enabled: bool = True
    bind_tls: bool = True
    timeout: int = 300
    
    def to_dict(self) -> Dict:
        return {
            "provider": self.provider.value,
            "local_port": self.local_port,
            "local_host": self.local_host,
            "subdomain": self.subdomain,
            "region": self.region,
            "hostname": self.hostname,
            "inspect_enabled": self.inspect_enabled,
            "bind_tls": self.bind_tls,
            "timeout": self.timeout
        }


@dataclass
class TunnelInfo:
    """Information about an active tunnel."""
    id: str
    provider: TunnelProvider
    public_url: str
    local_address: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "provider": self.provider.value,
            "public_url": self.public_url,
            "local_address": self.local_address,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "metadata": self.metadata
        }


class TunnelBase(ABC):
    """Base class for tunnel providers."""
    
    def __init__(self, config: TunnelConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._tunnel_info: Optional[TunnelInfo] = None
        self._is_running = False
    
    @abstractmethod
    def start(self) -> TunnelInfo:
        """Start the tunnel."""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop the tunnel."""
        pass
    
    @abstractmethod
    def get_public_url(self) -> Optional[str]:
        """Get the public URL."""
        pass
    
    def is_running(self) -> bool:
        """Check if tunnel is running."""
        if self._process is None:
            return False
        
        return self._process.poll() is None
    
    def get_info(self) -> Optional[TunnelInfo]:
        """Get tunnel information."""
        return self._tunnel_info


class NgrokTunnel(TunnelBase):
    """ngrok tunnel implementation."""
    
    def __init__(self, config: TunnelConfig):
        super().__init__(config)
        self._api_url = "http://localhost:4040"
        self._ngrok_path: Optional[str] = None
    
    def _find_ngrok(self) -> Optional[str]:
        """Find ngrok binary."""
        if self._ngrok_path:
            return self._ngrok_path
        
        # Check common locations
        paths = [
            "ngrok",
            "/usr/local/bin/ngrok",
            "/usr/bin/ngrok",
            "/opt/homebrew/bin/ngrok",
            os.path.expanduser("~/.local/bin/ngrok"),
        ]
        
        for path in paths:
            if shutil.which(path):
                self._ngrok_path = path
                return path
        
        return None
    
    def is_installed(self) -> bool:
        """Check if ngrok is installed."""
        return self._find_ngrok() is not None
    
    def set_auth_token(self, token: str) -> bool:
        """Set ngrok auth token."""
        ngrok = self._find_ngrok()
        if not ngrok:
            return False
        
        result = subprocess.run(
            [ngrok, "config", "add-authtoken", token],
            capture_output=True
        )
        
        return result.returncode == 0
    
    def start(self) -> TunnelInfo:
        """Start ngrok tunnel."""
        ngrok = self._find_ngrok()
        if not ngrok:
            raise RuntimeError("ngrok not found. Install from https://ngrok.com")
        
        if self._process and self.is_running():
            return self._tunnel_info
        
        # Build command
        cmd = [
            ngrok,
            "http",
            f"{self.config.local_host}:{self.config.local_port}",
        ]
        
        # Add options
        if self.config.subdomain:
            cmd.extend(["--subdomain", self.config.subdomain])
        
        if self.config.region:
            cmd.extend(["--region", self.config.region])
        
        if not self.config.inspect_enabled:
            cmd.append("--inspect=false")
        
        if self.config.bind_tls:
            cmd.append("--bind-tls=true")
        
        # Start process
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for tunnel to start
        import time
        max_wait = 10
        
        for _ in range(max_wait):
            time.sleep(1)
            
            try:
                url = self.get_public_url()
                if url:
                    self._is_running = True
                    
                    self._tunnel_info = TunnelInfo(
                        id=f"ngrok-{self._process.pid}",
                        provider=TunnelProvider.NGROK,
                        public_url=url,
                        local_address=f"{self.config.local_host}:{self.config.local_port}",
                        metadata={"api_url": self._api_url}
                    )
                    
                    logger.info(f"ngrok tunnel started: {url}")
                    return self._tunnel_info
            except Exception:
                continue
        
        raise RuntimeError("Failed to start ngrok tunnel")
    
    def stop(self) -> bool:
        """Stop ngrok tunnel."""
        if not self._process:
            return True
        
        self._process.terminate()
        
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        
        self._process = None
        self._is_running = False
        self._tunnel_info = None
        
        logger.info("ngrok tunnel stopped")
        return True
    
    def get_public_url(self) -> Optional[str]:
        """Get public URL from ngrok API."""
        try:
            url = f"{self._api_url}/api/tunnels"
            
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
            
            tunnels = data.get("tunnels", [])
            
            if tunnels:
                tunnel = tunnels[0]
                return tunnel.get("public_url")
        except Exception as e:
            logger.debug(f"Failed to get ngrok URL: {e}")
        
        return None
    
    def get_tunnels(self) -> List[Dict]:
        """Get all active ngrok tunnels."""
        try:
            url = f"{self._api_url}/api/tunnels"
            
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
            
            return data.get("tunnels", [])
        except Exception:
            return []


class CloudflareTunnel(TunnelBase):
    """Cloudflare tunnel implementation using cloudflared."""
    
    def __init__(self, config: TunnelConfig):
        super().__init__(config)
        self._cloudflared_path: Optional[str] = None
    
    def _find_cloudflared(self) -> Optional[str]:
        """Find cloudflared binary."""
        if self._cloudflared_path:
            return self._cloudflared_path
        
        paths = [
            "cloudflared",
            "/usr/local/bin/cloudflared",
            "/usr/bin/cloudflared",
            "/opt/homebrew/bin/cloudflared",
        ]
        
        for path in paths:
            if shutil.which(path):
                self._cloudflared_path = path
                return path
        
        return None
    
    def is_installed(self) -> bool:
        """Check if cloudflared is installed."""
        return self._find_cloudflared() is not None
    
    def login(self) -> bool:
        """Login to Cloudflare."""
        cloudflared = self._find_cloudflared()
        if not cloudflared:
            return False
        
        result = subprocess.run(
            [cloudflared, "tunnel", "login"],
            capture_output=True
        )
        
        return result.returncode == 0
    
    def create_tunnel(self, name: str) -> Optional[str]:
        """Create a named tunnel."""
        cloudflared = self._find_cloudflared()
        if not cloudflared:
            return None
        
        result = subprocess.run(
            [cloudflared, "tunnel", "create", name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Parse tunnel ID from output
            match = re.search(r'Tunnel credentials written to .+/([a-f0-9-]+)\.json', result.stderr)
            if match:
                return match.group(1)
        
        return None
    
    def start(self) -> TunnelInfo:
        """Start Cloudflare tunnel."""
        cloudflared = self._find_cloudflared()
        if not cloudflared:
            raise RuntimeError(
                "cloudflared not found. Install from "
                "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
            )
        
        if self._process and self.is_running():
            return self._tunnel_info
        
        # Build command - quick tunnel for instant URL
        cmd = [
            cloudflared,
            "tunnel",
            "--url", f"http://{self.config.local_host}:{self.config.local_port}",
            "--no-autoupdate",
        ]
        
        # Add hostname if specified
        if self.config.hostname:
            cmd.extend(["--hostname", self.config.hostname])
        
        # Start process
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Parse URL from output
        import time
        max_wait = 15
        
        for _ in range(max_wait):
            time.sleep(1)
            
            # Read stderr for URL
            if self._process.stderr:
                line = self._process.stderr.readline()
                
                # Look for tunnel URL
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match:
                    url = match.group(0)
                    
                    self._is_running = True
                    self._tunnel_info = TunnelInfo(
                        id=f"cloudflare-{self._process.pid}",
                        provider=TunnelProvider.CLOUDFLARE,
                        public_url=url,
                        local_address=f"{self.config.local_host}:{self.config.local_port}"
                    )
                    
                    logger.info(f"Cloudflare tunnel started: {url}")
                    return self._tunnel_info
        
        raise RuntimeError("Failed to start Cloudflare tunnel")
    
    def stop(self) -> bool:
        """Stop Cloudflare tunnel."""
        if not self._process:
            return True
        
        self._process.terminate()
        
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        
        self._process = None
        self._is_running = False
        self._tunnel_info = None
        
        logger.info("Cloudflare tunnel stopped")
        return True
    
    def get_public_url(self) -> Optional[str]:
        """Get public URL."""
        if self._tunnel_info:
            return self._tunnel_info.public_url
        return None


class LocaltunnelTunnel(TunnelBase):
    """localtunnel implementation."""
    
    def __init__(self, config: TunnelConfig):
        super().__init__(config)
        self._lt_path: Optional[str] = None
    
    def _find_lt(self) -> Optional[str]:
        """Find lt (localtunnel) binary."""
        if self._lt_path:
            return self._lt_path
        
        # localtunnel is an npm package
        if shutil.which("lt"):
            self._lt_path = "lt"
            return "lt"
        
        # Check npx
        if shutil.which("npx"):
            self._lt_path = "npx"
            return "npx"
        
        return None
    
    def is_installed(self) -> bool:
        """Check if localtunnel is installed."""
        return self._find_lt() is not None
    
    def install(self) -> bool:
        """Install localtunnel via npm."""
        npm = shutil.which("npm")
        if not npm:
            return False
        
        result = subprocess.run(
            [npm, "install", "-g", "localtunnel"],
            capture_output=True
        )
        
        return result.returncode == 0
    
    def start(self) -> TunnelInfo:
        """Start localtunnel."""
        lt = self._find_lt()
        if not lt:
            raise RuntimeError(
                "localtunnel not found. Install with: npm install -g localtunnel"
            )
        
        if self._process and self.is_running():
            return self._tunnel_info
        
        # Build command
        if lt == "npx":
            cmd = ["npx", "localtunnel", "--port", str(self.config.local_port)]
        else:
            cmd = ["lt", "--port", str(self.config.local_port)]
        
        if self.config.subdomain:
            cmd.extend(["--subdomain", self.config.subdomain])
        
        # Start process
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Parse URL from output
        import time
        max_wait = 15
        
        for _ in range(max_wait):
            time.sleep(1)
            
            if self._process.stdout:
                line = self._process.stdout.readline()
                
                # Look for URL
                match = re.search(r'https://[a-zA-Z0-9-]+\.loca\.lt', line)
                if match:
                    url = match.group(0)
                    
                    self._is_running = True
                    self._tunnel_info = TunnelInfo(
                        id=f"localtunnel-{self._process.pid}",
                        provider=TunnelProvider.LOCALTUNNEL,
                        public_url=url,
                        local_address=f"localhost:{self.config.local_port}"
                    )
                    
                    logger.info(f"localtunnel started: {url}")
                    return self._tunnel_info
        
        raise RuntimeError("Failed to start localtunnel")
    
    def stop(self) -> bool:
        """Stop localtunnel."""
        if not self._process:
            return True
        
        self._process.terminate()
        
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        
        self._process = None
        self._is_running = False
        self._tunnel_info = None
        
        logger.info("localtunnel stopped")
        return True
    
    def get_public_url(self) -> Optional[str]:
        """Get public URL."""
        if self._tunnel_info:
            return self._tunnel_info.public_url
        return None


class TunnelManager:
    """
    Central tunnel management.
    Supports multiple providers with automatic failover.
    """
    
    def __init__(self):
        self._tunnels: Dict[str, TunnelBase] = {}
        self._active_tunnels: Dict[str, TunnelInfo] = {}
    
    def create_tunnel(
        self,
        provider: TunnelProvider,
        local_port: int,
        **kwargs
    ) -> TunnelBase:
        """Create a tunnel with specified provider."""
        config = TunnelConfig(
            provider=provider,
            local_port=local_port,
            **kwargs
        )
        
        if provider == TunnelProvider.NGROK:
            tunnel = NgrokTunnel(config)
        elif provider == TunnelProvider.CLOUDFLARE:
            tunnel = CloudflareTunnel(config)
        elif provider == TunnelProvider.LOCALTUNNEL:
            tunnel = LocaltunnelTunnel(config)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        tunnel_id = f"{provider.value}-{local_port}"
        self._tunnels[tunnel_id] = tunnel
        
        return tunnel
    
    def start_tunnel(
        self,
        provider: TunnelProvider,
        local_port: int,
        **kwargs
    ) -> TunnelInfo:
        """Start a tunnel and return info."""
        tunnel = self.create_tunnel(provider, local_port, **kwargs)
        info = tunnel.start()
        
        self._active_tunnels[info.id] = info
        
        return info
    
    def stop_tunnel(self, tunnel_id: str) -> bool:
        """Stop a tunnel by ID."""
        if tunnel_id in self._tunnels:
            return self._tunnels[tunnel_id].stop()
        
        return False
    
    def get_tunnel(self, tunnel_id: str) -> Optional[TunnelBase]:
        """Get tunnel by ID."""
        return self._tunnels.get(tunnel_id)
    
    def list_tunnels(self) -> List[TunnelInfo]:
        """List all active tunnels."""
        return list(self._active_tunnels.values())
    
    def stop_all(self):
        """Stop all tunnels."""
        for tunnel in self._tunnels.values():
            tunnel.stop()
        
        self._active_tunnels.clear()
    
    def auto_select(self, local_port: int) -> Optional[TunnelProvider]:
        """Automatically select available provider."""
        # Check providers in order of preference
        providers = [
            (TunnelProvider.NGROK, NgrokTunnel(TunnelConfig())),
            (TunnelProvider.CLOUDFLARE, CloudflareTunnel(TunnelConfig())),
            (TunnelProvider.LOCALTUNNEL, LocaltunnelTunnel(TunnelConfig())),
        ]
        
        for provider, tunnel in providers:
            if tunnel.is_installed():
                return provider
        
        return None


class URLGenerator:
    """Generate and manage tunnel URLs."""
    
    @staticmethod
    def generate_subdomain(prefix: str = "sentience") -> str:
        """Generate unique subdomain."""
        import random
        import string
        
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{prefix}-{suffix}"
    
    @staticmethod
    def parse_url(url: str) -> Dict[str, str]:
        """Parse tunnel URL into components."""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        
        return {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "port": parsed.port,
            "path": parsed.path,
            "full": url
        }
    
    @staticmethod
    def is_https(url: str) -> bool:
        """Check if URL uses HTTPS."""
        return url.startswith("https://")
    
    @staticmethod
    def to_websocket_url(http_url: str) -> str:
        """Convert HTTP URL to WebSocket URL."""
        return http_url.replace("http://", "ws://").replace("https://", "wss://")


def quick_tunnel(local_port: int = 8000) -> TunnelInfo:
    """
    Quick tunnel creation with auto provider selection.
    Convenience function for rapid development.
    """
    manager = TunnelManager()
    
    # Auto-select provider
    provider = manager.auto_select(local_port)
    
    if not provider:
        raise RuntimeError(
            "No tunnel provider found. Install one of:\n"
            "  - ngrok: https://ngrok.com\n"
            "  - cloudflared: https://developers.cloudflare.com/cloudflare-one/\n"
            "  - localtunnel: npm install -g localtunnel"
        )
    
    return manager.start_tunnel(provider, local_port)


# CLI interface
def main():
    """CLI for tunnel management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sentience Tunnel Manager")
    subparsers = parser.add_subparsers(dest="command")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start a tunnel")
    start_parser.add_argument("port", type=int, nargs="?", default=8000, help="Local port")
    start_parser.add_argument("--provider", choices=["ngrok", "cloudflare", "localtunnel"],
                              help="Tunnel provider")
    start_parser.add_argument("--subdomain", help="Subdomain")
    start_parser.add_argument("--region", help="Region (ngrok)")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop tunnel")
    stop_parser.add_argument("tunnel_id", nargs="?", help="Tunnel ID")
    
    # List command
    subparsers.add_parser("list", help="List active tunnels")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check tunnel status")
    status_parser.add_argument("tunnel_id", nargs="?", help="Tunnel ID")
    
    args = parser.parse_args()
    
    manager = TunnelManager()
    
    if args.command == "start":
        provider_map = {
            "ngrok": TunnelProvider.NGROK,
            "cloudflare": TunnelProvider.CLOUDFLARE,
            "localtunnel": TunnelProvider.LOCALTUNNEL
        }
        
        if args.provider:
            provider = provider_map[args.provider]
        else:
            provider = manager.auto_select(args.port)
            if not provider:
                print("No tunnel provider found!")
                print("Install one of:")
                print("  - ngrok: https://ngrok.com")
                print("  - cloudflared: https://developers.cloudflare.com/cloudflare-one/")
                print("  - localtunnel: npm install -g localtunnel")
                sys.exit(1)
        
        try:
            info = manager.start_tunnel(
                provider=provider,
                local_port=args.port,
                subdomain=args.subdomain,
                region=args.region
            )
            
            print(f"Tunnel started!")
            print(f"  ID: {info.id}")
            print(f"  URL: {info.public_url}")
            print(f"  Local: {info.local_address}")
            
        except Exception as e:
            print(f"Failed to start tunnel: {e}")
            sys.exit(1)
    
    elif args.command == "stop":
        if args.tunnel_id:
            manager.stop_tunnel(args.tunnel_id)
        else:
            manager.stop_all()
        print("Tunnel stopped")
    
    elif args.command == "list":
        tunnels = manager.list_tunnels()
        if not tunnels:
            print("No active tunnels")
        else:
            for info in tunnels:
                print(f"{info.id}: {info.public_url} -> {info.local_address}")
    
    elif args.command == "status":
        if args.tunnel_id:
            tunnel = manager.get_tunnel(args.tunnel_id)
            if tunnel:
                info = tunnel.get_info()
                if info:
                    print(json.dumps(info.to_dict(), indent=2))
                else:
                    print("Tunnel not running")
            else:
                print("Tunnel not found")
        else:
            tunnels = manager.list_tunnels()
            print(json.dumps([t.to_dict() for t in tunnels], indent=2))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
