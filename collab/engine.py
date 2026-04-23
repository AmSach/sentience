"""Collaboration engine - shared workspaces, team support, file sharing, real-time sync."""
import os, json, time, uuid, sqlite3
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class ShareConfig:
    share_id: str
    item_type: str  # file, folder, workspace
    item_path: str
    shared_with: List[str]  # user IDs or emails
    permissions: Dict[str, str]  # user -> read/write/admin
    expires_at: Optional[float]
    created_at: float
    created_by: str

class FileShare:
    def __init__(self, config: ShareConfig):
        self.config = config
        self.access_log: List[Dict] = []
    
    def can_access(self, user_id: str) -> bool:
        if self.config.expires_at and time.time() > self.config.expires_at:
            return False
        return user_id in self.config.shared_with
    
    def get_permission(self, user_id: str) -> str:
        return self.config.permissions.get(user_id, "none")
    
    def log_access(self, user_id: str, action: str):
        self.access_log.append({"user": user_id, "action": action, "at": time.time()})

class CollabRoom:
    """A shared workspace room for collaboration."""
    def __init__(self, room_id: str, name: str, owner: str):
        self.room_id = room_id
        self.name = name
        self.owner = owner
        self.members: Dict[str, Dict] = {}
        self.messages: List[Dict] = []
        self.files: List[Dict] = []
        self.tasks: List[Dict] = []
        self.created_at = time.time()
    
    def add_member(self, user_id: str, role: str = "member"):
        self.members[user_id] = {"role": role, "joined_at": time.time()}
    
    def remove_member(self, user_id: str):
        self.members.pop(user_id, None)
    
    def add_message(self, user_id: str, text: str, attachments: List[str] = None):
        msg = {"id": str(uuid.uuid4()), "user": user_id, "text": text, "attachments": attachments or [], "at": time.time()}
        self.messages.append(msg)
        return msg
    
    def add_task(self, title: str, assigned_to: str, created_by: str, due: float = None):
        task = {"id": str(uuid.uuid4()), "title": title, "assigned_to": assigned_to, "created_by": created_by, "status": "pending", "due": due, "created_at": time.time()}
        self.tasks.append(task)
        return task

class CollabManager:
    """Manage collaboration rooms, sharing, and team workspaces."""
    def __init__(self, db_path: str = "sentience_collab.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.rooms: Dict[str, CollabRoom] = {}
        self.shares: Dict[str, FileShare] = {}
        self._init()
    
    def _init(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS collab_rooms (
                room_id TEXT PRIMARY KEY, name TEXT, owner TEXT, created_at REAL,
                members TEXT, messages TEXT, files TEXT, tasks TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS file_shares (
                share_id TEXT PRIMARY KEY, item_type TEXT, item_path TEXT,
                shared_with TEXT, permissions TEXT, expires_at REAL,
                created_at REAL, created_by TEXT
            )
        """)
        self.conn.commit()
    
    def create_room(self, name: str, owner: str) -> CollabRoom:
        room = CollabRoom(str(uuid.uuid4()), name, owner)
        room.add_member(owner, "admin")
        self.rooms[room.room_id] = room
        self._save_room(room)
        return room
    
    def get_room(self, room_id: str) -> Optional[CollabRoom]:
        if room_id in self.rooms:
            return self.rooms[room_id]
        row = self.conn.execute("SELECT * FROM collab_rooms WHERE room_id = ?", (room_id,)).fetchone()
        if row:
            room = CollabRoom(row["room_id"], row["name"], row["owner"])
            room.members = json.loads(row["members"])
            room.messages = json.loads(row["messages"])
            room.files = json.loads(row["files"])
            room.tasks = json.loads(row["tasks"])
            self.rooms[room_id] = room
            return room
        return None
    
    def _save_room(self, room: CollabRoom):
        self.conn.execute("""
            INSERT OR REPLACE INTO collab_rooms 
            (room_id, name, owner, created_at, members, messages, files, tasks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (room.room_id, room.name, room.owner, room.created_at,
              json.dumps(room.members), json.dumps(room.messages),
              json.dumps(room.files), json.dumps(room.tasks)))
        self.conn.commit()
    
    def share_file(self, path: str, shared_with: List[str], permissions: Dict[str, str], shared_by: str, expires_hours: int = None) -> str:
        share_id = str(uuid.uuid4())
        config = ShareConfig(share_id, "file", path, shared_with, permissions, time.time() + expires_hours*3600 if expires_hours else None, time.time(), shared_by)
        share = FileShare(config)
        self.shares[share_id] = share
        self.conn.execute("""
            INSERT INTO file_shares (share_id, item_type, item_path, shared_with, permissions, expires_at, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (share_id, "file", path, json.dumps(shared_with), json.dumps(permissions), config.expires_at, config.created_at, shared_by))
        self.conn.commit()
        return share_id
    
    def get_share(self, share_id: str) -> Optional[FileShare]:
        if share_id in self.shares:
            return self.shares[share_id]
        row = self.conn.execute("SELECT * FROM file_shares WHERE share_id = ?", (share_id,)).fetchone()
        if row:
            config = ShareConfig(
                row["share_id"], row["item_type"], row["item_path"],
                json.loads(row["shared_with"]), json.loads(row["permissions"]),
                row["expires_at"], row["created_at"], row["created_by"]
            )
            self.shares[share_id] = FileShare(config)
            return self.shares[share_id]
        return None
    
    def list_user_rooms(self, user_id: str) -> List[CollabRoom]:
        rooms = []
        for room in self.rooms.values():
            if user_id in room.members:
                rooms.append(room)
        return rooms
