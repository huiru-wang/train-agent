import json
import logging

from langchain.tools import tool, ToolRuntime

from src.agent.state import TrainAgentState
from src.storage.database import Database
from src.storage.file_store import FileStore

logger = logging.getLogger(__name__)


async def save_output_artifact(
    db: Database,
    file_store: FileStore,
    workspace_id: str,
    type: str,
    title: str,
    content: str,
    filename: str = "",
) -> tuple[dict, str]:
    """Save an output artifact to the file store and create a task record in DB."""
    if not filename:
        safe_title = title.replace(" ", "_").replace("/", "_")
        extension_map = {"ppt": ".html", "report": ".md"}
        filename = f"{safe_title}{extension_map.get(type, '.txt')}"

    task = await db.create_task(
        workspace_id=workspace_id, type=type, title=title
    )
    logger.info("[save_output] task created: id=%s, type=%s, title=%s", task["id"], type, title)

    try:
        content_bytes = content.encode("utf-8")
        file_path = await file_store.save_async(
            workspace_id,
            f"outputs/{filename}",
            content_bytes,
        )
        logger.info("[save_output] file saved: %s (%d bytes)", file_path, len(content_bytes))

        result_data = json.dumps(
            {"file_path": file_path, "filename": filename},
            ensure_ascii=False,
        )
        await db.update_task(
            task["id"], status="completed", result_data=result_data
        )
        return task, f"产出已保存: {title}。用户可在右侧产出面板查看和下载。"

    except Exception as exc:
        await db.update_task(
            task["id"],
            status="failed",
            result_data=json.dumps({"error": str(exc), "filename": filename}),
        )
        logger.error("[save_output] failed: %s", exc, exc_info=True)
        return task, f"产出保存失败: {exc}"


def create_save_output_tool(db: Database, file_store: FileStore):
    @tool
    async def save_output(
        runtime: ToolRuntime[TrainAgentState],
        type: str,
        title: str,
        content: str,
        filename: str = "",
    ) -> str:
        """保存产出物（PPT、报告等）。这是将产出物交付给用户的唯一方式。

        调用后，产出物会出现在用户的右侧产出面板中，可预览和下载。
        你必须在完成产出内容后调用此工具，否则用户无法获取结果。

        Args:
            type: 产出文件类型 — 'ppt' | 'report'
            title: 产出标题，如"新员工消防培训"
            content: 完整的产出内容（PPT 为自包含 HTML，报告为 Markdown）
            filename: 文件名（可选，默认根据 title + type 自动生成）
        """
        workspace_id = runtime.state.get("workspace_id", "default")
        logger.info(
            "[save_output] type=%s, title=%s, content_len=%d, workspace=%s",
            type, title, len(content), workspace_id,
        )

        _, message = await save_output_artifact(
            db=db,
            file_store=file_store,
            workspace_id=workspace_id,
            type=type,
            title=title,
            content=content,
            filename=filename,
        )
        return message

    return save_output
