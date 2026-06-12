"""Dependency injection for API routes."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from src.agent.skill_manager import SkillManager
from src.services.doc_service import DocService
from src.storage.database import Database
from src.storage.file_store import FileStore
from src.storage.vector_store import VectorStore

load_dotenv()

DATA_DIR = os.getenv("DATA_DIR", "./data")

db = Database(f"{DATA_DIR}/train_agent.db")
vector_store = VectorStore(f"{DATA_DIR}/chroma")
file_store = FileStore(f"{DATA_DIR}/files")

llm = ChatOpenAI(
    model=os.getenv("SUMMARIZATION_MODEL"),
    api_key=os.getenv("SUMMARIZATION_API_KEY"),
    base_url=os.getenv("SUMMARIZATION_API_BASE"),
)

doc_service = DocService(
    db=db, vector_store=vector_store, file_store=file_store, llm=llm
)
skill_manager = SkillManager(os.path.join(os.path.dirname(__file__), "../../skills"))
