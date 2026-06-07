import json
import logging
from pathlib import Path

from langchain.tools import tool, ToolRuntime

from src.agent.state import TrainAgentState
from src.storage.database import Database
from src.storage.file_store import FileStore

logger = logging.getLogger(__name__)


class OutputSaveError(RuntimeError):
    pass


def _ppt_skill_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "skills" / "ppt"


def _inline_ppt_assets(html: str, skill_dir: Path | None = None) -> str:
    if "./assets/" not in html:
        return html

    import re

    skill_dir = skill_dir or _ppt_skill_dir()
    assets_dir = skill_dir / "assets"
    if not assets_dir.exists():
        raise OutputSaveError(
            f"PPT assets directory missing: {assets_dir}. "
            "Cannot create a standalone HTML deck."
        )

    link_re = re.compile(
        r'<link\s[^>]*href="(\./assets/[^"]+)"[^>]*/?>',
        re.IGNORECASE,
    )
    script_re = re.compile(
        r'<script\s[^>]*src="(\./assets/[^"]+)"[^>]*>\s*</script>',
        re.IGNORECASE,
    )

    def read_asset(relative_path: str) -> str:
        clean = relative_path.removeprefix("./assets/")
        file_path = assets_dir / clean
        if not file_path.exists():
            raise OutputSaveError(f"PPT asset not found: {file_path}")
        return file_path.read_text(encoding="utf-8", errors="ignore")

    def replace_link(match: re.Match) -> str:
        return f"<style>\n{read_asset(match.group(1))}\n</style>"

    def replace_script(match: re.Match) -> str:
        return f"<script>\n{read_asset(match.group(1))}\n</script>"

    bundled = link_re.sub(replace_link, html)
    bundled = script_re.sub(replace_script, bundled)
    if "./assets/" in bundled:
        raise OutputSaveError("PPT HTML still contains unresolved ./assets/ references.")
    return bundled


async def save_output_artifact(
    db: Database,
    file_store: FileStore,
    workspace_id: str,
    type: str,
    title: str,
    content: str,
    filename: str = "",
) -> tuple[dict, str]:
    task = await db.create_task(
        workspace_id=workspace_id, type=type, title=title
    )
    logger.info("[Tool:save_output] task created (pending): id=%s", task["id"])

    try:
        if not filename:
            safe_title = title.replace(" ", "_").replace("/", "_")
            ext_map = {"ppt": ".html", "report": ".md"}
            filename = f"{safe_title}{ext_map.get(type, '.txt')}"

        final_content = content

        file_path = await file_store.save_async(
            workspace_id,
            f"outputs/{filename}",
            final_content.encode("utf-8"),
        )
        logger.info("[Tool:save_output] file saved to: %s", file_path)

        result_data = json.dumps({"file_path": file_path, "filename": filename})
        await db.update_task(
            task["id"], status="completed", result_data=result_data
        )
        logger.info("[Tool:save_output] task completed: id=%s", task["id"])
        return task, f"产出已保存: {title}。用户可在右侧产出面板查看和下载。"
    except Exception as exc:
        await db.update_task(
            task["id"],
            status="failed",
            result_data=json.dumps({"error": str(exc), "filename": filename}),
        )
        logger.error("[Tool:save_output] failed: %s", exc, exc_info=True)
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
        """保存 Skill 执行的产出物。当你完成了一个产出（如 PPT、报告等）时，使用此工具保存结果。
        产出物会出现在用户的产出面板中，可预览和下载。

        Args:
            type: 产出类型，如 'ppt', 'report'
            title: 产出标题
            content: 产出内容（如 HTML 文本）
            filename: 保存的文件名（可选，默认根据 title 和 type 自动生成）
        """
        workspace_id = runtime.state.get("workspace_id", "default")
        logger.info("[Tool:save_output] type=%s, title=%s, content_len=%d, workspace=%s",
                     type, title, len(content), workspace_id)

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
