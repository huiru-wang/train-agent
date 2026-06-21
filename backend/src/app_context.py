"""Shared application context bundling storage and service dependencies."""

import os
from dataclasses import dataclass

from src.managers.skill_manager import SkillManager
from src.storage.database import Database
from src.storage.file_store import FileStore
from src.storage.vector_store import VectorStore


@dataclass
class AppContext:
    db: Database
    vector_store: VectorStore
    file_store: FileStore
    skill_manager: SkillManager

    @classmethod
    def from_env(cls) -> "AppContext":
        """Create an AppContext from environment variables."""
        data_dir = os.getenv("DATA_DIR", "./data")
        return cls(
            db=Database(f"{data_dir}/train_agent.db"),
            vector_store=VectorStore(f"{data_dir}/chroma"),
            file_store=FileStore(f"{data_dir}/files"),
            skill_manager=SkillManager(
                os.path.join(os.path.dirname(__file__), "../skills")
            ),
        )
