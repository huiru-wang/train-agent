import json
import logging
import re
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.api.deps import db, doc_service, file_store, skill_manager, style_extract_manager, vector_store
from src.storage.database import _BUILTIN_VOICES

logger = logging.getLogger(__name__)

# Configure root logger for development
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Train Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logger.info("[API] starting up, initializing database...")
    await db.initialize()
    logger.info("[API] database initialized")


# --- Workspace ---


class CreateWorkspaceRequest(BaseModel):
    user_id: str
    name: str


@app.post("/api/workspaces")
async def create_workspace(req: CreateWorkspaceRequest):
    logger.info("[API] POST /api/workspaces user_id=%s name=%s", req.user_id, req.name)
    try:
        result = await db.create_workspace(user_id=req.user_id, name=req.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("[API] workspace created: id=%s", result["id"])
    return result


@app.get("/api/workspaces")
async def list_workspaces(user_id: str):
    logger.info("[API] GET /api/workspaces user_id=%s", user_id)
    return await db.list_workspaces(user_id=user_id)


@app.get("/api/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str):
    logger.info("[API] GET /api/workspaces/%s", workspace_id)
    workspace = await db.get_workspace(workspace_id)
    if not workspace:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


class UpdateThreadRequest(BaseModel):
    thread_id: str


class UpdateConfigRequest(BaseModel):
    key: str
    value: str | int | float | bool | dict | list | None


class SaveTaskFileRequest(BaseModel):
    content: str


@app.patch("/api/workspaces/{workspace_id}/thread")
async def update_workspace_thread(workspace_id: str, req: UpdateThreadRequest):
    logger.info("[API] PATCH /api/workspaces/%s/thread thread_id=%s", workspace_id, req.thread_id)
    await db.update_workspace_thread_id(workspace_id, req.thread_id)
    return {"ok": True}


@app.patch("/api/workspaces/{workspace_id}/config")
async def update_workspace_config(workspace_id: str, req: UpdateConfigRequest):
    logger.info("[API] PATCH /api/workspaces/%s/config key=%s value=%s", workspace_id, req.key, req.value)
    try:
        ext_data = await db.update_workspace_ext_data(workspace_id, req.key, req.value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "ext_data": ext_data}


@app.get("/api/threads/{thread_id}/messages")
async def list_thread_messages(
    thread_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    before: int | None = Query(default=None, ge=1),
):
    logger.info(
        "[API] GET /api/threads/%s/messages limit=%s before=%s",
        thread_id,
        limit,
        before,
    )
    return await db.list_thread_messages(thread_id, limit=limit, before=before)


@app.get("/api/threads/{thread_id}/messages/{message_id}")
async def get_message_detail(thread_id: str, message_id: str):
    logger.info(
        "[API] GET /api/threads/%s/messages/%s",
        thread_id,
        message_id,
    )
    msg = await db.get_message_by_id(message_id, thread_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@app.delete("/api/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    logger.info("[API] DELETE /api/workspaces/%s", workspace_id)
    # Delete all documents, vector store, and files
    await doc_service.delete_workspace(workspace_id)
    # Delete workspace record from database
    await db.delete_workspace(workspace_id)
    return {"ok": True}


# --- Documents ---


@app.post("/api/workspaces/{workspace_id}/documents")
async def upload_document(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    logger.info("[API] POST /api/workspaces/%s/documents filename=%s", workspace_id, file.filename)
    content = await file.read()
    logger.info("[API] file read: %d bytes", len(content))
    doc = await doc_service.create_document_upload(
        workspace_id=workspace_id,
        filename=file.filename,
        content=content,
    )
    background_tasks.add_task(doc_service.process_document, doc["id"])
    logger.info("[API] upload result: id=%s status=%s", doc["id"], doc["status"])
    return doc


@app.get("/api/workspaces/{workspace_id}/documents")
async def list_documents(workspace_id: str):
    logger.info("[API] GET /api/workspaces/%s/documents", workspace_id)
    return await db.list_documents(workspace_id)


@app.delete("/api/workspaces/{workspace_id}/documents/{doc_id}")
async def delete_document(workspace_id: str, doc_id: str):
    logger.info("[API] DELETE /api/workspaces/%s/documents/%s", workspace_id, doc_id)
    await doc_service.delete_document(workspace_id, doc_id)
    return {"ok": True}


# --- Tasks ---


@app.get("/api/workspaces/{workspace_id}/tasks")
async def list_tasks(workspace_id: str):
    logger.info("[API] GET /api/workspaces/%s/tasks", workspace_id)
    return await db.list_tasks(workspace_id)


@app.delete("/api/workspaces/{workspace_id}/tasks/{task_id}")
async def delete_task(workspace_id: str, task_id: str):
    logger.info("[API] DELETE /api/workspaces/%s/tasks/%s", workspace_id, task_id)

    # Get task info before deleting (for file cleanup)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Cascade delete from DB (returns all deleted task IDs)
    deleted_ids = await db.delete_task(task_id)

    # --- File cleanup (delegated to FileStore for local/OSS transparency) ---
    if task["type"] == "ppt":
        # PPT: remove entire ppt/{ppt_task_id}/ directory
        await file_store.delete_ppt_task_dir(workspace_id, task_id)
        logger.info("[API] removed PPT output directory for task: %s", task_id)
    elif task["type"] == "narration":
        # Narration: delete individual files from result_data
        result_data = {}
        if task.get("result_data"):
            try:
                result_data = json.loads(task["result_data"])
            except (json.JSONDecodeError, TypeError):
                pass
        # Delete audio files
        for slide in result_data.get("slides", []):
            audio_path = slide.get("audio_path")
            if audio_path:
                await file_store.delete_async(audio_path)
        # Delete narration text file
        text_file_path = result_data.get("text_file_path")
        if text_file_path:
            await file_store.delete_async(text_file_path)
        logger.info("[API] cleaned narration files for task: %s", task_id)
    elif task["type"] == "ppt_style_extraction":
        # Style extraction: remove style/{task_id}/ directory
        await file_store.delete_style_task_dir(workspace_id, task_id)
        logger.info("[API] removed style extraction output directory for task: %s", task_id)

    return {"ok": True, "deleted_ids": deleted_ids}


@app.put("/api/workspaces/{workspace_id}/tasks/{task_id}/file")
async def save_task_file(workspace_id: str, task_id: str, req: SaveTaskFileRequest):
    """Save updated HTML content back to a PPT task's file."""
    logger.info("[API] PUT /api/workspaces/%s/tasks/%s/file content_len=%d", workspace_id, task_id, len(req.content))
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result_data = {}
    if task.get("result_data"):
        try:
            result_data = json.loads(task["result_data"])
        except (json.JSONDecodeError, TypeError):
            pass
    file_path = result_data.get("file_path", "")
    if not file_path:
        raise HTTPException(status_code=404, detail="File path not found in task result_data")
    if not await file_store.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    await file_store.write_text(file_path, req.content)
    logger.info("[API] saved task file: %s (%d bytes)", file_path, len(req.content))
    return {"ok": True}


# --- Style Extraction ---


@app.post("/api/workspaces/{workspace_id}/style-extraction")
async def submit_style_extraction(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload a PPTX file and start style extraction workflow."""
    logger.info("[API] POST /api/workspaces/%s/style-extraction filename=%s", workspace_id, file.filename)
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are accepted")

    content = await file.read()
    # PPTX is a temporary file — do NOT save to storage.
    # It will be written to a temp dir inside run_extraction and cleaned up automatically.

    task = await db.create_task(
        workspace_id=workspace_id,
        type="ppt_style_extraction",
        title=f"风格提取: {file.filename}",
    )
    logger.info("[API] style extraction task created: id=%s", task["id"])

    background_tasks.add_task(
        style_extract_manager.run_extraction,
        task["id"], workspace_id, content, file.filename,
    )
    return task


@app.get("/api/workspaces/{workspace_id}/tasks/{task_id}")
async def get_task(workspace_id: str, task_id: str):
    """Get a single task by ID."""
    logger.info("[API] GET /api/workspaces/%s/tasks/%s", workspace_id, task_id)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/api/workspaces/{workspace_id}/style-extraction/{task_id}")
async def delete_style_extraction(workspace_id: str, task_id: str):
    """Cancel running extraction and delete the task."""
    logger.info("[API] DELETE /api/workspaces/%s/style-extraction/%s", workspace_id, task_id)

    # Cancel if running
    await style_extract_manager.cancel_extraction(task_id)

    # Use the generic delete_task logic (which handles file cleanup for ppt_style_extraction)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    deleted_ids = await db.delete_task(task_id)

    await file_store.delete_style_task_dir(workspace_id, task_id)
    logger.info("[API] removed style extraction output directory for task: %s", task_id)

    return {"ok": True, "deleted_ids": deleted_ids}


class SaveStyleRequest(BaseModel):
    user_id: str


@app.post("/api/style-extraction/{task_id}/save")
async def save_style_from_extraction(task_id: str, req: SaveStyleRequest):
    """Save completed extraction result as a custom PPT style."""
    logger.info("[API] POST /api/style-extraction/%s/save user_id=%s", task_id, req.user_id)
    try:
        style = await style_extract_manager.save_as_custom_style(task_id, req.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return style


# --- File download ---


@app.get("/api/ppt-styles")
async def list_ppt_styles(user_id: str = Query(default="")):
    """List PPT styles: system builtin + user custom (if user_id provided)."""
    logger.info("[API] GET /api/ppt-styles user_id=%s", user_id)
    user_ids = ["system"]
    if user_id:
        user_ids.append(user_id)
    return await db.list_all_ppt_styles(user_ids)


@app.get("/api/voices")
async def list_voices():
    """List available TTS voices from builtin seed data."""
    logger.info("[API] GET /api/voices")
    return _BUILTIN_VOICES


@app.delete("/api/ppt-styles/{style_id}")
async def delete_ppt_style(style_id: str):
    """Delete a custom PPT style and its preview file."""
    logger.info("[API] DELETE /api/ppt-styles/%s", style_id)
    # Verify it exists and is not a system style
    style = await db.get_ppt_style(style_id)
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")
    if style["user_id"] == "system":
        raise HTTPException(status_code=403, detail="Cannot delete system styles")
    # Delete preview file and its directory if it exists
    preview_path = style.get("preview_path", "")
    if preview_path:
        if file_store.is_local_path(preview_path):
            # Local path (legacy or new): delete the directory containing the preview
            style_dir = Path(preview_path).parent
            await file_store.delete_dir(str(style_dir))
            logger.info("[API] deleted style directory: %s", style_dir)
        else:
            # OSS: use delete_user_style which handles prefix deletion
            await file_store.delete_user_style(style["user_id"], style_id)
            logger.info("[API] deleted style files for user=%s style=%s", style["user_id"], style_id)
    await db.delete_ppt_style(style_id)
    return {"ok": True}


# Regex for stripping external font <link> tags (Google Fonts, loli, fontshare, gstatic)
_FONT_LINK_RE = re.compile(
    r'<link[^>]*href=["\'][^"\']*(?:fonts\.googleapis|fonts\.loli|fontshare|gstatic)[^"\']*["\'][^>]*/?>',
    re.IGNORECASE,
)


async def _serve_file(file_path: str, disposition: str, thumb: int = 0):
    """Unified file serving via FileStore (local / OSS transparent).

    Parameters
    ----------
    file_path:   relative key like ``user/{user_id}/workspace/...``
    disposition: ``"attachment"`` (download) or ``"inline"`` (preview)
    thumb:       when 1 and file is HTML, strip external font <link> tags
    """
    if not await file_store.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    content = await file_store.read(file_path)
    mime, _ = guess_type(file_path)
    filename = Path(file_path).name

    # HTML + thumb mode: strip external font links to avoid render blocking
    if thumb and (mime or "").startswith("text/html"):
        html_text = content.decode("utf-8", errors="replace")
        html_text = _FONT_LINK_RE.sub("", html_text)
        return Response(
            content=html_text,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": disposition,
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    # Build Content-Disposition header
    if disposition == "attachment":
        # filename= must be ASCII-safe (HTTP headers are latin-1);
        # filename*=UTF-8 carries the real name for modern browsers (RFC 5987).
        ascii_name = filename.encode("ascii", errors="replace").decode("ascii")
        disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
    else:
        disp = "inline"

    return Response(
        content=content,
        media_type=mime or "application/octet-stream",
        headers={
            "Content-Disposition": disp,
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/tasks/{task_id}/download")
async def download_task_file(task_id: str):
    """Download the output file of a task (Content-Disposition: attachment).

    Frontend only needs the taskId — the backend resolves the file path
    from the task's result_data, keeping storage details encapsulated.
    """
    logger.info("[API] GET /api/tasks/%s/download", task_id)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result_data = json.loads(task.get("result_data") or "{}")
    if not isinstance(result_data, dict):
        result_data = {}
    file_path = result_data.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="No downloadable file for this task")
    return await _serve_file(file_path, disposition="attachment")


@app.get("/api/files/{file_path:path}")
async def download_file(file_path: str):
    """Download a file by its storage path (Content-Disposition: attachment).

    For inline preview, use GET /api/file-view/{file_path} instead.
    """
    logger.info("[API] GET /api/files/%s", file_path)
    return await _serve_file(file_path, disposition="attachment")


@app.get("/api/file-view/{file_path:path}")
async def view_file(file_path: str, thumb: int = Query(default=0)):
    """Serve a file inline for browser preview (Content-Disposition: inline).

    When thumb=1 and file is HTML, external font <link> tags are stripped.
    """
    logger.info("[API] GET /api/file-view/%s thumb=%s", file_path, thumb)
    return await _serve_file(file_path, disposition="inline", thumb=thumb)


# --- Static assets for PPT skill ---

_static_dir = Path(__file__).resolve().parent.parent.parent / "static"
_static_mounts = {
    "/ppt-assets": _static_dir / "ppt-assets",
    "/ppt-templates": _static_dir / "ppt-templates",
}
for mount_path, directory in _static_mounts.items():
    if directory.exists():
        app.mount(mount_path, StaticFiles(directory=str(directory)), name=mount_path.strip("/"))
    else:
        logger.warning("[API] static directory missing, skip mount: %s", directory)


@app.get("/api/ppt-style-preview/{preview_path:path}")
async def preview_ppt_style(preview_path: str, thumb: int = Query(default=0)):
    """Serve PPT style preview HTML for both system and custom styles.

    - System styles: plain filename (e.g. "01-bold-signal.html") served from static/ppt-styles/
    - Custom styles: served inline via FileStore (local or OSS)
    """
    logger.info("[API] GET /api/ppt-style-preview/%s thumb=%s", preview_path, thumb)
    builtin_dir = _static_dir / "ppt-styles"

    # System styles: plain filename (no path separator)
    if "/" not in preview_path and "\\" not in preview_path:
        resolved = builtin_dir / preview_path
        if not resolved.exists():
            raise HTTPException(status_code=404, detail=f"Preview file not found: {preview_path}")
        # For thumb mode, strip external font links
        if thumb:
            html_text = resolved.read_text(encoding="utf-8")
            html_text = _FONT_LINK_RE.sub("", html_text)
            return Response(
                content=html_text,
                media_type="text/html; charset=utf-8",
                headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
            )
        response = FileResponse(path=str(resolved), media_type="text/html")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    # Custom styles: serve inline via FileStore (local or OSS transparent)
    if not await file_store.exists(preview_path):
        raise HTTPException(status_code=404, detail=f"Preview file not found: {preview_path}")
    content = await file_store.read(preview_path)
    html_text = content.decode("utf-8", errors="replace")
    if thumb:
        html_text = _FONT_LINK_RE.sub("", html_text)
    return Response(
        content=html_text,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
