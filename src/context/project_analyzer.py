"""
Project Analyzer - Comprehensive project analysis for Sentience v3.0

Features:
- Language detection from file extensions, shebangs, and content
- Framework detection from config files and patterns
- Dependency mapping from various package managers
- Structure analysis with directory trees
- Config detection for multiple ecosystems
"""

import os
import re
import json
import tomli
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LanguageInfo:
    """Information about a detected language."""
    name: str
    file_count: int
    extensions: Set[str]
    percentage: float
    primary: bool = False


@dataclass
class Framework:
    """Detected framework information."""
    name: str
    version: Optional[str]
    config_file: str
    category: str  # web, data, ml, testing, etc.
    confidence: float


@dataclass
class Dependency:
    """Project dependency."""
    name: str
    version: Optional[str]
    source: str  # package manager name
    dev: bool = False
    direct: bool = True


@dataclass
class ConfigFile:
    """Detected configuration file."""
    path: str
    type: str
    parser: str
    content_hash: str


@dataclass
class ProjectStructure:
    """Project directory structure."""
    root: str
    directories: Dict[str, List[str]]
    file_types: Dict[str, int]
    total_files: int
    total_dirs: int
    depth: int


@dataclass
class ProjectAnalysis:
    """Complete project analysis result."""
    root_path: str
    languages: List[LanguageInfo]
    primary_language: Optional[LanguageInfo]
    frameworks: List[Framework]
    dependencies: List[Dependency]
    structure: ProjectStructure
    configs: List[ConfigFile]
    metadata: Dict[str, Any] = field(default_factory=dict)


# Language detection patterns
LANGUAGE_EXTENSIONS = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.jsx': 'JavaScript',
    '.ts': 'TypeScript',
    '.tsx': 'TypeScript',
    '.java': 'Java',
    '.kt': 'Kotlin',
    '.go': 'Go',
    '.rs': 'Rust',
    '.rb': 'Ruby',
    '.php': 'PHP',
    '.c': 'C',
    '.cpp': 'C++',
    '.cc': 'C++',
    '.cxx': 'C++',
    '.h': 'C',
    '.hpp': 'C++',
    '.cs': 'C#',
    '.swift': 'Swift',
    '.m': 'Objective-C',
    '.scala': 'Scala',
    '.ex': 'Elixir',
    '.exs': 'Elixir',
    '.erl': 'Erlang',
    '.hs': 'Haskell',
    '.lua': 'Lua',
    '.r': 'R',
    '.rpy': 'R',
    '.sh': 'Shell',
    '.bash': 'Shell',
    '.zsh': 'Shell',
    '.ps1': 'PowerShell',
    '.sql': 'SQL',
    '.html': 'HTML',
    '.css': 'CSS',
    '.scss': 'SCSS',
    '.less': 'LESS',
    '.vue': 'Vue',
    '.svelte': 'Svelte',
    '.dart': 'Dart',
    '.pl': 'Perl',
    '.pm': 'Perl',
    '.clj': 'Clojure',
    '.cljs': 'Clojure',
    '.elm': 'Elm',
    '.fs': 'F#',
    '.fsi': 'F#',
    '.fsscript': 'F#',
    '.ml': 'OCaml',
    '.mli': 'OCaml',
    '.jl': 'Julia',
    '.nim': 'Nim',
    '.cr': 'Crystal',
    '.d': 'D',
    '.zig': 'Zig',
    '.v': 'V',
    '.odin': 'Odin',
    '.sol': 'Solidity',
    '.vy': 'Vyper',
}

SHEBANG_PATTERNS = {
    'python': r'#!.*python',
    'ruby': r'#!.*ruby',
    'perl': r'#!.*perl',
    'bash': r'#!.*/bash',
    'sh': r'#!.*/sh',
    'zsh': r'#!.*/zsh',
    'node': r'#!.*node',
    'deno': r'#!.*deno',
}

