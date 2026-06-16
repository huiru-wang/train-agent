import os

from src.agent.message_history import MessageHistoryCallback, MessageHistoryMiddleware
from src.app_context import AppContext
from src.middlewares.inject_doc_context import create_inject_doc_context
from src.middlewares.logging_middlewares import (
    log_after_agent,
    log_after_model,
    log_before_agent,
    log_before_model,
)
from src.middlewares.model_message_sanitizer import sanitize_model_request
from src.middlewares.summarization import TrainAgentSummarizationMiddleware

__all__ = ["create_middlewares"]


def create_middlewares(
    ctx: AppContext,
    message_history_callback: MessageHistoryCallback,
) -> list:
    """Create all agent middlewares in execution order."""
    return [
        log_before_agent,
        MessageHistoryMiddleware(message_history_callback),
        log_before_model,
        sanitize_model_request,
        create_inject_doc_context(ctx.db),
        log_after_model,
        log_after_agent,
        TrainAgentSummarizationMiddleware(
            model=os.getenv("MAIN_MODEL"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_API_BASE"),
            trigger=("tokens", 20000),
            keep=("messages", 8),
            trim_tokens_to_summarize=12000,
            min_messages_since_summary=8,
        ),
    ]
