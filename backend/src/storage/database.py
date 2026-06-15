import uuid
from datetime import datetime, timezone
import json
from typing import Any

import aiosqlite


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection: aiosqlite.Connection | None = None

    async def initialize(self):
        if self.connection:
            return
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self._create_tables()

    async def ensure_initialized(self):
        if not self.connection:
            await self.initialize()

    async def _create_tables(self):
        await self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS workspace (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                thread_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS document (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                file_type TEXT,
                summary TEXT,
                storage_path TEXT,
                status TEXT DEFAULT 'uploaded',
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS task (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                title TEXT,
                status TEXT DEFAULT 'generating',
                result_data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                workspace_id TEXT,
                message_id TEXT NOT NULL,
                role TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_call_id TEXT,
                name TEXT,
                additional_kwargs TEXT,
                response_metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(thread_id, message_id, role)
            );
            CREATE INDEX IF NOT EXISTS idx_message_thread_id_id
                ON message(thread_id, id DESC);
            PRAGMA foreign_keys = ON;
        """)
        await self._migrate_tables()
        await self.connection.commit()

    async def _migrate_tables(self):
        cursor = await self.connection.execute("PRAGMA table_info(document)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "error_message" not in columns:
            await self.connection.execute("ALTER TABLE document ADD COLUMN error_message TEXT")
        if "updated_at" not in columns:
            await self.connection.execute(
                "ALTER TABLE document ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))"
            )

        cursor = await self.connection.execute("PRAGMA table_info(message)")
        message_columns = {row["name"] for row in await cursor.fetchall()}
        if message_columns:
            for column, ddl in {
                "workspace_id": "ALTER TABLE message ADD COLUMN workspace_id TEXT",
                "tool_calls": "ALTER TABLE message ADD COLUMN tool_calls TEXT",
                "tool_call_id": "ALTER TABLE message ADD COLUMN tool_call_id TEXT",
                "name": "ALTER TABLE message ADD COLUMN name TEXT",
                "additional_kwargs": "ALTER TABLE message ADD COLUMN additional_kwargs TEXT",
                "response_metadata": "ALTER TABLE message ADD COLUMN response_metadata TEXT",
                "updated_at": "ALTER TABLE message ADD COLUMN updated_at TEXT",
            }.items():
                if column not in message_columns:
                    await self.connection.execute(ddl)

    async def close(self):
        if self.connection:
            await self.connection.close()

    # --- Workspace ---

    async def create_workspace(self, user_id: str, name: str) -> dict:
        normalized_name = name.strip()
        cursor = await self.connection.execute(
            "SELECT id FROM workspace WHERE user_id = ? AND lower(name) = lower(?)",
            (user_id, normalized_name),
        )
        existing = await cursor.fetchone()
        if existing:
            raise ValueError("Workspace name already exists")

        workspace_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO workspace (id, user_id, name) VALUES (?, ?, ?)",
            (workspace_id, user_id, normalized_name),
        )
        await self.connection.commit()
        return {"id": workspace_id, "user_id": user_id, "name": normalized_name}

    async def get_workspace(self, workspace_id: str) -> dict | None:
        cursor = await self.connection.execute(
            "SELECT * FROM workspace WHERE id = ?", (workspace_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_workspaces(self, user_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM workspace WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_workspace(self, workspace_id: str):
        await self.connection.execute(
            "DELETE FROM workspace WHERE id = ?", (workspace_id,)
        )
        await self.connection.commit()

    async def update_workspace_thread_id(self, workspace_id: str, thread_id: str):
        await self.connection.execute(
            "UPDATE workspace SET thread_id = ? WHERE id = ?",
            (thread_id, workspace_id),
        )
        await self.connection.commit()

    # --- Message ---

    @staticmethod
    def _dump_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _load_json(value: str | None, fallback: Any) -> Any:
        if value is None:
            return fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback

    async def record_message(
        self,
        *,
        thread_id: str,
        workspace_id: str | None,
        message_id: str,
        role: str,
        content: Any,
        type: str | None = None,
        tool_calls: Any = None,
        tool_call_id: str | None = None,
        name: str | None = None,
        additional_kwargs: Any = None,
        response_metadata: Any = None,
    ) -> int:
        await self.ensure_initialized()
        now = datetime.now(timezone.utc).isoformat()
        message_type = type or role
        cursor = await self.connection.execute(
            """
            INSERT INTO message (
                thread_id, workspace_id, message_id, role, type, content,
                tool_calls, tool_call_id, name, additional_kwargs, response_metadata,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id, message_id, role) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                type = excluded.type,
                content = excluded.content,
                tool_calls = excluded.tool_calls,
                tool_call_id = excluded.tool_call_id,
                name = excluded.name,
                additional_kwargs = excluded.additional_kwargs,
                response_metadata = excluded.response_metadata,
                updated_at = excluded.updated_at
            RETURNING id
            """,
            (
                thread_id,
                workspace_id,
                message_id,
                role,
                message_type,
                self._dump_json(content),
                self._dump_json(tool_calls) if tool_calls is not None else None,
                tool_call_id,
                name,
                self._dump_json(additional_kwargs or {}),
                self._dump_json(response_metadata or {}),
                now,
                now,
            ),
        )
        row = await cursor.fetchone()
        await self.connection.commit()
        return int(row["id"])

    async def list_thread_messages(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        before: int | None = None,
    ) -> dict:
        await self.ensure_initialized()
        safe_limit = min(max(limit, 1), 100)
        params: list[Any] = [thread_id]
        where = "thread_id = ?"
        if before is not None:
            where += " AND id < ?"
            params.append(before)
        params.append(safe_limit + 1)
        cursor = await self.connection.execute(
            f"""
            SELECT *
            FROM message
            WHERE {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        has_more = len(rows) > safe_limit
        rows = rows[:safe_limit]
        messages = [self._message_row_to_dict(row) for row in reversed(rows)]
        return {
            "messages": messages,
            "next_cursor": int(rows[-1]["id"]) if has_more and rows else None,
        }

    def _message_row_to_dict(self, row: aiosqlite.Row) -> dict:
        return {
            "id": int(row["id"]),
            "thread_id": row["thread_id"],
            "workspace_id": row["workspace_id"],
            "message_id": row["message_id"],
            "role": row["role"],
            "type": row["type"],
            "content": self._load_json(row["content"], ""),
            "tool_calls": self._load_json(row["tool_calls"], []),
            "tool_call_id": row["tool_call_id"],
            "name": row["name"],
            "additional_kwargs": self._load_json(row["additional_kwargs"], {}),
            "response_metadata": self._load_json(row["response_metadata"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- Document ---


    async def create_document(
        self,
        workspace_id: str,
        filename: str,
        file_type: str,
        storage_path: str,
    ) -> dict:
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self.connection.execute(
            "INSERT INTO document (id, workspace_id, filename, file_type, storage_path, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, workspace_id, filename, file_type, storage_path, "uploaded", now, now),
        )
        await self.connection.commit()
        return {
            "id": doc_id,
            "workspace_id": workspace_id,
            "filename": filename,
            "file_type": file_type,
            "storage_path": storage_path,
            "summary": None,
            "status": "uploaded",
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }

    async def list_documents(self, workspace_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM document WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_document(self, doc_id: str, **kwargs):
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values()) + [doc_id]
        await self.connection.execute(
            f"UPDATE document SET {sets} WHERE id = ?", values
        )
        await self.connection.commit()

    async def delete_document(self, doc_id: str, workspace_id: str = None):
        if workspace_id:
            await self.connection.execute(
                "DELETE FROM document WHERE id = ? AND workspace_id = ?",
                (doc_id, workspace_id),
            )
        else:
            await self.connection.execute("DELETE FROM document WHERE id = ?", (doc_id,))
        await self.connection.commit()

    # --- Task ---

    async def create_task(
        self, workspace_id: str, type: str, title: str = None
    ) -> dict:
        task_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO task (id, workspace_id, type, title) VALUES (?, ?, ?, ?)",
            (task_id, workspace_id, type, title),
        )
        await self.connection.commit()
        return {
            "id": task_id,
            "workspace_id": workspace_id,
            "type": type,
            "title": title,
            "status": "generating",
        }

    async def list_tasks(self, workspace_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM task WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_task(self, task_id: str, **kwargs):
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values()) + [task_id]
        await self.connection.execute(
            f"UPDATE task SET {sets} WHERE id = ?", values
        )
        await self.connection.commit()

    async def delete_task(self, task_id: str):
        await self.connection.execute("DELETE FROM task WHERE id = ?", (task_id,))
        await self.connection.commit()
