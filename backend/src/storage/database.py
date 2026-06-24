import random
import uuid
from datetime import datetime
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
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
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
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS task (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                title TEXT,
                status TEXT DEFAULT 'generating',
                result_data TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
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
            CREATE TABLE IF NOT EXISTS ppt_style (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                name_en TEXT DEFAULT '',
                description TEXT DEFAULT '',
                style_description TEXT DEFAULT '',
                resource_manifest TEXT DEFAULT '[]',
                preview_path TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_ppt_style_user ON ppt_style(user_id);
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
                "ALTER TABLE document ADD COLUMN updated_at TEXT DEFAULT (datetime('now', 'localtime'))"
            )
        if "content_hash" not in columns:
            await self.connection.execute(
                "ALTER TABLE document ADD COLUMN content_hash TEXT"
            )
            await self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_hash ON document(workspace_id, content_hash)"
            )

        # workspace: add ext_data column with default config
        cursor = await self.connection.execute("PRAGMA table_info(workspace)")
        ws_columns = {row["name"] for row in await cursor.fetchall()}
        if "ext_data" not in ws_columns:
            default_voice_info = get_default_voice_info("Cherry")
            default_ext = json.dumps(
                {"ppt_style": "swiss-modern", "voice_info": default_voice_info},
                ensure_ascii=False,
            )
            await self.connection.execute(
                f"ALTER TABLE workspace ADD COLUMN ext_data TEXT DEFAULT '{default_ext}'"
            )
            # Backfill existing rows that have NULL ext_data
            await self.connection.execute(
                "UPDATE workspace SET ext_data = ? WHERE ext_data IS NULL",
                (default_ext,),
            )

        # Backfill voice_info for workspaces that have voice_id but no voice_info,
        # and migrate voice_id into voice_info.id
        cursor = await self.connection.execute("SELECT id, ext_data FROM workspace WHERE ext_data IS NOT NULL")
        for row in await cursor.fetchall():
            try:
                ext = json.loads(row["ext_data"]) if isinstance(row["ext_data"], str) else {}
            except (json.JSONDecodeError, TypeError):
                ext = {}
            changed = False
            # Migrate: old voice_id → voice_info with id
            if ext.get("voice_id") and not ext.get("voice_info"):
                vi = get_default_voice_info(ext["voice_id"])
                if vi:
                    ext["voice_info"] = vi
                    changed = True
            # Remove standalone voice_id (now inside voice_info.id)
            if "voice_id" in ext:
                del ext["voice_id"]
                changed = True
            if changed:
                await self.connection.execute(
                    "UPDATE workspace SET ext_data = ? WHERE id = ?",
                    (json.dumps(ext, ensure_ascii=False), row["id"]),
                )

        # task: add parent_task_id column
        cursor = await self.connection.execute("PRAGMA table_info(task)")
        task_columns = {row["name"] for row in await cursor.fetchall()}
        if "parent_task_id" not in task_columns:
            await self.connection.execute(
                "ALTER TABLE task ADD COLUMN parent_task_id TEXT REFERENCES task(id) ON DELETE SET NULL"
            )
            await self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_parent ON task(parent_task_id)"
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

        # ppt_style: add resource_manifest column
        cursor = await self.connection.execute("PRAGMA table_info(ppt_style)")
        ppt_style_columns = {row["name"] for row in await cursor.fetchall()}
        if "resource_manifest" not in ppt_style_columns:
            await self.connection.execute(
                "ALTER TABLE ppt_style ADD COLUMN resource_manifest TEXT DEFAULT '[]'"
            )

        # Seed builtin PPT styles
        for style in _BUILTIN_PPT_STYLES:
            await self.connection.execute(
                """INSERT OR IGNORE INTO ppt_style
                   (id, user_id, category, name, name_en, description, style_description, preview_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    style["id"],
                    style["user_id"],
                    style["category"],
                    style["name"],
                    style["name_en"],
                    style["description"],
                    style["style_description"],
                    style["preview_path"],
                ),
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
        default_voice_info = get_default_voice_info("Cherry")

        # Randomly pick a system style as default ppt_style
        default_style_id = "swiss-modern"  # fallback
        try:
            cursor = await self.connection.execute(
                "SELECT id FROM ppt_style WHERE user_id = 'system'"
            )
            system_styles = await cursor.fetchall()
            if system_styles:
                default_style_id = random.choice(system_styles)["id"]
        except Exception:
            pass  # table may not exist yet during migration

        default_ext_data = json.dumps(
            {"ppt_style": default_style_id, "voice_info": default_voice_info},
            ensure_ascii=False,
        )
        await self.connection.execute(
            "INSERT INTO workspace (id, user_id, name, ext_data) VALUES (?, ?, ?, ?)",
            (workspace_id, user_id, normalized_name, default_ext_data),
        )
        await self.connection.commit()
        return {
            "id": workspace_id,
            "user_id": user_id,
            "name": normalized_name,
            "ext_data": json.loads(default_ext_data),
        }

    async def get_workspace(self, workspace_id: str) -> dict | None:
        cursor = await self.connection.execute(
            "SELECT * FROM workspace WHERE id = ?", (workspace_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        # Parse ext_data JSON into dict
        raw_ext = data.get("ext_data")
        if isinstance(raw_ext, str):
            try:
                data["ext_data"] = json.loads(raw_ext)
            except (json.JSONDecodeError, TypeError):
                data["ext_data"] = {}
        elif raw_ext is None:
            data["ext_data"] = {}
        return data

    async def list_workspaces(self, user_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM workspace WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            data = dict(row)
            raw_ext = data.get("ext_data")
            if isinstance(raw_ext, str):
                try:
                    data["ext_data"] = json.loads(raw_ext)
                except (json.JSONDecodeError, TypeError):
                    data["ext_data"] = {}
            elif raw_ext is None:
                data["ext_data"] = {}
            results.append(data)
        return results

    async def delete_workspace(self, workspace_id: str):
        # Delete all messages for this workspace
        await self.connection.execute(
            "DELETE FROM message WHERE workspace_id = ?", (workspace_id,)
        )
        # Delete all tasks for this workspace
        await self.connection.execute(
            "DELETE FROM task WHERE workspace_id = ?", (workspace_id,)
        )
        # Delete the workspace record
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

    async def update_workspace_ext_data(self, workspace_id: str, key: str, value: Any):
        """Update a single key in workspace.ext_data JSON."""
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT ext_data FROM workspace WHERE id = ?", (workspace_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Workspace not found")
        raw = row["ext_data"]
        try:
            ext_data = json.loads(raw) if isinstance(raw, str) and raw else {}
        except (json.JSONDecodeError, TypeError):
            ext_data = {}
        ext_data[key] = value
        await self.connection.execute(
            "UPDATE workspace SET ext_data = ? WHERE id = ?",
            (json.dumps(ext_data, ensure_ascii=False), workspace_id),
        )
        await self.connection.commit()
        return ext_data

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
        now = datetime.now().isoformat()
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
        """Return messages grouped by turn (human message + following AI/tool messages).

        ``limit`` controls the number of *turns* (not individual messages).
        ``before`` is the row ``id`` of the oldest human message from the previous page.
        """
        await self.ensure_initialized()
        safe_limit = min(max(limit, 1), 100)
        params: list[Any] = [thread_id]
        where = "thread_id = ?"
        if before is not None:
            where += " AND id < ?"
            params.append(before)

        # Step 1: find the N most recent human message ids (turn boundaries)
        cursor = await self.connection.execute(
            f"SELECT id FROM message WHERE {where} AND role = 'human' "
            f"ORDER BY id DESC LIMIT ?",
            [*params, safe_limit],
        )
        human_ids = sorted(row["id"] for row in await cursor.fetchall())

        if not human_ids:
            return {"messages": [], "next_cursor": None}

        # Step 2: fetch all messages from the oldest turn boundary onward
        # When ``before`` is set, apply it as an upper bound so that this
        # page does not overlap with the previous (newer) page's results.
        oldest_turn_id = human_ids[0]
        if before is not None:
            cursor = await self.connection.execute(
                "SELECT * FROM message WHERE thread_id = ? AND id >= ? AND id < ? ORDER BY id ASC",
                [thread_id, oldest_turn_id, before],
            )
        else:
            cursor = await self.connection.execute(
                "SELECT * FROM message WHERE thread_id = ? AND id >= ? ORDER BY id ASC",
                [thread_id, oldest_turn_id],
            )
        rows = await cursor.fetchall()
        messages = [self._message_row_to_dict(row, strip_tool_content=True) for row in rows]

        # Check whether there are older turns
        cursor = await self.connection.execute(
            "SELECT 1 FROM message WHERE thread_id = ? AND role = 'human' AND id < ? LIMIT 1",
            [thread_id, oldest_turn_id],
        )
        has_more = await cursor.fetchone() is not None

        return {
            "messages": messages,
            "next_cursor": int(oldest_turn_id) if has_more else None,
        }

    def _message_row_to_dict(self, row: aiosqlite.Row, *, strip_tool_content: bool = False) -> dict:
        content = self._load_json(row["content"], "")
        # Strip tool message content in list response to reduce payload size;
        # content can be fetched individually via the detail endpoint.
        if strip_tool_content and row["role"] == "tool":
            content = ""
        return {
            "id": int(row["id"]),
            "thread_id": row["thread_id"],
            "workspace_id": row["workspace_id"],
            "message_id": row["message_id"],
            "role": row["role"],
            "type": row["type"],
            "content": content,
            "tool_calls": self._load_json(row["tool_calls"], []),
            "tool_call_id": row["tool_call_id"],
            "name": row["name"],
            "additional_kwargs": self._load_json(row["additional_kwargs"], {}),
            "response_metadata": self._load_json(row["response_metadata"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def get_message_by_id(self, message_id: str, thread_id: str) -> dict | None:
        """Fetch a single message by its message_id within the given thread."""
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT * FROM message WHERE message_id = ? AND thread_id = ?",
            [message_id, thread_id],
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._message_row_to_dict(row)

    # --- Document ---


    async def create_document(
        self,
        workspace_id: str,
        filename: str,
        file_type: str,
        storage_path: str,
        content_hash: str = "",
    ) -> dict:
        doc_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.connection.execute(
            "INSERT INTO document (id, workspace_id, filename, file_type, storage_path, content_hash, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, workspace_id, filename, file_type, storage_path, content_hash, "uploaded", now, now),
        )
        await self.connection.commit()
        return {
            "id": doc_id,
            "workspace_id": workspace_id,
            "filename": filename,
            "file_type": file_type,
            "storage_path": storage_path,
            "content_hash": content_hash,
            "summary": None,
            "status": "uploaded",
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }

    async def find_duplicate_document(
        self, workspace_id: str, filename: str, content_hash: str
    ) -> dict | None:
        """Find an existing non-error document with the same filename or content_hash.

        Returns the conflicting document dict, or None if no duplicate found.
        """
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT * FROM document "
            "WHERE workspace_id = ? AND status != 'error' "
            "AND (filename = ? OR content_hash = ?) "
            "ORDER BY created_at DESC LIMIT 1",
            (workspace_id, filename, content_hash),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_documents(self, workspace_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM document WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_document(self, doc_id: str, **kwargs):
        kwargs["updated_at"] = datetime.now().isoformat()
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
        self, workspace_id: str, type: str, title: str = None, parent_task_id: str = None
    ) -> dict:
        task_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO task (id, workspace_id, type, title, parent_task_id) VALUES (?, ?, ?, ?, ?)",
            (task_id, workspace_id, type, title, parent_task_id),
        )
        await self.connection.commit()
        return {
            "id": task_id,
            "workspace_id": workspace_id,
            "type": type,
            "title": title,
            "parent_task_id": parent_task_id,
            "status": "generating",
        }

    async def list_tasks(self, workspace_id: str) -> list[dict]:
        # Only return top-level tasks (PPT), nest children
        cursor = await self.connection.execute(
            "SELECT * FROM task WHERE workspace_id = ? AND parent_task_id IS NULL ORDER BY created_at DESC",
            (workspace_id,),
        )
        parents = [dict(row) for row in await cursor.fetchall()]

        if parents:
            parent_ids = [p["id"] for p in parents]
            placeholders = ",".join("?" * len(parent_ids))
            cursor = await self.connection.execute(
                f"SELECT * FROM task WHERE parent_task_id IN ({placeholders}) ORDER BY created_at",
                parent_ids,
            )
            children_map: dict[str, list[dict]] = {}
            for row in await cursor.fetchall():
                child = dict(row)
                children_map.setdefault(child["parent_task_id"], []).append(child)
            for parent in parents:
                parent["children"] = children_map.get(parent["id"], [])

        return parents

    async def get_task(self, task_id: str) -> dict | None:
        """Get a single task by ID."""
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT * FROM task WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        task = dict(row)
        # Attach children
        cursor = await self.connection.execute(
            "SELECT * FROM task WHERE parent_task_id = ? ORDER BY created_at",
            (task_id,),
        )
        task["children"] = [dict(r) for r in await cursor.fetchall()]
        return task

    async def get_task_result_data(self, task_id: str) -> dict:
        """Get parsed result_data for a task."""
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT result_data FROM task WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        if not row or not row["result_data"]:
            return {}
        try:
            return json.loads(row["result_data"])
        except (json.JSONDecodeError, TypeError):
            return {}

    async def update_task(self, task_id: str, **kwargs):
        kwargs["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values()) + [task_id]
        await self.connection.execute(
            f"UPDATE task SET {sets} WHERE id = ?", values
        )
        await self.connection.commit()

    async def delete_task(self, task_id: str) -> list[str]:
        """Delete a task. If PPT, also delete all child tasks (cascade).

        Returns list of deleted task IDs.
        """
        # Get task info
        cursor = await self.connection.execute(
            "SELECT id, type FROM task WHERE id = ?", (task_id,)
        )
        task = await cursor.fetchone()
        if not task:
            return []

        deleted_ids: list[str] = [task_id]

        if task["type"] == "ppt":
            # Cascade: find and delete all child tasks
            cursor = await self.connection.execute(
                "SELECT id FROM task WHERE parent_task_id = ?", (task_id,)
            )
            children = await cursor.fetchall()
            for child in children:
                deleted_ids.append(child["id"])
            await self.connection.execute(
                "DELETE FROM task WHERE parent_task_id = ?", (task_id,)
            )

        await self.connection.execute("DELETE FROM task WHERE id = ?", (task_id,))
        await self.connection.commit()
        return deleted_ids

    # --- PPT Style ---

    async def list_ppt_styles(self, user_id: str) -> list[dict]:
        """List styles for a user (without style_description)."""
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT id, user_id, category, name, name_en, description, preview_path, created_at "
            "FROM ppt_style WHERE user_id = ? ORDER BY category, name_en",
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def list_all_ppt_styles(self, user_ids: list[str]) -> list[dict]:
        """List styles for multiple user_ids (without style_description)."""
        await self.ensure_initialized()
        if not user_ids:
            return []
        placeholders = ",".join("?" * len(user_ids))
        cursor = await self.connection.execute(
            f"SELECT id, user_id, category, name, name_en, description, preview_path, created_at "
            f"FROM ppt_style WHERE user_id IN ({placeholders}) ORDER BY category, name_en",
            user_ids,
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_ppt_style_by_name_en(self, name_en: str, user_id: str | None = None) -> dict | None:
        """Get a single style by name_en. If user_id given, prefer user custom over system."""
        await self.ensure_initialized()
        if user_id:
            cursor = await self.connection.execute(
                "SELECT * FROM ppt_style WHERE name_en = ? AND user_id IN (?, 'system') "
                "ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END LIMIT 1",
                (name_en, user_id, user_id),
            )
        else:
            cursor = await self.connection.execute(
                "SELECT * FROM ppt_style WHERE name_en = ? LIMIT 1",
                (name_en,),
            )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_ppt_style(
        self,
        user_id: str,
        category: str,
        name: str,
        name_en: str = "",
        description: str = "",
        style_description: str = "",
        preview_path: str = "",
    ) -> dict:
        await self.ensure_initialized()
        style_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO ppt_style (id, user_id, category, name, name_en, description, style_description, preview_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (style_id, user_id, category, name, name_en, description, style_description, preview_path),
        )
        await self.connection.commit()
        return {
            "id": style_id,
            "user_id": user_id,
            "category": category,
            "name": name,
            "name_en": name_en,
            "description": description,
            "style_description": style_description,
            "preview_path": preview_path,
        }

    async def get_ppt_style(self, style_id: str) -> dict | None:
        """Get a single style by id."""
        await self.ensure_initialized()
        cursor = await self.connection.execute(
            "SELECT * FROM ppt_style WHERE id = ?", (style_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_ppt_style(self, style_id: str):
        await self.ensure_initialized()
        await self.connection.execute("DELETE FROM ppt_style WHERE id = ?", (style_id,))
        await self.connection.commit()

    async def update_ppt_style_preview_path(self, style_id: str, preview_path: str):
        """Update a style's preview_path to an independent location."""
        await self.ensure_initialized()
        await self.connection.execute(
            "UPDATE ppt_style SET preview_path = ? WHERE id = ?",
            (preview_path, style_id),
        )
        await self.connection.commit()

    async def update_ppt_style(self, style_id: str, **fields):
        """Update arbitrary fields of a ppt_style record."""
        if not fields:
            return
        await self.ensure_initialized()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [style_id]
        await self.connection.execute(
            f"UPDATE ppt_style SET {set_clause} WHERE id = ?",
            values,
        )
        await self.connection.commit()


# System builtin PPT style seed data
_BUILTIN_PPT_STYLES = [
    {
        "id": "sys-bold-signal",
        "user_id": "system",
        "category": "dark",
        "name": "醒目信号",
        "name_en": "bold-signal",
        "description": "暗色渐变底 + 醒目色卡 + 巨大序号，视觉冲击拉满",
        "preview_path": "01-bold-signal.html",
        "style_description": (
            "**Vibe:** Confident, bold, modern, high-impact\n\n"
            "**Layout:** Colored card on dark gradient. Number top-left, navigation top-right, title bottom-left.\n\n"
            "**Typography:**\n- Display: `Archivo Black` (900)\n- Body: `Space Grotesk` (400/500)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-primary: #1a1a1a;\n    --bg-gradient: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 50%, #1a1a1a 100%);\n    --card-bg: #FF5722;\n    --text-primary: #ffffff;\n    --text-on-card: #1a1a1a;\n}\n```\n\n"
            "**Signature Elements:**\n- Bold colored card as focal point (orange, coral, or vibrant accent)\n- Large section numbers (01, 02, etc.)\n- Navigation breadcrumbs with active/inactive opacity states\n- Grid-based layout for precise alignment"
        ),
    },
    {
        "id": "sys-electric-studio",
        "user_id": "system",
        "category": "dark",
        "name": "电光工作室",
        "name_en": "electric-studio",
        "description": "上下蓝白分屏，以引用排版为视觉焦点，干净利落",
        "preview_path": "02-electric-studio.html",
        "style_description": (
            "**Vibe:** Bold, clean, professional, high contrast\n\n"
            "**Layout:** Split panel—white top, blue bottom. Brand marks in corners.\n\n"
            "**Typography:**\n- Display: `Manrope` (800)\n- Body: `Manrope` (400/500)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-dark: #0a0a0a;\n    --bg-white: #ffffff;\n    --accent-blue: #4361ee;\n    --text-dark: #0a0a0a;\n    --text-light: #ffffff;\n}\n```\n\n"
            "**Signature Elements:**\n- Two-panel vertical split\n- Accent bar on panel edge\n- Quote typography as hero element\n- Minimal, confident spacing"
        ),
    },
    {
        "id": "sys-creative-voltage",
        "user_id": "system",
        "category": "dark",
        "name": "创意电压",
        "name_en": "creative-voltage",
        "description": "电光蓝与暗色左右分屏，霓虹黄高亮 + 半调纹理",
        "preview_path": "03-creative-voltage.html",
        "style_description": (
            "**Vibe:** Bold, creative, energetic, retro-modern\n\n"
            "**Layout:** Split panels—electric blue left, dark right. Script accents.\n\n"
            "**Typography:**\n- Display: `Syne` (700/800)\n- Mono: `Space Mono` (400/700)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-primary: #0066ff;\n    --bg-dark: #1a1a2e;\n    --accent-neon: #d4ff00;\n    --text-light: #ffffff;\n}\n```\n\n"
            "**Signature Elements:**\n- Electric blue + neon yellow contrast\n- Halftone texture patterns\n- Neon badges/callouts\n- Script typography for creative flair"
        ),
    },
    {
        "id": "sys-dark-botanical",
        "user_id": "system",
        "category": "dark",
        "name": "暗黑植物",
        "name_en": "dark-botanical",
        "description": "暗底 + 暖色柔光球 + 优雅衬线斜体，静谧高级",
        "preview_path": "04-dark-botanical.html",
        "style_description": (
            "**Vibe:** Elegant, sophisticated, artistic, premium\n\n"
            "**Layout:** Centered content on dark. Abstract soft shapes in corner.\n\n"
            "**Typography:**\n- Display: `Cormorant` (400/600) — elegant serif\n- Body: `IBM Plex Sans` (300/400)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-primary: #0f0f0f;\n    --text-primary: #e8e4df;\n    --text-secondary: #9a9590;\n    --accent-warm: #d4a574;\n    --accent-pink: #e8b4b8;\n    --accent-gold: #c9b896;\n}\n```\n\n"
            "**Signature Elements:**\n- Abstract soft gradient circles (blurred, overlapping)\n- Warm color accents (pink, gold, terracotta)\n- Thin vertical accent lines\n- Italic signature typography\n- **No illustrations—only abstract CSS shapes**"
        ),
    },
    {
        "id": "sys-neon-cyber",
        "user_id": "system",
        "category": "dark",
        "name": "霓虹赛博",
        "name_en": "neon-cyber",
        "description": "深空蓝底 + 粒子动画 + 青色/品红霓虹光晕",
        "preview_path": "09-neon-cyber.html",
        "style_description": (
            "**Vibe:** Futuristic, techy, confident\n\n"
            "**Typography:** `Clash Display` + `Satoshi` (Fontshare)\n\n"
            "**Colors:** Deep navy (#0a0f1c), cyan accent (#00ffcc), magenta (#ff00aa)\n\n"
            "**Signature:** Particle backgrounds, neon glow, grid patterns"
        ),
    },
    {
        "id": "sys-terminal-green",
        "user_id": "system",
        "category": "dark",
        "name": "终端黑客",
        "name_en": "terminal-green",
        "description": "终端窗口 + 闪烁绿光标 + 扫描线，极客美学",
        "preview_path": "10-terminal-green.html",
        "style_description": (
            "**Vibe:** Developer-focused, hacker aesthetic\n\n"
            "**Typography:** `JetBrains Mono` (monospace only)\n\n"
            "**Colors:** GitHub dark (#0d1117), terminal green (#39d353)\n\n"
            "**Signature:** Scan lines, blinking cursor, code syntax styling"
        ),
    },
    {
        "id": "sys-notebook-tabs",
        "user_id": "system",
        "category": "light",
        "name": "笔记标签",
        "name_en": "notebook-tabs",
        "description": "奶白纸卡 + 右侧彩色标签 + 左侧活页孔，编辑质感",
        "preview_path": "05-notebook-tabs.html",
        "style_description": (
            "**Vibe:** Editorial, organized, elegant, tactile\n\n"
            "**Layout:** Cream paper card on dark background. Colorful tabs on right edge.\n\n"
            "**Typography:**\n- Display: `Bodoni Moda` (400/700) — classic editorial\n- Body: `DM Sans` (400/500)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-outer: #2d2d2d;\n    --bg-page: #f8f6f1;\n    --text-primary: #1a1a1a;\n    --tab-1: #98d4bb; /* Mint */\n    --tab-2: #c7b8ea; /* Lavender */\n    --tab-3: #f4b8c5; /* Pink */\n    --tab-4: #a8d8ea; /* Sky */\n    --tab-5: #ffe6a7; /* Cream */\n}\n```\n\n"
            "**Signature Elements:**\n- Paper container with subtle shadow\n- Colorful section tabs on right edge (vertical text)\n- Binder hole decorations on left\n- Tab text must scale with viewport: `font-size: clamp(0.5rem, 1vh, 0.7rem)`"
        ),
    },
    {
        "id": "sys-pastel-geometry",
        "user_id": "system",
        "category": "light",
        "name": "粉彩几何",
        "name_en": "pastel-geometry",
        "description": "柔和粉彩底 + 圆角白卡 + 右侧竖排彩色药丸标签",
        "preview_path": "06-pastel-geometry.html",
        "style_description": (
            "**Vibe:** Friendly, organized, modern, approachable\n\n"
            "**Layout:** White card on pastel background. Vertical pills on right edge.\n\n"
            "**Typography:**\n- Display: `Plus Jakarta Sans` (700/800)\n- Body: `Plus Jakarta Sans` (400/500)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-primary: #c8d9e6;\n    --card-bg: #faf9f7;\n    --pill-pink: #f0b4d4;\n    --pill-mint: #a8d4c4;\n    --pill-sage: #5a7c6a;\n    --pill-lavender: #9b8dc4;\n    --pill-violet: #7c6aad;\n}\n```\n\n"
            "**Signature Elements:**\n- Rounded card with soft shadow\n- **Vertical pills on right edge** with varying heights (like tabs)\n- Consistent pill width, heights: short → medium → tall → medium → short\n- Download/action icon in corner"
        ),
    },
    {
        "id": "sys-split-pastel",
        "user_id": "system",
        "category": "light",
        "name": "分屏粉彩",
        "name_en": "split-pastel",
        "description": "蜜桃/薰衣草左右分屏 + 可爱圆角徽章 + 网格纹理",
        "preview_path": "07-split-pastel.html",
        "style_description": (
            "**Vibe:** Playful, modern, friendly, creative\n\n"
            "**Layout:** Two-color vertical split (peach left, lavender right).\n\n"
            "**Typography:**\n- Display: `Outfit` (700/800)\n- Body: `Outfit` (400/500)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-peach: #f5e6dc;\n    --bg-lavender: #e4dff0;\n    --text-dark: #1a1a1a;\n    --badge-mint: #c8f0d8;\n    --badge-yellow: #f0f0c8;\n    --badge-pink: #f0d4e0;\n}\n```\n\n"
            "**Signature Elements:**\n- Split background colors\n- Playful badge pills with icons\n- Grid pattern overlay on right panel\n- Rounded CTA buttons"
        ),
    },
    {
        "id": "sys-vintage-editorial",
        "user_id": "system",
        "category": "light",
        "name": "复古编辑",
        "name_en": "vintage-editorial",
        "description": "奶油底色 + 几何线条装饰 + 粗边框按钮，老派印刷感",
        "preview_path": "08-vintage-editorial.html",
        "style_description": (
            "**Vibe:** Witty, confident, editorial, personality-driven\n\n"
            "**Layout:** Centered content on cream. Abstract geometric shapes as accent.\n\n"
            "**Typography:**\n- Display: `Fraunces` (700/900) — distinctive serif\n- Body: `Work Sans` (400/500)\n\n"
            "**Colors:**\n```css\n:root {\n    --bg-cream: #f5f3ee;\n    --text-primary: #1a1a1a;\n    --text-secondary: #555;\n    --accent-warm: #e8d4c0;\n}\n```\n\n"
            "**Signature Elements:**\n- Abstract geometric shapes (circle outline + line + dot)\n- Bold bordered CTA boxes\n- Witty, conversational copy style\n- **No illustrations—only geometric CSS shapes**"
        ),
    },
    {
        "id": "sys-swiss-modern",
        "user_id": "system",
        "category": "light",
        "name": "瑞士网格",
        "name_en": "swiss-modern",
        "description": "纯白黑红三色 + 可见十二列网格 + 不对称布局",
        "preview_path": "11-swiss-modern.html",
        "style_description": (
            "**Vibe:** Clean, precise, Bauhaus-inspired\n\n"
            "**Typography:** `Archivo` (800) + `Nunito` (400)\n\n"
            "**Colors:** Pure white, pure black, red accent (#ff3300)\n\n"
            "**Signature:** Visible grid, asymmetric layouts, geometric shapes"
        ),
    },
    {
        "id": "sys-paper-and-ink",
        "user_id": "system",
        "category": "light",
        "name": "纸墨书香",
        "name_en": "paper-and-ink",
        "description": "奶油纸质感 + 首字下沉 + 优雅横线分隔，文学气息",
        "preview_path": "12-paper-ink.html",
        "style_description": (
            "**Vibe:** Editorial, literary, thoughtful\n\n"
            "**Typography:** `Cormorant Garamond` + `Source Serif 4`\n\n"
            "**Colors:** Warm cream (#faf9f7), charcoal (#1a1a1a), crimson accent (#c41e3a)\n\n"
            "**Signature:** Drop caps, pull quotes, elegant horizontal rules"
        ),
    },
]


# Builtin voice seed data (mirrors frontend VOICES constant)
_BUILTIN_VOICES = [
    {
        "id": "Cherry",
        "name": "芊悦",
        "trait": "阳光积极、亲切自然小姐姐",
        "gender": "female",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250211/tixcef/cherry.wav",
    },
    {
        "id": "Ethan",
        "name": "晨煦",
        "trait": "阳光、温暖、活力、朝气的男生",
        "gender": "male",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250211/emaqdp/ethan.wav",
    },
    {
        "id": "Chelsie",
        "name": "千雪",
        "trait": "二次元虚拟女友",
        "gender": "female",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250211/vnpxgw/chelsie.wav",
    },
    {
        "id": "Vivian",
        "name": "十三",
        "trait": "拽拽的、可爱的小暴躁",
        "gender": "female",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20251120/eetwkj/Vivian.wav",
    },
    {
        "id": "Eldric Sage",
        "name": "沧明子",
        "trait": "沉稳睿智的老者",
        "gender": "male",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20251120/hbvhwj/Eldric+Sage.wav",
    },
    {
        "id": "Neil",
        "name": "阿闻",
        "trait": "专业的新闻主持人",
        "gender": "male",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20251120/ucmfkt/Neil.wav",
    },
    {
        "id": "Vincent",
        "name": "田叔",
        "trait": "沙哑烟嗓",
        "gender": "male",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20251120/skfrkq/Vincent.wav",
    },
    {
        "id": "Bellona",
        "name": "燕铮莺",
        "trait": "声音洪亮、字正腔圆江湖",
        "gender": "female",
        "audio_url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20251120/wztwli/Bellona.wav",
    },
]


def get_default_voice_info(voice_id: str) -> dict:
    """Look up voice info from builtin seed data. Returns {id, name, trait, gender} or empty dict."""
    voice = next((v for v in _BUILTIN_VOICES if v["id"] == voice_id), None)
    if voice:
        return {"id": voice["id"], "name": voice["name"], "trait": voice["trait"], "gender": voice["gender"]}
    return {}
