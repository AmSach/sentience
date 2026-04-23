"""
Sentience v3.0 - SSL Certificate Manager
Self-signed certs, Let's Encrypt support, renewal, and key management.
"""

import os
import re
import sys
import json
import logging
import subprocess
import shutil
import tempfile
import socket
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
import ipaddress


logger = logging.getLogger("sentience.ssl")


class CertificateType(str, Enum):
    """Certificate types."""
    SELF_SIGNED = "self_signed"
    LETS_ENCRYPT = "lets_encrypt"
    CUSTOM = "custom"
    WILDCARD = "wildcard"


class KeyType(str, Enum):
    """Key types."""
    RSA = "rsa"
    ECDSA = "ecdsa"


class CertificateStatus(str, Enum):
    """Certificate status."""
    VALID = "valid"
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"
    INVALID = "invalid"
    PENDING = "pending"


@dataclass
class CertificateInfo:
    """Certificate information."""
    common_name: str
    issuer: str
    subject: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    san: List[str] = field(default_factory=list)
    key_type: KeyType = KeyType.RSA
    key_size: int = 2048
    cert_type: CertificateType = CertificateType.SELF_SIGNED
    status: CertificateStatus = CertificateStatus.VALID
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    chain_path: Optional[str] = None
    
    @property
    def days_until_expiry(self) -> int:
        """Calculate days until expiry."""
        delta = self.not_after - datetime.utcnow()
        return max(0, delta.days)
    
    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return datetime.utcnow() > self.not_after
    
    @property
    def is_expiring_soon(self, days: int = 30) -> bool:
        """Check if certificate expires soon."""
        return self.days_until_expiry <= days
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "common_name": self.common_name,
            "issuer": self.issuer,
            "subject": self.subject,
            "serial_number": self.serial_number,
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
            "san": self.san,
            "key_type": self.key_type.value,
            "key_size": self.key_size,
            "cert_type": self.cert_type.value,
            "status": self.status.value,
            "days_until_expiry": self.days_until_expiry,
            "cert_path": self.cert_path,
            "key_path": self.key_path,
            "chain_path": self.chain_path
        }


class KeyManager:
    """Manage private keys."""
    
    def __init__(self, key_dir: str = None):
        self.key_dir = Path(key_dir or os.path.expanduser("~/.sentience/keys"))
        self.key_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_rsa_key(
        self,
        key_size: int = 2048,
        password: str = None
    ) -> rsa.RSAPrivateKey:
        """Generate RSA private key."""
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
        
        return key
    
    def generate_ecdsa_key(
        self,
        curve: ec.EllipticCurve = None
    ) -> ec.EllipticCurvePrivateKey:
        """Generate ECDSA private key."""
        curve = curve or ec.SECP256R1()
        
        key = ec.generate_private_key(
            curve=curve,
            backend=default_backend()
        )
        
        return key
    
    def save_key(
        self,
        key: Any,
        name: str,
        password: str = None
    ) -> Path:
        """Save private key to file."""
        key_path = self.key_dir / f"{name}.key"
        
        encryption = None
        if password:
            encryption = serialization.BestAvailableEncryption(
                password.encode()
            )
        
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption or serialization.NoEncryption()
        )
        
        key_path.write_bytes(pem)
        key_path.chmod(0o600)
        
        logger.info(f"Saved key: {key_path}")
        return key_path
    
    def load_key(
        self,
        name: str,
        password: str = None
    ) -> Any:
        """Load private key from file."""
        key_path = self.key_dir / f"{name}.key"
        
        if not key_path.exists():
            raise FileNotFoundError(f"Key not found: {key_path}")
        
        pem = key_path.read_bytes()
        
        key = serialization.load_pem_private_key(
            pem,
            password=password.encode() if password else None,
            backend=default_backend()
        )
        
        return key
    
    def get_public_key_pem(self, key: Any) -> bytes:
        """Get public key in PEM format."""
        public_key = key.public_key()
        
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return pem


