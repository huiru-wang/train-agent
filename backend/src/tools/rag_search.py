import logging

from langchain.tools import tool, ToolRuntime

from src.agent.state import TrainAgentState
from src.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _format_location(result: dict) -> str:
    """Build a human-readable location string like '五、MySQL数据库 > 5.3 SQL语句 (p.38)'."""
    parts: list[str] = []

    chapter = result.get("chapter_title", "")
    section = result.get("section_title", "")

    if chapter and section and chapter != section:
        parts.append(f"{chapter} > {section}")
    elif section:
        parts.append(section)
    elif chapter:
        parts.append(chapter)

    page_start = result.get("page_start", 0)
    page_end = result.get("page_end", 0)
    if page_start > 0:
        if page_end > page_start:
            parts.append(f"p.{page_start}-{page_end}")
        else:
            parts.append(f"p.{page_start}")

    if not parts:
        chunk_idx = result.get("chunk_index", 0)
        parts.append(f"第{chunk_idx + 1}段")

    return " | ".join(parts)


def create_rag_search_tool(vector_store: VectorStore):
    @tool
    def rag_search(runtime: ToolRuntime[TrainAgentState], query: str, top_k: int = 5) -> str:
        """从当前工作区的知识库中检索相关文档片段。当用户提出与文档内容相关的问题时使用。"""
        workspace_id = runtime.state.get("workspace_id", "default")
        logger.info("[Tool:rag_search] query='%s', top_k=%d, workspace=%s", query[:80], top_k, workspace_id)
        try:
            results = vector_store.search(
                workspace_id=workspace_id, query=query, top_k=top_k
            )
        except Exception as exc:
            logger.error("[Tool:rag_search] search failed: %s", exc, exc_info=True)
            return f"知识库检索失败: {exc}"
        if not results:
            logger.info("[Tool:rag_search] no results found")
            return "未找到相关文档内容。"
        output = []
        for i, result in enumerate(results):
            filename = result.get("filename", "unknown")
            location = _format_location(result)
            output.append(
                f"[片段{i + 1}] 📄 {filename} | {location}\n{result['text']}"
            )
        logger.info("[Tool:rag_search] returned %d results", len(results))
        return "\n\n".join(output)

    return rag_search
