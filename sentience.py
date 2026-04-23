#!/usr/bin/env python3
"""
Sentience v3.0 - Local AI Computer
Complete desktop application with all features
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Core imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.config import Config
from src.core.memory import MemorySystem
from src.core.engine import SentienceEngine
from src.core.tools import ToolRegistry

# Component imports
from src.gui.main_window import MainWindow
from src.lsp.client import LSPClient, PythonLSPClient
from src.skills.registry import SkillRegistry
from src.integrations.oauth_manager import OAuthManager
from src.hosting.server import HostingServer
from src.automations.scheduler import AutomationScheduler
from src.browser.engine import BrowserEngine
from src.forms.engine import FormManager
from src.context.engine import ContextManager
from src.memory.engine import SentienceVault, KnowledgeGraph, LearningSystem


class SentienceApp:
    """Main Sentience Application"""
    
    def __init__(self, config_dir: str = None):
        self.config_dir = Path(config_dir or Path.home() / ".sentience")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.config = Config(self.config_dir / "config.json")
        self.memory = MemorySystem(self.config_dir / "memory.db")
        self.engine = None
        self.tools = ToolRegistry()
        
        # Feature components
        self.lsp_clients: Dict[str, LSPClient] = {}
        self.skill_registry = SkillRegistry()
        self.oauth_manager = OAuthManager()
        self.hosting_server = None
        self.automation_scheduler = None
        self.browser_engine = None
        self.form_manager = FormManager()
        self.context_manager = ContextManager()
        self.vault = SentienceVault()
        self.knowledge_graph = KnowledgeGraph()
        self.learning_system = LearningSystem()
        
        # UI
        self.main_window = None
        
    def initialize(self):
        """Initialize all components"""
        print("Initializing Sentience...")
        
        # Load config
        self.config.load()
        
        # Initialize engine with BYOK
        self.engine = SentienceEngine(
            provider=self.config.get("provider", "openai"),
            model=self.config.get("model", "gpt-4o"),
            api_key=self._get_api_key()
        )
        
        # Register tools
        self._register_tools()
        
        # Start automation scheduler
        self.automation_scheduler = AutomationScheduler()
        self.automation_scheduler.start()
        
        print("Sentience initialized!")
        
    def _get_api_key(self) -> str:
        """Get API key from config or environment"""
        provider = self.config.get("provider", "openai")
        
        # Check environment
        env_keys = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY"
        }
        
        env_key = os.environ.get(env_keys.get(provider, ""))
        if env_key:
            return env_key
            
        # Check config
        return self.config.get("api_key", "")
        
    def _register_tools(self):
        """Register all tools"""
        
        # File tools
        @self.tools.register("read_file")
        def read_file(path: str) -> str:
            """Read file content"""
            return Path(path).read_text()
            
        @self.tools.register("write_file")
        def write_file(path: str, content: str) -> bool:
            """Write content to file"""
            Path(path).write_text(content)
            return True
            
        @self.tools.register("list_dir")
        def list_dir(path: str) -> List[str]:
            """List directory contents"""
            return [f.name for f in Path(path).iterdir()]
            
        @self.tools.register("search_files")
        def search_files(pattern: str, path: str = ".") -> List[str]:
            """Search for files matching pattern"""
            import fnmatch
            results = []
            for f in Path(path).rglob("*"):
                if fnmatch.fnmatch(f.name, pattern):
                    results.append(str(f))
            return results
            
        # Code tools
        @self.tools.register("analyze_code")
        def analyze_code(code: str) -> Dict:
            """Analyze code quality"""
            skill = self.skill_registry.get("code-analyzer")
            if skill:
                return skill.execute(code=code)
            return {}
            
        @self.tools.register("generate_tests")
        def generate_tests(code: str) -> str:
            """Generate unit tests"""
            skill = self.skill_registry.get("test-generator")
            if skill:
                return skill.execute(code=code)
            return ""
            
        # Web tools
        @self.tools.register("browse")
        async def browse(url: str) -> Dict:
            """Browse URL"""
            if not self.browser_engine:
                self.browser_engine = BrowserEngine()
                await self.browser_engine.start()
            return await self.browser_engine.browse(url)
            
        @self.tools.register("search_web")
        def search_web(query: str) -> List[Dict]:
            """Search the web"""
            import requests
            # Using DuckDuckGo instant answer API
            resp = requests.get(f"https://api.duckduckgo.com/?q={query}&format=json")
            return resp.json().get("RelatedTopics", [])
            
        # Memory tools
        @self.tools.register("remember")
        def remember(key: str, value: str) -> bool:
            """Store in memory"""
            self.memory.set(key, value)
            return True
            
        @self.tools.register("recall")
        def recall(key: str) -> Optional[str]:
            """Recall from memory"""
            return self.memory.get(key)
            
        @self.tools.register("create_note")
        def create_note(title: str, content: str, tags: List[str] = None) -> Dict:
            """Create a note in vault"""
            note = self.vault.create_note(title, content, tags)
            return {"id": note.id, "title": note.title, "path": note.path}
            
        # Form tools
        @self.tools.register("fill_form")
        def fill_form(form_path: str, output_path: str, values: Dict) -> Dict:
            """Fill PDF/DOCX form"""
            return self.form_manager.fill_form(form_path, output_path, values)
            
        # Integration tools
        @self.tools.register("send_email")
        def send_email(to: str, subject: str, body: str) -> Dict:
            """Send email"""
            from src.integrations.oauth_manager import GmailClient
            client = GmailClient(self.oauth_manager)
            if self.oauth_manager.has_valid_token("google"):
                return client.send_email(to, subject, body)
            return {"error": "Gmail not connected. Run: sentience connect gmail"}
            
        @self.tools.register("search_notion")
        def search_notion(query: str) -> List[Dict]:
            """Search Notion"""
            from src.integrations.oauth_manager import NotionClient
            client = NotionClient(self.oauth_manager)
            if self.oauth_manager.has_valid_token("notion"):
                pages = client.list_pages()
                return [p for p in pages if query.lower() in p.get("title", "").lower()]
            return []
            
        # Automation tools
        @self.tools.register("schedule_task")
        def schedule_task(name: str, instruction: str, schedule: str) -> Dict:
            """Schedule a task"""
            # Parse schedule (simplified)
            trigger_config = {"hour": 9}  # Default 9am
            automation = self.automation_scheduler.create_automation(
                name=name,
                instruction=instruction,
                trigger_type="cron",
                trigger_config=trigger_config
            )
            return {"id": automation.id, "name": automation.name}
            
        @self.tools.register("list_automations")
        def list_automations() -> List[Dict]:
            """List all automations"""
            return [
                {"id": a.id, "name": a.name, "enabled": a.enabled}
                for a in self.automation_scheduler.db.list_automations()
            ]
            
        # Hosting tools
        @self.tools.register("create_site")
        def create_site(name: str, content: str) -> Dict:
            """Create a local website"""
            site_dir = self.config_dir / "sites" / name
            site_dir.mkdir(parents=True, exist_ok=True)
            
            (site_dir / "index.html").write_text(content)
            
            if not self.hosting_server:
                self.hosting_server = HostingServer(str(site_dir), port=3000)
                
            return {"url": f"http://localhost:3000/{name}", "path": str(site_dir)}
            
        # Shell tools
        @self.tools.register("run_command")
        def run_command(cmd: str) -> Dict:
            """Run shell command"""
            import subprocess
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
            
        print(f"Registered {len(self.tools.tools)} tools")
        
    def run_cli(self):
        """Run CLI interface"""
        print("\n" + "="*50)
        print("Sentience v3.0 - Local AI Computer")
        print("="*50)
        print("\nType your message. Commands: /tools, /help, /quit\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                    
                if user_input == "/quit":
                    print("Goodbye!")
                    break
                    
                elif user_input == "/tools":
                    print("\nAvailable tools:")
                    for name, tool in self.tools.tools.items():
                        print(f"  - {name}")
                    print()
                    
                elif user_input == "/help":
                    print("\nCommands:")
                    print("  /tools - List available tools")
                    print("  /help - Show this help")
                    print("  /quit - Exit Sentience")
                    print("\nJust type your message to interact with AI.")
                    
                else:
                    # Process with engine
                    response = self.engine.process(
                        user_input,
                        tools=self.tools,
                        memory=self.memory,
                        context=self.context_manager.get_context_window()
                    )
                    
                    print(f"\nSentience: {response}\n")
                    
                    # Log interaction
                    self.learning_system.log_interaction(
                        type="chat",
                        input=user_input,
                        output=response
                    )
                    
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
                
    def run_gui(self):
        """Run GUI interface"""
        from PySide6.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        self.main_window = MainWindow()
        self.main_window.show()
        sys.exit(app.exec())
        
    def cleanup(self):
        """Cleanup resources"""
        if self.automation_scheduler:
            self.automation_scheduler.stop()
            
        if self.browser_engine:
            asyncio.run(self.browser_engine.stop())
            
        for client in self.lsp_clients.values():
            client.stop()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sentience - Local AI Computer")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--gui", action="store_true", help="Run in GUI mode")
    parser.add_argument("--config", type=str, help="Config directory")
    parser.add_argument("--provider", type=str, help="LLM provider")
    parser.add_argument("--model", type=str, help="LLM model")
    
    args = parser.parse_args()
    
    app = SentienceApp(args.config)
    app.initialize()
    
    # Override config
    if args.provider:
        app.config.set("provider", args.provider)
    if args.model:
        app.config.set("model", args.model)
        
    try:
        if args.cli or not args.gui:
            app.run_cli()
        else:
            app.run_gui()
    finally:
        app.cleanup()


if __name__ == "__main__":
    main()