class SelfSignedCertificate:
    """Generate self-signed certificates."""
    
    def __init__(self, cert_dir: str = None):
        self.cert_dir = Path(cert_dir or os.path.expanduser("~/.sentience/certs"))
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self.key_manager = KeyManager(self.cert_dir / "keys")
    
    def generate_ca(
        self,
        name: str = "Sentience Root CA",
        key_size: int = 4096,
        validity_days: int = 3650
    ) -> Tuple[Path, Path]:
        """Generate self-signed CA certificate."""
        # Generate key
        key = self.key_manager.generate_rsa_key(key_size)
        
        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sentience"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        ])
        
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )
        
        # Save files
        ca_name = name.lower().replace(" ", "-")
        key_path = self.key_manager.save_key(key, f"{ca_name}-ca")
        
        cert_path = self.cert_dir / f"{ca_name}-ca.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        
        logger.info(f"Generated CA: {cert_path}")
        return cert_path, key_path
    
    def generate_cert(
        self,
        domain: str,
        ca_cert_path: Path = None,
        ca_key_path: Path = None,
        san: List[str] = None,
        ip_addresses: List[str] = None,
        key_type: KeyType = KeyType.RSA,
        key_size: int = 2048,
        validity_days: int = 365,
        is_server: bool = True
    ) -> Tuple[Path, Path]:
        """Generate certificate signed by CA."""
        # Load or create CA
        if ca_cert_path and ca_key_path:
            ca_cert_pem = Path(ca_cert_path).read_bytes()
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
            ca_key = self.key_manager.load_key(
                ca_key_path.stem.replace("-ca", "-ca")
            )
        else:
            # Self-signed (no CA)
            ca_cert_path, ca_key_path = self.generate_ca()
            ca_cert_pem = Path(ca_cert_path).read_bytes()
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
            ca_key = self.key_manager.load_key(
                ca_key_path.stem.replace("-ca", "-ca")
            )
        
        # Generate key
        if key_type == KeyType.RSA:
            key = self.key_manager.generate_rsa_key(key_size)
        else:
            key = self.key_manager.generate_ecdsa_key()
        
        # Build subject
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, domain),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sentience"),
        ])
        
        # Build SAN
        san_list = [x509.DNSName(domain)]
        
        # Add additional SANs
        for name in (san or []):
            if name not in [domain, "localhost"]:
                san_list.append(x509.DNSName(name))
        
        # Add localhost
        san_list.append(x509.DNSName("localhost"))
        
        # Add IP addresses
        if ip_addresses:
            for ip in ip_addresses:
                try:
                    san_list.append(x509.IPAddress(ipaddress.ip_address(ip)))
                except ValueError:
                    pass
        
        # Always add common IPs
        san_list.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
        san_list.append(x509.IPAddress(ipaddress.ip_address("::1")))
        
        # Build certificate
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
                    ca_cert.extensions.get_extension_for_class(
                        x509.SubjectKeyIdentifier
                    ).value
                ),
                critical=False,
            )
        )
        
        # Add server auth extension
        if is_server:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
            
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
        
        cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
        
        # Save files
        key_path = self.key_manager.save_key(key, domain)
        
        cert_path = self.cert_dir / f"{domain}.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        
        # Create full chain (cert + CA)
        chain_path = self.cert_dir / f"{domain}-chain.pem"
        chain_path.write_bytes(
            cert.public_bytes(serialization.Encoding.PEM) +
            ca_cert_pem
        )
        
        logger.info(f"Generated certificate: {cert_path}")
        return cert_path, key_path
    
    def generate_wildcard(
        self,
        base_domain: str,
        **kwargs
    ) -> Tuple[Path, Path]:
        """Generate wildcard certificate."""
        return self.generate_cert(
            f"*.{base_domain}",
            san=[base_domain],
            **kwargs
        )


