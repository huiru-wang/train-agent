from typing import Any

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AnyMessage, HumanMessage


class TrainAgentSummarizationMiddleware(SummarizationMiddleware):
    """Train Agent summarization with UI-safe markers and a simple cooldown."""

    def __init__(
        self,
        *args,
        min_messages_since_summary: int = 8,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.min_messages_since_summary = min_messages_since_summary

    def _should_summarize(self, messages: list[AnyMessage], total_tokens: int) -> bool:
        if not super()._should_summarize(messages, total_tokens):
            return False

        last_summary_index = self._last_summary_index(messages)
        if last_summary_index is None:
            return True

        messages_since_summary = len(messages) - last_summary_index - 1
        return messages_since_summary >= self.min_messages_since_summary

    @staticmethod
    def _build_new_messages(summary: str) -> list[HumanMessage]:
        return [
            HumanMessage(
                content=f"Here is a summary of the conversation to date:\n\n{summary}",
                additional_kwargs={
                    "lc_source": "summarization",
                    "train_agent_hidden": True,
                },
            )
        ]

    @staticmethod
    def _last_summary_index(messages: list[AnyMessage]) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            if _is_summary_message(messages[index]):
                return index
        return None


def _is_summary_message(message: Any) -> bool:
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if additional_kwargs is None and isinstance(message, dict):
        additional_kwargs = message.get("additional_kwargs")
    return (
        isinstance(additional_kwargs, dict)
        and additional_kwargs.get("lc_source") == "summarization"
    )
