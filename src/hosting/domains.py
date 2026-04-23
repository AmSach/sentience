"""
Sentience v3.0 - Custom Domain Management
Local DNS resolution, hosts file management, and SSL cert generation.
"""

import os
import re
import sys
import json
import logging
import subprocess
import platform
import socket
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
from ipaddress import IPv4Address, IPv6Address, ip_address


logger = logging.getLogger("sentience.domains")


@dataclass
class DomainConfig:
    """Domain configuration."""
    name: str
    ip: str = "127.0.0.1"
    port: int = 8000
    ssl_enabled: bool = False
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "ssl_enabled": self.ssl_enabled,
            "ssl_cert": self.ssl_cert,
            "ssl_key": self.ssl_key,
            "aliases": self.aliases,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "DomainConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            ip=data.get("ip", "127.0.0.1"),
            port=data.get("port", 8000),
            ssl_enabled=data.get("ssl_enabled", False),
            ssl_cert=data.get("ssl_cert"),
            ssl_key=data.get("ssl_key"),
            aliases=data.get("aliases", []),
            enabled=data.get("enabled", True),
            created_at=datetime.fromisoformat(data["created_at"]) 
                       if "created_at" in data else datetime.utcnow()
        )


class DomainValidator:
    """Domain validation utilities."""
    
    # Domain regex patterns
    DOMAIN_PATTERN = re.compile(
        r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z]{2,}$'
    )
    LOCAL_DOMAIN_PATTERN = re.compile(
        r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*local$'
    )
    DEV_DOMAIN_PATTERN = re.compile(
        r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*dev$'
    )
    
    @classmethod
    def validate_domain(cls, domain: str) -> bool:
        """Validate domain name format."""
        if len(domain) > 253:
            return False
        return bool(cls.DOMAIN_PATTERN.match(domain))
    
    @classmethod
    def validate_local_domain(cls, domain: str) -> bool:
        """Validate .local domain."""
        return bool(cls.LOCAL_DOMAIN_PATTERN.match(domain))
    
    @classmethod
    def validate_ip(cls, ip: str) -> bool:
        """Validate IP address."""
        try:
            ip_address(ip)
            return True
        except ValueError:
            return False
    
    @classmethod
    def is_localhost(cls, domain: str) -> bool:
        """Check if domain resolves to localhost."""
        localhost_domains = {
            "localhost", "localhost.localdomain",
            "127.0.0.1", "::1"
        }
        return domain.lower() in localhost_domains
    
    @classmethod
    def normalize_domain(cls, domain: str) -> str:
        """Normalize domain name."""
        return domain.lower().strip().rstrip(".")


