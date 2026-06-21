import json
import logging
import shutil
from mimetypes import guess_type
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

    # --- File cleanup ---
    output_base = Path(file_store.base_dir) / workspace_id / "outputs"

    if task["type"] == "ppt":
        # PPT: remove entire outputs/{ppt_task_id}/ directory
        ppt_dir = output_base / task_id
        if ppt_dir.exists():
            shutil.rmtree(ppt_dir, ignore_errors=True)
            logger.info("[API] removed PPT output directory: %s", ppt_dir)
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
                p = Path(audio_path)
                if p.exists():
                    p.unlink(missing_ok=True)
        # Delete narration text file
        for f in output_base.rglob(f"{task_id}_narration.md"):
            f.unlink(missing_ok=True)
        logger.info("[API] cleaned narration files for task: %s", task_id)
    elif task["type"] == "ppt_style_extraction":
        # Style extraction: remove outputs/{task_id}/ directory
        se_dir = output_base / task_id
        if se_dir.exists():
            shutil.rmtree(se_dir, ignore_errors=True)
            logger.info("[API] removed style extraction output directory: %s", se_dir)

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
    resolved = Path(file_path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    resolved.write_text(req.content, encoding="utf-8")
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
    pptx_path = await file_store.save_async(workspace_id, file.filename, content)

    task = await db.create_task(
        workspace_id=workspace_id,
        type="ppt_style_extraction",
        title=f"风格提取: {file.filename}",
    )
    logger.info("[API] style extraction task created: id=%s", task["id"])

    background_tasks.add_task(style_extract_manager.run_extraction, task["id"], workspace_id, pptx_path)
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

    output_base = Path(file_store.base_dir) / workspace_id / "outputs"
    se_dir = output_base / task_id
    if se_dir.exists():
        shutil.rmtree(se_dir, ignore_errors=True)
        logger.info("[API] removed style extraction output directory: %s", se_dir)

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
    if preview_path and "/" in preview_path:
        p = Path(preview_path)
        if p.exists():
            # Remove the style directory (parent of preview.html)
            style_dir = p.parent
            shutil.rmtree(style_dir, ignore_errors=True)
            logger.info("[API] deleted style directory: %s", style_dir)
    await db.delete_ppt_style(style_id)
    return {"ok": True}


@app.get("/api/files/{file_path:path}")
async def download_file(file_path: str):
    """Download a file by its storage path. Supports output files and documents."""
    logger.info("[API] GET /api/files/%s", file_path)
    resolved = Path(file_path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    mime, _ = guess_type(str(resolved))
    response = FileResponse(
        path=str(resolved),
        filename=resolved.name,
        media_type=mime or "application/octet-stream",
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


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
async def preview_ppt_style(preview_path: str):
    """Serve PPT style preview HTML for both system and custom styles."""
    logger.info("[API] GET /api/ppt-style-preview/%s", preview_path)
    builtin_dir = _static_dir / "ppt-styles"
    # System styles: plain filename (e.g. "01-bold-signal.html")
    # Custom styles: path with separators (e.g. "data/files/.../preview.html")
    if "/" not in preview_path and "\\" not in preview_path:
        resolved = builtin_dir / preview_path
    else:
        resolved = Path(preview_path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Preview file not found: {preview_path}")
    response = FileResponse(path=str(resolved), media_type="text/html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response
