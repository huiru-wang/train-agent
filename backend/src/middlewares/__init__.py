import os

from src.agent.message_history import MessageHistoryCallback, MessageHistoryMiddleware
from src.app_context import AppContext
from src.middlewares.context_inject_middleware import ContextInjectMiddleware
from src.middlewares.logging_middlewares import LoggingMiddleware
from src.middlewares.model_message_sanitizer import ModelMessageSanitizerMiddleware
from src.middlewares.summarization import TrainAgentSummarizationMiddleware

__all__ = ["create_middlewares"]


def create_middlewares(
    ctx: AppContext,
    message_history_callback: MessageHistoryCallback,
) -> list:
    """中间件统一注册, 注意顺序, 遵循洋葱模型"""
    return [
        ContextInjectMiddleware(ctx.db),
        MessageHistoryMiddleware(message_history_callback),
        ModelMessageSanitizerMiddleware(),
        TrainAgentSummarizationMiddleware(
            model=os.getenv("MAIN_MODEL"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_API_BASE"),
            trigger=("tokens", 40000),
            keep=("messages", 8),
            trim_tokens_to_summarize=12000,
            min_messages_since_summary=8,
        ),
        LoggingMiddleware(),
    ]
