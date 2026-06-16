"""Dependency injection for API routes."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from src.app_context import AppContext
from src.services.doc_service import DocService

load_dotenv()

app_ctx = AppContext.from_env()

# Backward-compatible aliases
db = app_ctx.db
vector_store = app_ctx.vector_store
file_store = app_ctx.file_store
skill_manager = app_ctx.skill_manager

llm = ChatOpenAI(
    model=os.getenv("SUMMARIZATION_MODEL"),
    api_key=os.getenv("SUMMARIZATION_API_KEY"),
    base_url=os.getenv("SUMMARIZATION_API_BASE"),
)

doc_service = DocService(
    db=db, vector_store=vector_store, file_store=file_store, llm=llm
)
