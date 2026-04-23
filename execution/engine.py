"""Execution engine - background task runner, multi-step workflows, task queue."""
import os, sys, json, time, threading, queue, traceback, uuid
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import sqlite3

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING = "waiting"

class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

@dataclass
class TaskResult:
    task_id: str
    status: str
    result: Any
    error: Optional[str]
    started_at: float
    completed_at: Optional[float]
    output_files: List[str]
    logs: List[str]

class Task:
    def __init__(self, task_id: str, instruction: str, priority: int = 1, context: Dict = None):
        self.id = task_id
        self.instruction = instruction
        self.priority = priority
        self.context = context or {}
        self.status = TaskStatus.PENDING
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.result: Any = None
        self.error: Optional[str] = None
        self.output_files: List[str] = []
        self.logs: List[str] = []
        self.steps: List[Dict] = []
        self.retry_count = 0
        self.max_retries = 2

class TaskQueue:
    """Persistent task queue with SQLite backing."""
    
    def __init__(self, db_path: str = "sentience_tasks.db"):
        self.db_path = db_path
        self._init_db()
        self.queue = queue.PriorityQueue()
        self.workers: List[threading.Thread] = []
        self.running = True
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                instruction TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                context TEXT,
                result TEXT,
                error TEXT,
                created_at REAL,
                started_at REAL,
                completed_at REAL,
                retry_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
        conn.commit()
        conn.close()
    
    def add_task(self, task: Task) -> str:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO tasks (id, instruction, priority, status, context, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task.id, task.instruction, task.priority, task.status.value, json.dumps(task.context), task.created_at))
        conn.commit()
        conn.close()
        self.queue.put((task.priority, -time.time(), task.id))
        return task.id
    
    def get_task(self) -> Optional[str]:
        try:
            priority, neg_time, task_id = self.queue.get_nowait()
            return task_id
        except:
            return None
    
    def update_task(self, task_id: str, **kwargs):
        conn = sqlite3.connect(self.db_path)
        for key, value in kwargs.items():
            if key == "context":
                value = json.dumps(value)
            col = key
            conn.execute(f"UPDATE tasks SET {col} = ? WHERE id = ?", (value, task_id))
        conn.commit()
        conn.close()
    
    def list_tasks(self, status: Optional[str] = None) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        if status:
            rows = conn.execute("SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at ASC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY priority DESC, created_at ASC").fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM tasks LIMIT 0").description]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]