# Framework detection patterns
FRAMEWORK_CONFIGS = {
    # Python
    'requirements.txt': {'frameworks': ['Python'], 'category': 'general'},
    'setup.py': {'frameworks': ['Python'], 'category': 'general'},
    'pyproject.toml': {'frameworks': ['Python'], 'category': 'general'},
    'Pipfile': {'frameworks': ['Python', 'Pipenv'], 'category': 'general'},
    'poetry.lock': {'frameworks': ['Python', 'Poetry'], 'category': 'general'},
    
    # JavaScript/TypeScript
    'package.json': {'frameworks': ['Node.js'], 'category': 'general'},
    'yarn.lock': {'frameworks': ['Node.js', 'Yarn'], 'category': 'general'},
    'pnpm-lock.yaml': {'frameworks': ['Node.js', 'pnpm'], 'category': 'general'},
    'bun.lockb': {'frameworks': ['Node.js', 'Bun'], 'category': 'general'},
    
    # Go
    'go.mod': {'frameworks': ['Go'], 'category': 'general'},
    'go.sum': {'frameworks': ['Go'], 'category': 'general'},
    
    # Rust
    'Cargo.toml': {'frameworks': ['Rust'], 'category': 'general'},
    'Cargo.lock': {'frameworks': ['Rust'], 'category': 'general'},
    
    # Ruby
    'Gemfile': {'frameworks': ['Ruby', 'Bundler'], 'category': 'general'},
    'Gemfile.lock': {'frameworks': ['Ruby', 'Bundler'], 'category': 'general'},
    
    # PHP
    'composer.json': {'frameworks': ['PHP', 'Composer'], 'category': 'general'},
    'composer.lock': {'frameworks': ['PHP', 'Composer'], 'category': 'general'},
    
    # Java
    'pom.xml': {'frameworks': ['Java', 'Maven'], 'category': 'general'},
    'build.gradle': {'frameworks': ['Java', 'Gradle'], 'category': 'general'},
    'build.gradle.kts': {'frameworks': ['Java', 'Gradle'], 'category': 'general'},
    
    # Elixir
    'mix.exs': {'frameworks': ['Elixir', 'Mix'], 'category': 'general'},
    
    # Clojure
    'project.clj': {'frameworks': ['Clojure', 'Leiningen'], 'category': 'general'},
    
    # .NET
    '*.csproj': {'frameworks': ['.NET'], 'category': 'general'},
    '*.fsproj': {'frameworks': ['.NET', 'F#'], 'category': 'general'},
    'packages.config': {'frameworks': ['.NET', 'NuGet'], 'category': 'general'},
}