class LetsEncryptManager:
    """Manage Let's Encrypt certificates using certbot."""
    
    def __init__(self, cert_dir: str = "/etc/letsencrypt"):
        self.cert_dir = Path(cert_dir)
        self._certbot_path: Optional[str] = None
    
    def _find_certbot(self) -> Optional[str]:
        """Find certbot binary."""
        if self._certbot_path:
            return self._certbot_path
        
        paths = [
            "certbot",
            "/usr/bin/certbot",
            "/usr/local/bin/certbot",
            "/opt/homebrew/bin/certbot",
        ]
        
        for path in paths:
            if shutil.which(path):
                self._certbot_path = path
                return path
        
        return None
    
    def is_installed(self) -> bool:
        """Check if certbot is installed."""
        return self._find_certbot() is not None
    
    def install(self) -> bool:
        """Install certbot."""
        # Try different installation methods
        install_commands = [
            ["apt-get", "install", "-y", "certbot"],
            ["yum", "install", "-y", "certbot"],
            ["brew", "install", "certbot"],
            ["pip", "install", "certbot"],
        ]
        
        for cmd in install_commands:
            try:
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
        
        return False
    
    def request_cert(
        self,
        domain: str,
        email: str,
        webroot: str = None,
        standalone: bool = False,
        dns_provider: str = None,
        test: bool = False
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Request Let's Encrypt certificate."""
        certbot = self._find_certbot()
        if not certbot:
            raise RuntimeError("certbot not found")
        
        cmd = [certbot, "certonly", "--non-interactive", "--agree-tos"]
        
        cmd.extend(["--email", email, "-d", domain])
        
        if test:
            cmd.append("--test-cert")
        
        if webroot:
            cmd.extend(["--webroot", "-w", webroot])
        elif standalone:
            cmd.append("--standalone")
        elif dns_provider:
            cmd.extend([f"--{dns_provider}", "--dns-{dns_provider}-credentials"])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"certbot failed: {result.stderr}")
            return None, None
        
        # Find certificate
        cert_path = self.cert_dir / "live" / domain / "cert.pem"
        key_path = self.cert_dir / "live" / domain / "privkey.pem"
        
        if cert_path.exists() and key_path.exists():
            logger.info(f"Certificate issued: {cert_path}")
            return cert_path, key_path
        
        return None, None
    
    def renew(self, dry_run: bool = False) -> bool:
        """Renew certificates."""
        certbot = self._find_certbot()
        if not certbot:
            return False
        
        cmd = [certbot, "renew", "--non-interactive"]
        
        if dry_run:
            cmd.append("--dry-run")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return result.returncode == 0
    
    def revoke(self, domain: str) -> bool:
        """Revoke certificate."""
        certbot = self._find_certbot()
        if not certbot:
            return False
        
        cert_path = self.cert_dir / "live" / domain / "cert.pem"
        
        if not cert_path.exists():
            return False
        
        result = subprocess.run(
            [certbot, "revoke", "--cert-path", str(cert_path), "--non-interactive"],
            capture_output=True
        )
        
        return result.returncode == 0


