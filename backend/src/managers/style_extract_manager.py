"""Style extraction manager: parse PPTX → LLM style template → LLM preview HTML."""

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.managers.prompt_manager import PromptManager
from src.storage.database import Database
from src.storage.file_store import FileStore

logger = logging.getLogger(__name__)

# Re-exported for scripts.parse_pptx import
import sys as _sys

# Allow `from scripts.parse_pptx import parse_pptx_to_markdown` when running from backend/
_backend_dir = Path(__file__).resolve().parent.parent.parent
if str(_backend_dir) not in _sys.path:
    _sys.path.insert(0, str(_backend_dir))

from scripts.parse_pptx import parse_pptx_to_markdown as _parse_pptx_to_markdown  # noqa: E402


# ============================================================
# Frontmatter Parsing
# ============================================================
def _parse_frontmatter(llm_output: str) -> dict:
    """Parse YAML frontmatter from LLM-generated Markdown.

    Expected format:
    ---
    name: 蓝色商务卡片风
    name_en: blue-business-card
    description: 深蓝商务风格，卡片式布局...
    ---

    # 蓝色商务卡片风
    ...

    Returns dict with keys: name, name_en, description, style_description (full markdown)
    """
    output = llm_output.strip()

    # Strip code fence if present (```markdown ... ```)
    fence_match = re.search(r"```(?:markdown)?\s*\n?([\s\S]*?)\n?\s*```", output)
    if fence_match:
        output = fence_match.group(1).strip()

    # Extract YAML frontmatter between --- delimiters
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n([\s\S]*)$", output, re.DOTALL)
    if not fm_match:
        logger.warning("[StyleExtract] no YAML frontmatter found in LLM output")
        return {
            "name": "",
            "name_en": "",
            "description": "",
            "style_description": output,
        }

    frontmatter_text = fm_match.group(1)
    body = fm_match.group(2)
    full_markdown = output  # Keep the complete markdown as style_description

    # Parse simple YAML key-value pairs (name, name_en, description)
    name = ""
    name_en = ""
    description = ""

    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if line.startswith("name:"):
            val = line[len("name:"):].strip().strip("\"'")
            # Don't overwrite name_en with name
            if "name_en" not in line[:7]:
                name = val
        elif line.startswith("name_en:"):
            name_en = line[len("name_en:"):].strip().strip("\"'")
        elif line.startswith("description:"):
            description = line[len("description:"):].strip().strip("\"'")

    # Reconstruct full markdown (frontmatter + body) as style_description
    style_description = f"---\n{frontmatter_text}\n---\n{body}"

    return {
        "name": name,
        "name_en": name_en,
        "description": description,
        "style_description": style_description,
    }


def _resolve_style_name_en(name_en: str, name: str) -> str:
    """Ensure name_en is valid kebab-case. Generate fallback if needed."""
    if name_en:
        name_en = re.sub(r"[^a-zA-Z0-9\s-]", "", name_en).strip().lower()
        name_en = re.sub(r"\s+", "-", name_en)

    if not name_en or not re.search(r"[a-z]", name_en):
        fallback = name or "unnamed"
        short_hash = hashlib.md5(fallback.encode()).hexdigest()[:6]
        name_en = f"style-{short_hash}"

    return name_en