FRAMEWORK_IMPORTS = {
    # Python web frameworks
    'flask': {'name': 'Flask', 'category': 'web'},
    'django': {'name': 'Django', 'category': 'web'},
    'fastapi': {'name': 'FastAPI', 'category': 'web'},
    'tornado': {'name': 'Tornado', 'category': 'web'},
    'aiohttp': {'name': 'aiohttp', 'category': 'web'},
    'sanic': {'name': 'Sanic', 'category': 'web'},
    'bottle': {'name': 'Bottle', 'category': 'web'},
    'pyramid': {'name': 'Pyramid', 'category': 'web'},
    
    # Python data/ML
    'pandas': {'name': 'Pandas', 'category': 'data'},
    'numpy': {'name': 'NumPy', 'category': 'data'},
    'scipy': {'name': 'SciPy', 'category': 'data'},
    'sklearn': {'name': 'scikit-learn', 'category': 'ml'},
    'tensorflow': {'name': 'TensorFlow', 'category': 'ml'},
    'torch': {'name': 'PyTorch', 'category': 'ml'},
    'keras': {'name': 'Keras', 'category': 'ml'},
    'transformers': {'name': 'Transformers', 'category': 'ml'},
    'spacy': {'name': 'spaCy', 'category': 'ml'},
    'matplotlib': {'name': 'Matplotlib', 'category': 'data'},
    'plotly': {'name': 'Plotly', 'category': 'data'},
    
    # Python testing
    'pytest': {'name': 'pytest', 'category': 'testing'},
    'unittest': {'name': 'unittest', 'category': 'testing'},
    'nose': {'name': 'nose', 'category': 'testing'},
    'hypothesis': {'name': 'Hypothesis', 'category': 'testing'},
    
    # JavaScript/TypeScript frameworks
    'react': {'name': 'React', 'category': 'web'},
    'vue': {'name': 'Vue', 'category': 'web'},
    'angular': {'name': 'Angular', 'category': 'web'},
    'svelte': {'name': 'Svelte', 'category': 'web'},
    'next': {'name': 'Next.js', 'category': 'web'},
    'nuxt': {'name': 'Nuxt', 'category': 'web'},
    'express': {'name': 'Express', 'category': 'web'},
    'fastify': {'name': 'Fastify', 'category': 'web'},
    'koa': {'name': 'Koa', 'category': 'web'},
    'hono': {'name': 'Hono', 'category': 'web'},
    'nestjs': {'name': 'NestJS', 'category': 'web'},
    'graphql': {'name': 'GraphQL', 'category': 'api'},
    'apollo': {'name': 'Apollo', 'category': 'api'},
    
    # Go frameworks
    'gin': {'name': 'Gin', 'category': 'web'},
    'echo': {'name': 'Echo', 'category': 'web'},
    'fiber': {'name': 'Fiber', 'category': 'web'},
    'chi': {'name': 'Chi', 'category': 'web'},
    
    # Rust frameworks
    'actix': {'name': 'Actix', 'category': 'web'},
    'rocket': {'name': 'Rocket', 'category': 'web'},
    'warp': {'name': 'Warp', 'category': 'web'},
    'axum': {'name': 'Axum', 'category': 'web'},
    
    # Ruby frameworks
    'rails': {'name': 'Rails', 'category': 'web'},
    'sinatra': {'name': 'Sinatra', 'category': 'web'},
    'hanami': {'name': 'Hanami', 'category': 'web'},
    
    # PHP frameworks
    'laravel': {'name': 'Laravel', 'category': 'web'},
    'symfony': {'name': 'Symfony', 'category': 'web'},
    'codeigniter': {'name': 'CodeIgniter', 'category': 'web'},
}

