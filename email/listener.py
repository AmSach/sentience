"""Email listener - IMAP polling, auto-replies, email-to-task."""
import imaplib, smtplib, email as em, time, json, threading, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailListener:
    def __init__(self, smtp_host="smtp.gmail.com", imap_host="imap.gmail.com", port=993):
        self.smtp_host = smtp_host
        self.imap_host = imap_host
        self.port = port
        self.username = None
        self.password = None
        self.running = False
        self.thread = None
        self.handlers = []
        self.processed_ids = set()
        self.rules = []

    def login(self, username, password):
        self.username = username
        self.password = password

    def add_rule(self, from_address=None, subject_contains=None, body_contains=None, action="forward", action_data=None):
        self.rules.append({"from": from_address, "subject": subject_contains, "body": body_contains, "action": action, "data": action_data})

    def add_handler(self, handler_fn):
        self.handlers.append(handler_fn)

    def start(self, poll_interval=60):
        self.poll_interval = poll_interval
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def _poll_loop(self):
        while self.running:
            try:
                mail = imaplib.IMAP4_SSL(self.imap_host, self.port)
                mail.login(self.username, self.password)
                mail.select("INBOX")
                _, msgs = mail.search(None, "UNSEEN")
                for num in msgs[0].split():
                    try:
                        _, data = mail.fetch(num, "(RFC822)")
                        msg = em.message_from_bytes(data[0][1])
                        msg_id = msg.get("Message-ID", num.decode())
                        if msg_id not in self.processed_ids:
                            self.processed_ids.add(msg_id)
                            self._process(msg)
                    except: pass
                mail.logout()
            except Exception as e:
                print(f"Email poll error: {e}")
            time.sleep(self.poll_interval)

    def _process(self, msg):
        sender = em.utils.parseaddr(msg.get("From", ""))[1]
        subject = msg.get("Subject", "")
        body = self._get_body(msg)
        for rule in self.rules:
            match = True
            if rule.get("from") and rule["from"] not in sender: match = False
            if rule.get("subject") and rule["subject"] not in subject: match = False
            if rule.get("body") and rule["body"] not in body: match = False
            if match:
                if rule["action"] == "reply":
                    self._send_reply(sender, rule["data"]["message"], msg)
                elif rule["action"] == "forward":
                    pass
                elif rule["action"] == "task":
                    pass
        for handler in self.handlers:
            try: handler(sender, subject, body, msg)
            except: pass

    def _get_body(self, msg):
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try: return part.get_payload(decode=True).decode()
                except: pass
        return ""

    def _send_reply(self, to, message, original):
        msg = MIMEMultipart()
        msg["To"] = to
        msg["From"] = self.username
        msg["Subject"] = f"Re: {original.get('Subject', '')}"
        msg.attach(MIMEText(message, "plain"))
        s = smtplib.SMTP(self.smtp_host, 587)
        s.ehlo()
        s.starttls()
        s.login(self.username, self.password)
        s.sendmail(self.username, [to], msg.as_bytes())
        s.quit()

    def stop(self): self.running = False

    def fetch_recent(self, limit=20):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_host, self.port)
            mail.login(self.username, self.password)
            mail.select("INBOX")
            _, msgs = mail.search(None, "ALL")
            results = []
            for num in msgs[0].split()[-limit:]:
                _, data = mail.fetch(num, "(RFC822)")
                msg = em.message_from_bytes(data[0][1])
                sender = em.utils.parseaddr(msg.get("From", ""))[1]
                subject = msg.get("Subject", "")
                date = msg.get("Date", "")
                results.append({"from": sender, "subject": subject, "date": date, "snippet": self._get_body(msg)[:200]})
            mail.logout()
            return results
        except Exception as e:
            return [{"error": str(e)}]

    def send_email(self, to, subject, body, cc=None, attachments=None):
        msg = MIMEMultipart()
        msg["To"] = to
        msg["From"] = self.username
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        if attachments:
            for path in attachments if isinstance(attachments, list) else [attachments]:
                with open(path, "rb") as f:
                    part = MIMEBase()
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(path)}")
                    msg.attach(part)
        s = smtplib.SMTP(self.smtp_host, 587)
        s.ehlo()
        s.starttls()
        s.login(self.username, self.password)
        s.sendmail(self.username, [to], msg.as_bytes())
        s.quit()
        return {"sent": True, "to": to}

_listener = EmailListener()

def get_listener(): return _listener

def configure_gmail(username, password, poll_interval=60):
    _listener.login(username, password)
    _listener.start(poll_interval)
    return {"status": "listening", "poll_interval": poll_interval}
