#!/usr/bin/env python3
"""Email Integration Module - IMAP/SMTP email handling"""
import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import policy
from email.parser import BytesParser
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
from datetime import datetime

class EmailClient:
    """Email client with IMAP read and SMTP send capabilities"""
    
    def __init__(self, imap_server: str, smtp_server: str, email_address: str, 
                 password: str, imap_port: int = 993, smtp_port: int = 587):
        self.imap_server = imap_server
        self.smtp_server = smtp_server
        self.email_address = email_address
        self.password = password
        self.imap_port = imap_port
        self.smtp_port = smtp_port
        self._imap = None
        self._smtp = None
    
    def connect_imap(self) -> Dict:
        """Connect to IMAP server"""
        try:
            self._imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self._imap.login(self.email_address, self.password)
            return {"success": True, "message": "IMAP connected"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def connect_smtp(self) -> Dict:
        """Connect to SMTP server"""
        try:
            self._smtp = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self._smtp.starttls()
            self._smtp.login(self.email_address, self.password)
            return {"success": True, "message": "SMTP connected"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def disconnect(self):
        """Disconnect from servers"""
        try:
            if self._imap:
                self._imap.close()
                self._imap.logout()
        except:
            pass
        try:
            if self._smtp:
                self._smtp.quit()
        except:
            pass
    
    def list_folders(self) -> Dict:
        """List email folders"""
        if not self._imap:
            return {"success": False, "error": "Not connected to IMAP"}
        
        try:
            status, folders = self._imap.list()
            if status != "OK":
                return {"success": False, "error": "Failed to list folders"}
            
            result = []
            for folder in folders:
                folder_str = folder.decode()
                result.append(folder_str)
            return {"success": True, "folders": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_unread(self, folder: str = "INBOX", limit: int = 20) -> Dict:
        """Get unread emails from folder"""
        if not self._imap:
            return {"success": False, "error": "Not connected to IMAP"}
        
        try:
            status, _ = self._imap.select(folder)
            if status != "OK":
                return {"success": False, "error": f"Cannot select folder {folder}"}
            
            # Search for unread messages
            status, message_ids = self._imap.search(None, "UNSEEN")
            if status != "OK":
                return {"success": False, "error": "Search failed"}
            
            ids = message_ids[0].split()
            emails = []
            
            for msg_id in ids[:limit]:
                status, msg_data = self._imap.fetch(msg_id, "(RFC822)")
                if status == "OK":
                    raw_email = msg_data[0][1]
                    msg = BytesParser(policy=policy.default).parsebytes(raw_email)
                    
                    emails.append({
                        "id": msg_id.decode(),
                        "from": msg.get("From", ""),
                        "to": msg.get("To", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""),
                        "body": self._get_body(msg)[:2000]  # Limit body size
                    })
            
            return {"success": True, "emails": emails, "count": len(emails)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_email(self, msg_id: int, folder: str = "INBOX") -> Dict:
        """Get specific email by ID"""
        if not self._imap:
            return {"success": False, "error": "Not connected to IMAP"}
        
        try:
            status, _ = self._imap.select(folder)
            if status != "OK":
                return {"success": False, "error": f"Cannot select folder {folder}"}
            
            status, msg_data = self._imap.fetch(str(msg_id), "(RFC822)")
            if status != "OK":
                return {"success": False, "error": "Failed to fetch email"}
            
            raw_email = msg_data[0][1]
            msg = BytesParser(policy=policy.default).parsebytes(raw_email)
            
            return {
                "success": True,
                "email": {
                    "id": msg_id,
                    "from": msg.get("From", ""),
                    "to": msg.get("To", ""),
                    "cc": msg.get("Cc", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "body": self._get_body(msg),
                    "attachments": self._get_attachments(msg)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_body(self, msg) -> str:
        """Extract body text from email message"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode()
                    except:
                        body = str(part.get_payload())
                    break
                elif content_type == "text/html" and not body:
                    try:
                        body = part.get_payload(decode=True).decode()
                    except:
                        body = str(part.get_payload())
        else:
            try:
                body = msg.get_payload(decode=True).decode()
            except:
                body = str(msg.get_payload())
        return body
    
    def _get_attachments(self, msg) -> List[Dict]:
        """Extract attachment info from email"""
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    attachments.append({
                        "filename": part.get_filename(),
                        "content_type": part.get_content_type(),
                        "size": len(part.get_payload(decode=True) or b"")
                    })
        return attachments
    
    def send_email(self, to: str, subject: str, body: str, 
                   cc: str = None, bcc: str = None,
                   html: bool = False, attachments: List[str] = None) -> Dict:
        """Send email via SMTP"""
        try:
            if not self._smtp:
                self.connect_smtp()
            
            if html:
                msg = MIMEMultipart("alternative")
            else:
                msg = MIMEMultipart()
            
            msg["From"] = self.email_address
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc
            if bcc:
                msg["Bcc"] = bcc
            
            if html:
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))
            
            # Add attachments if provided
            if attachments:
                for filepath in attachments:
                    path = Path(filepath)
                    if path.exists():
                        with open(path, "rb") as f:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(f.read())
                        part.add_header("Content-Disposition", 
                                       f"attachment; filename={path.name}")
                        msg.attach(part)
            
            recipients = [to]
            if cc:
                recipients.append(cc)
            if bcc:
                recipients.append(bcc)
            
            self._smtp.sendmail(self.email_address, recipients, msg.as_string())
            
            return {"success": True, "message": f"Email sent to {to}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def search(self, criteria: str, folder: str = "INBOX", limit: int = 50) -> Dict:
        """Search emails with criteria"""
        if not self._imap:
            return {"success": False, "error": "Not connected to IMAP"}
        
        try:
            status, _ = self._imap.select(folder)
            if status != "OK":
                return {"success": False, "error": f"Cannot select folder {folder}"}
            
            status, message_ids = self._imap.search(None, criteria)
            if status != "OK":
                return {"success": False, "error": "Search failed"}
            
            ids = message_ids[0].split()
            emails = []
            
            for msg_id in ids[:limit]:
                status, msg_data = self._imap.fetch(msg_id, "(RFC822)")
                if status == "OK":
                    raw_email = msg_data[0][1]
                    msg = BytesParser(policy=policy.default).parsebytes(raw_email)
                    
                    emails.append({
                        "id": msg_id.decode(),
                        "from": msg.get("From", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", "")
                    })
            
            return {"success": True, "emails": emails, "count": len(emails)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_email(self, msg_id: int, folder: str = "INBOX") -> Dict:
        """Delete email by ID"""
        if not self._imap:
            return {"success": False, "error": "Not connected to IMAP"}
        
        try:
            status, _ = self._imap.select(folder)
            if status != "OK":
                return {"success": False, "error": f"Cannot select folder {folder}"}
            
            self._imap.store(str(msg_id), "+FLAGS", "\\Deleted")
            self._imap.expunge()
            
            return {"success": True, "message": f"Email {msg_id} deleted"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def mark_read(self, msg_id: int, folder: str = "INBOX") -> Dict:
        """Mark email as read"""
        if not self._imap:
            return {"success": False, "error": "Not connected to IMAP"}
        
        try:
            status, _ = self._imap.select(folder)
            if status != "OK":
                return {"success": False, "error": f"Cannot select folder {folder}"}
            
            self._imap.store(str(msg_id), "+FLAGS", "\\Seen")
            
            return {"success": True, "message": f"Email {msg_id} marked as read"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Common email providers
EMAIL_PROVIDERS = {
    "gmail": {
        "imap": "imap.gmail.com",
        "smtp": "smtp.gmail.com",
        "imap_port": 993,
        "smtp_port": 587
    },
    "outlook": {
        "imap": "outlook.office365.com",
        "smtp": "smtp.office365.com",
        "imap_port": 993,
        "smtp_port": 587
    },
    "yahoo": {
        "imap": "imap.mail.yahoo.com",
        "smtp": "smtp.mail.yahoo.com",
        "imap_port": 993,
        "smtp_port": 587
    }
}

# Tool definitions for AI
EMAIL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "email_get_unread",
            "description": "Get unread emails from inbox",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Folder name (default: INBOX)"},
                    "limit": {"type": "integer", "description": "Max emails to fetch"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_send",
            "description": "Send an email",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"}
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_search",
            "description": "Search emails by criteria",
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {"type": "string", "description": "IMAP search criteria (e.g., 'FROM \"john\"')"},
                    "folder": {"type": "string", "description": "Folder to search in"}
                },
                "required": ["criteria"]
            }
        }
    }
]

# Singleton instance
_email_client: Optional[EmailClient] = None

def init_email(provider: str, email_address: str, password: str) -> Dict:
    """Initialize email client with provider settings"""
    global _email_client
    
    settings = EMAIL_PROVIDERS.get(provider)
    if not settings:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    
    _email_client = EmailClient(
        imap_server=settings["imap"],
        smtp_server=settings["smtp"],
        email_address=email_address,
        password=password,
        imap_port=settings["imap_port"],
        smtp_port=settings["smtp_port"]
    )
    
    # Connect
    imap_result = _email_client.connect_imap()
    smtp_result = _email_client.connect_smtp()
    
    return {
        "success": imap_result["success"] and smtp_result["success"],
        "imap": imap_result,
        "smtp": smtp_result
    }

def execute_email_tool(name: str, args: Dict) -> Dict:
    """Execute email tool by name"""
    global _email_client
    
    if not _email_client:
        return {"success": False, "error": "Email not initialized. Run init_email first."}
    
    if name == "email_get_unread":
        return _email_client.get_unread(
            folder=args.get("folder", "INBOX"),
            limit=args.get("limit", 20)
        )
    elif name == "email_send":
        return _email_client.send_email(
            to=args.get("to", ""),
            subject=args.get("subject", ""),
            body=args.get("body", "")
        )
    elif name == "email_search":
        return _email_client.search(
            criteria=args.get("criteria", "ALL"),
            folder=args.get("folder", "INBOX")
        )
    else:
        return {"success": False, "error": f"Unknown email tool: {name}"}
