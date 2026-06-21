import json

import pytest

from src.storage.database import Database


@pytest.mark.asyncio
async def test_messages_are_persisted_and_paginated_by_thread(tmp_path):
    db = Database(str(tmp_path / "train_agent.db"))
    await db.initialize()

    try:
        # Turn 1: human + ai (thread-a)
        await db.record_message(
            thread_id="thread-a",
            workspace_id="workspace-1",
            message_id="msg-1",
            role="human",
            content="你好",
        )
        await db.record_message(
            thread_id="thread-a",
            workspace_id="workspace-1",
            message_id="msg-2",
            role="ai",
            content=[{"type": "text", "text": "你好，有什么可以帮你？"}],
            tool_calls=[{"id": "call-1", "name": "rag_search", "args": {"query": "培训"}}],
        )

        # Turn 2: human + ai (thread-a)
        turn2_human_id = await db.record_message(
            thread_id="thread-a",
            workspace_id="workspace-1",
            message_id="msg-3",
            role="human",
            content="帮我查一下培训资料",
        )
        await db.record_message(
            thread_id="thread-a",
            workspace_id="workspace-1",
            message_id="msg-4",
            role="ai",
            content="好的，正在查询...",
        )

        # Different thread — must not appear in thread-a results
        await db.record_message(
            thread_id="thread-b",
            workspace_id="workspace-1",
            message_id="msg-other",
            role="human",
            content="不要返回我",
        )

        # --- Page 1: most recent turn (limit=1, no before) ---
        page1 = await db.list_thread_messages("thread-a", limit=1)

        # Should return only turn 2 (2 messages: human + ai)
        assert len(page1["messages"]) == 2
        assert [m["message_id"] for m in page1["messages"]] == ["msg-3", "msg-4"]
        assert page1["messages"][0]["role"] == "human"
        assert page1["messages"][1]["role"] == "ai"
        # There is an older turn → next_cursor points to turn 2's human row id
        assert page1["next_cursor"] == turn2_human_id

        # --- Page 2: older turn (before=turn2_human_id) ---
        page2 = await db.list_thread_messages(
            "thread-a", limit=10, before=page1["next_cursor"]
        )

        # Should return only turn 1 (2 messages: human + ai)
        assert len(page2["messages"]) == 2
        assert [m["message_id"] for m in page2["messages"]] == ["msg-1", "msg-2"]
        assert page2["messages"][0]["content"] == "你好"
        assert page2["messages"][1]["content"] == [{"type": "text", "text": "你好，有什么可以帮你？"}]
        assert page2["messages"][1]["tool_calls"] == [
            {"id": "call-1", "name": "rag_search", "args": {"query": "培训"}}
        ]
        # No more older turns
        assert page2["next_cursor"] is None

        # --- Verify: page2 results do NOT overlap with page1 ---
        page1_ids = {m["id"] for m in page1["messages"]}
        page2_ids = {m["id"] for m in page2["messages"]}
        assert page1_ids.isdisjoint(page2_ids), "Pages must not overlap"

        # --- Verify: raw DB content is correctly serialized ---
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


@pytest.mark.asyncio
async def test_pagination_with_before_does_not_return_newer_messages(tmp_path):
    """Regression test: Step 2 must respect the ``before`` upper bound."""
    db = Database(str(tmp_path / "train_agent.db"))
    await db.initialize()

    try:
        # Create 3 turns
        for i in range(1, 4):
            await db.record_message(
                thread_id="t",
                workspace_id="w",
                message_id=f"human-{i}",
                role="human",
                content=f"question {i}",
            )
            await db.record_message(
                thread_id="t",
                workspace_id="w",
                message_id=f"ai-{i}",
                role="ai",
                content=f"answer {i}",
            )

        # Page 1: most recent turn (turn 3)
        page1 = await db.list_thread_messages("t", limit=1)
        page1_ids = {m["id"] for m in page1["messages"]}
        assert page1["next_cursor"] is not None

        # Page 2: older turns, using page1's next_cursor as before
        page2 = await db.list_thread_messages("t", limit=1, before=page1["next_cursor"])
        page2_ids = {m["id"] for m in page2["messages"]}

        # Critical: page2 must NOT contain any message from page1
        assert page1_ids.isdisjoint(page2_ids), (
            f"Overlap detected: page1={page1_ids}, page2={page2_ids}"
        )

        # All page2 messages must have id < page1's next_cursor
        for m in page2["messages"]:
            assert m["id"] < page1["next_cursor"], (
                f"Message id={m['id']} should be < cursor={page1['next_cursor']}"
            )
    finally:
        await db.close()
