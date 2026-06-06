import uuid
from datetime import datetime, timezone

import aiosqlite


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection: aiosqlite.Connection | None = None

    async def initialize(self):
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self._create_tables()

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

    async def delete_document(self, doc_id: str):
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
