import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.message_history import MessageHistoryCallback, MessageHistoryMiddleware
from src.storage.database import Database


@pytest.mark.asyncio
async def test_message_history_callback_records_new_messages_once(tmp_path):
    db = Database(str(tmp_path / "train_agent.db"))
    await db.initialize()
    callback = MessageHistoryCallback(db)

    messages = [
        HumanMessage(id="human-1", content="请总结文档"),
        AIMessage(
            id="ai-1",
            content="我先检索资料。",
            tool_calls=[{"id": "call-1", "name": "rag_search", "args": {"query": "文档"}}],
        ),
        ToolMessage(id="tool-1", content="检索结果", tool_call_id="call-1", name="rag_search"),
    ]

    try:
        await callback.record_messages(
            thread_id="thread-a",
            workspace_id="workspace-1",
            messages=messages,
        )
        await callback.record_messages(
            thread_id="thread-a",
            workspace_id="workspace-1",
            messages=messages,
        )

        page = await db.list_thread_messages("thread-a", limit=10)

        assert [message["role"] for message in page["messages"]] == ["human", "ai", "tool"]
        assert page["messages"][0]["content"] == "请总结文档"
        assert page["messages"][1]["tool_calls"] == [
            {"id": "call-1", "name": "rag_search", "args": {"query": "文档"}}
        ]
        assert page["messages"][2]["tool_call_id"] == "call-1"
        assert page["messages"][2]["name"] == "rag_search"
    finally:
        await db.close()


def test_message_history_middleware_reads_thread_id_from_runtime_execution_info():
    middleware = MessageHistoryMiddleware(MessageHistoryCallback(db=None))
    runtime = type(
        "Runtime",
        (),
        {"execution_info": type("ExecutionInfo", (), {"thread_id": "thread-from-runtime"})()},
    )()

    assert middleware._thread_id(runtime) == "thread-from-runtime"


@pytest.mark.asyncio
async def test_message_history_callback_skips_summarization_messages(tmp_path):
    db = Database(str(tmp_path / "train_agent.db"))
    await db.initialize()
    callback = MessageHistoryCallback(db)

    try:
        await callback.record_messages(
            thread_id="thread-a",
            workspace_id="workspace-1",
            messages=[
                HumanMessage(id="human-1", content="正常问题"),
                AIMessage(
                    id="summary-1",
                    content="SESSION INTENT\nSUMMARY\n压缩后的内部摘要",
                    additional_kwargs={"lc_source": "summarization"},
                ),
            ],
        )

        page = await db.list_thread_messages("thread-a", limit=10)

        assert [message["message_id"] for message in page["messages"]] == ["human-1"]
    finally:
        await db.close()