class CertificateManager:
    """
    Central SSL certificate management.
    Handles all certificate types and operations.
    """
    
    CONFIG_FILE = "certificates.json"
    
    def __init__(self, cert_dir: str = None):
        self.cert_dir = Path(cert_dir or os.path.expanduser("~/.sentience/certs"))
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        self.self_signed = SelfSignedCertificate(str(self.cert_dir))
        self.lets_encrypt = LetsEncryptManager()
        self._certificates: Dict[str, CertificateInfo] = {}
        
        self._load_config()
    
    def _load_config(self):
        """Load certificate configurations."""
        config_path = self.cert_dir / self.CONFIG_FILE
        
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            
            for name, cert_data in data.get("certificates", {}).items():
                info = CertificateInfo(
                    common_name=cert_data["common_name"],
                    issuer=cert_data["issuer"],
                    subject=cert_data["subject"],
                    serial_number=cert_data["serial_number"],
                    not_before=datetime.fromisoformat(cert_data["not_before"]),
                    not_after=datetime.fromisoformat(cert_data["not_after"]),
                    san=cert_data.get("san", []),
                    key_type=KeyType(cert_data.get("key_type", "rsa")),
                    key_size=cert_data.get("key_size", 2048),
                    cert_type=CertificateType(cert_data.get("cert_type", "self_signed")),
                    cert_path=cert_data.get("cert_path"),
                    key_path=cert_data.get("key_path"),
                    chain_path=cert_data.get("chain_path")
                )
                self._certificates[name] = info
    
    def _save_config(self):
        """Save certificate configurations."""
        config_path = self.cert_dir / self.CONFIG_FILE
        
        data = {
            "version": "3.0",
            "certificates": {
                name: info.to_dict()
                for name, info in self._certificates.items()
            }
        }
        
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_certificate_info(self, cert_path: str) -> CertificateInfo:
        """Parse certificate and get info."""
        cert_pem = Path(cert_path).read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Extract info
        common_name = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        issuer = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        
        # Get SAN
        san = []
        try:
            san_ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    san.append(name.value)
        except x509.ExtensionNotFound:
            pass
        
        # Determine key type
        key_type = KeyType.RSA
        key_size = 2048
        
        public_key = cert.public_key()
        if isinstance(public_key, rsa.RSAPublicKey):
            key_type = KeyType.RSA
            key_size = public_key.key_size
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            key_type = KeyType.ECDSA
            key_size = public_key.curve.key_size
        
        # Determine status
        status = CertificateStatus.VALID
        now = datetime.utcnow()
        
        if now > cert.not_valid_after:
            status = CertificateStatus.EXPIRED
        elif (cert.not_valid_after - now).days <= 30:
            status = CertificateStatus.EXPIRING_SOON
        
        # Determine certificate type
        cert_type = CertificateType.SELF_SIGNED
        
        if "Let's Encrypt" in issuer or "letsencrypt" in issuer.lower():
            cert_type = CertificateType.LETS_ENCRYPT
        elif issuer == common_name:
            cert_type = CertificateType.SELF_SIGNED
        elif "*" in common_name:
            cert_type = CertificateType.WILDCARD
        
        return CertificateInfo(
            common_name=common_name,
            issuer=issuer,
            subject=str(cert.subject),
            serial_number=hex(cert.serial_number)[2:].upper(),
            not_before=cert.not_valid_before,
            not_after=cert.not_valid_after,
            san=san,
            key_type=key_type,
            key_size=key_size,
            cert_type=cert_type,
            status=status,
            cert_path=str(cert_path)
        )
    
    def generate_self_signed(
        self,
        domain: str,
        san: List[str] = None,
        validity_days: int = 365,
        key_size: int = 2048
    ) -> Tuple[str, str]:
        """Generate self-signed certificate."""
        cert_path, key_path = self.self_signed.generate_cert(
            domain=domain,
            san=san,
            validity_days=validity_days,
            key_size=key_size
        )
        
        # Get info and store
        info = self.get_certificate_info(str(cert_path))
        info.key_path = str(key_path)
        
        self._certificates[domain] = info
        self._save_config()
        
        return str(cert_path), str(key_path)
    
    def request_lets_encrypt(
        self,
        domain: str,
        email: str,
        webroot: str = None,
        test: bool = False
    ) -> Tuple[Optional[str], Optional[str]]:
        """Request Let's Encrypt certificate."""
        cert_path, key_path = self.lets_encrypt.request_cert(
            domain=domain,
            email=email,
            webroot=webroot,
            test=test
        )
        
        if cert_path and key_path:
            info = self.get_certificate_info(str(cert_path))
            info.key_path = str(key_path)
            
            self._certificates[domain] = info
            self._save_config()
            
            return str(cert_path), str(key_path)
        
        return None, None
    
    def get_cert_paths(self, domain: str) -> Tuple[Optional[str], Optional[str]]:
        """Get certificate paths for domain."""
        if domain in self._certificates:
            info = self._certificates[domain]
            return info.cert_path, info.key_path
        
        # Check if cert exists
        cert_path = self.cert_dir / f"{domain}.pem"
        key_path = self.cert_dir / "keys" / f"{domain}.key"
        
        if cert_path.exists() and key_path.exists():
            return str(cert_path), str(key_path)
        
        return None, None
    
    def list_certificates(self) -> List[CertificateInfo]:
        """List all managed certificates."""
        return list(self._certificates.values())
    
    def check_expiry(self, domain: str = None) -> List[Dict]:
        """Check certificate expiry."""
        results = []
        
        certs = (
            [self._certificates[domain]] if domain else 
            list(self._certificates.values())
        )
        
        for info in certs:
            results.append({
                "domain": info.common_name,
                "status": info.status.value,
                "days_until_expiry": info.days_until_expiry,
                "expires": info.not_after.isoformat(),
                "needs_renewal": info.is_expiring_soon
            })
        
        return results
    
    def renew_certificate(self, domain: str) -> bool:
        """Renew a certificate."""
        if domain not in self._certificates:
            return False
        
        info = self._certificates[domain]
        
        if info.cert_type == CertificateType.LETS_ENCRYPT:
            return self.lets_encrypt.renew()
        elif info.cert_type == CertificateType.SELF_SIGNED:
            # Regenerate self-signed cert
            cert_path, key_path = self.generate_self_signed(
                domain=domain,
                san=info.san
            )
            return bool(cert_path)
        
        return False
    
    def delete_certificate(self, domain: str) -> bool:
        """Delete a certificate."""
        if domain not in self._certificates:
            return True
        
        info = self._certificates[domain]
        
        # Delete files
        if info.cert_path and Path(info.cert_path).exists():
            Path(info.cert_path).unlink()
        
        if info.key_path and Path(info.key_path).exists():
            Path(info.key_path).unlink()
        
        if info.chain_path and Path(info.chain_path).exists():
            Path(info.chain_path).unlink()
        
        del self._certificates[domain]
        self._save_config()
        
        return True
    
    def verify_certificate(self, domain: str) -> Dict[str, Any]:
        """Verify certificate is valid and working."""
        cert_path, key_path = self.get_cert_paths(domain)
        
        if not cert_path or not key_path:
            return {
                "valid": False,
                "error": "Certificate not found"
            }
        
        results = {
            "valid": True,
            "cert_exists": Path(cert_path).exists(),
            "key_exists": Path(key_path).exists(),
            "cert_readable": False,
            "key_readable": False,
            "chain_valid": False
        }
        
        try:
            info = self.get_certificate_info(cert_path)
            results.update({
                "cert_readable": True,
                "common_name": info.common_name,
                "issuer": info.issuer,
                "expires": info.not_after.isoformat(),
                "days_until_expiry": info.days_until_expiry,
                "status": info.status.value,
                "san": info.san
            })
            
            if info.is_expired:
                results["valid"] = False
                results["error"] = "Certificate expired"
        
        except Exception as e:
            results["cert_readable"] = False
            results["valid"] = False
            results["error"] = str(e)
        
        # Try to read key
        try:
            key_manager = KeyManager()
            key_manager.load_key(Path(key_path).stem)
            results["key_readable"] = True
        except Exception:
            results["key_readable"] = False
            results["valid"] = False
        
        return results


