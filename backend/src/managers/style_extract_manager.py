"""Style extraction manager: parse PPTX → LLM style description → LLM preview HTML."""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.managers.prompt_manager import PromptManager
from src.storage.database import Database
from src.storage.file_store import FileStore

logger = logging.getLogger(__name__)

# Re-exported for scripts/parse_pptx import
import sys as _sys

# Allow `from scripts.parse_pptx import parse_pptx` when running from backend/
_backend_dir = Path(__file__).resolve().parent.parent.parent
if str(_backend_dir) not in _sys.path:
    _sys.path.insert(0, str(_backend_dir))

from scripts.parse_pptx import parse_pptx as _parse_pptx  # noqa: E402


# ============================================================
# format_data: convert parse_pptx output to LLM-readable text
# ============================================================
def format_data(data: dict) -> str:
    """将 parse_pptx 输出的结构化数据格式化为 LLM 可读文本。"""
    lines: list[str] = []

    fi = data["file_info"]
    lines.append("=== PPTX 基本信息 ===")
    lines.append(f"- 幻灯片数: {fi['slide_count']}")
    lines.append(f"- 尺寸: {fi['width_inches']}\" x {fi['height_inches']}\" (比例 {fi['aspect_ratio']})")
    lines.append("")

    lines.append("=== 主题色方案 ===")
    for k, v in data["theme"]["colors"].items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("=== 主题字体方案 ===")
    for k, v in data["theme"]["fonts"].items():
        lines.append(f"  {k}: {v or '(空)'}")
    lines.append("")

    s = data["style_summary"]
    lines.append("=== 文字色频率 Top 15 ===")
    lines.append("  " + ", ".join(f"{c['color']}({c['count']})" for c in s["text_colors"]))
    lines.append("")
    lines.append("=== 填充色频率 Top 15 ===")
    lines.append("  " + ", ".join(f"{c['color']}({c['count']})" for c in s["fill_colors"]))
    lines.append("")
    lines.append("=== 字体使用频率 ===")
    lines.append("  " + ", ".join(f"{f['name']}({f['count']})" for f in s["fonts"]))
    lines.append("")
    lines.append("=== 字号分布 Top 15 ===")
    lines.append("  " + ", ".join(f"{sz['size_pt']}pt({sz['count']})" for sz in s["font_sizes"]))
    lines.append("")
    lines.append("=== 形状类型统计 ===")
    lines.append("  " + ", ".join(f"{t['type']}({t['count']})" for t in s["shape_types"]))
    lines.append("")
    lines.append("=== 布局类型分布 ===")
    lines.append(f"  {json.dumps(s['layout_distribution'], ensure_ascii=False)}")
    lines.append(f"  有图片的页数: {s['slides_with_images']}")
    lines.append(f"  有表格的页数: {s['slides_with_tables']}")
    lines.append(f"  有图表的页数: {s['slides_with_charts']}")
    lines.append("")

    img = data["image_analysis"]
    lines.append("=== 背景图分析 ===")
    for bg in img["background_images"]:
        colors_str = ", ".join(f"{c['color']}({c['pct']}%)" for c in bg["dominant_colors"][:4])
        lines.append(f"  - 尺寸{bg['dimensions']}, {bg['size_kb']}KB, 用于slide {bg['used_in_slides']}")
        lines.append(f"    主色: {colors_str}")
    lines.append("")
    lines.append("=== 小图标信息 ===")
    lines.append(f"  数量: {img['icon_count']} 张")
    lines.append(f"  平均大小: {img['icon_avg_size_bytes']} 字节")
    lines.append("")

    lines.append("=== 每页摘要 ===")
    for slide in s["slide_summaries"]:
        tags = []
        if slide["has_image"]:
            tags.append("有图")
        if slide["has_table"]:
            tags.append("有表")
        if slide["has_chart"]:
            tags.append("有图表")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"  slide {slide['index']:2d}: {slide['shape_count']:2d} shapes, {slide['layout_type']}{tag_str}")
    lines.append("")

    return "\n".join(lines)