CONFIG_PATTERNS = {
    'tsconfig.json': {'type': 'typescript', 'parser': 'json'},
    'jsconfig.json': {'type': 'javascript', 'parser': 'json'},
    '.eslintrc': {'type': 'eslint', 'parser': 'json/yaml'},
    '.eslintrc.json': {'type': 'eslint', 'parser': 'json'},
    '.eslintrc.yaml': {'type': 'eslint', 'parser': 'yaml'},
    '.eslintrc.yml': {'type': 'eslint', 'parser': 'yaml'},
    '.prettierrc': {'type': 'prettier', 'parser': 'json/yaml'},
    '.prettierrc.json': {'type': 'prettier', 'parser': 'json'},
    'prettier.config.js': {'type': 'prettier', 'parser': 'js'},
    '.babelrc': {'type': 'babel', 'parser': 'json'},
    'babel.config.js': {'type': 'babel', 'parser': 'js'},
    'webpack.config.js': {'type': 'webpack', 'parser': 'js'},
    'vite.config.js': {'type': 'vite', 'parser': 'js'},
    'vite.config.ts': {'type': 'vite', 'parser': 'js'},
    'rollup.config.js': {'type': 'rollup', 'parser': 'js'},
    'jest.config.js': {'type': 'jest', 'parser': 'js'},
    'vitest.config.ts': {'type': 'vitest', 'parser': 'js'},
    'karma.conf.js': {'type': 'karma', 'parser': 'js'},
    'mocha.opts': {'type': 'mocha', 'parser': 'text'},
    '.mocharc.json': {'type': 'mocha', 'parser': 'json'},
    'pytest.ini': {'type': 'pytest', 'parser': 'ini'},
    'setup.cfg': {'type': 'setuptools', 'parser': 'ini'},
    'tox.ini': {'type': 'tox', 'parser': 'ini'},
    '.flake8': {'type': 'flake8', 'parser': 'ini'},
    'pylintrc': {'type': 'pylint', 'parser': 'ini'},
    '.pylintrc': {'type': 'pylint', 'parser': 'ini'},
    'mypy.ini': {'type': 'mypy', 'parser': 'ini'},
    '.mypy.ini': {'type': 'mypy', 'parser': 'ini'},
    'ruff.toml': {'type': 'ruff', 'parser': 'toml'},
    'Makefile': {'type': 'make', 'parser': 'makefile'},
    'Dockerfile': {'type': 'docker', 'parser': 'dockerfile'},
    'docker-compose.yml': {'type': 'docker-compose', 'parser': 'yaml'},
    'docker-compose.yaml': {'type': 'docker-compose', 'parser': 'yaml'},
    '.github/workflows': {'type': 'github-actions', 'parser': 'yaml'},
    '.gitlab-ci.yml': {'type': 'gitlab-ci', 'parser': 'yaml'},
    'Jenkinsfile': {'type': 'jenkins', 'parser': 'groovy'},
    'terraform': {'type': 'terraform', 'parser': 'hcl'},
    '.env': {'type': 'env', 'parser': 'env'},
    '.env.local': {'type': 'env', 'parser': 'env'},
    '.editorconfig': {'type': 'editorconfig', 'parser': 'ini'},
    '.gitignore': {'type': 'gitignore', 'parser': 'gitignore'},
    '.dockerignore': {'type': 'dockerignore', 'parser': 'gitignore'},
}

IGNORE_DIRS = {
    'node_modules', '.git', '__pycache__', '.pytest_cache', '.mypy_cache',
    'venv', '.venv', 'env', '.env', 'dist', 'build', 'target', 'out',
    '.next', '.nuxt', '.output', 'coverage', '.coverage', 'htmlcov',
    '.idea', '.vscode', '*.egg-info', 'site-packages', 'vendor',
    'Pods', '.gradle', '.mvn', 'bower_components', 'jspm_packages',
}


