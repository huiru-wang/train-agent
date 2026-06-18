import json
import logging

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from src.agent.prompt_manager import SYSTEM_PROMPT
from src.storage.database import Database

logger = logging.getLogger(__name__)


def context_inject_middleware(db: Database):
    """工厂函数，返回注入文档上下文的 dynamic_prompt middleware。"""

    @dynamic_prompt
    async def inject_context(request: ModelRequest) -> str:
        workspace_id = request.state.get("workspace_id", "default")
        ppt_style = request.state.get("ppt_style", "")
        doc_summaries = []
        ppt_tasks_info = []
        if db:
            if db.connection is None:
                await db.initialize()
            docs = await db.list_documents(workspace_id)
            doc_summaries = [
                f"[{d['filename']}](doc_id:{d['id']}): {d['summary']}"
                for d in docs
                if d.get("summary")
            ]

            # Query PPT tasks and extract metadata for system prompt injection
            ppt_tasks = await db.list_tasks(workspace_id)
            for task in ppt_tasks:
                if task.get("status") != "completed":
                    continue
                result_data = {}
                if task.get("result_data"):
                    try:
                        result_data = json.loads(task["result_data"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                outline = result_data.get("outline", {})
                topic = outline.get("topic", "")
                summary = outline.get("summary", "")

                # Summarize children (e.g. narration tasks)
                children = task.get("children", [])
                child_labels = []
                for child in children:
                    ctype = child.get("type", "")
                    cstatus = child.get("status", "")
                    status_map = {
                        "completed": "✅已完成",
                        "narrating": "⏳文本生成中",
                        "tts_generating": "🔊音频生成中",
                        "tts_failed": "⚠️音频失败",
                        "failed": "❌失败",
                    }
                    type_map = {"narration": "口播稿"}
                    label = type_map.get(ctype, ctype)
                    label += status_map.get(cstatus, cstatus)
                    child_labels.append(label)
                children_text = ", ".join(child_labels) if child_labels else "无"

                ppt_tasks_info.append({
                    "id": task["id"],
                    "title": task.get("title", "未命名"),
                    "topic": topic,
                    "summary": summary,
                    "children": children_text,
                })

        # 注入当前工作区的文档内容摘要
        prompt = SYSTEM_PROMPT
        if doc_summaries:
            summaries_text = "\n".join(f"- {s}" for s in doc_summaries)
            prompt += f"\n\n## 当前知识库文档摘要\n{summaries_text}"

        # 注入用户配置偏好（PPT样式）
        if ppt_style:
            prompt += (
                f"\n\n## 用户配置偏好\n"
                f"- PPT视觉风格：{ppt_style}（用户已预选，生成PPT时直接使用该风格，跳过风格询问步骤）"
            )

        # 注入当前工作区的PPT任务
        if ppt_tasks_info:
            rows = []
            for t in ppt_tasks_info:
                rows.append(
                    f"| {t['id']} | {t['title']} | {t['topic']} | {t['summary']} | {t['children']} |"
                )
            table = (
                "| 任务ID | 标题 | 主题 | 摘要 | 子任务 |\n"
                "|--------|------|------|------|--------|\n"
            ) + "\n".join(rows)
            prompt += (
                f"\n\n## 当前PPT产出\n"
                f"以下是当前工作区已生成的 PPT，可用于口播稿生成等后续操作。\n"
                f"当用户请求生成口播稿但未指定 PPT 时，从此表格中引导用户选择。\n\n"
                f"{table}"
            )

        logger.info(
            "[Middleware] inject_doc_context | workspace=%s | ppt_style=%s | doc_count=%d | ppt_count=%d",
            workspace_id,
            ppt_style,
            len(doc_summaries),
            len(ppt_tasks_info),
        )
        return prompt

    return inject_context
