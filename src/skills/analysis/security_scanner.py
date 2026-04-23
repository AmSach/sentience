"""
Security Scanner Skill
Vulnerability detection and security analysis.
"""

import os
import re
from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum

METADATA = {
    "name": "security-scanner",
    "description": "Scan code for security vulnerabilities, unsafe patterns, and potential exploits",
    "category": "analysis",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["security scan", "vulnerability scan", "check security", "find vulnerabilities"],
    "dependencies": [],
    "tags": ["security", "vulnerability", "analysis", "scan"]
}

SKILL_NAME = "security-scanner"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "analysis"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Vulnerability:
    id: str
    name: str
    description: str
    severity: Severity
    line: int
    column: int
    code_snippet: str
    fix_suggestion: str
    cwe: str = ""


class SecurityPatterns:
    """Common security vulnerability patterns."""
    
    PATTERNS = {
        # SQL Injection
        "sql_injection": {
            "python": [
                (r'execute\s*\(\s*[f]?["\'].*\+.*["\']', "Direct string concatenation in SQL query"),
                (r'execute\s*\(\s*[f]?["\'].*%s.*["\'].*%', "String formatting in SQL - use parameterized queries"),
                (r'cursor\.execute\s*\(\s*["\'].*\{.*\}.*["\']\.format', "String format in SQL query"),
                (r'f["\'].*SELECT.*\{.*\}.*["\']', "f-string in SQL query"),
            ],
            "javascript": [
                (r'query\s*\(\s*[`"\'].*\+.*[`"\']', "Direct string concatenation in SQL query"),
                (r'query\s*\(\s*[`"\'].*\$\{.*\}.*[`"\']', "Template literal in SQL query"),
            ],
            "cwe": "CWE-89"
        },
        
        # XSS
        "xss": {
            "python": [
                (r'return\s+.*\+.*request\.', "Unescaped output with request data"),
                (r'markup\.Markup\s*\(\s*request\.', "Potential XSS with Markup"),
                (r'render_template_string\s*\(\s*request\.', "Template injection risk"),
            ],
            "javascript": [
                (r'innerHTML\s*=\s*.*request', "innerHTML assignment with request data"),
                (r'document\.write\s*\(', "document.write is XSS-prone"),
                (r'dangerouslySetInnerHTML', "React dangerouslySetInnerHTML - ensure sanitization"),
                (r'\.html\s*\(\s*.*request', "jQuery .html() with request data"),
            ],
            "cwe": "CWE-79"
        },
        
        # Hardcoded Secrets
        "hardcoded_secrets": {
            "python": [
                (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
                (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
                (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
                (r'token\s*=\s*["\'][^"\']+["\']', "Hardcoded token"),
                (r'aws_access_key_id\s*=\s*["\'][A-Z0-9]{20}["\']', "Hardcoded AWS access key"),
                (r'aws_secret_access_key\s*=\s*["\'][A-Za-z0-9/+=]{40}["\']', "Hardcoded AWS secret key"),
            ],
            "javascript": [
                (r'password\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded password"),
                (r'apiKey\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded API key"),
                (r'secret\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded secret"),
                (r'token\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded token"),
                (r'privateKey\s*[:=]\s*["\'].*-----BEGIN', "Hardcoded private key"),
            ],
            "cwe": "CWE-798"
        },
        
        # Path Traversal
        "path_traversal": {
            "python": [
                (r'open\s*\(\s*request\.', "Opening file with request path"),
                (r'open\s*\(\s*.*\+.*request\.', "Path concatenation with request"),
                (r'send_file\s*\(\s*request\.', "send_file with request path"),
                (r'os\.path\.join\s*\(\s*[^,]*,\s*request\.', "Path join with request data"),
            ],
            "javascript": [
                (r'fs\.readFile\s*\(\s*req\.', "Reading file with request path"),
                (r'fs\.readFile\s*\(\s*.*\+.*req\.', "Path concatenation with request"),
                (r'readFileSync\s*\(\s*req\.', "Reading file with request path"),
                (r'path\.join\s*\(\s*[^,]*,\s*req\.', "Path join with request data"),
            ],
            "cwe": "CWE-22"
        },
        
        # Command Injection
        "command_injection": {
            "python": [
                (r'os\.system\s*\(\s*.*request', "os.system with request data"),
                (r'subprocess\.call\s*\(\s*.*request', "subprocess with request data"),
                (r'subprocess\.run\s*\(\s*.*request', "subprocess with request data"),
                (r'eval\s*\(\s*request', "eval with request data - critical RCE"),
                (r'exec\s*\(\s*request', "exec with request data - critical RCE"),
            ],
            "javascript": [
                (r'eval\s*\(\s*.*req\.', "eval with request data"),
                (r'exec\s*\(\s*.*req\.', "exec with request data"),
                (r'child_process\.exec\s*\(\s*.*req\.', "child_process.exec with request"),
                (r'child_process\.spawn\s*\(\s*.*req\.', "child_process.spawn with request"),
            ],
            "cwe": "CWE-78"
        },
        
        # Insecure Deserialization
        "insecure_deserialization": {
            "python": [
                (r'pickle\.loads\s*\(', "pickle.loads is insecure"),
                (r'pickle\.load\s*\(', "pickle.load is insecure"),
                (r'marshal\.loads\s*\(', "marshal.loads is insecure"),
                (r'yaml\.load\s*\([^)]*\)\s*$', "yaml.load without Loader - use yaml.safe_load"),
                (r'yaml\.unsafe_load\s*\(', "yaml.unsafe_load is dangerous"),
            ],
            "javascript": [
                (r'eval\s*\(\s*.*JSON', "eval with JSON - use JSON.parse"),
            ],
            "cwe": "CWE-502"
        },
        
        # SSRF
        "ssrf": {
            "python": [
                (r'requests\.get\s*\(\s*request\.', "requests.get with request URL"),
                (r'urllib\.request\.urlopen\s*\(\s*request\.', "urlopen with request URL"),
                (r'httpx\.get\s*\(\s*request\.', "httpx.get with request URL"),
            ],
            "javascript": [
                (r'fetch\s*\(\s*req\.', "fetch with request URL"),
                (r'axios\.get\s*\(\s*req\.', "axios.get with request URL"),
                (r'http\.get\s*\(\s*req\.', "http.get with request URL"),
            ],
            "cwe": "CWE-918"
        },
        
        # Weak Cryptography
        "weak_crypto": {
            "python": [
                (r'hashlib\.md5\s*\(', "MD5 is cryptographically broken"),
                (r'hashlib\.sha1\s*\(', "SHA1 is cryptographically weak"),
                (r'DES\s*\(', "DES is insecure - use AES"),
                (r'random\.random\s*\(\s*\)', "Use secrets module for security-sensitive randomness"),
            ],
            "javascript": [
                (r'crypto\.createHash\s*\(\s*["\']md5["\']', "MD5 is cryptographically broken"),
                (r'crypto\.createHash\s*\(\s*["\']sha1["\']', "SHA1 is cryptographically weak"),
                (r'Math\.random\s*\(\s*\)', "Math.random is not cryptographically secure"),
            ],
            "cwe": "CWE-327"
        },
        
        # Debug Mode
        "debug_mode": {
            "python": [
                (r'debug\s*=\s*True', "Debug mode enabled in production"),
                (r'app\.run\s*\([^)]*debug\s*=\s*True', "Flask debug mode enabled"),
                (r'DEBUG\s*=\s*True', "DEBUG flag set to True"),
            ],
            "javascript": [
                (r'debug\s*:\s*true', "Debug mode enabled"),
                (r'NODE_ENV\s*=\s*["\']development["\']', "Development environment"),
            ],
            "cwe": "CWE-489"
        }
    }


class SecurityScanner:
    """Main security scanner class."""
    
    def __init__(self):
        self.vulnerabilities: List[Vulnerability] = []
    
    def scan_file(self, filepath: str, language: str = None) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        
        language = language or self._detect_language(filepath)
        return self.scan_code(code, language, filepath)
    
    def scan_code(self, code: str, language: str = "python", filepath: str = None) -> Dict[str, Any]:
        self.vulnerabilities = []
        lines = code.split('\n')
        
        for vuln_type, patterns in SecurityPatterns.PATTERNS.items():
            lang_patterns = patterns.get(language, patterns.get("python", []))
            
            for pattern, description in lang_patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        # Check for comments that might suppress
                        if '#' in line and '# nosec' in line:
                            continue
                        if '//' in line and '// nosec' in line:
                            continue
                        
                        self.vulnerabilities.append(Vulnerability(
                            id=f"{vuln_type}_{len(self.vulnerabilities)}",
                            name=vuln_type.replace('_', ' ').title(),
                            description=description,
                            severity=self._get_severity(vuln_type),
                            line=i,
                            column=0,
                            code_snippet=line.strip()[:100],
                            fix_suggestion=self._get_fix_suggestion(vuln_type),
                            cwe=patterns.get("cwe", "")
                        ))
        
        return {
            "success": True,
            "vulnerabilities": [self._vuln_to_dict(v) for v in self.vulnerabilities],
            "summary": self._generate_summary(),
            "language": language,
            "filepath": filepath,
            "total_issues": len(self.vulnerabilities),
            "severity_breakdown": self._get_severity_breakdown()
        }
    
    def _detect_language(self, filepath: str) -> str:
        ext_map = {'.py': 'python', '.js': 'javascript', '.jsx': 'javascript', 
                   '.ts': 'javascript', '.tsx': 'javascript'}
        ext = os.path.splitext(filepath)[1].lower()
        return ext_map.get(ext, 'python')
    
    def _get_severity(self, vuln_type: str) -> Severity:
        critical = ['command_injection', 'sql_injection', 'insecure_deserialization', 'hardcoded_secrets']
        high = ['xss', 'ssrf', 'path_traversal']
        medium = ['weak_crypto']
        low = ['debug_mode']
        
        if vuln_type in critical:
            return Severity.CRITICAL
        elif vuln_type in high:
            return Severity.HIGH
        elif vuln_type in medium:
            return Severity.MEDIUM
        elif vuln_type in low:
            return Severity.LOW
        return Severity.INFO
    
    def _get_fix_suggestion(self, vuln_type: str) -> str:
        suggestions = {
            "sql_injection": "Use parameterized queries or prepared statements",
            "xss": "Escape output and use Content Security Policy",
            "hardcoded_secrets": "Use environment variables or secret management",
            "path_traversal": "Validate and sanitize paths, use allowlists",
            "command_injection": "Use subprocess with shell=False and argument lists",
            "insecure_deserialization": "Use safe serialization formats (JSON) or signed data",
            "ssrf": "Validate URLs against an allowlist and use network policies",
            "weak_crypto": "Use SHA-256+ for hashing, AES for encryption",
            "debug_mode": "Disable debug mode in production"
        }
        return suggestions.get(vuln_type, "Review and fix the security issue")
    
    def _vuln_to_dict(self, vuln: Vulnerability) -> Dict[str, Any]:
        return {
            "id": vuln.id,
            "name": vuln.name,
            "description": vuln.description,
            "severity": vuln.severity.value,
            "line": vuln.line,
            "column": vuln.column,
            "code_snippet": vuln.code_snippet,
            "fix_suggestion": vuln.fix_suggestion,
            "cwe": vuln.cwe
        }
    
    def _generate_summary(self) -> str:
        if not self.vulnerabilities:
            return "No security vulnerabilities found"
        
        critical = len([v for v in self.vulnerabilities if v.severity == Severity.CRITICAL])
        high = len([v for v in self.vulnerabilities if v.severity == Severity.HIGH])
        medium = len([v for v in self.vulnerabilities if v.severity == Severity.MEDIUM])
        low = len([v for v in self.vulnerabilities if v.severity == Severity.LOW])
        
        return f"Found {len(self.vulnerabilities)} vulnerabilities: {critical} critical, {high} high, {medium} medium, {low} low"
    
    def _get_severity_breakdown(self) -> Dict[str, int]:
        return {
            "critical": len([v for v in self.vulnerabilities if v.severity == Severity.CRITICAL]),
            "high": len([v for v in self.vulnerabilities if v.severity == Severity.HIGH]),
            "medium": len([v for v in self.vulnerabilities if v.severity == Severity.MEDIUM]),
            "low": len([v for v in self.vulnerabilities if v.severity == Severity.LOW]),
            "info": len([v for v in self.vulnerabilities if v.severity == Severity.INFO])
        }


def execute(filepath: str = None, code: str = None, language: str = None, **kwargs) -> Dict[str, Any]:
    """
    Scan code for security vulnerabilities.
    
    Args:
        filepath: Path to source file
        code: Source code string (if no filepath)
        language: Language override (python/javascript)
    
    Returns:
        Security scan results with vulnerabilities and recommendations
    """
    scanner = SecurityScanner()
    
    if filepath:
        return scanner.scan_file(filepath, language)
    elif code:
        return scanner.scan_code(code, language or "python")
    else:
        return {"success": False, "error": "Either filepath or code must be provided"}
