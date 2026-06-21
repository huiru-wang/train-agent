import json
import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.managers.prompt_manager import SYSTEM_PROMPT
from src.storage.database import Database

logger = logging.getLogger(__name__)


class ContextInjectMiddleware(AgentMiddleware):
    """Inject dynamic document context and PPT metadata into the system prompt."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        workspace_id = request.state.get("workspace_id", "default")
        ppt_style = request.state.get("ppt_style", "")
        voice_id = request.state.get("voice_id", "")
        current_ppt_task_id = request.state.get("current_ppt_task_id", "")
        doc_summaries = []
        ppt_tasks_info = []

        if self.db:
            if self.db.connection is None:
                await self.db.initialize()
            docs = await self.db.list_documents(workspace_id)
            doc_summaries = [
                f"[{d['filename']}](doc_id:{d['id']}): {d['summary']}"
                for d in docs
                if d.get("summary")
            ]

            # Query PPT tasks and extract metadata for system prompt injection
            ppt_tasks = await self.db.list_tasks(workspace_id)
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
                if not isinstance(outline, dict):
                    outline = {}
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

        # Build dynamic system prompt
        prompt = SYSTEM_PROMPT
        if doc_summaries:
            summaries_text = "\n".join(f"- {s}" for s in doc_summaries)
            prompt += f"\n\n## 当前知识库文档摘要\n{summaries_text}"

        # Fetch workspace once for both ppt_style and voice_info
        ws = None
        ext_data: dict = {}
        if self.db and self.db.connection:
            try:
                ws = await self.db.get_workspace(workspace_id)
                ext_data = (ws.get("ext_data") or {}) if ws else {}
            except Exception:
                logger.warning("[ContextInjectMiddleware] failed to fetch workspace=%s", workspace_id)

        # Build user preference section (ppt_style + voice)
        pref_lines: list[str] = []
        style_record = None

        if ppt_style:
            try:
                user_id = ws.get("user_id", "") if ws else ""
                style_record = await self.db.get_ppt_style_by_name_en(ppt_style, user_id=user_id)
            except Exception:
                logger.warning("[ContextInjectMiddleware] failed to look up ppt_style=%s", ppt_style)

            if style_record and style_record.get("style_description"):
                pref_lines.append(
                    f"- PPT视觉风格：{style_record['name']}（{ppt_style}）"
                    f"（用户已预选，生成PPT时直接使用该风格，跳过风格询问步骤）"
                )
            else:
                pref_lines.append(
                    f"- PPT视觉风格：{ppt_style}（用户已预选，生成PPT时直接使用该风格，跳过风格询问步骤）"
                )

        # Voice preference from ext_data.voice_info
        voice_info = ext_data.get("voice_info") if ext_data else None
        if voice_info and isinstance(voice_info, dict) and voice_info.get("name"):
            gender_map = {"female": "女性", "male": "男性"}
            gender_label = gender_map.get(voice_info.get("gender", ""), "")
            voice_line = f"- 语音音色：{voice_info['name']}"
            if gender_label:
                voice_line += f"（{gender_label}"
                if voice_info.get("trait"):
                    voice_line += f"，{voice_info['trait']}"
                voice_line += "）"
            elif voice_info.get("trait"):
                voice_line += f"（{voice_info['trait']}）"
            voice_line += "（生成口播稿时默认使用该音色）"
            pref_lines.append(voice_line)
        elif voice_id:
            # Fallback for old data without voice_info
            pref_lines.append(f"- 语音音色：{voice_id}（生成口播稿时默认使用该音色）")

        if pref_lines:
            prompt += f"\n\n## 用户配置偏好\n" + "\n".join(pref_lines)

        # Append style_description after preference section (separate sub-heading)
        if style_record and style_record.get("style_description"):
            prompt += f"\n\n### 风格详细描述\n{style_record['style_description']}"

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
            f"""
            [ContextInjectMiddleware] context_inject | 
            workspaceId={workspace_id} | 
            ppt_style={ppt_style} | 
            voice_id={voice_id} | 
            current_ppt_task_id={current_ppt_task_id} | 
            system_prompt={prompt}
            """
        )
        
        request = request.override(system_message=SystemMessage(content=prompt))
        return await handler(request)