class ExecutionEngine:
    """Main execution engine - runs tasks, manages workflows, background processing."""
    
    def __init__(self, agent, workspace: str = "."):
        self.agent = agent
        self.workspace = workspace
        self.task_queue = TaskQueue(os.path.join(workspace, "sentience_tasks.db"))
        self.background_runner = BackgroundRunner(self)
        self.workflows: Dict[str, Callable] = {}
        self._register_builtin_workflows()
    
    def _register_builtin_workflows(self):
        """Register built-in multi-step workflows."""
        self.workflows["research_report"] = self._wf_research_report
        self.workflows["form_fill"] = self._wf_form_fill
        self.workflows["code_review"] = self._wf_code_review
        self.workflows["data_analysis"] = self._wf_data_analysis
        self.workflows["web_scrape_summarize"] = self._wf_web_scrape_summarize
        self.workflows["document_processor"] = self._wf_document_processor
        self.workflows["backup_sync"] = self._wf_backup_sync
        self.workflows["email_campaign"] = self._wf_email_campaign
    
    def _wf_research_report(self, context: Dict) -> TaskResult:
        """Workflow: Research a topic and generate a report."""
        topic = context.get("topic", "")
        depth = context.get("depth", 3)
        from .research.engine import ResearchEngine
        engine = ResearchEngine()
        results = engine.deep_research(topic, depth)
        report = self.agent.process(f"Write a comprehensive report on: {topic}\n\nResearch findings: {results}")
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"report": report, "research": results}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_form_fill(self, context: Dict) -> TaskResult:
        """Workflow: Auto-fill a form using reference documents."""
        from ..forms.engine import AutoFillEngine, create_form_from_template
        form = create_form_from_template(context.get("form_type", "government_form"))
        engine = AutoFillEngine(self.agent)
        profile = context.get("profile", {})
        docs = context.get("reference_docs", [])
        filled = engine.fill_form(form, docs, profile)
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"form": asdict(filled)}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_code_review(self, context: Dict) -> TaskResult:
        """Workflow: Review code, run tests, suggest fixes."""
        files = context.get("files", [])
        results = []
        for f in files:
            review = self.agent.process(f"Review this code and suggest improvements:\n\n{open(f).read()}")
            results.append({"file": f, "review": review})
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"reviews": results}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_data_analysis(self, context: Dict) -> TaskResult:
        """Workflow: Analyze data files and generate insights."""
        from ..analysis.engine import SentienceAnalysis
        analyzer = SentienceAnalysis()
        files = context.get("data_files", [])
        results = []
        for f in files:
            text = open(f).read()
            analysis = analyzer.analyze_document(text, "full")
            results.append({"file": f, "analysis": analysis})
        summary = self.agent.process(f"Summarize these data analysis results:\n\n{results}")
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"analyses": results, "summary": summary}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_web_scrape_summarize(self, context: Dict) -> TaskResult:
        """Workflow: Scrape URLs and summarize content."""
        from ..research.engine import ResearchEngine
        engine = ResearchEngine()
        urls = context.get("urls", [])
        results = []
        for url in urls:
            page = engine.web.fetch_page(url)
            if "content" in page:
                summary = self.agent.process(f"Summarize this article:\n\n{page['content'][:3000]}")
                results.append({"url": url, "title": page.get("title",""), "summary": summary})
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"articles": results}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_document_processor(self, context: Dict) -> TaskResult:
        """Workflow: Process documents - convert, extract, summarize."""
        from ..analysis.engine import SentienceAnalysis
        from ..multimodal.engine import MultimodalEngine
        analyzer = SentienceAnalysis()
        multimodal = MultimodalEngine()
        files = context.get("files", [])
        results = []
        for f in files:
            if f.endswith(".pdf"):
                text = multimodal.pdf_to_text(f)
            else:
                text = open(f).read()
            analysis = analyzer.analyze_document(text, "full")
            summary = analyzer.generate_summary(text, 500)
            results.append({"file": f, "analysis": analysis, "summary": summary})
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"processed": results}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_backup_sync(self, context: Dict) -> TaskResult:
        """Workflow: Backup files to cloud storage."""
        from ..cloud import CloudManager
        cloud = CloudManager()
        files = context.get("files", [])
        dest = context.get("destination", "dropbox")
        results = cloud.upload_files(files, dest)
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"uploaded": results}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def _wf_email_campaign(self, context: Dict) -> TaskResult:
        """Workflow: Send personalized emails to a list."""
        from ..email import EmailManager
        emails = context.get("recipients", [])
        template = context.get("template", "")
        customizations = context.get("customizations", {})
        manager = EmailManager()
        results = []
        for recipient in emails:
            merged = template
            for key, val in {**customizations, **recipient}.items():
                merged = merged.replace(f"{{{key}}}", str(val))
            result = manager.send(recipient.get("email"), context.get("subject", ""), merged)
            results.append({"recipient": recipient.get("email"), "status": result})
        return TaskResult(task_id=context.get("task_id",""), status="completed", result={"emails": results}, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
    
    def submit_task(self, instruction: str, priority: int = 1, workflow: Optional[str] = None, context: Dict = None) -> str:
        """Submit a task for execution."""
        task_id = str(uuid.uuid4())
        task = Task(task_id, instruction, priority, context or {})
        task.context["workflow"] = workflow
        return self.task_queue.add_task(task)
    
    def submit_background(self, instruction: str, context: Dict = None) -> str:
        """Submit a task for background execution."""
        return self.submit_task(instruction, priority=1, context=context)
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        tasks = self.task_queue.list_tasks()
        for t in tasks:
            if t["id"] == task_id:
                return t
        return None
    
    def list_tasks(self, status: Optional[str] = None) -> List[Dict]:
        return self.task_queue.list_tasks(status)
    
    def cancel_task(self, task_id: str) -> bool:
        self.task_queue.update_task(task_id, status="cancelled")
        return True

class BackgroundRunner:
    """Background worker that processes tasks."""
    
    def __init__(self, engine: ExecutionEngine):
        self.engine = engine
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.running = True
        self.thread.start()
    
    def _run(self):
        while self.running:
            task_id = self.engine.task_queue.get_task()
            if task_id:
                self._execute_task(task_id)
            time.sleep(1)
    
    def _execute_task(self, task_id: str):
        self.engine.task_queue.update_task(task_id, status="running", started_at=time.time())
        tasks = self.engine.task_queue.list_tasks()
        task_data = next((t for t in tasks if t["id"] == task_id), None)
        if not task_data:
            return
        instruction = task_data["instruction"]
        context = json.loads(task_data.get("context", "{}"))
        workflow = context.get("workflow")
        try:
            if workflow and workflow in self.engine.workflows:
                result = self.engine.workflows[workflow]({**context, "task_id": task_id})
            else:
                result_text = self.engine.agent.process(instruction)
                result = TaskResult(task_id=task_id, status="completed", result=result_text, error=None, started_at=time.time(), completed_at=time.time(), output_files=[], logs=[])
            self.engine.task_queue.update_task(task_id, status="completed", completed_at=time.time(), result=json.dumps(asdict(result)) if hasattr(result, "__dict__") else str(result))
        except Exception as e:
            self.engine.task_queue.update_task(task_id, status="failed", completed_at=time.time(), error=str(e))
