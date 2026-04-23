"""
Sentience v3.0 - Deployment System
Build optimization, asset bundling, environment config, and process management.
"""

import os
import re
import sys
import json
import shutil
import logging
import subprocess
import hashlib
import tempfile
import asyncio
import signal
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import fnmatch


logger = logging.getLogger("sentience.deploy")


class BuildEnvironment(str, Enum):
    """Build environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AssetType(str, Enum):
    """Asset types."""
    JAVASCRIPT = "javascript"
    CSS = "css"
    IMAGE = "image"
    FONT = "font"
    HTML = "html"
    JSON = "json"
    OTHER = "other"


@dataclass
class BuildConfig:
    """Build configuration."""
    name: str = "sentience-app"
    version: str = "1.0.0"
    environment: BuildEnvironment = BuildEnvironment.DEVELOPMENT
    source_dir: str = "src"
    output_dir: str = "dist"
    static_dir: str = "static"
    
    # Optimization settings
    minify: bool = True
    source_maps: bool = True
    bundle_js: bool = True
    bundle_css: bool = True
    compress_images: bool = True
    cache_busting: bool = True
    
    # Environment variables
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    # File patterns
    include_patterns: List[str] = field(default_factory=lambda: ["**/*"])
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "node_modules", ".git", "__pycache__", "*.pyc", ".env"
    ])
    
    # Build hooks
    pre_build: List[str] = field(default_factory=list)
    post_build: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "environment": self.environment.value,
            "source_dir": self.source_dir,
            "output_dir": self.output_dir,
            "static_dir": self.static_dir,
            "minify": self.minify,
            "source_maps": self.source_maps,
            "bundle_js": self.bundle_js,
            "bundle_css": self.bundle_css,
            "compress_images": self.compress_images,
            "cache_busting": self.cache_busting,
            "env_vars": self.env_vars,
            "include_patterns": self.include_patterns,
            "exclude_patterns": self.exclude_patterns,
            "pre_build": self.pre_build,
            "post_build": self.post_build
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BuildConfig":
        """Create from dictionary."""
        return cls(
            name=data.get("name", "sentience-app"),
            version=data.get("version", "1.0.0"),
            environment=BuildEnvironment(data.get("environment", "development")),
            source_dir=data.get("source_dir", "src"),
            output_dir=data.get("output_dir", "dist"),
            static_dir=data.get("static_dir", "static"),
            minify=data.get("minify", True),
            source_maps=data.get("source_maps", True),
            bundle_js=data.get("bundle_js", True),
            bundle_css=data.get("bundle_css", True),
            compress_images=data.get("compress_images", True),
            cache_busting=data.get("cache_busting", True),
            env_vars=data.get("env_vars", {}),
            include_patterns=data.get("include_patterns", ["**/*"]),
            exclude_patterns=data.get("exclude_patterns", ["node_modules", ".git"]),
            pre_build=data.get("pre_build", []),
            post_build=data.get("post_build", [])
        )
    
    @classmethod
    def load(cls, path: str) -> "BuildConfig":
        """Load config from file."""
        path = Path(path)
        
        if path.suffix == ".json":
            with open(path) as f:
                data = json.load(f)
        elif path.suffix in [".yaml", ".yml"]:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")
        
        return cls.from_dict(data)


@dataclass
class AssetManifest:
    """Asset manifest for cache busting and bundling."""
    assets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    bundles: Dict[str, List[str]] = field(default_factory=dict)
    entrypoints: Dict[str, str] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_asset(
        self,
        source_path: str,
        output_path: str,
        asset_type: AssetType,
        content_hash: str = None
    ):
        """Add asset to manifest."""
        self.assets[output_path] = {
            "source": source_path,
            "type": asset_type.value,
            "hash": content_hash,
            "size": os.path.getsize(source_path) if os.path.exists(source_path) else 0
        }
    
    def add_bundle(self, bundle_name: str, assets: List[str]):
        """Add bundle to manifest."""
        self.bundles[bundle_name] = assets
    
    def to_json(self) -> str:
        """Convert to JSON."""
        return json.dumps({
            "assets": self.assets,
            "bundles": self.bundles,
            "entrypoints": self.entrypoints,
            "generated_at": self.generated_at.isoformat()
        }, indent=2)


class AssetBundler:
    """Bundle and optimize assets."""
    
    JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
    CSS_EXTENSIONS = {".css", ".scss", ".sass", ".less"}
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}
    FONT_EXTENSIONS = {".woff", ".woff2", ".ttf", ".eot", ".otf"}
    
    def __init__(self, config: BuildConfig):
        self.config = config
        self.manifest = AssetManifest()
        self._file_hashes: Dict[str, str] = {}
    
    def get_asset_type(self, path: Path) -> AssetType:
        """Determine asset type from extension."""
        ext = path.suffix.lower()
        
        if ext in self.JS_EXTENSIONS:
            return AssetType.JAVASCRIPT
        elif ext in self.CSS_EXTENSIONS:
            return AssetType.CSS
        elif ext in self.IMAGE_EXTENSIONS:
            return AssetType.IMAGE
        elif ext in self.FONT_EXTENSIONS:
            return AssetType.FONT
        elif ext == ".html":
            return AssetType.HTML
        elif ext == ".json":
            return AssetType.JSON
        
        return AssetType.OTHER
    
    def compute_hash(self, content: bytes) -> str:
        """Compute content hash for cache busting."""
        return hashlib.sha256(content).hexdigest()[:12]
    
    def should_include(self, path: Path) -> bool:
        """Check if file should be included in build."""
        path_str = str(path)
        
        # Check exclude patterns
        for pattern in self.config.exclude_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return False
            if pattern in path_str:
                return False
        
        # Check include patterns
        for pattern in self.config.include_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return True
        
        return False
    
    def bundle_javascript(
        self,
        files: List[Path],
        output_name: str = "bundle.js"
    ) -> Optional[Path]:
        """Bundle JavaScript files."""
        if not self.config.bundle_js:
            return None
        
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bundled_content = []
        
        for file in sorted(files):
            if not file.exists():
                continue
            
            content = file.read_text()
            
            # Add source map reference
            if self.config.source_maps:
                bundled_content.append(f"// Source: {file.name}")
            
            bundled_content.append(content)
        
        # Combine all JS
        combined = "\n".join(bundled_content)
        
        # Minify if enabled
        if self.config.minify and self.config.environment == BuildEnvironment.PRODUCTION:
            combined = self._minify_js(combined)
        
        # Add cache busting hash
        if self.config.cache_busting:
            content_hash = self.compute_hash(combined.encode())
            output_name = f"bundle.{content_hash}.js"
        
        output_path = output_dir / output_name
        output_path.write_text(combined)
        
        # Add to manifest
        self.manifest.add_asset(
            str(output_path),
            output_name,
            AssetType.JAVASCRIPT,
            self.compute_hash(combined.encode())
        )
        
        self.manifest.add_bundle(output_name, [str(f) for f in files])
        
        logger.info(f"Bundled {len(files)} JS files -> {output_name}")
        return output_path
    
    def bundle_css(
        self,
        files: List[Path],
        output_name: str = "bundle.css"
    ) -> Optional[Path]:
        """Bundle CSS files."""
        if not self.config.bundle_css:
            return None
        
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bundled_content = []
        
        for file in sorted(files):
            if not file.exists():
                continue
            
            content = file.read_text()
            bundled_content.append(f"/* Source: {file.name} */\n{content}")
        
        combined = "\n".join(bundled_content)
        
        # Minify if enabled
        if self.config.minify and self.config.environment == BuildEnvironment.PRODUCTION:
            combined = self._minify_css(combined)
        
        # Add cache busting hash
        if self.config.cache_busting:
            content_hash = self.compute_hash(combined.encode())
            output_name = f"bundle.{content_hash}.css"
        
        output_path = output_dir / output_name
        output_path.write_text(combined)
        
        self.manifest.add_asset(
            str(output_path),
            output_name,
            AssetType.CSS,
            self.compute_hash(combined.encode())
        )
        
        self.manifest.add_bundle(output_name, [str(f) for f in files])
        
        logger.info(f"Bundled {len(files)} CSS files -> {output_name}")
        return output_path
    
    def _minify_js(self, content: str) -> str:
        """Minify JavaScript content."""
        # Simple minification - remove comments and extra whitespace
        # For production, use terser or uglifyjs
        
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove spaces around operators
        content = re.sub(r'\s*([{};,:\[\]()])\s*', r'\1', content)
        
        return content.strip()
    
    def _minify_css(self, content: str) -> str:
        """Minify CSS content."""
        # Remove comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove unnecessary spaces
        content = re.sub(r'\s*([{};:,>~+])\s*', r'\1', content)
        
        return content.strip()
    
    def copy_static_files(self) -> int:
        """Copy static files to output directory."""
        source_dir = Path(self.config.static_dir)
        output_dir = Path(self.config.output_dir)
        
        if not source_dir.exists():
            return 0
        
        count = 0
        
        for file in source_dir.rglob("*"):
            if file.is_file() and self.should_include(file):
                relative = file.relative_to(source_dir)
                output_path = output_dir / relative
                
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                asset_type = self.get_asset_type(file)
                
                # Handle images
                if asset_type == AssetType.IMAGE and self.config.compress_images:
                    self._compress_image(file, output_path)
                else:
                    shutil.copy2(file, output_path)
                
                # Add to manifest
                self.manifest.add_asset(
                    str(file),
                    str(relative),
                    asset_type
                )
                
                count += 1
        
        logger.info(f"Copied {count} static files")
        return count
    
    def _compress_image(self, source: Path, output: Path):
        """Compress image file."""
        # Basic compression using PIL if available
        try:
            from PIL import Image
            
            with Image.open(source) as img:
                # Preserve format
                if source.suffix.lower() in [".jpg", ".jpeg"]:
                    img.save(output, "JPEG", quality=85, optimize=True)
                elif source.suffix.lower() == ".png":
                    img.save(output, "PNG", optimize=True)
                elif source.suffix.lower() == ".webp":
                    img.save(output, "WEBP", quality=85)
                else:
                    shutil.copy2(source, output)
        except ImportError:
            # PIL not available, just copy
            shutil.copy2(source, output)
    
    def process_html_files(self) -> int:
        """Process HTML files and update asset references."""
        output_dir = Path(self.config.output_dir)
        
        count = 0
        
        for html_file in output_dir.rglob("*.html"):
            content = html_file.read_text()
            
            # Update asset references with cache-busted names
            for output_path, asset_info in self.manifest.assets.items():
                if self.config.cache_busting and asset_info.get("hash"):
                    original_name = asset_info["source"]
                    # Replace references in HTML
                    # This is simplified - in production use proper HTML parsing
                    content = content.replace(
                        f'href="{original_name}"',
                        f'href="{output_path}"'
                    )
                    content = content.replace(
                        f'src="{original_name}"',
                        f'src="{output_path}"'
                    )
            
            html_file.write_text(content)
            count += 1
        
        return count


class EnvironmentManager:
    """Manage environment configuration."""
    
    ENV_FILE = ".env"
    ENV_EXAMPLE = ".env.example"
    
    def __init__(self, config_dir: str = "."):
        self.config_dir = Path(config_dir)
        self._env_vars: Dict[str, str] = {}
    
    def load_env(self, env_file: str = None) -> Dict[str, str]:
        """Load environment variables from file."""
        env_path = self.config_dir / (env_file or self.ENV_FILE)
        
        if not env_path.exists():
            return {}
        
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                
                if not line or line.startswith("#"):
                    continue
                
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    self._env_vars[key] = value
                    os.environ[key] = value
        
        return self._env_vars
    
    def save_env(self, env_vars: Dict[str, str], env_file: str = None):
        """Save environment variables to file."""
        env_path = self.config_dir / (env_file or self.ENV_FILE)
        
        lines = ["# Environment configuration"]
        lines.append(f"# Generated: {datetime.utcnow().isoformat()}")
        lines.append("")
        
        for key, value in sorted(env_vars.items()):
            if " " in value or '"' in value:
                value = f'"{value}"'
            lines.append(f"{key}={value}")
        
        env_path.write_text("\n".join(lines))
    
    def generate_example(self, env_vars: Dict[str, str] = None):
        """Generate .env.example file."""
        example_path = self.config_dir / self.ENV_EXAMPLE
        
        lines = ["# Environment configuration example"]
        lines.append("# Copy to .env and fill in values")
        lines.append("")
        
        for key, value in sorted((env_vars or {}).items()):
            lines.append(f"{key}=")
        
        example_path.write_text("\n".join(lines))
    
    def interpolate(self, template: str) -> str:
        """Interpolate environment variables in template."""
        for key, value in self._env_vars.items():
            template = template.replace(f"${{{key}}}", value)
            template = template.replace(f"${key}", value)
        
        return template


class ProcessManager:
    """Manage long-running processes."""
    
    def __init__(self, work_dir: str = "."):
        self.work_dir = Path(work_dir)
        self._processes: Dict[str, subprocess.Popen] = {}
        self._logs: Dict[str, Path] = {}
        self._pid_dir = self.work_dir / ".pids"
        self._pid_dir.mkdir(parents=True, exist_ok=True)
    
    def start(
        self,
        name: str,
        command: List[str],
        env: Dict[str, str] = None,
        background: bool = True
    ) -> subprocess.Popen:
        """Start a process."""
        if name in self._processes and self._processes[name].poll() is None:
            logger.warning(f"Process '{name}' already running")
            return self._processes[name]
        
        # Setup environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        
        # Setup logging
        log_dir = self.work_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        stdout_path = log_dir / f"{name}.log"
        stderr_path = log_dir / f"{name}_error.log"
        
        self._logs[name] = stdout_path
        
        # Start process
        kwargs = {
            "cwd": self.work_dir,
            "env": process_env,
        }
        
        if background:
            kwargs["stdout"] = open(stdout_path, "a")
            kwargs["stderr"] = open(stderr_path, "a")
        
        process = subprocess.Popen(command, **kwargs)
        
        # Save PID
        pid_file = self._pid_dir / f"{name}.pid"
        pid_file.write_text(str(process.pid))
        
        self._processes[name] = process
        logger.info(f"Started process '{name}' (PID: {process.pid})")
        
        return process
    
    def stop(self, name: str, timeout: int = 10) -> bool:
        """Stop a process."""
        if name not in self._processes:
            return True
        
        process = self._processes[name]
        
        if process.poll() is not None:
            return True
        
        # Try graceful shutdown
        process.terminate()
        
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Force kill
            process.kill()
            process.wait()
        
        # Clean up PID file
        pid_file = self._pid_dir / f"{name}.pid"
        if pid_file.exists():
            pid_file.unlink()
        
        del self._processes[name]
        logger.info(f"Stopped process '{name}'")
        return True
    
    def restart(self, name: str) -> Optional[subprocess.Popen]:
        """Restart a process."""
        # Get current config
        pid_file = self._pid_dir / f"{name}.pid"
        if not pid_file.exists():
            return None
        
        # Stop and restart would need stored config
        self.stop(name)
        
        # Note: Would need to store command to restart
        return None
    
    def status(self, name: str = None) -> Dict[str, Dict]:
        """Get process status."""
        if name:
            if name not in self._processes:
                return {name: {"status": "not_found"}}
            
            process = self._processes[name]
            return {
                name: {
                    "status": "running" if process.poll() is None else "stopped",
                    "pid": process.pid,
                    "exit_code": process.returncode
                }
            }
        
        return {
            n: {
                "status": "running" if p.poll() is None else "stopped",
                "pid": p.pid,
                "exit_code": p.returncode
            }
            for n, p in self._processes.items()
        }
    
    def logs(self, name: str, lines: int = 100) -> str:
        """Get process logs."""
        if name not in self._logs:
            return ""
        
        log_path = self._logs[name]
        if not log_path.exists():
            return ""
        
        with open(log_path) as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    
    def stop_all(self):
        """Stop all managed processes."""
        for name in list(self._processes.keys()):
            self.stop(name)


class DeploymentPipeline:
    """Complete deployment pipeline."""
    
    def __init__(
        self,
        config: BuildConfig,
        work_dir: str = "."
    ):
        self.config = config
        self.work_dir = Path(work_dir)
        self.bundler = AssetBundler(config)
        self.env_manager = EnvironmentManager(work_dir)
        self.process_manager = ProcessManager(work_dir)
        self._build_id: Optional[str] = None
    
    def pre_build(self) -> bool:
        """Run pre-build hooks."""
        for command in self.config.pre_build:
            logger.info(f"Running pre-build: {command}")
            
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.work_dir,
                capture_output=True
            )
            
            if result.returncode != 0:
                logger.error(f"Pre-build failed: {result.stderr.decode()}")
                return False
        
        return True
    
    def build(self) -> bool:
        """Run the build process."""
        self._build_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        logger.info(f"Starting build {self._build_id}")
        
        # Load environment
        self.env_manager.load_env()
        self.env_manager._env_vars.update(self.config.env_vars)
        
        # Run pre-build hooks
        if not self.pre_build():
            return False
        
        # Clean output directory
        output_dir = Path(self.config.output_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        
        # Collect source files
        source_dir = Path(self.config.source_dir)
        
        js_files = []
        css_files = []
        
        for file in source_dir.rglob("*"):
            if not file.is_file():
                continue
            
            if not self.bundler.should_include(file):
                continue
            
            asset_type = self.bundler.get_asset_type(file)
            
            if asset_type == AssetType.JAVASCRIPT:
                js_files.append(file)
            elif asset_type == AssetType.CSS:
                css_files.append(file)
        
        # Bundle assets
        if js_files and self.config.bundle_js:
            self.bundler.bundle_javascript(js_files)
        
        if css_files and self.config.bundle_css:
            self.bundler.bundle_css(css_files)
        
        # Copy static files
        self.bundler.copy_static_files()
        
        # Process HTML
        self.bundler.process_html_files()
        
        # Save manifest
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(self.bundler.manifest.to_json())
        
        # Run post-build hooks
        if not self.post_build():
            return False
        
        logger.info(f"Build complete: {self._build_id}")
        return True
    
    def post_build(self) -> bool:
        """Run post-build hooks."""
        for command in self.config.post_build:
            logger.info(f"Running post-build: {command}")
            
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.work_dir,
                capture_output=True
            )
            
            if result.returncode != 0:
                logger.error(f"Post-build failed: {result.stderr.decode()}")
                return False
        
        return True
    
    def deploy(
        self,
        host: str = "localhost",
        port: int = 8000,
        command: str = None
    ) -> subprocess.Popen:
        """Deploy the built application."""
        output_dir = Path(self.config.output_dir)
        
        if not output_dir.exists():
            raise RuntimeError("Build output not found. Run build first.")
        
        # Default command for serving
        if not command:
            command = [
                sys.executable, "-m", "http.server",
                str(port),
                "--directory", str(output_dir)
            ]
        
        # Start process
        env = self.env_manager._env_vars.copy()
        env.update({
            "HOST": host,
            "PORT": str(port),
            "BUILD_ID": self._build_id or "unknown"
        })
        
        return self.process_manager.start(
            "server",
            command,
            env=env
        )
    
    def rollback(self) -> bool:
        """Rollback to previous build."""
        # Check for backup
        output_dir = Path(self.config.output_dir)
        backup_dir = output_dir.parent / f"{output_dir.name}.backup"
        
        if not backup_dir.exists():
            logger.error("No backup found for rollback")
            return False
        
        # Swap directories
        temp_dir = output_dir.parent / f"{output_dir.name}.temp"
        output_dir.rename(temp_dir)
        backup_dir.rename(output_dir)
        temp_dir.rename(backup_dir)
        
        logger.info("Rollback complete")
        return True
    
    def create_backup(self):
        """Create backup of current build."""
        output_dir = Path(self.config.output_dir)
        backup_dir = output_dir.parent / f"{output_dir.name}.backup"
        
        if output_dir.exists():
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            
            shutil.copytree(output_dir, backup_dir)
            logger.info("Backup created")


def create_deployment(
    name: str = "sentience-app",
    environment: str = "development",
    **kwargs
) -> DeploymentPipeline:
    """Factory function to create deployment pipeline."""
    
    config = BuildConfig(
        name=name,
        environment=BuildEnvironment(environment),
        **kwargs
    )
    
    return DeploymentPipeline(config)


# CLI interface
def main():
    """CLI for deployment."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sentience Deployment System")
    subparsers = parser.add_subparsers(dest="command")
    
    # Build command
    build_parser = subparsers.add_parser("build", help="Build the application")
    build_parser.add_argument("--config", help="Config file path")
    build_parser.add_argument("--env", default="development", help="Environment")
    build_parser.add_argument("--output", help="Output directory")
    
    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy the application")
    deploy_parser.add_argument("--host", default="localhost", help="Host")
    deploy_parser.add_argument("--port", type=int, default=8000, help="Port")
    deploy_parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop deployment")
    
    # Status command
    subparsers.add_parser("status", help="Show deployment status")
    
    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show logs")
    logs_parser.add_argument("--lines", type=int, default=100, help="Number of lines")
    
    args = parser.parse_args()
    
    # Load config
    config = BuildConfig(environment=BuildEnvironment(args.env if hasattr(args, 'env') else 'development'))
    
    if hasattr(args, 'config') and args.config:
        config = BuildConfig.load(args.config)
    
    if hasattr(args, 'output') and args.output:
        config.output_dir = args.output
    
    pipeline = DeploymentPipeline(config)
    
    if args.command == "build":
        success = pipeline.build()
        print(f"Build {'succeeded' if success else 'failed'}")
        
    elif args.command == "deploy":
        pipeline.build()
        process = pipeline.deploy(
            host=args.host,
            port=args.port
        )
        print(f"Deployed at http://{args.host}:{args.port}")
        print(f"PID: {process.pid}")
        
    elif args.command == "stop":
        pipeline.process_manager.stop_all()
        print("Stopped all processes")
        
    elif args.command == "status":
        status = pipeline.process_manager.status()
        print(json.dumps(status, indent=2))
        
    elif args.command == "logs":
        logs = pipeline.process_manager.logs("server", lines=args.lines)
        print(logs)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