class HostsFileManager:
    """Manage /etc/hosts or Windows hosts file."""
    
    def __init__(self, hosts_path: str = None):
        self.system = platform.system()
        
        if hosts_path:
            self.hosts_path = Path(hosts_path)
        elif self.system == "Windows":
            self.hosts_path = Path(
                os.environ.get("SystemRoot", r"C:\Windows")
            ) / "System32" / "drivers" / "etc" / "hosts"
        else:
            self.hosts_path = Path("/etc/hosts")
        
        self._entries: Dict[str, str] = {}
        self._load_entries()
    
    def _load_entries(self):
        """Load existing hosts entries."""
        if not self.hosts_path.exists():
            return
        
        with open(self.hosts_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    for domain in parts[1:]:
                        self._entries[domain.lower()] = ip
    
    def get_ip(self, domain: str) -> Optional[str]:
        """Get IP for domain."""
        return self._entries.get(domain.lower())
    
    def has_entry(self, domain: str) -> bool:
        """Check if domain has entry."""
        return domain.lower() in self._entries
    
    def add_entry(self, domain: str, ip: str = "127.0.0.1") -> bool:
        """Add hosts entry."""
        domain = domain.lower()
        
        if not DomainValidator.validate_ip(ip):
            raise ValueError(f"Invalid IP address: {ip}")
        
        if self._entries.get(domain) == ip:
            logger.debug(f"Entry already exists: {ip} {domain}")
            return True
        
        # Check if we have write permissions
        if not os.access(self.hosts_path, os.W_OK):
            logger.warning(f"No write access to {self.hosts_path}")
            return self._add_with_sudo(domain, ip)
        
        # Add entry
        with open(self.hosts_path, "a") as f:
            f.write(f"\n# Sentience v3.0 Domain\n{ip}\t{domain}\n")
        
        self._entries[domain] = ip
        logger.info(f"Added hosts entry: {ip} {domain}")
        return True
    
    def _add_with_sudo(self, domain: str, ip: str) -> bool:
        """Add entry with sudo on Unix systems."""
        if self.system == "Windows":
            logger.error("Cannot write to hosts file - need admin privileges")
            return False
        
        try:
            entry = f"{ip}\t{domain}\n"
            result = subprocess.run(
                ["sudo", "tee", "-a", str(self.hosts_path)],
                input=f"# Sentience v3.0\n{entry}".encode(),
                capture_output=True
            )
            
            if result.returncode == 0:
                self._entries[domain] = ip
                logger.info(f"Added hosts entry with sudo: {ip} {domain}")
                return True
        except Exception as e:
            logger.error(f"Failed to add entry with sudo: {e}")
        
        return False
    
    def remove_entry(self, domain: str) -> bool:
        """Remove hosts entry."""
        domain = domain.lower()
        
        if domain not in self._entries:
            return True
        
        if not os.access(self.hosts_path, os.W_OK):
            return self._remove_with_sudo(domain)
        
        # Read and rewrite file without the entry
        lines = []
        with open(self.hosts_path, "r") as f:
            for line in f:
                if domain in line.lower() and not line.strip().startswith("#"):
                    continue
                lines.append(line)
        
        with open(self.hosts_path, "w") as f:
            f.writelines(lines)
        
        del self._entries[domain]
        logger.info(f"Removed hosts entry: {domain}")
        return True
    
    def _remove_with_sudo(self, domain: str) -> bool:
        """Remove entry with sudo."""
        if self.system == "Windows":
            return False
        
        try:
            # Create temp file without the entry
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                with open(self.hosts_path, "r") as f:
                    for line in f:
                        if domain in line.lower() and not line.strip().startswith("#"):
                            continue
                        tmp.write(line)
                
                tmp_path = tmp.name
            
            # Copy with sudo
            subprocess.run(["sudo", "cp", tmp_path, str(self.hosts_path)], check=True)
            os.unlink(tmp_path)
            
            del self._entries[domain]
            return True
        except Exception as e:
            logger.error(f"Failed to remove entry with sudo: {e}")
            return False
    
    def list_sentience_entries(self) -> Dict[str, str]:
        """List all Sentience-managed entries."""
        if not self.hosts_path.exists():
            return {}
        
        entries = {}
        with open(self.hosts_path, "r") as f:
            content = f.read()
        
        # Find Sentience section
        in_section = False
        for line in content.split("\n"):
            if "Sentience" in line:
                in_section = True
                continue
            
            if in_section and line.strip() and not line.startswith("#"):
                parts = line.split()
                if len(parts) >= 2:
                    entries[parts[1]] = parts[0]
            elif line.startswith("#") and in_section and "Sentience" not in line:
                in_section = False
        
        return entries


class LocalDNSResolver:
    """Local DNS resolution for development domains."""
    
    def __init__(self, hosts_manager: HostsFileManager = None):
        self.hosts = hosts_manager or HostsFileManager()
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._cache_ttl = 300  # 5 minutes
    
    def resolve(self, domain: str) -> Optional[str]:
        """Resolve domain to IP address."""
        domain = DomainValidator.normalize_domain(domain)
        
        # Check cache
        if domain in self._cache:
            ip, timestamp = self._cache[domain]
            if datetime.now().timestamp() - timestamp < self._cache_ttl:
                return ip
        
        # Check hosts file first
        ip = self.hosts.get_ip(domain)
        if ip:
            self._cache[domain] = (ip, datetime.now().timestamp())
            return ip
        
        # Try system DNS
        try:
            result = socket.gethostbyname(domain)
            self._cache[domain] = (result, datetime.now().timestamp())
            return result
        except socket.gaierror:
            return None
    
    def add_local_domain(self, domain: str, ip: str = "127.0.0.1") -> bool:
        """Add local domain mapping."""
        return self.hosts.add_entry(domain, ip)
    
    def remove_local_domain(self, domain: str) -> bool:
        """Remove local domain mapping."""
        return self.hosts.remove_entry(domain)
    
    def clear_cache(self):
        """Clear DNS cache."""
        self._cache.clear()
    
    def ping(self, domain: str) -> Dict[str, any]:
        """Ping a domain and return results."""
        ip = self.resolve(domain)
        
        result = {
            "domain": domain,
            "ip": ip,
            "reachable": False,
            "latency_ms": None
        }
        
        if not ip:
            return result
        
        # Try to connect
        try:
            import time
            start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ip, 80))
            latency = (time.time() - start) * 1000
            sock.close()
            
            result["reachable"] = True
            result["latency_ms"] = round(latency, 2)
        except (socket.timeout, ConnectionRefusedError):
            pass
        
        return result


