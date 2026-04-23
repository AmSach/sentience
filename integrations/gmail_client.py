"""Gmail Integration - emails, search, send, labels."""
import os, json, base64
# IntegrationRegistry

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

class GmailIntegration:
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]
    
    def __init__(self, config):
        self.config = config
        self.service = None
    
    def connect(self) -> bool:
        if not GOOGLE_AVAILABLE:
            return False
        creds = None
        token_path = f"/tmp/.sentience/gmail_token_{self.config.user_id}.json"
        try:
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            if not creds or not creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(self.config.secrets["credentials_file"], self.SCOPES)
                creds = flow.run_local_server(port=0)
                os.makedirs(os.path.dirname(token_path), exist_ok=True)
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
            self.service = build("gmail", "v1", credentials=creds)
            return True
        except Exception:
            return False
    
    def list_emails(self, query: str = "", max_results: int = 20):
        if not self.service:
            return {"error": "Not connected"}
        results = self.service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])
        emails = []
        for msg in messages:
            email = self.service.users().messages().get(userId="me", id=msg["id"], format="metadata", metadataHeaders=["Subject", "From", "Date"]).execute()
            headers = {h["name"]: h["value"] for h in email["payload"]["headers"]}
            emails.append({"id": msg["id"], "subject": headers.get("Subject", ""), "from": headers.get("From", ""), "date": headers.get("Date", "")})
        return {"emails": emails}
    
    def send_email(self, to: str, subject: str, body: str):
        if not self.service:
            return {"error": "Not connected"}
        from email.mime.text import MIMEText
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"sent": True}
