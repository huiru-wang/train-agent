from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.middlewares.summarization import TrainAgentSummarizationMiddleware


def _middleware(*, trigger=("messages", 4), keep=("messages", 2), min_messages_since_summary=3):
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(text="compressed summary")
    return TrainAgentSummarizationMiddleware(
        model=model,
        trigger=trigger,
        keep=keep,
        token_counter=len,
        min_messages_since_summary=min_messages_since_summary,
    )


def test_summary_message_is_marked_hidden_for_ui_filtering():
    middleware = _middleware()

    result = middleware.before_model(
        {
            "messages": [
                HumanMessage(content="user-1"),
                AIMessage(content="assistant-1"),
                HumanMessage(content="user-2"),
                AIMessage(content="assistant-2"),
            ]
        },
        runtime=SimpleNamespace(),
    )

    summary_message = result["messages"][1]
    assert summary_message.additional_kwargs["lc_source"] == "summarization"
    assert summary_message.additional_kwargs["train_agent_hidden"] is True


def test_summary_cooldown_skips_when_too_few_messages_since_last_summary():
    middleware = _middleware(trigger=("messages", 3), keep=("messages", 1), min_messages_since_summary=3)

    result = middleware.before_model(
        {
            "messages": [
                HumanMessage(
                    content="Here is a summary of the conversation to date:\n\ncompressed summary",
                    additional_kwargs={"lc_source": "summarization"},
                ),
                HumanMessage(content="user-2"),
                AIMessage(content="assistant-2"),
            ]
        },
        runtime=SimpleNamespace(),
    )

    assert result is None
