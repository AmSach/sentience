"""
Database Tools Skill
SQL operations and database management.
"""

import os
import sqlite3
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from contextlib import contextmanager

METADATA = {
    "name": "database-tools",
    "description": "SQL operations, query building, and database management for SQLite",
    "category": "data",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["database", "sql", "query", "sqlite", "db"],
    "dependencies": [],
    "tags": ["database", "sql", "sqlite", "query"]
}

SKILL_NAME = "database-tools"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "data"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class TableInfo:
    name: str
    columns: List[Dict[str, Any]]
    row_count: int
    primary_key: str


class SQLiteDatabase:
    """SQLite database operations."""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
    
    @contextmanager
    def connect(self):
        """Context manager for database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def execute(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute SQL and return results."""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            
            if sql.strip().upper().startswith(('SELECT', 'PRAGMA')):
                columns = [description[0] for description in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return rows
            else:
                conn.commit()
                return [{"affected_rows": cursor.rowcount}]
    
    def execute_script(self, script: str) -> None:
        """Execute multiple SQL statements."""
        with self.connect() as conn:
            conn.executescript(script)
            conn.commit()
    
    def create_table(self, table: str, columns: Dict[str, str], 
                    primary_key: str = None, if_not_exists: bool = True) -> bool:
        """Create a table."""
        exists_clause = "IF NOT EXISTS" if if_not_exists else ""
        
        col_defs = []
        for col_name, col_type in columns.items():
            col_def = f"{col_name} {col_type}"
            if primary_key and col_name == primary_key:
                col_def += " PRIMARY KEY"
            col_defs.append(col_def)
        
        sql = f"CREATE TABLE {exists_clause} {table} ({', '.join(col_defs)})"
        self.execute(sql)
        return True
    
    def drop_table(self, table: str, if_exists: bool = True) -> bool:
        """Drop a table."""
        exists_clause = "IF EXISTS" if if_exists else ""
        sql = f"DROP TABLE {exists_clause} {table}"
        self.execute(sql)
        return True
    
    def get_tables(self) -> List[str]:
        """Get list of tables."""
        results = self.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [r['name'] for r in results]
    
    def get_table_info(self, table: str) -> TableInfo:
        """Get table information."""
        columns = self.execute(f"PRAGMA table_info({table})")
        
        primary_key = None
        for col in columns:
            if col['pk']:
                primary_key = col['name']
        
        count_result = self.execute(f"SELECT COUNT(*) as count FROM {table}")
        row_count = count_result[0]['count'] if count_result else 0
        
        return TableInfo(
            name=table,
            columns=columns,
            row_count=row_count,
            primary_key=primary_key
        )
    
    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row."""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(data.values()))
            conn.commit()
            return cursor.lastrowid
    
    def insert_many(self, table: str, rows: List[Dict[str, Any]]) -> int:
        """Insert multiple rows."""
        if not rows:
            return 0
        
        columns = ', '.join(rows[0].keys())
        placeholders = ', '.join(['?' for _ in rows[0]])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.executemany(sql, [tuple(r.values()) for r in rows])
            conn.commit()
            return cursor.rowcount
    
    def update(self, table: str, data: Dict[str, Any], where: str, 
               where_params: tuple = ()) -> int:
        """Update rows."""
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(data.values()) + where_params)
            conn.commit()
            return cursor.rowcount
    
    def delete(self, table: str, where: str, where_params: tuple = ()) -> int:
        """Delete rows."""
        sql = f"DELETE FROM {table} WHERE {where}"
        
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, where_params)
            conn.commit()
            return cursor.rowcount
    
    def select(self, table: str, columns: List[str] = None, where: str = None,
               where_params: tuple = (), order_by: str = None, limit: int = None) -> List[Dict]:
        """Select rows."""
        col_str = ', '.join(columns) if columns else '*'
        sql = f"SELECT {col_str} FROM {table}"
        
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"
        
        return self.execute(sql, where_params)
    
    def query(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute raw SQL query."""
        return self.execute(sql, params)


class QueryBuilder:
    """Build SQL queries programmatically."""
    
    def __init__(self, table: str):
        self.table = table
        self._select = ["*"]
        self._where = []
        self._where_params = []
        self._joins = []
        self._order = []
        self._group = []
        self._having = []
        self._limit = None
        self._offset = None
    
    def select(self, *columns: str) -> 'QueryBuilder':
        """Add columns to select."""
        if columns:
            self._select = list(columns)
        return self
    
    def where(self, condition: str, *params) -> 'QueryBuilder':
        """Add WHERE condition."""
        self._where.append(condition)
        self._where_params.extend(params)
        return self
    
    def where_in(self, column: str, values: List) -> 'QueryBuilder':
        """Add WHERE IN condition."""
        placeholders = ', '.join(['?' for _ in values])
        self._where.append(f"{column} IN ({placeholders})")
        self._where_params.extend(values)
        return self
    
    def where_like(self, column: str, pattern: str) -> 'QueryBuilder':
        """Add WHERE LIKE condition."""
        self._where.append(f"{column} LIKE ?")
        self._where_params.append(pattern)
        return self
    
    def where_between(self, column: str, start, end) -> 'QueryBuilder':
        """Add WHERE BETWEEN condition."""
        self._where.append(f"{column} BETWEEN ? AND ?")
        self._where_params.extend([start, end])
        return self
    
    def join(self, table: str, on: str, join_type: str = "INNER") -> 'QueryBuilder':
        """Add JOIN clause."""
        self._joins.append(f"{join_type} JOIN {table} ON {on}")
        return self
    
    def left_join(self, table: str, on: str) -> 'QueryBuilder':
        """Add LEFT JOIN clause."""
        return self.join(table, on, "LEFT")
    
    def order_by(self, *columns: str) -> 'QueryBuilder':
        """Add ORDER BY clause."""
        self._order.extend(columns)
        return self
    
    def group_by(self, *columns: str) -> 'QueryBuilder':
        """Add GROUP BY clause."""
        self._group.extend(columns)
        return self
    
    def having(self, condition: str) -> 'QueryBuilder':
        """Add HAVING clause."""
        self._having.append(condition)
        return self
    
    def limit(self, n: int) -> 'QueryBuilder':
        """Set LIMIT."""
        self._limit = n
        return self
    
    def offset(self, n: int) -> 'QueryBuilder':
        """Set OFFSET."""
        self._offset = n
        return self
    
    def build(self) -> tuple:
        """Build SQL query and params."""
        sql_parts = [f"SELECT {', '.join(self._select)} FROM {self.table}"]
        
        if self._joins:
            sql_parts.extend(self._joins)
        
        if self._where:
            sql_parts.append(f"WHERE {' AND '.join(self._where)}")
        
        if self._group:
            sql_parts.append(f"GROUP BY {', '.join(self._group)}")
        
        if self._having:
            sql_parts.append(f"HAVING {' AND '.join(self._having)}")
        
        if self._order:
            sql_parts.append(f"ORDER BY {', '.join(self._order)}")
        
        if self._limit is not None:
            sql_parts.append(f"LIMIT {self._limit}")
        
        if self._offset is not None:
            sql_parts.append(f"OFFSET {self._offset}")
        
        return ' '.join(sql_parts), tuple(self._where_params)
    
    def __str__(self) -> str:
        return self.build()[0]


def execute(
    db_path: str = ":memory:",
    operation: str = "query",
    **kwargs
) -> Dict[str, Any]:
    """
    Perform database operations.
    
    Args:
        db_path: Path to SQLite database (or :memory:)
        operation: Operation (query/create/insert/update/delete/select/tables/info/builder)
    
    Returns:
        Operation results
    """
    db = SQLiteDatabase(db_path)
    
    if operation == "query":
        sql = kwargs.get('sql')
        params = kwargs.get('params', ())
        
        if not sql:
            return {"success": False, "error": "sql required"}
        
        results = db.query(sql, params)
        return {
            "success": True,
            "results": results,
            "row_count": len(results)
        }
    
    elif operation == "execute":
        sql = kwargs.get('sql')
        params = kwargs.get('params', ())
        
        if not sql:
            return {"success": False, "error": "sql required"}
        
        results = db.execute(sql, params)
        return {
            "success": True,
            "affected_rows": results[0].get('affected_rows', 0) if results else 0
        }
    
    elif operation == "create":
        table = kwargs.get('table')
        columns = kwargs.get('columns')
        primary_key = kwargs.get('primary_key')
        
        if not table or not columns:
            return {"success": False, "error": "table and columns required"}
        
        db.create_table(table, columns, primary_key)
        return {
            "success": True,
            "message": f"Table '{table}' created"
        }
    
    elif operation == "insert":
        table = kwargs.get('table')
        data = kwargs.get('data')
        
        if not table or not data:
            return {"success": False, "error": "table and data required"}
        
        if isinstance(data, list):
            count = db.insert_many(table, data)
            return {"success": True, "rows_inserted": count}
        else:
            row_id = db.insert(table, data)
            return {"success": True, "row_id": row_id}
    
    elif operation == "update":
        table = kwargs.get('table')
        data = kwargs.get('data')
        where = kwargs.get('where')
        where_params = kwargs.get('where_params', ())
        
        if not table or not data or not where:
            return {"success": False, "error": "table, data, and where required"}
        
        count = db.update(table, data, where, tuple(where_params))
        return {"success": True, "rows_updated": count}
    
    elif operation == "delete":
        table = kwargs.get('table')
        where = kwargs.get('where')
        where_params = kwargs.get('where_params', ())
        
        if not table or not where:
            return {"success": False, "error": "table and where required"}
        
        count = db.delete(table, where, tuple(where_params))
        return {"success": True, "rows_deleted": count}
    
    elif operation == "select":
        table = kwargs.get('table')
        columns = kwargs.get('columns')
        where = kwargs.get('where')
        where_params = kwargs.get('where_params', ())
        order_by = kwargs.get('order_by')
        limit = kwargs.get('limit')
        
        if not table:
            return {"success": False, "error": "table required"}
        
        results = db.select(table, columns, where, tuple(where_params), order_by, limit)
        return {
            "success": True,
            "results": results,
            "row_count": len(results)
        }
    
    elif operation == "tables":
        tables = db.get_tables()
        return {
            "success": True,
            "tables": tables
        }
    
    elif operation == "info":
        table = kwargs.get('table')
        
        if not table:
            return {"success": False, "error": "table required"}
        
        info = db.get_table_info(table)
        return {
            "success": True,
            "table": info.name,
            "columns": info.columns,
            "row_count": info.row_count,
            "primary_key": info.primary_key
        }
    
    elif operation == "builder":
        table = kwargs.get('table')
        
        if not table:
            return {"success": False, "error": "table required"}
        
        builder = QueryBuilder(table)
        
        # Apply builder methods
        if kwargs.get('select'):
            builder.select(*kwargs['select'])
        if kwargs.get('where'):
            builder.where(*kwargs['where'])
        if kwargs.get('where_in'):
            builder.where_in(*kwargs['where_in'])
        if kwargs.get('join'):
            builder.join(*kwargs['join'])
        if kwargs.get('order_by'):
            builder.order_by(*kwargs['order_by'])
        if kwargs.get('limit'):
            builder.limit(kwargs['limit'])
        
        sql, params = builder.build()
        
        # Execute or return
        if kwargs.get('execute', False):
            results = db.query(sql, params)
            return {
                "success": True,
                "sql": sql,
                "params": params,
                "results": results
            }
        
        return {
            "success": True,
            "sql": sql,
            "params": params
        }
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