class StyleExtractManager:
    """管理 PPTX 风格提取的完整异步工作流。"""

    def __init__(self, db: Database, file_store: FileStore):
        self.db = db
        self.file_store = file_store
        self._prompt_manager = PromptManager()
        self._active_tasks: dict[str, asyncio.Event] = {}
        # 纯文本 LLM: 用于 style_description 和 preview_html 生成
        self._text_llm = ChatOpenAI(
            model=os.getenv("SUMMARIZATION_MODEL"),
            api_key=os.getenv("SUMMARIZATION_API_KEY"),
            base_url=os.getenv("SUMMARIZATION_API_BASE"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_extraction(self, task_id: str, workspace_id: str, pptx_content: bytes, pptx_filename: str):
        """异步执行完整风格提取工作流。

        Steps:
        1. parsing — 保存源 PPTX + 解析为 Markdown + 提取图片资源
        2. analyzing_style — LLM 生成风格模板（Markdown + frontmatter）
        3. generating_preview — LLM 生成预览 HTML
        4. completed — 保存产出文件
        """
        cancel_event = asyncio.Event()
        self._active_tasks[task_id] = cancel_event

        try:
            # --- Step 1: Save source PPTX + Parse + Extract images ---
            await self._check_cancel(cancel_event)
            await self._update_progress(task_id, "parsing", pptx_filename=pptx_filename)

            # Resolve user_id for path construction
            user_id = await self.file_store._resolve_user_id(workspace_id)
            ws_prefix = self.file_store._ws_prefix(user_id, workspace_id)

            # Save source PPTX to: user/{user_id}/workspace/{workspace_id}/style/{task_id}/{pptx_filename}
            pptx_key = f"{ws_prefix}/style/{task_id}/{pptx_filename}"
            await self.file_store._provider.save_async(pptx_key, pptx_content)
            logger.info("[StyleExtract] saved source PPTX: %s", pptx_key)

            # Determine resource base URL for image paths in Markdown
            resource_prefix = f"{ws_prefix}/style/{task_id}"
            if self.file_store._provider.is_local:
                # Local mode: use the served file URL pattern
                resource_base_url = ""  # Keep original relative paths
            else:
                # OSS mode: use public URL for the resource directory
                resource_base_url = self.file_store._provider.get_public_url(resource_prefix)

            # Parse PPTX to Markdown, extracting images to temp resource dir
            with tempfile.TemporaryDirectory(prefix="style_extract_") as tmp_dir:
                tmp_pptx = Path(tmp_dir) / pptx_filename
                tmp_pptx.write_bytes(pptx_content)

                markdown_text, media_files = await asyncio.to_thread(
                    _parse_pptx_to_markdown,
                    str(tmp_pptx),
                    tmp_dir,
                    resource_base_url,
                )

                # Upload extracted images to FileStore: style/{task_id}/resource/{filename}
                resource_dir = Path(tmp_dir) / "resource"
                if resource_dir.exists():
                    for img_file in sorted(resource_dir.iterdir()):
                        if img_file.is_file():
                            img_key = f"{resource_prefix}/resource/{img_file.name}"
                            img_content = img_file.read_bytes()
                            await self.file_store._provider.save_async(img_key, img_content)
                            logger.debug("[StyleExtract] uploaded resource: %s", img_key)

            logger.info("[StyleExtract] PARSED task=%s markdown_len=%s media_count=%s", task_id, markdown_text, media_files)

            # --- Step 2: LLM — Style Template ---
            await self._check_cancel(cancel_event)
            await self._update_progress(task_id, "analyzing_style", pptx_filename=pptx_filename)

            style_desc_prompt = self._prompt_manager.build_style_description_prompt(markdown_text)
            raw_style_output = await self._llm_invoke(
                self._text_llm,
                style_desc_prompt,
                "请根据以上 PPTX 结构化解析报告，生成风格模版。",
            )
            logger.info("[StyleExtract] STYLE_TEMPLATE task=%s len=%d", task_id, len(raw_style_output))

            # Parse frontmatter for name/name_en/description
            parsed = _parse_frontmatter(raw_style_output)
            style_name = parsed["name"] or "未命名风格"
            style_name_en = _resolve_style_name_en(parsed["name_en"], style_name)
            description = parsed["description"]
            style_description = parsed["style_description"]

            # --- Step 3: LLM — Preview HTML ---
            await self._check_cancel(cancel_event)
            await self._update_progress(
                task_id, "generating_preview",
                pptx_filename=pptx_filename,
                description=description,
                style_description=style_description,
                style_name=style_name,
                style_name_en=style_name_en,
            )

            preview_html_prompt = self._prompt_manager.build_preview_html_prompt(
                style_description, resource_base_url
            )
            preview_html = await self._llm_invoke(
                self._text_llm,
                preview_html_prompt,
                "请严格按照以上风格模版，生成完整的预览 HTML 文件。",
            )
            logger.info("[StyleExtract] PREVIEW_HTML task=%s len=%d", task_id, len(preview_html))

            # Clean up markdown code fences from LLM output
            preview_html = self._strip_code_fence(preview_html)

            # --- Step 4: Save & Complete ---
            await self._check_cancel(cancel_event)

            # Save preview HTML to: user/{user_id}/workspace/{workspace_id}/style/{task_id}/preview.html
            preview_path = await self.file_store.save_style_output(
                workspace_id, task_id, "preview.html", preview_html.encode("utf-8")
            )

            result_data = {
                "description": description,
                "style_description": style_description,
                "style_name": style_name,
                "style_name_en": style_name_en,
                "preview_html_path": preview_path,
                "pptx_filename": pptx_filename,
                "pptx_storage_key": pptx_key,
                "resource_prefix": resource_prefix,
                "progress_step": "completed",
            }
            await self.db.update_task(
                task_id,
                status="completed",
                title=style_name,
                result_data=json.dumps(result_data, ensure_ascii=False),
            )
            logger.info("[StyleExtract] COMPLETED task=%s style_name=%s", task_id, style_name)

        except _CancelledError:
            logger.info("[StyleExtract] task=%s cancelled", task_id)
            await self.db.update_task(task_id, status="cancelled")
        except Exception as exc:
            logger.error("[StyleExtract] task=%s failed: %s", task_id, exc, exc_info=True)
            error_data = {"error": str(exc), "pptx_filename": pptx_filename, "progress_step": "failed"}
            await self.db.update_task(
                task_id, status="failed",
                result_data=json.dumps(error_data, ensure_ascii=False),
            )
        finally:
            self._active_tasks.pop(task_id, None)

    async def cancel_extraction(self, task_id: str):
        """中断正在执行的工作流。"""
        event = self._active_tasks.get(task_id)
        if event:
            event.set()
            logger.info("[StyleExtract] cancel requested for task=%s", task_id)

    async def save_as_custom_style(self, task_id: str, user_id: str) -> dict:
        """将已完成任务的产出保存为自定义风格到 ppt_style 表。

        Migrates all files (source PPTX, resource images, preview HTML)
        from the workspace task directory to the user style directory.
        """
        await self.db.ensure_initialized()
        task = await self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        if task["status"] != "completed":
            raise ValueError(f"Task not completed: {task_id} (status={task['status']})")

        result_data = task.get("result_data")
        if isinstance(result_data, str):
            result_data = json.loads(result_data)
        if not result_data:
            raise ValueError(f"Task has no result_data: {task_id}")

        # Duplicate save check
        if result_data.get("saved_style_id"):
            raise ValueError("该风格已保存，请勿重复操作")

        style_name = result_data.get("style_name", "未命名风格")
        style_name_en = result_data.get("style_name_en", "unnamed-style")
        style_description = result_data.get("style_description", "")
        description = result_data.get("description", "")

        # Create style record in DB
        style = await self.db.create_ppt_style(
            user_id=user_id,
            category="custom",
            name=style_name,
            name_en=style_name_en,
            description=description,
            style_description=style_description,
            preview_path="",  # Will be updated after migration
        )

        style_id = style["id"]

        # Migrate all resources from task directory to user style directory
        resource_prefix = result_data.get("resource_prefix", "")
        pptx_storage_key = result_data.get("pptx_storage_key", "")
        preview_html_path = result_data.get("preview_html_path", "")

        target_prefix = f"user/{user_id}/style/{style_id}"

        try:
            # 1. Migrate source PPTX
            if pptx_storage_key:
                pptx_filename = result_data.get("pptx_filename", "source.pptx")
                content = await self.file_store.read(pptx_storage_key)
                dest_key = f"{target_prefix}/{pptx_filename}"
                await self.file_store._provider.save_async(dest_key, content)
                logger.info("[StyleExtract] migrated PPTX to: %s", dest_key)

            # 2. Migrate resource images (resource/ subdirectory)
            if resource_prefix:
                src_resource_prefix = f"{resource_prefix}/resource/"
                # For OSS: list objects with prefix and copy
                # For local: copy directory contents
                if not self.file_store._provider.is_local:
                    # OSS: iterate and copy
                    import oss2  # type: ignore
                    provider = self.file_store._provider
                    for obj in oss2.ObjectIterator(provider._bucket, prefix=src_resource_prefix):
                        if obj.key.endswith("/"):
                            continue  # Skip directory markers
                        filename = obj.key.split("/")[-1]
                        content = await self.file_store.read(obj.key)
                        dest_key = f"{target_prefix}/resource/{filename}"
                        await self.file_store._provider.save_async(dest_key, content)
                        logger.debug("[StyleExtract] migrated resource: %s -> %s", obj.key, dest_key)
                else:
                    # Local: copy directory
                    src_dir = self.file_store.base_dir / src_resource_prefix.rstrip("/")
                    if src_dir.exists() and src_dir.is_dir():
                        for img_file in sorted(src_dir.iterdir()):
                            if img_file.is_file():
                                content = img_file.read_bytes()
                                dest_key = f"{target_prefix}/resource/{img_file.name}"
                                await self.file_store._provider.save_async(dest_key, content)
                                logger.debug("[StyleExtract] migrated resource: %s", dest_key)

            # 3. Migrate preview HTML
            if preview_html_path:
                if await self.file_store.exists(preview_html_path):
                    content = await self.file_store.read(preview_html_path)
                    dest_key = f"{target_prefix}/preview.html"
                    new_preview_path = await self.file_store._provider.save_async(dest_key, content)
                    await self.db.update_ppt_style_preview_path(style_id, new_preview_path)
                    style["preview_path"] = new_preview_path
                    logger.info("[StyleExtract] migrated preview HTML to: %s", new_preview_path)

        except Exception as e:
            logger.error("[StyleExtract] file migration failed for style %s: %s", style_id, e, exc_info=True)
            # Don't fail the save - DB record is already created

        # Mark task as saved to prevent duplicate saves
        result_data["saved_style_id"] = style_id
        await self.db.update_task(
            task_id,
            result_data=json.dumps(result_data, ensure_ascii=False),
        )

        logger.info("[StyleExtract] saved custom style: id=%s name=%s user=%s", style_id, style_name, user_id)
        return style

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _update_progress(self, task_id: str, step: str, **extra):
        """更新 task 的 status 和 result_data 中的 progress_step。"""
        existing = await self.db.get_task_result_data(task_id)
        existing["progress_step"] = step
        existing.update(extra)
        await self.db.update_task(
            task_id,
            status="generating",
            result_data=json.dumps(existing, ensure_ascii=False),
        )

    async def _check_cancel(self, event: asyncio.Event):
        if event.is_set():
            raise _CancelledError()

    async def _llm_invoke(self, llm: ChatOpenAI, system_prompt: str, user_message: str) -> str:
        """调用指定 LLM 并返回文本内容。"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        response = await llm.ainvoke(messages)
        return response.content

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """从 LLM 输出中提取纯 HTML 内容。

        Handles three cases:
        1. ```html ... ``` code fence
        2. ``` ... ``` code fence
        3. No code fence (just strip)
        """
        text = text.strip()
        fence_match = re.search(r"```(?:html)?\s*\n?([\s\S]*?)\n?\s*```", text)
        if fence_match:
            return fence_match.group(1).strip()
        return text


class _CancelledError(Exception):
    """内部取消信号。"""
    pass
