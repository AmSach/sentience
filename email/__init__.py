"""Email integration - Gmail, SMTP, IMAP, auto-replies."""
import smtplib, imaplib, email, json, time, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

class EmailClient:
    def __init__(self, provider="gmail", smtp_host=None, smtp_port=587, imap_host=None):
        self.provider = provider
        self.smtp_host = smtp_host or self._smtp_host()
        self.smtp_port = smtp_port
        self.imap_host = imap_host or self._imap_host()
        self.username = None
        self.password = None
        self.smtp = None
        self.imap = None

    def _smtp_host(self): return {"gmail": "smtp.gmail.com", "outlook": "smtp-mail.outlook.com", "yahoo": "smtp.mail.yahoo.com"}.get(self.provider, "smtp.gmail.com")
    def _imap_host(self): return {"gmail": "imap.gmail.com", "outlook": "outlook.office365.com", "yahoo": "imap.mail.yahoo.com"}.get(self.provider, "imap.gmail.com")

    def login(self, username, password):
        self.username = username
        self.password = password

    def send(self, to, subject, body, cc=None, bcc=None, attachments=None):
        msg = MIMEMultipart()
        msg["From"] = self.username
        msg["To"] = to
        msg["Subject"] = subject
        if cc: msg["Cc"] = cc
        msg.attach(MIMEText(body, "plain"))
        if attachments:
            for f in attachments:
                with open(f, "rb") as a: p = MIMEBase(); p.set_payload(a.read()); encoders.encode_base64(p); p.add_header("Content-Disposition", f"attachment; filename={os.path.basename(f)}"); msg.attach(p)
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
                s.starttls()
                s.login(self.username, self.password)
                s.sendmail(self.username, [to], msg.as_string())
            return {"status": "sent", "to": to, "subject": subject}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def read_inbox(self, limit=20, unread_only=False):
        try:
            self.imap = imaplib.IMAP4_SSL(self.imap_host)
            self.imap.login(self.username, self.password)
            self.imap.select('INBOX' if not unread_only else 'INBOX.UNSEEN')
            _, msgs = self.imap.search(None, "ALL" if not unread_only else "UNSEEN")
            results = []
            for num in msgs[0].split()[-limit:]:
                _, data = self.imap.fetch(num, "(RFC822)")
                e = email.message_from_bytes(data[0][1])
                results.append({"from": e["From"], "subject": e["Subject"], "date": e["Date"], "id": num.decode()})
            self.imap.logout()
            return {"emails": results}
        except Exception as e:
            return {"error": str(e)}

    def search(self, query, folder="INBOX"):
        try:
            self.imap = imaplib.IMAP4_SSL(self.imap_host)
            self.imap.login(self.username, self.password)
            self.imap.select(folder)
            _, msgs = self.imap.search(None, f'SUBJECT "{query}"')
            results = []
            for num in msgs[0].split():
                _, data = self.imap.fetch(num, "(RFC822)")
                e = email.message_from_bytes(data[0][1])
                results.append({"from": e["From"], "subject": e["Subject"], "date": e["Date"], "id": num.decode()})
            self.imap.logout()
            return {"emails": results}
        except Exception as e:
            return {"error": str(e)}

    def auto_reply(self, rule, smtp_creds):
        """Listen for matching emails and send auto-replies."""
        import threading
        def _listen():
            while True:
                matches = self.search(rule["match_subject"] if rule.get("match_subject") else "ALL")
                for m in matches.get("emails", [])[:rule.get("max_replies", 5)]:
                    self.send(to=m["from"], subject=rule.get("reply_subject", "Re: "+m["subject"]), body=rule.get("reply_body", "Thank you for your email."), smtp_creds=smtp_creds)
                time.sleep(rule.get("check_interval", 300))
        threading.Thread(target=_listen, daemon=True).start()
        return {"status": "auto_reply_started", "rule": rule}

    def execute_tool(self, tool_name, args, ctx):
        return {"tool": tool_name, "result": getattr(self, tool_name, lambda a: {"error":"not found"})(args)}
__all__ = ["EmailClient"]
