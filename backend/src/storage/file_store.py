import asyncio
import shutil
from pathlib import Path


class FileStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, workspace_id: str, filename: str, content: bytes) -> str:
        workspace_dir = self.base_dir / workspace_id
        file_path = workspace_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return str(file_path)

    async def save_async(self, workspace_id: str, filename: str, content: bytes) -> str:
        """Async-safe version of save that wraps blocking I/O in a thread."""
        workspace_dir = self.base_dir / workspace_id
        file_path = workspace_dir / filename

        def _write():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

        await asyncio.to_thread(_write)
        return str(file_path)

    def delete(self, file_path: str):
        path = Path(file_path)
        if path.exists():
            path.unlink()

    def delete_workspace(self, workspace_id: str):
        workspace_dir = self.base_dir / workspace_id
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