def _parse_style_response(llm_output: str) -> dict:
    """解析风格描述 LLM 输出。

    优先尝试直接 json.loads（JSON mode 下 LLM 直接返回纯 JSON）。
    失败时回退到从 markdown fence 中提取 JSON。
    返回 dict with keys: name, name_en, description, style_description。
    """
    cleaned = llm_output.strip()

    # Primary: direct JSON parse (response_format=json_object mode)
    try:
        data = json.loads(cleaned)
        return {
            "name": data.get("name", "").strip(),
            "name_en": data.get("name_en", "").strip(),
            "description": data.get("description", "").strip(),
            "style_description": data.get("style_description", "").strip(),
        }
    except json.JSONDecodeError:
        pass

    # Fallback: strip markdown code fence and try again
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", cleaned)
    if fence_match:
        json_str = fence_match.group(1).strip()
        try:
            data = json.loads(json_str)
            return {
                "name": data.get("name", "").strip(),
                "name_en": data.get("name_en", "").strip(),
                "description": data.get("description", "").strip(),
                "style_description": data.get("style_description", "").strip(),
            }
        except json.JSONDecodeError:
            pass

    # Final fallback: extract JSON object from text
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return {
                "name": data.get("name", "").strip(),
                "name_en": data.get("name_en", "").strip(),
                "description": data.get("description", "").strip(),
                "style_description": data.get("style_description", "").strip(),
            }
        except json.JSONDecodeError:
            pass

    logger.warning("[StyleExtract] failed to parse JSON from LLM output, using raw text")
    return {
        "name": "",
        "name_en": "",
        "description": "",
        "style_description": cleaned,
    }


def _resolve_style_names(parsed: dict) -> tuple[str, str]:
    """从解析结果中确定风格名称。
    优先使用 JSON 中的 name/name_en，fallback 到从 description 提取。
    返回 (name, name_en)。
    """
    name = parsed.get("name", "")
    name_en = parsed.get("name_en", "")

    # Fallback: extract from description
    if not name:
        desc = parsed.get("description", "")
        if desc:
            cn_match = re.match(r"([\u4e00-\u9fff]{2,6})", desc)
            if cn_match:
                name = cn_match.group(1)

    # Fallback: first heading in style_description
    if not name:
        sd = parsed.get("style_description", "")
        m = re.search(r"^#+\s+(.+)", sd, re.MULTILINE)
        if m:
            name = m.group(1).strip()

    name = name or "未命名风格"

    # Ensure name_en is kebab-case
    if name_en:
        name_en = re.sub(r"[^a-zA-Z0-9\s-]", "", name_en).strip().lower()
        name_en = re.sub(r"\s+", "-", name_en)

    # If still no English name, generate hash-based slug
    if not name_en or not re.search(r"[a-z]", name_en):
        short_hash = hashlib.md5(name.encode()).hexdigest()[:6]
        name_en = f"style-{short_hash}"

    return name, name_en


