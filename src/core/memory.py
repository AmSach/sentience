#!/usr/bin/env python3
"""Memory System"""
import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, Optional
import lz4.frame

class MemorySystem:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value BLOB)")
        conn.commit()
        conn.close()
        
    def set(self, key: str, value: Any):
        """Store value (compressed)"""
        data = lz4.frame.compress(json.dumps(value).encode())
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO memory VALUES (?, ?)", (key, data))
        conn.commit()
        conn.close()
        
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value FROM memory WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(lz4.frame.decompress(row[0]).decode())
        return None
        
    def delete(self, key: str):
        """Delete key"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM memory WHERE key = ?", (key,))
        conn.commit()
        conn.close()
        
    def list_keys(self) -> list:
        """List all keys"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT key FROM memory")
        keys = [row[0] for row in c.fetchall()]
        conn.close()
        return keys
