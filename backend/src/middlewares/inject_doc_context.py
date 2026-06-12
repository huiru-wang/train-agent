import logging

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from src.agent.prompt_manager import SYSTEM_PROMPT
from src.storage.database import Database

logger = logging.getLogger(__name__)


def create_inject_doc_context(db: Database):
    """工厂函数，返回注入文档上下文的 dynamic_prompt middleware。"""

    @dynamic_prompt
    async def inject_doc_context(request: ModelRequest) -> str:
        workspace_id = request.state.get("workspace_id", "default")
        doc_summaries = []
        if db:
            if db.connection is None:
                await db.initialize()
            docs = await db.list_documents(workspace_id)
            doc_summaries = [
                f"[{d['filename']}](doc_id:{d['id']}): {d['summary']}"
                for d in docs
                if d.get("summary")
            ]

        prompt = SYSTEM_PROMPT
        if doc_summaries:
            summaries_text = "\n".join(f"- {s}" for s in doc_summaries)
            prompt += f"\n\n## 当前知识库文档摘要\n{summaries_text}"

        logger.info(
            "[Middleware] inject_doc_context | workspace=%s | doc_count=%d",
            workspace_id,
            len(doc_summaries),
        )
        return prompt

    return inject_doc_context
