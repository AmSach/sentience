"""Automation system - scheduled tasks, triggers, multi-step workflows."""
import os, json, time, threading, re, hashlib
from datetime import datetime

class SentienceAutomation:
    def __init__(self):
        self.tasks = []
        self.history = []
        self.running = False
        self.thread = None

    def add_task(self, name, instruction, rrule, enabled=True, delivery="chat"):
        task = {"id": hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12], "name": name, "instruction": instruction, "rrule": rrule, "enabled": enabled, "delivery": delivery, "last_run": None, "next_run": self._calc_next(rrule), "created_at": time.time(), "run_count": 0}
        self.tasks.append(task)
        return task["id"]

    def _calc_next(self, rrule):
        now = time.time()
        try:
            parts = rrule.upper().split(";")
            freq = parts[0].split("=")[-1] if "=" in parts[0] else parts[0]
            interval = int([p for p in parts if "INTERVAL" in p][0].split("=")[-1]) if any("INTERVAL" in p for p in parts) else 1
            ms = {"MINUTELY": 60, "HOURLY": 3600, "DAILY": 86400, "WEEKLY": 604800, "MONTHLY": 2592000}.get(freq, 86400)
            return now + ms * interval
        except: return now + 86400

    def remove_task(self, task_id): self.tasks = [t for t in self.tasks if t["id"] != task_id]

    def list_tasks(self):
        return [{"id": t["id"], "name": t["name"], "enabled": t["enabled"], "rrule": t["rrule"], "next_run": t["next_run"], "last_run": t["last_run"]} for t in self.tasks]

    def enable_task(self, task_id, enabled=True):
        for t in self.tasks:
            if t["id"] == task_id: t["enabled"] = enabled

    def start(self, agent_callback):
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, args=(agent_callback,), daemon=True)
        self.thread.start()

    def _run_loop(self, agent_callback):
        while self.running:
            now = time.time()
            for t in self.tasks:
                if t["enabled"] and t["next_run"] and now >= t["next_run"]:
                    try:
                        result = agent_callback(t["instruction"])
                        t["last_run"] = now
                        t["next_run"] = self._calc_next(t["rrule"])
                        t["run_count"] = t.get("run_count", 0) + 1
                        self.history.append({"task_id": t["id"], "name": t["name"], "executed_at": now, "result": "ok"})
                    except Exception as e:
                        self.history.append({"task_id": t["id"], "name": t["name"], "executed_at": now, "result": str(e)})
            time.sleep(30)

    def stop(self): self.running = False

    def export_tasks(self):
        return json.dumps([{"name": t["name"], "instruction": t["instruction"], "rrule": t["rrule"]} for t in self.tasks], indent=2)

    def import_tasks(self, json_str):
        try:
            tasks = json.loads(json_str)
            for t in tasks: self.add_task(t["name"], t["instruction"], t["rrule"])
            return {"imported": len(tasks)}
        except Exception as e: return {"error": str(e)}

_automation = SentienceAutomation()
def get_automation(): return _automation
