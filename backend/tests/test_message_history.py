import json

import pytest

from src.storage.database import Database


@pytest.mark.asyncio
async def test_messages_are_persisted_and_paginated_by_thread(tmp_path):
    db = Database(str(tmp_path / "train_agent.db"))
    await db.initialize()

    try:
        first = await db.record_message(
            thread_id="thread-a",
            workspace_id="workspace-1",
            message_id="msg-1",
            role="human",
            content="你好",
        )
        second = await db.record_message(
            thread_id="thread-a",
            workspace_id="workspace-1",
            message_id="msg-2",
            role="ai",
            content=[{"type": "text", "text": "你好，有什么可以帮你？"}],
            tool_calls=[{"id": "call-1", "name": "rag_search", "args": {"query": "培训"}}],
        )
        await db.record_message(
            thread_id="thread-b",
            workspace_id="workspace-1",
            message_id="msg-other",
            role="human",
            content="不要返回我",
        )

        page = await db.list_thread_messages("thread-a", limit=1)

        assert page["next_cursor"] == second
        assert len(page["messages"]) == 1
        assert page["messages"][0]["message_id"] == "msg-2"
        assert page["messages"][0]["role"] == "ai"
        assert page["messages"][0]["type"] == "ai"
        assert page["messages"][0]["content"] == [{"type": "text", "text": "你好，有什么可以帮你？"}]
        assert page["messages"][0]["tool_calls"] == [
            {"id": "call-1", "name": "rag_search", "args": {"query": "培训"}}
        ]

        older_page = await db.list_thread_messages("thread-a", limit=10, before=page["next_cursor"])

        assert older_page["next_cursor"] is None
        assert [message["message_id"] for message in older_page["messages"]] == ["msg-1"]
        assert older_page["messages"][0]["content"] == "你好"

        raw = await db.connection.execute_fetchall(
            "SELECT content, tool_calls FROM message WHERE message_id = ?",
            ("msg-2",),
        )
        assert json.loads(raw[0]["content"]) == [{"type": "text", "text": "你好，有什么可以帮你？"}]
        assert json.loads(raw[0]["tool_calls"]) == [
            {"id": "call-1", "name": "rag_search", "args": {"query": "培训"}}
        ]
    finally:
        await db.close()
