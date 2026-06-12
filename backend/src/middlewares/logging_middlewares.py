import logging

from langchain.agents.middleware import (
    AgentState,
    after_agent,
    after_model,
    before_agent,
    before_model,
)
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


@before_agent
def log_before_agent(state: AgentState, runtime: Runtime) -> None:
    """在 Agent 循环开始前打印日志。"""
    messages = state.get("messages", [])
    logger.info(
        "[Middleware] before_agent | workspace=%s | message_count=%d",
        state.get("workspace_id", "default"),
        len(messages),
    )


@after_agent
def log_after_agent(state: AgentState, runtime: Runtime) -> None:
    """在 Agent 循环结束后打印日志。"""
    messages = state.get("messages", [])
    logger.info(
        "[Middleware] after_agent | workspace=%s | total_messages=%d",
        state.get("workspace_id", "default"),
        len(messages),
    )


@before_model
def log_before_model(state: AgentState, runtime: Runtime) -> None:
    """在每次 LLM 调用前打印日志。"""
    messages = state.get("messages", [])
    logger.info(
        "[Middleware] before_model | workspace=%s | context_length=%d",
        state.get("workspace_id", "default"),
        len(messages),
    )


@after_model
def log_after_model(state: AgentState, runtime: Runtime) -> None:
    """在每次 LLM 响应后打印日志。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    tool_calls = getattr(last_message, "tool_calls", []) if last_message else []
    logger.info(
        "[Middleware] after_model | workspace=%s | tool_calls=%s",
        state.get("workspace_id", "default"),
        [tc.get("name") if isinstance(tc, dict) else tc.get("name", "") for tc in tool_calls],
    )
