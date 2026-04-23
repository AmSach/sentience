"""Linear Integration - issues, projects, teams."""
import os, json

try:
    from linear_api import LinearClient
    LINEAR_AVAILABLE = True
except ImportError:
    LINEAR_AVAILABLE = False

class LinearIntegration:
    def __init__(self, config):
        self.config = config
        self.client = None
    
    def connect(self) -> bool:
        if not LINEAR_AVAILABLE:
            return False
        try:
            self.client = LinearClient(token=self.config.secrets.get("api_key"))
            return True
        except Exception:
            return False
    
    def list_issues(self, team_id: str = None):
        if not self.client:
            return {"error": "Not connected"}
        filters = {"state": {"notEq": "completed"}}
        issues = self.client.issues(filter=filters)
        return {"issues": list(issues)[:20]}
    
    def create_issue(self, title: str, description: str = "", team_id: str = None):
        if not self.client:
            return {"error": "Not connected"}
        issue = self.client.create_issue(title=title, description=description, team_id=team_id)
        return {"created": issue.id}