class MkcertManager:
    """Manage SSL certificates using mkcert."""
    
    def __init__(self, cert_dir: str = None):
        self.cert_dir = Path(cert_dir or os.path.expanduser("~/.sentience/certs"))
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self._mkcert_path: Optional[str] = None
    
    def find_mkcert(self) -> Optional[str]:
        """Find mkcert binary."""
        if self._mkcert_path:
            return self._mkcert_path
        
        # Check common locations
        paths = [
            "mkcert",
            "/usr/local/bin/mkcert",
            "/usr/bin/mkcert",
            "/opt/homebrew/bin/mkcert",
        ]
        
        for path in paths:
            if shutil.which(path):
                self._mkcert_path = path
                return path
        
        return None
    
    def is_installed(self) -> bool:
        """Check if mkcert is installed."""
        return self.find_mkcert() is not None
    
    def install(self) -> bool:
        """Install mkcert CA."""
        mkcert = self.find_mkcert()
        if not mkcert:
            logger.error("mkcert not found. Install with: brew install mkcert "
                        "or choco install mkcert")
            return False
        
        try:
            result = subprocess.run(
                [mkcert, "-install"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("mkcert CA installed successfully")
                return True
            else:
                logger.error(f"mkcert install failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Failed to run mkcert: {e}")
            return False
    
    def generate_cert(
        self,
        domain: str,
        aliases: List[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Generate SSL certificate for domain."""
        mkcert = self.find_mkcert()
        if not mkcert:
            logger.error("mkcert not found")
            return None, None
        
        # Prepare domains
        all_domains = [domain]
        if aliases:
            all_domains.extend(aliases)
        
        # Generate cert paths
        cert_file = self.cert_dir / f"{domain}.pem"
        key_file = self.cert_dir / f"{domain}-key.pem"
        
        try:
            # Run mkcert
            cmd = [
                mkcert,
                "-cert-file", str(cert_file),
                "-key-file", str(key_file),
            ] + all_domains
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Generated certificate for {domain}")
                return str(cert_file), str(key_file)
            else:
                logger.error(f"Certificate generation failed: {result.stderr}")
                return None, None
        except Exception as e:
            logger.error(f"Failed to generate certificate: {e}")
            return None, None
    
    def generate_wildcard_cert(
        self,
        base_domain: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Generate wildcard certificate."""
        return self.generate_cert(
            f"*.{base_domain}",
            aliases=[base_domain]
        )
    
    def cert_exists(self, domain: str) -> bool:
        """Check if certificate exists."""
        cert_file = self.cert_dir / f"{domain}.pem"
        key_file = self.cert_dir / f"{domain}-key.pem"
        return cert_file.exists() and key_file.exists()
    
    def get_cert_paths(self, domain: str) -> Tuple[Optional[str], Optional[str]]:
        """Get certificate paths for domain."""
        cert_file = self.cert_dir / f"{domain}.pem"
        key_file = self.cert_dir / f"{domain}-key.pem"
        
        if cert_file.exists() and key_file.exists():
            return str(cert_file), str(key_file)
        return None, None


class DomainManager:
    """
    Central domain management for Sentience v3.0.
    Handles registration, DNS, and SSL certificates.
    """
    
    CONFIG_FILE = "domains.json"
    
    def __init__(
        self,
        config_dir: str = None,
        cert_dir: str = None
    ):
        self.config_dir = Path(config_dir or os.path.expanduser("~/.sentience"))
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.hosts = HostsFileManager()
        self.dns = LocalDNSResolver(self.hosts)
        self.mkcert = MkcertManager(cert_dir)
        
        self._domains: Dict[str, DomainConfig] = {}
        self._load_config()
    
    def _load_config(self):
        """Load domain configurations."""
        config_path = self.config_dir / self.CONFIG_FILE
        
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            
            for name, config in data.get("domains", {}).items():
                self._domains[name] = DomainConfig.from_dict(config)
    
    def _save_config(self):
        """Save domain configurations."""
        config_path = self.config_dir / self.CONFIG_FILE
        
        data = {
            "version": "3.0",
            "domains": {
                name: config.to_dict()
                for name, config in self._domains.items()
            }
        }
        
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def register_domain(
        self,
        domain: str,
        ip: str = "127.0.0.1",
        port: int = 8000,
        enable_ssl: bool = True,
        aliases: List[str] = None
    ) -> DomainConfig:
        """Register a new local domain."""
        domain = DomainValidator.normalize_domain(domain)
        
        # Validate domain
        if not DomainValidator.validate_domain(domain):
            if not (DomainValidator.validate_local_domain(domain) or
                    DomainValidator.validate_dev_domain(domain)):
                raise ValueError(f"Invalid domain name: {domain}")
        
        # Validate IP
        if not DomainValidator.validate_ip(ip):
            raise ValueError(f"Invalid IP address: {ip}")
        
        # Create config
        config = DomainConfig(
            name=domain,
            ip=ip,
            port=port,
            ssl_enabled=enable_ssl,
            aliases=aliases or []
        )
        
        # Add to hosts file
        if not self.hosts.add_entry(domain, ip):
            raise RuntimeError(f"Failed to add hosts entry for {domain}")
        
        # Add aliases to hosts
        for alias in (aliases or []):
            self.hosts.add_entry(alias, ip)
        
        # Generate SSL certificate
        if enable_ssl and self.mkcert.is_installed():
            cert, key = self.mkcert.generate_cert(domain, aliases)
            if cert and key:
                config.ssl_cert = cert
                config.ssl_key = key
        
        # Save config
        self._domains[domain] = config
        self._save_config()
        
        logger.info(f"Registered domain: {domain}")
        return config
    
    def unregister_domain(self, domain: str) -> bool:
        """Unregister a domain."""
        domain = DomainValidator.normalize_domain(domain)
        
        if domain not in self._domains:
            return True
        
        config = self._domains[domain]
        
        # Remove from hosts
        self.hosts.remove_entry(domain)
        
        # Remove aliases
        for alias in config.aliases:
            self.hosts.remove_entry(alias)
        
        # Remove from config
        del self._domains[domain]
        self._save_config()
        
        logger.info(f"Unregistered domain: {domain}")
        return True
    
    def get_domain(self, domain: str) -> Optional[DomainConfig]:
        """Get domain configuration."""
        return self._domains.get(DomainValidator.normalize_domain(domain))
    
    def list_domains(self) -> List[DomainConfig]:
        """List all registered domains."""
        return list(self._domains.values())
    
    def enable_ssl(self, domain: str) -> bool:
        """Enable SSL for domain."""
        config = self.get_domain(domain)
        if not config:
            return False
        
        if config.ssl_cert and config.ssl_key:
            config.ssl_enabled = True
            self._save_config()
            return True
        
        # Generate new cert
        if self.mkcert.is_installed():
            cert, key = self.mkcert.generate_cert(domain, config.aliases)
            if cert and key:
                config.ssl_cert = cert
                config.ssl_key = key
                config.ssl_enabled = True
                self._save_config()
                return True
        
        return False
    
    def disable_ssl(self, domain: str) -> bool:
        """Disable SSL for domain."""
        config = self.get_domain(domain)
        if not config:
            return False
        
        config.ssl_enabled = False
        self._save_config()
        return True
    
    def get_url(self, domain: str, path: str = "/") -> str:
        """Get full URL for domain."""
        config = self.get_domain(domain)
        if not config:
            return None
        
        scheme = "https" if config.ssl_enabled else "http"
        port_suffix = ""
        
        # Only add port if non-standard
        if config.ssl_enabled and config.port != 443:
            port_suffix = f":{config.port}"
        elif not config.ssl_enabled and config.port != 80:
            port_suffix = f":{config.port}"
        
        return f"{scheme}://{config.name}{port_suffix}{path}"
    
    def test_domain(self, domain: str) -> Dict[str, any]:
        """Test domain resolution and connectivity."""
        config = self.get_domain(domain)
        if not config:
            return {"error": "Domain not registered"}
        
        results = {
            "domain": domain,
            "registered": True,
            "dns": self.dns.ping(domain),
            "ssl": {
                "enabled": config.ssl_enabled,
                "cert_exists": bool(config.ssl_cert),
                "valid": self._check_cert_valid(domain) if config.ssl_cert else False
            }
        }
        
        # Test HTTP/HTTPS connection
        results["http"] = self._test_connection(domain, config.port, ssl=False)
        if config.ssl_enabled:
            results["https"] = self._test_connection(domain, config.port, ssl=True)
        
        return results
    
    def _check_cert_valid(self, domain: str) -> bool:
        """Check if SSL certificate is valid."""
        import ssl
        from datetime import datetime
        
        cert_path = self._domains.get(domain, {}).ssl_cert
        if not cert_path or not os.path.exists(cert_path):
            return False
        
        try:
            with open(cert_path, "rb") as f:
                cert_data = f.read()
            
            # Parse certificate
            import OpenSSL
            cert = OpenSSL.crypto.load_certificate(
                OpenSSL.crypto.FILETYPE_PEM, cert_data
            )
            
            # Check expiration
            expires = datetime.strptime(
                cert.get_notAfter().decode(), "%Y%m%d%H%M%SZ"
            )
            
            return expires > datetime.utcnow()
        except Exception:
            # If OpenSSL not available, just check file exists
            return os.path.exists(cert_path)
    
    def _test_connection(
        self,
        domain: str,
        port: int,
        ssl: bool
    ) -> Dict[str, any]:
        """Test HTTP connection to domain."""
        import time
        import urllib.request
        import urllib.error
        
        scheme = "https" if ssl else "http"
        url = f"{scheme}://{domain}:{port}/"
        
        result = {
            "url": url,
            "success": False,
            "status": None,
            "latency_ms": None,
            "error": None
        }
        
        try:
            start = time.time()
            
            # Create request with SSL context
            if ssl:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urllib.request.urlopen(url, timeout=5, context=ctx)
            else:
                response = urllib.request.urlopen(url, timeout=5)
            
            latency = (time.time() - start) * 1000
            
            result["success"] = True
            result["status"] = response.status
            result["latency_ms"] = round(latency, 2)
        except urllib.error.HTTPError as e:
            result["status"] = e.code
            result["error"] = str(e)
        except urllib.error.URLError as e:
            result["error"] = str(e.reason)
        except Exception as e:
            result["error"] = str(e)
        
        return result


# CLI interface
def main():
    """CLI for domain management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sentience Domain Manager")
    subparsers = parser.add_subparsers(dest="command")
    
    # Register command
    register_parser = subparsers.add_parser("register", help="Register a domain")
    register_parser.add_argument("domain", help="Domain name")
    register_parser.add_argument("--ip", default="127.0.0.1", help="IP address")
    register_parser.add_argument("--port", type=int, default=8000, help="Port")
    register_parser.add_argument("--no-ssl", action="store_true", help="Disable SSL")
    register_parser.add_argument("--alias", action="append", help="Domain alias")
    
    # Unregister command
    unregister_parser = subparsers.add_parser("unregister", help="Unregister a domain")
    unregister_parser.add_argument("domain", help="Domain name")
    
    # List command
    subparsers.add_parser("list", help="List registered domains")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test a domain")
    test_parser.add_argument("domain", help="Domain name")
    
    # SSL command
    ssl_parser = subparsers.add_parser("ssl", help="Manage SSL for domain")
    ssl_parser.add_argument("domain", help="Domain name")
    ssl_parser.add_argument("--enable", action="store_true", help="Enable SSL")
    ssl_parser.add_argument("--disable", action="store_true", help="Disable SSL")
    
    args = parser.parse_args()
    
    manager = DomainManager()
    
    if args.command == "register":
        config = manager.register_domain(
            args.domain,
            ip=args.ip,
            port=args.port,
            enable_ssl=not args.no_ssl,
            aliases=args.alias
        )
        print(f"Registered: {config.name}")
        print(f"URL: {manager.get_url(args.domain)}")
        
    elif args.command == "unregister":
        manager.unregister_domain(args.domain)
        print(f"Unregistered: {args.domain}")
        
    elif args.command == "list":
        for config in manager.list_domains():
            url = manager.get_url(config.name)
            ssl_status = "🔒" if config.ssl_enabled else "🔓"
            print(f"{ssl_status} {config.name} -> {config.ip}:{config.port} ({url})")
    
    elif args.command == "test":
        results = manager.test_domain(args.domain)
        print(json.dumps(results, indent=2))
    
    elif args.command == "ssl":
        if args.enable:
            manager.enable_ssl(args.domain)
            print(f"SSL enabled for {args.domain}")
        elif args.disable:
            manager.disable_ssl(args.domain)
            print(f"SSL disabled for {args.domain}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