class ProjectAnalyzer:
    """Analyzes project structure, languages, frameworks, and dependencies."""
    
    def __init__(self, root_path: str, max_depth: int = 10):
        self.root_path = Path(root_path).resolve()
        self.max_depth = max_depth
        self._file_cache: Dict[str, str] = {}
    
    def analyze(self) -> ProjectAnalysis:
        """Perform complete project analysis."""
        logger.info(f"Analyzing project at {self.root_path}")
        
        structure = self._analyze_structure()
        languages = self._detect_languages()
        frameworks = self._detect_frameworks()
        dependencies = self._map_dependencies()
        configs = self._detect_configs()
        
        # Determine primary language
        primary_language = None
        if languages:
            primary_language = max(languages, key=lambda l: l.file_count)
            primary_language.primary = True
        
        return ProjectAnalysis(
            root_path=str(self.root_path),
            languages=languages,
            primary_language=primary_language,
            frameworks=frameworks,
            dependencies=dependencies,
            structure=structure,
            configs=configs,
            metadata={
                'analysis_timestamp': self._get_timestamp(),
                'analyzer_version': '1.0.0',
            }
        )
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def _analyze_structure(self) -> ProjectStructure:
        """Analyze project directory structure."""
        directories: Dict[str, List[str]] = defaultdict(list)
        file_types: Dict[str, int] = defaultdict(int)
        total_files = 0
        total_dirs = 0
        max_depth_found = 0
        
        for root, dirs, files in os.walk(self.root_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self._should_ignore(d, root)]
            
            rel_root = os.path.relpath(root, self.root_path)
            if rel_root == '.':
                rel_root = 'root'
            
            depth = rel_root.count(os.sep)
            max_depth_found = max(max_depth_found, depth)
            
            if depth <= self.max_depth:
                for d in dirs:
                    directories[rel_root].append(d + '/')
                    total_dirs += 1
                
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext:
                        file_types[ext] += 1
                    else:
                        file_types['(no extension)'] += 1
                    total_files += 1
        
        return ProjectStructure(
            root=str(self.root_path),
            directories=dict(directories),
            file_types=dict(file_types),
            total_files=total_files,
            total_dirs=total_dirs,
            depth=max_depth_found
        )
    
    def _detect_languages(self) -> List[LanguageInfo]:
        """Detect programming languages used in the project."""
        language_files: Dict[str, Set[str]] = defaultdict(set)
        language_extensions_map: Dict[str, Set[str]] = defaultdict(set)
        total = 0
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not self._should_ignore(d, root)]
            
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                filepath = os.path.join(root, filename)
                
                # Check extension
                if ext in LANGUAGE_EXTENSIONS:
                    lang = LANGUAGE_EXTENSIONS[ext]
                    language_files[lang].add(filepath)
                    language_extensions_map[lang].add(ext)
                    total += 1
                
                # Check shebang for scripts without extension
                if not ext or ext in ('.sh', '.bash', '.zsh'):
                    detected = self._detect_from_shebang(filepath)
                    if detected:
                        language_files[detected].add(filepath)
                        language_extensions_map[detected].add(ext or '(shebang)')
                        if not ext:
                            total += 1
        
        result = []
        for lang, files in language_files.items():
            percentage = (len(files) / total * 100) if total > 0 else 0
            result.append(LanguageInfo(
                name=lang,
                file_count=len(files),
                extensions=language_extensions_map[lang],
                percentage=round(percentage, 2)
            ))
        
        return sorted(result, key=lambda l: l.file_count, reverse=True)
    
    def _detect_from_shebang(self, filepath: str) -> Optional[str]:
        """Detect language from shebang line."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                for lang, pattern in SHEBANG_PATTERNS.items():
                    if re.search(pattern, first_line, re.IGNORECASE):
                        return lang.capitalize()
        except (IOError, OSError):
            pass
        return None
    
    def _detect_frameworks(self) -> List[Framework]:
        """Detect frameworks and libraries used."""
        frameworks: Dict[str, Framework] = {}
        
        # Check config files
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not self._should_ignore(d, root)]
            
            for filename in files:
                if filename in FRAMEWORK_CONFIGS:
                    config_info = FRAMEWORK_CONFIGS[filename]
                    for fw_name in config_info['frameworks']:
                        if fw_name not in frameworks:
                            version = self._extract_version(os.path.join(root, filename), fw_name)
                            frameworks[fw_name] = Framework(
                                name=fw_name,
                                version=version,
                                config_file=os.path.join(root, filename),
                                category=config_info['category'],
                                confidence=1.0
                            )
        
        # Check imports in code files
        detected_imports = self._detect_imports()
        for import_name, info in detected_imports.items():
            fw_name = info['name']
            if fw_name not in frameworks:
                frameworks[fw_name] = Framework(
                    name=fw_name,
                    version=None,
                    config_file='(detected from imports)',
                    category=info['category'],
                    confidence=0.8
                )
        
        return list(frameworks.values())
    
    def _detect_imports(self) -> Dict[str, Dict]:
        """Detect framework imports in code files."""
        imports: Dict[str, Dict] = {}
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not self._should_ignore(d, root)]
            
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                filepath = os.path.join(root, filename)
                
                # Python files
                if ext == '.py':
                    py_imports = self._extract_python_imports(filepath)
                    for imp in py_imports:
                        base_name = imp.split('.')[0].lower()
                        if base_name in FRAMEWORK_IMPORTS:
                            imports[base_name] = FRAMEWORK_IMPORTS[base_name]
                
                # JavaScript/TypeScript files
                elif ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'):
                    js_imports = self._extract_js_imports(filepath)
                    for imp in js_imports:
                        base_name = imp.split('/')[0].lower().replace('@', '')
                        if base_name in FRAMEWORK_IMPORTS:
                            imports[base_name] = FRAMEWORK_IMPORTS[base_name]
        
        return imports
    
    def _extract_python_imports(self, filepath: str) -> Set[str]:
        """Extract imports from Python file."""
        imports: Set[str] = set()
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Match import statements
            patterns = [
                r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+import',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    imports.add(match.group(1))
        except (IOError, OSError):
            pass
        return imports
    
    def _extract_js_imports(self, filepath: str) -> Set[str]:
        """Extract imports from JavaScript/TypeScript file."""
        imports: Set[str] = set()
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Match import statements
            patterns = [
                r"import\s+.*?from\s+['\"]([^'\"]+)['\"]",
                r"import\s+['\"]([^'\"]+)['\"]",
                r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    imp = match.group(1)
                    # Only include non-relative imports
                    if not imp.startswith('.') and not imp.startswith('/'):
                        imports.add(imp)
        except (IOError, OSError):
            pass
        return imports
    
    def _extract_version(self, filepath: str, framework: str) -> Optional[str]:
        """Extract version from config file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # JSON files
            if filepath.endswith('.json'):
                data = json.loads(content)
                # Check dependencies
                for section in ['dependencies', 'devDependencies', 'peerDependencies']:
                    if section in data:
                        if framework in data[section]:
                            return data[section][framework].strip('^~>=<')
            
            # TOML files
            elif filepath.endswith('.toml'):
                try:
                    data = tomli.loads(content)
                    # Poetry format
                    if 'tool' in data and 'poetry' in data['tool']:
                        deps = data['tool']['poetry'].get('dependencies', {})
                        if framework.lower() in deps:
                            ver = deps[framework.lower()]
                            if isinstance(ver, str):
                                return ver.strip('^~>=<')
                    # PEP 621 format
                    elif 'project' in data:
                        deps = data['project'].get('dependencies', [])
                        for dep in deps:
                            if dep.lower().startswith(framework.lower()):
                                match = re.search(r'[=<>!~]+\s*([0-9.]+)', dep)
                                if match:
                                    return match.group(1)
                except Exception:
                    pass
            
            # Requirements.txt format
            elif 'requirements' in filepath.lower():
                for line in content.splitlines():
                    if line.strip().lower().startswith(framework.lower()):
                        match = re.search(r'[=<>!~]+\s*([0-9.]+)', line)
                        if match:
                            return match.group(1)
        except Exception:
            pass
        return None
    
    def _map_dependencies(self) -> List[Dependency]:
        """Map all project dependencies."""
        dependencies: Dict[str, Dependency] = {}
        
        # Python dependencies
        requirements_file = self.root_path / 'requirements.txt'
        if requirements_file.exists():
            deps = self._parse_requirements(requirements_file)
            for name, version in deps.items():
                dependencies[name] = Dependency(
                    name=name,
                    version=version,
                    source='pip',
                    dev=False,
                    direct=True
                )
        
        # Pipenv
        pipfile = self.root_path / 'Pipfile'
        if pipfile.exists():
            deps = self._parse_pipfile(pipfile)
            for name, info in deps.items():
                dependencies[name] = Dependency(
                    name=name,
                    version=info.get('version'),
                    source='pipenv',
                    dev=info.get('dev', False),
                    direct=True
                )
        
        # Poetry
        pyproject = self.root_path / 'pyproject.toml'
        if pyproject.exists():
            deps = self._parse_pyproject(pyproject)
            for name, info in deps.items():
                if name not in dependencies:
                    dependencies[name] = Dependency(
                        name=name,
                        version=info.get('version'),
                        source='poetry',
                        dev=info.get('dev', False),
                        direct=info.get('direct', True)
                    )
        
        # Node.js dependencies
        package_json = self.root_path / 'package.json'
        if package_json.exists():
            deps = self._parse_package_json(package_json)
            for name, info in deps.items():
                dependencies[name] = Dependency(
                    name=name,
                    version=info.get('version'),
                    source='npm',
                    dev=info.get('dev', False),
                    direct=True
                )
        
        # Go dependencies
        go_mod = self.root_path / 'go.mod'
        if go_mod.exists():
            deps = self._parse_go_mod(go_mod)
            for name, version in deps.items():
                dependencies[name] = Dependency(
                    name=name,
                    version=version,
                    source='go',
                    dev=False,
                    direct=True
                )
        
        # Rust dependencies
        cargo_toml = self.root_path / 'Cargo.toml'
        if cargo_toml.exists():
            deps = self._parse_cargo_toml(cargo_toml)
            for name, info in deps.items():
                dependencies[name] = Dependency(
                    name=name,
                    version=info.get('version'),
                    source='cargo',
                    dev=info.get('dev', False),
                    direct=info.get('direct', True)
                )
        
        return list(dependencies.values())
    
    def _parse_requirements(self, filepath: Path) -> Dict[str, Optional[str]]:
        """Parse requirements.txt file."""
        deps: Dict[str, Optional[str]] = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Parse package spec
                        match = re.match(r'^([a-zA-Z0-9_-]+)\s*([=<>!~]+)?\s*([0-9.]+)?', line)
                        if match:
                            name = match.group(1)
                            version = match.group(3) if match.group(3) else None
                            deps[name] = version
        except (IOError, OSError):
            pass
        return deps
    
    def _parse_pipfile(self, filepath: Path) -> Dict[str, Dict]:
        """Parse Pipfile."""
        deps: Dict[str, Dict] = {}
        try:
            import tomli
            with open(filepath, 'rb') as f:
                data = tomli.load(f)
            
            for section, is_dev in [('[packages]', False), ('[dev-packages]', True)]:
                section_name = section.strip('[]')
                if section_name in data:
                    for name, version in data[section_name].items():
                        version_str = version if isinstance(version, str) else None
                        deps[name] = {'version': version_str, 'dev': is_dev}
        except Exception:
            pass
        return deps
    
    def _parse_pyproject(self, filepath: Path) -> Dict[str, Dict]:
        """Parse pyproject.toml for dependencies."""
        deps: Dict[str, Dict] = {}
        try:
            with open(filepath, 'rb') as f:
                data = tomli.load(f)
            
            # PEP 621 format
            if 'project' in data:
                for dep_str in data['project'].get('dependencies', []):
                    match = re.match(r'^([a-zA-Z0-9_-]+)\s*([=<>!~]+)?\s*([0-9.]+)?', dep_str)
                    if match:
                        deps[match.group(1)] = {
                            'version': match.group(3),
                            'dev': False,
                            'direct': True
                        }
                
                for dep_str in data['project'].get('optional-dependencies', {}).get('dev', []):
                    match = re.match(r'^([a-zA-Z0-9_-]+)\s*([=<>!~]+)?\s*([0-9.]+)?', dep_str)
                    if match:
                        deps[match.group(1)] = {
                            'version': match.group(3),
                            'dev': True,
                            'direct': True
                        }
            
            # Poetry format
            if 'tool' in data and 'poetry' in data['tool']:
                poetry = data['tool']['poetry']
                for name, spec in poetry.get('dependencies', {}).items():
                    if name == 'python':
                        continue
                    version = spec if isinstance(spec, str) else None
                    deps[name] = {'version': version, 'dev': False, 'direct': True}
                
                for name, spec in poetry.get('dev-dependencies', {}).items():
                    version = spec if isinstance(spec, str) else None
                    deps[name] = {'version': version, 'dev': True, 'direct': True}
        except Exception:
            pass
        return deps
    
    def _parse_package_json(self, filepath: Path) -> Dict[str, Dict]:
        """Parse package.json for dependencies."""
        deps: Dict[str, Dict] = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for name, version in data.get('dependencies', {}).items():
                deps[name] = {'version': version.strip('^~>=<'), 'dev': False}
            
            for name, version in data.get('devDependencies', {}).items():
                deps[name] = {'version': version.strip('^~>=<'), 'dev': True}
            
            for name, version in data.get('peerDependencies', {}).items():
                deps[name] = {'version': version.strip('^~>=<'), 'dev': False}
        except (IOError, json.JSONDecodeError):
            pass
        return deps
    
    def _parse_go_mod(self, filepath: Path) -> Dict[str, str]:
        """Parse go.mod for dependencies."""
        deps: Dict[str, str] = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Match require block
            require_block = re.search(r'require\s*\((.*?)\)', content, re.DOTALL)
            if require_block:
                for line in require_block.group(1).splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        deps[parts[0]] = parts[1].strip('"')
            
            # Match single require statements
            for match in re.finditer(r'^require\s+(\S+)\s+(\S+)', content, re.MULTILINE):
                deps[match.group(1)] = match.group(2).strip('"')
        except (IOError, OSError):
            pass
        return deps
    
    def _parse_cargo_toml(self, filepath: Path) -> Dict[str, Dict]:
        """Parse Cargo.toml for dependencies."""
        deps: Dict[str, Dict] = {}
        try:
            with open(filepath, 'rb') as f:
                data = tomli.load(f)
            
            for name, spec in data.get('dependencies', {}).items():
                version = spec if isinstance(spec, str) else spec.get('version')
                deps[name] = {'version': version, 'dev': False, 'direct': True}
            
            for name, spec in data.get('dev-dependencies', {}).items():
                version = spec if isinstance(spec, str) else spec.get('version')
                deps[name] = {'version': version, 'dev': True, 'direct': True}
        except Exception:
            pass
        return deps
    
    def _detect_configs(self) -> List[ConfigFile]:
        """Detect configuration files."""
        configs: List[ConfigFile] = []
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not self._should_ignore(d, root)]
            
            for filename in files:
                if filename in CONFIG_PATTERNS:
                    config_info = CONFIG_PATTERNS[filename]
                    filepath = os.path.join(root, filename)
                    content_hash = self._file_hash(filepath)
                    
                    configs.append(ConfigFile(
                        path=filepath,
                        type=config_info['type'],
                        parser=config_info['parser'],
                        content_hash=content_hash
                    ))
                
                # Check for config patterns
                for pattern, config_info in CONFIG_PATTERNS.items():
                    if '*' in pattern:
                        import fnmatch
                        if fnmatch.fnmatch(filename, pattern):
                            filepath = os.path.join(root, filename)
                            configs.append(ConfigFile(
                                path=filepath,
                                type=config_info['type'],
                                parser=config_info['parser'],
                                content_hash=self._file_hash(filepath)
                            ))
        
        return configs
    
    def _file_hash(self, filepath: str) -> str:
        """Get SHA256 hash of file content."""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except (IOError, OSError):
            return 'unknown'
    
    def _should_ignore(self, dirname: str, root: str) -> bool:
        """Check if directory should be ignored."""
        if dirname in IGNORE_DIRS:
            return True
        # Check glob patterns
        import fnmatch
        for pattern in IGNORE_DIRS:
            if '*' in pattern and fnmatch.fnmatch(dirname, pattern):
                return True
        return False


def analyze_project(path: str) -> ProjectAnalysis:
    """Convenience function to analyze a project."""
    analyzer = ProjectAnalyzer(path)
    return analyzer.analyze()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        result = analyze_project(sys.argv[1])
        print(f"Languages: {[l.name for l in result.languages]}")
        print(f"Primary: {result.primary_language.name if result.primary_language else 'None'}")
        print(f"Frameworks: {[f.name for f in result.frameworks]}")
        print(f"Dependencies: {len(result.dependencies)}")
        print(f"Config files: {len(result.configs)}")