# CLI interface
def main():
    """CLI for SSL management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sentience SSL Manager")
    subparsers = parser.add_subparsers(dest="command")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate certificate")
    gen_parser.add_argument("domain", help="Domain name")
    gen_parser.add_argument("--san", action="append", help="Subject Alternative Name")
    gen_parser.add_argument("--days", type=int, default=365, help="Validity days")
    gen_parser.add_argument("--key-size", type=int, default=2048, help="Key size")
    
    # Request command (Let's Encrypt)
    req_parser = subparsers.add_parser("request", help="Request Let's Encrypt cert")
    req_parser.add_argument("domain", help="Domain name")
    req_parser.add_argument("email", help="Email address")
    req_parser.add_argument("--webroot", help="Webroot path")
    req_parser.add_argument("--test", action="store_true", help="Use staging server")
    
    # List command
    subparsers.add_parser("list", help="List certificates")
    
    # Check command
    check_parser = subparsers.add_parser("check", help="Check certificate expiry")
    check_parser.add_argument("domain", nargs="?", help="Domain name")
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify certificate")
    verify_parser.add_argument("domain", help="Domain name")
    
    # Renew command
    renew_parser = subparsers.add_parser("renew", help="Renew certificate")
    renew_parser.add_argument("domain", help="Domain name")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete certificate")
    delete_parser.add_argument("domain", help="Domain name")
    
    args = parser.parse_args()
    
    manager = CertificateManager()
    
    if args.command == "generate":
        cert_path, key_path = manager.generate_self_signed(
            domain=args.domain,
            san=args.san,
            validity_days=args.days,
            key_size=args.key_size
        )
        print(f"Generated certificate:")
        print(f"  Cert: {cert_path}")
        print(f"  Key:  {key_path}")
    
    elif args.command == "request":
        cert_path, key_path = manager.request_lets_encrypt(
            domain=args.domain,
            email=args.email,
            webroot=args.webroot,
            test=args.test
        )
        if cert_path:
            print(f"Certificate issued:")
            print(f"  Cert: {cert_path}")
            print(f"  Key:  {key_path}")
        else:
            print("Failed to request certificate")
            sys.exit(1)
    
    elif args.command == "list":
        certs = manager.list_certificates()
        if not certs:
            print("No certificates")
        else:
            for info in certs:
                status_icon = "✓" if info.status == CertificateStatus.VALID else "!"
                print(f"{status_icon} {info.common_name}")
                print(f"  Type: {info.cert_type.value}")
                print(f"  Status: {info.status.value}")
                print(f"  Expires: {info.not_after.isoformat()} ({info.days_until_expiry} days)")
                print()
    
    elif args.command == "check":
        results = manager.check_expiry(args.domain)
        print(json.dumps(results, indent=2))
    
    elif args.command == "verify":
        results = manager.verify_certificate(args.domain)
        print(json.dumps(results, indent=2))
    
    elif args.command == "renew":
        success = manager.renew_certificate(args.domain)
        print(f"Renewal {'successful' if success else 'failed'}")
    
    elif args.command == "delete":
        success = manager.delete_certificate(args.domain)
        print(f"Certificate {'deleted' if success else 'not found'}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