class StyleExtractManager:
    """管理 PPTX 风格提取的完整异步工作流。"""

    def __init__(self, db: Database, file_store: FileStore):
        self.db = db
        self.file_store = file_store
        self._prompt_manager = PromptManager()
        self._active_tasks: dict[str, asyncio.Event] = {}
        # JSON mode LLM: 用于 style_description 生成，强制 JSON 输出
        self._json_llm = ChatOpenAI(
            model=os.getenv("SUMMARIZATION_MODEL"),
            api_key=os.getenv("SUMMARIZATION_API_KEY"),
            base_url=os.getenv("SUMMARIZATION_API_BASE"),
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        # 纯文本 LLM: 用于 preview_html 生成
        self._text_llm = ChatOpenAI(
            model=os.getenv("SUMMARIZATION_MODEL"),
            api_key=os.getenv("SUMMARIZATION_API_KEY"),
            base_url=os.getenv("SUMMARIZATION_API_BASE"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_extraction(self, task_id: str, workspace_id: str, pptx_path: str):
        """异步执行完整风格提取工作流。

        Steps:
        1. parsing  — 解析 PPTX 结构
        2. analyzing_style — LLM 生成风格描述
        3. generating_preview — LLM 生成预览 HTML
        4. completed — 保存产出文件
        """
        cancel_event = asyncio.Event()
        self._active_tasks[task_id] = cancel_event
        pptx_filename = Path(pptx_path).name

        try:
            # --- Step 1: Parse PPTX ---
            await self._check_cancel(cancel_event)
            await self._update_progress(task_id, "parsing", pptx_filename=pptx_filename)

            with tempfile.TemporaryDirectory(prefix="style_extract_") as tmp_dir:
                pptx_data = await asyncio.to_thread(_parse_pptx, pptx_path, tmp_dir)

            data_text = format_data(pptx_data)
            logger.info(f"[StyleExtract] PARSED task={task_id} data_text={data_text}")

            # --- Step 2: LLM — Style Description ---
            await self._check_cancel(cancel_event)
            await self._update_progress(task_id, "analyzing_style", pptx_filename=pptx_filename)

            style_description_prompt = self._prompt_manager.build_style_description_prompt(data_text)
            raw_style_output = await self._llm_invoke(
                self._json_llm,
                style_description_prompt, "请根据以上 PPTX 解析数据，生成风格描述 JSON。"
            )
            logger.info(f"[StyleExtract] STYLE_DESC task={task_id} style_output={raw_style_output}")

            # Parse JSON response into structured data
            parsed = _parse_style_response(raw_style_output)
            short_description = parsed["description"]
            style_description = parsed["style_description"]

            # Fallback: if description is empty, extract from style_description Vibe line
            if not short_description and style_description:
                vibe_match = re.search(r"Vibe[：:]\s*(.+)", style_description)
                if vibe_match:
                    short_description = vibe_match.group(1).strip()

            # Resolve style names (prefer JSON name fields, fallback to extraction)
            style_name, style_name_en = _resolve_style_names(parsed)

            # --- Step 3: LLM — Preview HTML ---
            await self._check_cancel(cancel_event)
            await self._update_progress(
                task_id, "generating_preview",
                pptx_filename=pptx_filename,
                description=short_description,
                style_description=style_description,
                style_name=style_name,
                style_name_en=style_name_en,
            )

            preview_html_prompt = self._prompt_manager.build_preview_html_prompt(style_description, data_text)
            preview_html = await self._llm_invoke(
                self._text_llm,
                preview_html_prompt, "请严格按照以上风格规范，生成完整的预览 HTML 文件。"
            )
            logger.info(f"[StyleExtract] PREVIEW_HTML task={task_id} preview_html={preview_html}")
            
            # 清理 LLM 输出中可能的 markdown 代码块包裹
            preview_html = self._strip_code_fence(preview_html)

            # --- Step 4: Save & Complete ---
            await self._check_cancel(cancel_event)

            output_dir = f"outputs/{task_id}"
            preview_path = await self.file_store.save_async(
                workspace_id, f"{output_dir}/preview.html", preview_html.encode("utf-8")
            )

            result_data = {
                "description": short_description,
                "style_description": style_description,
                "style_name": style_name,
                "style_name_en": style_name_en,
                "preview_html_path": preview_path,
                "pptx_filename": pptx_filename,
                "progress_step": "completed",
            }
            await self.db.update_task(
                task_id,
                status="completed",
                title=style_name,
                result_data=json.dumps(result_data, ensure_ascii=False),
            )
            logger.info(f"[StyleExtract] COMPLETED task={task_id} style_name={style_name}")

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
        """将已完成任务的产出保存为自定义风格到 ppt_style 表。"""
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
        source_preview_path = result_data.get("preview_html_path", "")

        # Fallback: if description is missing (old tasks), extract from style_description
        if not description:
            desc_match = re.search(r"Vibe[：:]\s*(.+)", style_description)
            description = desc_match.group(1).strip() if desc_match else style_description[:100]

        # Create style record in DB
        style = await self.db.create_ppt_style(
            user_id=user_id,
            category="custom",
            name=style_name,
            name_en=style_name_en,
            description=description,
            style_description=style_description,
            preview_path=source_preview_path,
        )

        # Copy preview HTML to independent user styles directory
        # Path: data/user/{user_id}/styles/{style_id}/preview.html
        if source_preview_path:
            source = Path(source_preview_path)
            if source.exists():
                data_dir = self.file_store.base_dir.parent
                style_dir = data_dir / "user" / user_id / "styles" / style["id"]
                style_dir.mkdir(parents=True, exist_ok=True)
                dest = style_dir / "preview.html"
                dest.write_bytes(source.read_bytes())
                style_preview_path = str(dest)
                await self.db.update_ppt_style_preview_path(style["id"], style_preview_path)
                style["preview_path"] = style_preview_path
                logger.info("[StyleExtract] copied preview HTML to: %s", style_preview_path)

        # Mark task as saved to prevent duplicate saves
        result_data["saved_style_id"] = style["id"]
        await self.db.update_task(
            task_id,
            result_data=json.dumps(result_data, ensure_ascii=False),
        )

        logger.info("[StyleExtract] saved custom style: id=%s name=%s user=%s", style["id"], style_name, user_id)
        return style

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _update_progress(self, task_id: str, step: str, **extra):
        """更新 task 的 status 和 result_data 中的 progress_step。"""
        # Preserve existing result_data fields
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

        处理三种情况：
        1. ```html ... ``` code fence（提取 fence 内的内容）
        2. ``` ... ``` code fence（同上）
        3. 无 code fence（直接 strip）
        """
        text = text.strip()
        # Try to find content inside a code fence (```html or ```)
        fence_match = re.search(r"```(?:html)?\s*\n?([\s\S]*?)\n?\s*```", text)
        if fence_match:
            return fence_match.group(1).strip()
        # No code fence found, just strip
        return text


class _CancelledError(Exception):
    """内部取消信号。"""
    pass
