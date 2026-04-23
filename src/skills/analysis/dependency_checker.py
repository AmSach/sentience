"""
Dependency Checker Skill
Check for outdated and vulnerable dependencies.
"""

import os
import re
import json
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

METADATA = {
    "name": "dependency-checker",
    "description": "Check for outdated packages, vulnerable dependencies, and version conflicts",
    "category": "analysis",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["check dependencies", "outdated packages", "vulnerable dependencies", "dependency audit"],
    "dependencies": [],
    "tags": ["dependencies", "packages", "security", "audit"]
}

SKILL_NAME = "dependency-checker"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "analysis"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class PackageInfo:
    name: str
    installed_version: str
    latest_version: str
    is_outdated: bool
    vulnerabilities: List[Dict[str, Any]]
    license: str = "unknown"
    deprecated: bool = False


class PythonDependencyChecker:
    """Check Python dependencies using pip."""
    
    def check_outdated(self) -> List[PackageInfo]:
        packages = []
        try:
            result = subprocess.run(
                ["pip", "list", "--outdated", "--format=json"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                data = json.loads(result.stdout) if result.stdout.strip() else []
                for pkg in data:
                    packages.append(PackageInfo(
                        name=pkg.get("name", ""),
                        installed_version=pkg.get("version", ""),
                        latest_version=pkg.get("latest_version", ""),
                        is_outdated=True,
                        vulnerabilities=[],
                        license="unknown"
                    ))
        except Exception as e:
            pass
        return packages
    
    def check_vulnerabilities(self) -> List[Dict[str, Any]]:
        vulnerabilities = []
        try:
            result = subprocess.run(
                ["pip", "audit", "--format=json"],
                capture_output=True, text=True, timeout=120
            )
            if result.stdout.strip():
                data = json.loads(result.stdout)
                for vuln in data.get("vulnerabilities", []:
                    vulnerabilities.append({
                        "package": vuln.get("package", {}).get("name", "unknown"),
                        "installed_version": vuln.get("package", {}).get("version", "unknown"),
                        "vulnerability_id": vuln.get("id", ""),
                        "severity": vuln.get("severity", "unknown"),
                        "description": vuln.get("description", ""),
                        "fix_versions": vuln.get("fix_versions", [])
                    })
        except FileNotFoundError:
            # pip-audit not installed
            pass
        except Exception as e:
            pass
        return vulnerabilities
    
    def parse_requirements(self, filepath: str) -> List[Dict[str, str]]:
        if not os.path.exists(filepath):
            return []
        
        requirements = []
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parse package name and version
                match = re.match(r'^([a-zA-Z0-9_-]+)\s*([<>=!]+)\s*([0-9.]+)', line)
                if match:
                    requirements.append({
                        "name": match.group(1),
                        "operator": match.group(2),
                        "version": match.group(3),
                        "raw": line
                    })
                else:
                    requirements.append({
                        "name": line.split('[')[0].strip(),
                        "operator": "",
                        "version": "any",
                        "raw": line
                    })
        return requirements


class NodeDependencyChecker:
    """Check Node.js dependencies using npm."""
    
    def check_outdated(self, directory: str = ".") -> List[PackageInfo]:
        packages = []
        try:
            result = subprocess.run(
                ["npm", "outdated", "--json"],
                capture_output=True, text=True, 
                cwd=directory, timeout=60
            )
            if result.stdout.strip():
                data = json.loads(result.stdout)
                for name, info in data.items():
                    packages.append(PackageInfo(
                        name=name,
                        installed_version=info.get("current", ""),
                        latest_version=info.get("latest", ""),
                        is_outdated=True,
                        vulnerabilities=[],
                        license=info.get("license", "unknown")
                    ))
        except Exception as e:
            pass
        return packages
    
    def check_vulnerabilities(self, directory: str = ".") -> List[Dict[str, Any]]:
        vulnerabilities = []
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                capture_output=True, text=True,
                cwd=directory, timeout=120
            )
            if result.stdout.strip():
                data = json.loads(result.stdout)
                audit_data = data.get("auditReportVersion", 0)
                
                if audit_data >= 2:
                    for vuln in data.get("vulnerabilities", []:
                        vulnerabilities.append({
                            "package": vuln.get("name", "unknown"),
                            "severity": vuln.get("severity", "unknown"),
                            "via": vuln.get("via", []),
                            "fix_available": vuln.get("fixAvailable", False)
                        })
                else:
                    for name, info in data.get("advisories", {}).items():
                        vulnerabilities.append({
                            "package": info.get("module_name", "unknown"),
                            "vulnerability_id": info.get("id", ""),
                            "severity": info.get("severity", "unknown"),
                            "title": info.get("title", ""),
                            "url": info.get("url", ""),
                            "fix_versions": info.get("patched_versions", "")
                        })
        except Exception as e:
            pass
        return vulnerabilities
    
    def parse_package_json(self, filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            return {}
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return {
            "dependencies": data.get("dependencies", {}),
            "dev_dependencies": data.get("devDependencies", {}),
            "peer_dependencies": data.get("peerDependencies", {}),
            "engines": data.get("engines", {})
        }


def execute(directory: str = ".", project_type: str = None, check_vulnerabilities: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Check for outdated and vulnerable dependencies.
    
    Args:
        directory: Project directory
        project_type: Project type (python/node/auto)
        check_vulnerabilities: Whether to run vulnerability scan
    
    Returns:
        Dependency check results with outdated packages and vulnerabilities
    """
    directory = os.path.abspath(directory)
    
    # Auto-detect project type
    if not project_type:
        if os.path.exists(os.path.join(directory, "package.json")):
            project_type = "node"
        elif os.path.exists(os.path.join(directory, "requirements.txt")) or \
             os.path.exists(os.path.join(directory, "pyproject.toml")):
            project_type = "python"
        else:
            project_type = "python"  # default
    
    results = {
        "success": True,
        "project_type": project_type,
        "directory": directory,
        "outdated": [],
        "vulnerabilities": [],
        "summary": ""
    }
    
    if project_type == "python":
        checker = PythonDependencyChecker()
        results["outdated"] = [
            {"name": p.name, "installed": p.installed_version, "latest": p.latest_version}
            for p in checker.check_outdated()
        ]
        
        if check_vulnerabilities:
            results["vulnerabilities"] = checker.check_vulnerabilities()
        
        # Parse requirements if exists
        req_file = os.path.join(directory, "requirements.txt")
        if os.path.exists(req_file):
            results["requirements"] = checker.parse_requirements(req_file)
            
    elif project_type == "node":
        checker = NodeDependencyChecker()
        results["outdated"] = [
            {"name": p.name, "installed": p.installed_version, "latest": p.latest_version}
            for p in checker.check_outdated(directory)
        ]
        
        if check_vulnerabilities:
            results["vulnerabilities"] = checker.check_vulnerabilities(directory)
        
        # Parse package.json
        pkg_file = os.path.join(directory, "package.json")
        if os.path.exists(pkg_file):
            results["package_info"] = checker.parse_package_json(pkg_file)
    
    # Generate summary
    outdated_count = len(results["outdated"])
    vuln_count = len(results["vulnerabilities"])
    critical_vulns = len([v for v in results["vulnerabilities"] if v.get("severity") in ["critical", "high"]])
    
    results["summary"] = f"Found {outdated_count} outdated packages, {vuln_count} vulnerabilities ({critical_vulns} critical/high)"
    results["total_outdated"] = outdated_count
    results["total_vulnerabilities"] = vuln_count
    
    return results
