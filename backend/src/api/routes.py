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

from src.api.deps import db, doc_service, file_store, skill_manager, vector_store

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


# --- File download ---


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
