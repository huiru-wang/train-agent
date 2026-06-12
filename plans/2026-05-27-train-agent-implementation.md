# Train Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-executing-plans to implement this plan task-by-task.

**Goal:** Build a training-domain Agent product with knowledge-base RAG chat, document management, /ppt skill, and output tracking.

**Architecture:** LangGraph Python backend (ReAct agent with Context/Tool/Skill managers) + Next.js frontend (@langchain/react + assistant-ui). SQLite for structured data, ChromaDB for vectors.

**Tech Stack:** Python 3.12+, uv, LangChain, LangGraph, FastAPI | Next.js 15, TypeScript, Tailwind CSS 4, @assistant-ui/react, @langchain/react

**LLM Provider:** Dashscope (OpenAI Compatible) — `https://dashscope.aliyuncs.com/compatible-mode/v1`
**LLM Model:** `qwen-plus` | **Embedding Model:** `text-embedding-v2`

---

## Phase 1: Backend Foundation

### Task 1: Project Scaffolding (Backend)

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/langgraph.json`
- Create: `backend/src/__init__.py`
- Create: `backend/.env.example`
- Create: `backend/.python-version`

**Step 1: Initialize backend project with uv**

```bash
cd /Users/whr/workspace/projects/train-agent
mkdir -p backend/src
cd backend
```

`pyproject.toml`:
```toml
[project]
name = "train-agent"
version = "0.1.0"
description = "Training domain Agent with RAG and skills"
requires-python = ">=3.12"
dependencies = [
    "langchain>=0.3",
    "langgraph>=0.4",
    "langchain-openai>=0.3",
    "langchain-community>=0.3",
    "dashscope>=1.20",
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "chromadb>=1.0",
    "python-multipart>=0.0.20",
    "aiosqlite>=0.21",
    "python-docx>=1.1",
    "pymupdf>=1.25",
    "httpx>=0.28",
    "python-dotenv>=1.1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.25", "ruff>=0.11"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`langgraph.json`:
```json
{
  "python_version": "3.12",
  "dependencies": ["."],
  "graphs": {
    "train_agent": "src.agent.graph:graph"
  },
  "env": ".env"
}
```

`.env.example`:
```
DASHSCOPE_API_KEY=your_dashscope_api_key
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v2
DATA_DIR=./data
```

`.python-version`:
```
3.12
```

**Step 2: Install dependencies**

```bash
cd /Users/whr/workspace/projects/train-agent/backend
uv sync
```

**Step 3: Commit**

```bash
git add .
git commit -m "feat: scaffold backend project with uv and langgraph config"
```

---

### Task 2: Storage Layer — SQLite

**Files:**
- Create: `backend/src/storage/__init__.py`
- Create: `backend/src/storage/database.py`
- Create: `backend/tests/test_database.py`

**Step 1: Write failing tests**

`backend/tests/test_database.py`:
```python
import pytest
import asyncio
from src.storage.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_create_workspace(db):
    ws = await db.create_workspace(user_id="user1", name="My Workspace")
    assert ws["id"] is not None
    assert ws["name"] == "My Workspace"
    assert ws["user_id"] == "user1"


@pytest.mark.asyncio
async def test_list_workspaces(db):
    await db.create_workspace(user_id="user1", name="WS1")
    await db.create_workspace(user_id="user1", name="WS2")
    workspaces = await db.list_workspaces(user_id="user1")
    assert len(workspaces) == 2


@pytest.mark.asyncio
async def test_delete_workspace(db):
    ws = await db.create_workspace(user_id="user1", name="ToDelete")
    await db.delete_workspace(ws["id"])
    workspaces = await db.list_workspaces(user_id="user1")
    assert len(workspaces) == 0


@pytest.mark.asyncio
async def test_create_document(db):
    ws = await db.create_workspace(user_id="user1", name="WS")
    doc = await db.create_document(
        workspace_id=ws["id"],
        filename="test.pdf",
        file_type="pdf",
        storage_path="/data/test.pdf",
    )
    assert doc["id"] is not None
    assert doc["status"] == "processing"


@pytest.mark.asyncio
async def test_create_task(db):
    ws = await db.create_workspace(user_id="user1", name="WS")
    task = await db.create_task(
        workspace_id=ws["id"],
        type="ppt",
        title="AI Training PPT",
    )
    assert task["status"] == "generating"
```

**Step 2: Run tests to verify failure**

```bash
cd /Users/whr/workspace/projects/train-agent/backend
uv run pytest tests/test_database.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement Database class**

`backend/src/storage/database.py`:
```python
import uuid
import aiosqlite
from datetime import datetime, timezone


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection: aiosqlite.Connection | None = None

    async def initialize(self):
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self._create_tables()

    async def _create_tables(self):
        await self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS workspace (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS document (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                file_type TEXT,
                summary TEXT,
                storage_path TEXT,
                status TEXT DEFAULT 'processing',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS task (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                title TEXT,
                status TEXT DEFAULT 'generating',
                result_data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await self.connection.commit()

    async def close(self):
        if self.connection:
            await self.connection.close()

    # --- Workspace ---
    async def create_workspace(self, user_id: str, name: str) -> dict:
        workspace_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO workspace (id, user_id, name) VALUES (?, ?, ?)",
            (workspace_id, user_id, name),
        )
        await self.connection.commit()
        return {"id": workspace_id, "user_id": user_id, "name": name}

    async def list_workspaces(self, user_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM workspace WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_workspace(self, workspace_id: str):
        await self.connection.execute("DELETE FROM workspace WHERE id = ?", (workspace_id,))
        await self.connection.commit()

    # --- Document ---
    async def create_document(self, workspace_id: str, filename: str, file_type: str, storage_path: str) -> dict:
        doc_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO document (id, workspace_id, filename, file_type, storage_path) VALUES (?, ?, ?, ?, ?)",
            (doc_id, workspace_id, filename, file_type, storage_path),
        )
        await self.connection.commit()
        return {"id": doc_id, "workspace_id": workspace_id, "filename": filename, "file_type": file_type, "status": "processing"}

    async def list_documents(self, workspace_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM document WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_document(self, doc_id: str, **kwargs):
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [doc_id]
        await self.connection.execute(f"UPDATE document SET {sets} WHERE id = ?", values)
        await self.connection.commit()

    async def delete_document(self, doc_id: str):
        await self.connection.execute("DELETE FROM document WHERE id = ?", (doc_id,))
        await self.connection.commit()

    # --- Task ---
    async def create_task(self, workspace_id: str, type: str, title: str = None) -> dict:
        task_id = str(uuid.uuid4())
        await self.connection.execute(
            "INSERT INTO task (id, workspace_id, type, title) VALUES (?, ?, ?, ?)",
            (task_id, workspace_id, type, title),
        )
        await self.connection.commit()
        return {"id": task_id, "workspace_id": workspace_id, "type": type, "title": title, "status": "generating"}

    async def list_tasks(self, workspace_id: str) -> list[dict]:
        cursor = await self.connection.execute(
            "SELECT * FROM task WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_task(self, task_id: str, **kwargs):
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [task_id]
        await self.connection.execute(f"UPDATE task SET {sets} WHERE id = ?", values)
        await self.connection.commit()
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_database.py -v
```
Expected: ALL PASS

**Step 5: Commit**

```bash
git add .
git commit -m "feat: implement SQLite storage layer with workspace/document/task tables"
```

---

### Task 3: Storage Layer — ChromaDB Vector Store

**Files:**
- Create: `backend/src/storage/vector_store.py`
- Create: `backend/tests/test_vector_store.py`

**Step 1: Write failing test**

```python
import pytest
from src.storage.vector_store import VectorStore


@pytest.fixture
def store(tmp_path):
    return VectorStore(persist_dir=str(tmp_path / "chroma"))


def test_add_and_search(store):
    store.add_chunks(
        workspace_id="ws1",
        doc_id="doc1",
        chunks=["LangChain is a framework for LLM apps", "ChromaDB stores vectors"],
    )
    results = store.search(workspace_id="ws1", query="what is langchain", top_k=1)
    assert len(results) == 1
    assert "LangChain" in results[0]["text"]
    assert results[0]["doc_id"] == "doc1"


def test_delete_by_doc_id(store):
    store.add_chunks(workspace_id="ws1", doc_id="doc1", chunks=["chunk1"])
    store.add_chunks(workspace_id="ws1", doc_id="doc2", chunks=["chunk2"])
    store.delete_by_doc_id(workspace_id="ws1", doc_id="doc1")
    results = store.search(workspace_id="ws1", query="chunk", top_k=10)
    assert all(r["doc_id"] == "doc2" for r in results)
```

**Step 2: Implement VectorStore**

```python
import os
import uuid
import chromadb
import dashscope
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings


class DashscopeEmbeddingFunction(EmbeddingFunction):
    """ChromaDB embedding function using Dashscope text-embedding-v2."""

    def __init__(self, model: str = None):
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

    def __call__(self, input: Documents) -> Embeddings:
        response = dashscope.TextEmbedding.call(
            model=self.model,
            input=input,
            api_key=os.getenv("DASHSCOPE_API_KEY"),
        )
        return [item["embedding"] for item in response.output["embeddings"]]


class VectorStore:
    def __init__(self, persist_dir: str):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self._embedding_fn = DashscopeEmbeddingFunction()

    def _get_collection(self, workspace_id: str):
        return self.client.get_or_create_collection(
            name=f"ws_{workspace_id}",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embedding_fn,
        )

    def add_chunks(self, workspace_id: str, doc_id: str, chunks: list[str]):
        collection = self._get_collection(workspace_id)
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"doc_id": doc_id} for _ in chunks]
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)

    def search(self, workspace_id: str, query: str, top_k: int = 5, doc_id: str | None = None) -> list[dict]:
        collection = self._get_collection(workspace_id)
        where = {"doc_id": doc_id} if doc_id else None
        results = collection.query(query_texts=[query], n_results=top_k, where=where)
        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "text": doc,
                "doc_id": results["metadatas"][0][i]["doc_id"],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
        return output

    def delete_by_doc_id(self, workspace_id: str, doc_id: str):
        collection = self._get_collection(workspace_id)
        collection.delete(where={"doc_id": doc_id})

    def delete_workspace(self, workspace_id: str):
        try:
            self.client.delete_collection(f"ws_{workspace_id}")
        except ValueError:
            pass
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_vector_store.py -v
git add .
git commit -m "feat: implement ChromaDB vector store with per-workspace collections"
```

---

### Task 4: Document Service (Upload + Parse + Vectorize)

**Files:**
- Create: `backend/src/services/__init__.py`
- Create: `backend/src/services/doc_service.py`
- Create: `backend/src/storage/file_store.py`
- Create: `backend/tests/test_doc_service.py`

**Step 1: Implement FileStore**

```python
import os
import shutil
from pathlib import Path


class FileStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, workspace_id: str, filename: str, content: bytes) -> str:
        workspace_dir = self.base_dir / workspace_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        file_path = workspace_dir / filename
        file_path.write_bytes(content)
        return str(file_path)

    def delete(self, file_path: str):
        path = Path(file_path)
        if path.exists():
            path.unlink()

    def delete_workspace(self, workspace_id: str):
        workspace_dir = self.base_dir / workspace_id
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
```

**Step 2: Implement DocService with parsers**

```python
import re
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.storage.database import Database
from src.storage.vector_store import VectorStore
from src.storage.file_store import FileStore


class DocService:
    def __init__(self, db: Database, vector_store: VectorStore, file_store: FileStore, llm=None):
        self.db = db
        self.vector_store = vector_store
        self.file_store = file_store
        self.llm = llm
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    async def upload_document(self, workspace_id: str, filename: str, content: bytes) -> dict:
        file_type = self._detect_type(filename)
        storage_path = self.file_store.save(workspace_id, filename, content)
        doc = await self.db.create_document(
            workspace_id=workspace_id,
            filename=filename,
            file_type=file_type,
            storage_path=storage_path,
        )
        # Parse, chunk, vectorize
        try:
            text = self._parse(file_type, content, storage_path)
            chunks = self.splitter.split_text(text)
            self.vector_store.add_chunks(workspace_id=workspace_id, doc_id=doc["id"], chunks=chunks)
            summary = await self._generate_summary(text)
            await self.db.update_document(doc["id"], status="ready", summary=summary)
            doc["status"] = "ready"
            doc["summary"] = summary
        except Exception as e:
            await self.db.update_document(doc["id"], status="error")
            doc["status"] = "error"
        return doc

    async def delete_document(self, workspace_id: str, doc_id: str):
        docs = await self.db.list_documents(workspace_id)
        doc = next((d for d in docs if d["id"] == doc_id), None)
        if doc:
            self.file_store.delete(doc["storage_path"])
            self.vector_store.delete_by_doc_id(workspace_id, doc_id)
            await self.db.delete_document(doc_id)

    def _detect_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        mapping = {".pdf": "pdf", ".docx": "docx", ".doc": "docx", ".md": "markdown"}
        return mapping.get(ext, "unknown")

    def _parse(self, file_type: str, content: bytes, storage_path: str) -> str:
        if file_type == "pdf":
            return self._parse_pdf(storage_path)
        elif file_type == "docx":
            return self._parse_docx(content)
        elif file_type == "markdown":
            return content.decode("utf-8")
        else:
            return content.decode("utf-8", errors="ignore")

    def _parse_pdf(self, path: str) -> str:
        import fitz
        doc = fitz.open(path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text

    def _parse_docx(self, content: bytes) -> str:
        import io
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    async def _generate_summary(self, text: str) -> str:
        if not self.llm:
            return text[:500] + "..." if len(text) > 500 else text
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content="用一段话总结以下文档的核心内容，200字以内："),
            HumanMessage(content=text[:8000]),
        ]
        response = await self.llm.ainvoke(messages)
        return response.content
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_doc_service.py -v
git add .
git commit -m "feat: implement doc service with PDF/DOCX/MD parsing and vectorization"
```

---

### Task 5: Context Manager

**Files:**
- Create: `backend/src/agent/__init__.py`
- Create: `backend/src/agent/context_manager.py`
- Create: `backend/tests/test_context_manager.py`

**Step 1: Implement ContextManager**

```python
from dataclasses import dataclass, field
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage


@dataclass
class ContextConfig:
    max_tokens: int = 120000
    compression_threshold: float = 0.7  # 70% triggers compression
    summary_target_tokens: int = 500


class ContextManager:
    def __init__(self, config: ContextConfig = None, llm=None):
        self.config = config or ContextConfig()
        self.llm = llm

    def build(
        self,
        system_prompt: str,
        doc_summaries: list[str],
        current_input: str,
        rag_chunks: list[str],
        history: list[BaseMessage],
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = []

        # Layer 0: System Prompt (immutable)
        full_system = system_prompt
        # Layer 1: Document summaries (immutable)
        if doc_summaries:
            summaries_text = "\n\n".join(f"[文档] {s}" for s in doc_summaries)
            full_system += f"\n\n## 当前知识库文档摘要\n{summaries_text}"
        messages.append(SystemMessage(content=full_system))

        # Layer 3: History (compressible)
        messages.extend(history)

        # Layer 2: Current turn with RAG context (immutable)
        current_content = current_input
        if rag_chunks:
            refs = "\n\n".join(f"[参考{i+1}] {chunk}" for i, chunk in enumerate(rag_chunks))
            current_content = f"以下是相关文档片段供参考：\n{refs}\n\n用户问题：{current_input}"
        messages.append(HumanMessage(content=current_content))

        return messages

    async def compress_history(self, history: list[BaseMessage]) -> list[BaseMessage]:
        """Compress older messages into a summary when token budget is tight."""
        if not self.llm or len(history) <= 4:
            return history

        # Keep last 4 messages, compress the rest
        to_compress = history[:-4]
        to_keep = history[-4:]

        conversation_text = "\n".join(
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
            for m in to_compress
        )

        from langchain_core.messages import SystemMessage as SM, HumanMessage as HM
        summary_response = await self.llm.ainvoke([
            SM(content="将以下对话压缩为简短摘要，保留关键信息和决策："),
            HM(content=conversation_text),
        ])

        compressed = [AIMessage(content=f"[历史摘要] {summary_response.content}")]
        return compressed + to_keep
```

**Step 2: Run tests, commit**

```bash
uv run pytest tests/test_context_manager.py -v
git add .
git commit -m "feat: implement context manager with layered strategy and compression"
```

---

### Task 6: Tools — clarify_form + rag_search + load_skill

**Files:**
- Create: `backend/src/tools/__init__.py`
- Create: `backend/src/tools/clarify_form.py`
- Create: `backend/src/tools/rag_search.py`
- Create: `backend/src/tools/load_skill.py`
- Create: `backend/src/tools/save_output.py`
- Create: `backend/src/agent/skill_manager.py`
- Create: `backend/skills/` (skills directory)
- Create: `backend/tests/test_skill_manager.py`

**Step 1: Implement clarify_form tool**

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class FormField(BaseModel):
    name: str = Field(description="字段名")
    label: str = Field(description="显示标签")
    type: str = Field(description="字段类型: text/select/multiselect")
    options: list[str] | None = Field(default=None, description="选项列表(select/multiselect时必填)")
    required: bool = Field(default=True)


class ClarifyFormInput(BaseModel):
    title: str = Field(description="表单标题")
    description: str = Field(description="向用户说明为什么需要这些信息")
    fields: list[FormField] = Field(description="表单字段列表")


@tool(args_schema=ClarifyFormInput)
def clarify_form(title: str, description: str, fields: list[dict]) -> str:
    """向用户展示一个表单来收集信息。当需要用户澄清意图、选择选项或提供详细参数时使用此工具。
    表单会在前端渲染为交互式UI，用户填写后结果会返回给你。"""
    # The actual form rendering happens on frontend via tool_call message type
    # This tool returns a placeholder; the real result comes from user interaction
    return f"[等待用户填写表单: {title}]"
```

**Step 2: Implement rag_search tool**

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class RagSearchInput(BaseModel):
    query: str = Field(description="搜索查询")
    top_k: int = Field(default=5, description="返回结果数量")


# This will be instantiated with vector_store dependency at graph build time
def create_rag_search_tool(vector_store, workspace_id: str):
    @tool
    def rag_search(query: str, top_k: int = 5) -> str:
        """从当前工作区的知识库中检索相关文档片段。当用户提出与文档内容相关的问题时使用。"""
        results = vector_store.search(workspace_id=workspace_id, query=query, top_k=top_k)
        if not results:
            return "未找到相关文档内容。"
        output = []
        for i, r in enumerate(results):
            output.append(f"[片段{i+1}] (来源: doc_{r['doc_id'][:8]})\n{r['text']}")
        return "\n\n".join(output)

    return rag_search
```

**Step 3: Implement SkillManager**

`backend/src/agent/skill_manager.py`:
```python
import yaml
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SkillMeta:
    name: str
    description: str
    file_path: str


class SkillManager:
    """Scans a skills directory for SKILL.md files, provides list and load capabilities.
    Agent is unaware of any skill business logic — it only sees name + description."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillMeta] = {}
        self._scan()

    def _scan(self):
        if not self.skills_dir.exists():
            return
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            meta = self._parse_frontmatter(skill_file)
            if meta:
                self._skills[meta.name] = meta

    def _parse_frontmatter(self, path: Path) -> SkillMeta | None:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        end = content.index("---", 3)
        front = yaml.safe_load(content[3:end])
        return SkillMeta(
            name=front["name"],
            description=front.get("description", ""),
            file_path=str(path),
        )

    def list_skills(self) -> list[dict]:
        return [{"name": s.name, "description": s.description} for s in self._skills.values()]

    def load_skill(self, name: str) -> str | None:
        skill = self._skills.get(name)
        if not skill:
            return None
        return Path(skill.file_path).read_text(encoding="utf-8")
```

**Step 4: Implement load_skill tool (LangChain Skills pattern — progressive disclosure)**

`backend/src/tools/load_skill.py`:
```python
from langchain_core.tools import tool
from src.agent.skill_manager import SkillManager


def create_load_skill_tool(skill_manager: SkillManager):
    """Create the load_skill tool with dynamic docstring listing available skills.
    
    Follows the LangChain Skills pattern: a single tool whose docstring
    contains all available skill names + descriptions. Agent sees the list
    via the tool schema and loads on-demand. Agent never knows skill internals.
    """
    available = skill_manager.list_skills()
    skill_list = "\n".join(f"    - {s['name']}: {s['description']}" for s in available)

    @tool
    def load_skill(skill_name: str) -> str:
        """placeholder"""
        content = skill_manager.load_skill(skill_name)
        if content is None:
            available_names = [s["name"] for s in skill_manager.list_skills()]
            return f"Skill '{skill_name}' not found. Available: {', '.join(available_names)}"
        return content

    load_skill.__doc__ = f"""Load a specialized skill prompt. After loading, follow the skill's instructions exactly.

Available skills:
{skill_list if skill_list else '    (no skills registered)'}

Returns the skill's full prompt and instructions."""

    return load_skill
```

**Step 5: Implement save_output tool**

`backend/src/tools/save_output.py`:
```python
from langchain_core.tools import tool


def create_save_output_tool(db, file_store, workspace_id: str):
    @tool
    def save_output(type: str, title: str, content: str, filename: str = "") -> str:
        """保存 Skill 执行的产出物。当你完成了一个产出（如 PPT、报告等）时，使用此工具保存结果。
        产出物会出现在用户的产出面板中，可预览和下载。

        Args:
            type: 产出类型，如 'ppt', 'report'
            title: 产出标题
            content: 产出内容（如 HTML 文本）
            filename: 保存的文件名（可选，默认根据 title 和 type 自动生成）
        """
        import asyncio

        if not filename:
            safe_title = title.replace(" ", "_").replace("/", "_")
            ext_map = {"ppt": ".html", "report": ".md"}
            filename = f"{safe_title}{ext_map.get(type, '.txt')}"

        # Save file
        file_path = file_store.save(workspace_id, f"outputs/{filename}", content.encode("utf-8"))

        # Create task record — run async db call in sync context
        loop = asyncio.get_event_loop()
        import json
        result_data = json.dumps({"file_path": file_path, "filename": filename})

        async def _create():
            task = await db.create_task(workspace_id=workspace_id, type=type, title=title)
            await db.update_task(task["id"], status="completed", result_data=result_data)
            return task

        task = loop.run_until_complete(_create())
        return f"产出已保存: {title} (类型: {type})。用户可在产出面板查看。"

    return save_output
```

**Step 6: Run tests, commit**

```bash
uv run pytest tests/test_skill_manager.py -v
git add .
git commit -m "feat: implement SkillManager, load_skill, and save_output tools"
```

---

### Task 7: Prompt Manager

**Files:**
- Create: `backend/src/agent/prompt_manager.py`

```python
SYSTEM_PROMPT = """你是一个专业的企业培训助手，专注于帮助用户进行培训相关工作。

## 你的能力
- 基于上传的培训文档进行问答和讨论
- 帮助用户理解和整理培训内容
- 根据文档内容生成培训PPT（使用 /ppt 命令触发）
- 通过表单收集必要信息以更好地服务用户

## 行为准则
1. 只处理与培训、学习、教育相关的请求
2. 对于非培训场景的请求（如写代码、闲聊、翻译无关文本等），礼貌拒绝并引导回培训话题
3. 回答要基于用户上传的文档内容，引用时注明来源
4. 如果文档中没有相关信息，如实告知用户
5. 语言风格：专业、友好、清晰

## 技能使用
你可以通过 load_skill 工具查看和加载可用技能。
当用户使用 / 命令时（如 /ppt），先查看 load_skill 工具描述中列出的可用技能，
找到匹配的技能后调用 load_skill(skill_name="xxx") 加载完整指引并严格按其执行。
即使没有 / 命令，当你判断某个技能适用于当前任务时，也应主动加载使用。
"""
```

**Commit:**

```bash
git add .
git commit -m "feat: add prompt manager with training-domain system prompt"
```

---

### Task 8: Agent Graph (ReAct Loop with LangGraph)

**Files:**
- Create: `backend/src/agent/graph.py`
- Create: `backend/src/agent/state.py`

**Step 1: Define state**

`backend/src/agent/state.py`:
```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    workspace_id: str
```

**Step 2: Implement graph**

`backend/src/agent/graph.py`:
```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from src.agent.state import AgentState
from src.agent.context_manager import ContextManager
from src.agent.prompt_manager import SYSTEM_PROMPT
from src.tools.clarify_form import clarify_form
from src.tools.rag_search import create_rag_search_tool
from src.tools.load_skill import create_load_skill_tool
from src.tools.save_output import create_save_output_tool
from src.agent.skill_manager import SkillManager
from src.storage.vector_store import VectorStore
from src.storage.file_store import FileStore
from src.storage.database import Database

import os


def create_graph(db: Database, vector_store: VectorStore, file_store: FileStore = None, skill_manager: SkillManager = None):
    model = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
        openai_api_base=os.getenv("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        streaming=True,
    )
    context_manager = ContextManager(llm=model)

    async def agent_node(state: AgentState):
        workspace_id = state.get("workspace_id", "default")

        # Build tools with workspace context
        rag_tool = create_rag_search_tool(vector_store, workspace_id)
        load_skill_tool = create_load_skill_tool(skill_manager)
        save_output_tool = create_save_output_tool(db, file_store, workspace_id)
        tools = [clarify_form, rag_tool, load_skill_tool, save_output_tool]
        model_with_tools = model.bind_tools(tools)

        # Get document summaries for context
        docs = await db.list_documents(workspace_id)
        doc_summaries = [d["summary"] for d in docs if d.get("summary")]

        # Build context
        messages = state["messages"]
        # For now, pass messages directly (context compression in future iteration)
        response = await model_with_tools.ainvoke(messages)

        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # Build graph
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)

    # Tool node needs dynamic tools — simplified for now
    tool_node = ToolNode([clarify_form])
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# Default graph instance for langgraph serve
# Will be properly initialized with dependencies in production
_default_skill_manager = SkillManager(os.path.join(os.path.dirname(__file__), "../../skills"))
graph = create_graph(db=None, vector_store=None, skill_manager=_default_skill_manager)
```

**Step 3: Commit**

```bash
git add .
git commit -m "feat: implement ReAct agent graph with LangGraph StateGraph"
```

---

### Task 9: REST API Routes (FastAPI)

**Files:**
- Create: `backend/src/api/__init__.py`
- Create: `backend/src/api/routes.py`
- Create: `backend/src/api/deps.py`

**Step 1: Implement routes**

`backend/src/api/deps.py`:
```python
"""Dependency injection for API routes."""
from src.storage.database import Database
from src.storage.vector_store import VectorStore
from src.storage.file_store import FileStore
from src.services.doc_service import DocService
import os

DATA_DIR = os.getenv("DATA_DIR", "./data")

db = Database(f"{DATA_DIR}/train_agent.db")
vector_store = VectorStore(f"{DATA_DIR}/chroma")
file_store = FileStore(f"{DATA_DIR}/files")
doc_service = DocService(db=db, vector_store=vector_store, file_store=file_store)
```

`backend/src/api/routes.py`:
```python
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.deps import db, doc_service

app = FastAPI(title="Train Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await db.initialize()


# --- Workspace ---
class CreateWorkspaceRequest(BaseModel):
    user_id: str
    name: str


@app.post("/api/workspaces")
async def create_workspace(req: CreateWorkspaceRequest):
    return await db.create_workspace(user_id=req.user_id, name=req.name)


@app.get("/api/workspaces")
async def list_workspaces(user_id: str):
    return await db.list_workspaces(user_id=user_id)


@app.delete("/api/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    await db.delete_workspace(workspace_id)
    return {"ok": True}


# --- Documents ---
@app.post("/api/workspaces/{workspace_id}/documents")
async def upload_document(workspace_id: str, file: UploadFile = File(...)):
    content = await file.read()
    doc = await doc_service.upload_document(
        workspace_id=workspace_id,
        filename=file.filename,
        content=content,
    )
    return doc


@app.get("/api/workspaces/{workspace_id}/documents")
async def list_documents(workspace_id: str):
    return await db.list_documents(workspace_id)


@app.delete("/api/workspaces/{workspace_id}/documents/{doc_id}")
async def delete_document(workspace_id: str, doc_id: str):
    await doc_service.delete_document(workspace_id, doc_id)
    return {"ok": True}


# --- Tasks ---
@app.get("/api/workspaces/{workspace_id}/tasks")
async def list_tasks(workspace_id: str):
    return await db.list_tasks(workspace_id)
```

**Step 2: Commit**

```bash
git add .
git commit -m "feat: implement REST API routes for workspace/document/task management"
```

---

## Phase 2: Frontend

### Task 10: Frontend Scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts` (if needed for v4)
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/globals.css`

**Step 1: Initialize Next.js project**

```bash
cd /Users/whr/workspace/projects/train-agent
npx create-next-app@latest frontend --typescript --tailwind --app --src-dir --no-import-alias --skip-install
cd frontend
```

**Step 2: Install dependencies**

```bash
npm install @assistant-ui/react @assistant-ui/react-markdown @langchain/react @langchain/langgraph @langchain/core lucide-react zustand
npm install -D tailwindcss @tailwindcss/postcss
```

**Step 3: Commit**

```bash
git add .
git commit -m "feat: scaffold Next.js frontend with assistant-ui and langchain dependencies"
```

---

### Task 11: Workspace Home Page

**Files:**
- Create: `frontend/src/lib/user.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/components/workspace/workspace-card.tsx`
- Create: `frontend/src/components/workspace/create-dialog.tsx`

**Key implementation:**
- `user.ts`: Generate/retrieve userId from localStorage
- `api.ts`: REST client wrapping fetch for workspace/doc/task endpoints
- Home page: Grid of workspace cards with create/delete actions
- Clean, minimal UI inspired by assistant-ui-claude styling (dark theme, warm tones)

**Commit:**

```bash
git add .
git commit -m "feat: implement workspace home page with create/delete functionality"
```

---

### Task 12: Three-Panel Workspace Layout

**Files:**
- Create: `frontend/src/app/workspace/[id]/page.tsx`
- Create: `frontend/src/app/workspace/[id]/layout.tsx`
- Create: `frontend/src/components/layout/three-panel.tsx`

**Key implementation:**
- Resizable three-panel layout (left: docs, center: chat, right: tasks)
- Panels with min/max width constraints
- Responsive collapse for mobile (future, skip for MVP)

**Commit:**

```bash
git add .
git commit -m "feat: implement three-panel workspace layout"
```

---

### Task 13: Chat Panel (Core)

**Files:**
- Create: `frontend/src/components/chat/chat-panel.tsx`
- Create: `frontend/src/components/chat/message-list.tsx`
- Create: `frontend/src/components/chat/composer.tsx`
- Create: `frontend/src/lib/message-utils.ts`

**Key implementation:**
- Use `@langchain/react` useStream hook connected to LangGraph server
- Use `@assistant-ui/react` primitives (ThreadPrimitive, ComposerPrimitive, MessagePrimitive)
- Message rendering: text (markdown), tool calls, reasoning
- `/` command detection in composer input
- Styling: Claude-style from reference project (dark theme, warm palette)

**Reference: `assistant-ui-claude` patterns:**
- `useStream` → `useExternalStoreRuntime` → `AssistantRuntimeProvider`
- Message conversion: `toThreadMessages` / `toLangGraphMessageContent`

**Commit:**

```bash
git add .
git commit -m "feat: implement chat panel with streaming and assistant-ui integration"
```

---

### Task 14: Document Panel

**Files:**
- Create: `frontend/src/components/docs/doc-panel.tsx`
- Create: `frontend/src/components/docs/doc-list.tsx`
- Create: `frontend/src/components/docs/upload-button.tsx`

**Key implementation:**
- Document list fetched from REST API
- Upload button → file picker → multipart POST
- Status indicators (processing spinner / ready check / error icon)
- Delete with confirmation dialog
- Auto-refresh after upload

**Commit:**

```bash
git add .
git commit -m "feat: implement document panel with upload and management"
```

---

### Task 15: Task/Output Panel

**Files:**
- Create: `frontend/src/components/tasks/task-panel.tsx`
- Create: `frontend/src/components/tasks/task-card.tsx`

**Key implementation:**
- Poll `/api/workspaces/{id}/tasks` every 5 seconds
- Task cards with status badge (generating/completed/failed)
- Completed tasks show download/preview button
- Empty state when no outputs

**Commit:**

```bash
git add .
git commit -m "feat: implement task/output panel with polling and status display"
```

---

### Task 16: Clarify Form Rendering

**Files:**
- Create: `frontend/src/components/chat/clarify-form.tsx`

**Key implementation:**
- When a message contains `tool_call` with name `clarify_form`, render form UI
- Support field types: text input, select, multiselect
- On submit, send form result back as human message to continue the conversation
- Disabled state after submission

**Commit:**

```bash
git add .
git commit -m "feat: implement clarify form rendering in chat messages"
```

---

## Phase 3: Integration & Polish

### Task 17: PPT Skill — Write SKILL.md

**Files:**
- Create: `backend/skills/ppt/SKILL.md`
- Create: `backend/skills/ppt/style-presets.md` (optional reference, linked from SKILL.md)

**Key implementation:**

The PPT skill is a SKILL.md file — pure prompt, no code. The Agent loads it via `load_skill("ppt")` and follows its instructions using existing tools (clarify_form, rag_search) and LLM generation.

`backend/skills/ppt/SKILL.md`:
```markdown
---
name: ppt
description: Use when the user wants to create a training presentation or PPT from uploaded documents. Triggered by /ppt command or explicit request for slides.
---

# Training PPT Generator

Generate training presentations as single-file HTML based on uploaded knowledge base documents.

## Process

1. **Collect requirements** — Use clarify_form to gather:
   - Presentation topic/title
   - Target audience
   - Approximate slide count (5-10 / 10-20 / 20+)
   - Style preference (professional / creative / minimal)

2. **Retrieve content** — Use rag_search to find relevant document chunks for the topic.

3. **Generate presentation** — Create a single self-contained HTML file with:
   - Inline CSS and JS (zero dependencies)
   - Responsive slides using viewport units
   - Keyboard/click navigation
   - Clean typography and color scheme
   - Content sourced from retrieved document chunks

4. **Save output** — Save the HTML file and create a Task record:
   - Call the save_output tool with type="ppt", the HTML content, and a title
   - The file will appear in the user's Task/Output panel

5. **Confirm** — Tell the user the PPT is ready and can be previewed/downloaded from the output panel.

## Style Guidelines
Reference: /Users/whr/workspace/projects/frontend-slides
- Use clamp() for responsive font sizes
- Each slide must fit 100vh exactly
- No scrolling within slides
- Use web fonts (Google Fonts or Fontshare)
```

**Why this works:**
- Agent loads this via `load_skill("ppt")` → gets the full prompt
- Agent follows the process using existing tools (clarify_form, rag_search)
- Agent generates HTML via its own LLM capability
- No PPT-specific code in the agent — pure prompt-driven specialization
- New skills = new SKILL.md file, zero code changes

**Commit:**

```bash
git add .
git commit -m "feat: add PPT skill as SKILL.md (prompt-driven, LangChain Skills pattern)"
```

---

### Task 18: /Command Input Handling

**Files:**
- Modify: `frontend/src/components/chat/composer.tsx`
- Create: `frontend/src/components/chat/command-menu.tsx`

**Key implementation:**
- Detect `/` as first character in composer input
- Show dropdown menu with available commands (/ppt)
- On select, prepend command to message or auto-submit
- Send command hint in message metadata to backend

**Commit:**

```bash
git add .
git commit -m "feat: implement /command menu in chat composer"
```

---

### Task 19: End-to-End Integration

**Files:**
- Modify: `backend/src/agent/graph.py` (wire up all dependencies properly)
- Create: `backend/src/main.py` (startup script that initializes everything)

**Key implementation:**
- Proper dependency injection: db, vector_store, file_store all initialized at startup
- LangGraph serve config points to properly initialized graph
- Frontend env vars configured to point to backend
- Test full flow: upload doc → chat about it → /ppt → see output in task panel

**Commit:**

```bash
git add .
git commit -m "feat: wire up end-to-end integration between frontend and backend"
```

---

### Task 20: Polish & README

**Files:**
- Create: `README.md`
- Create: `frontend/.env.local.example`
- Create: `backend/.env`

**Key implementation:**
- README with setup instructions, architecture overview, dev commands
- Environment variable documentation
- Development startup script (run both frontend and backend)

**Commit:**

```bash
git add .
git commit -m "docs: add README and development setup instructions"
```

---

## Architecture Note: Skills Pattern

This project follows the [LangChain Skills pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/skills):
- Skills = prompt-driven specializations (SKILL.md files)
- Single `load_skill` tool with progressive disclosure (available skills listed in docstring)
- Agent is completely unaware of skill business logic
- Adding new skills = adding a new `skills/<name>/SKILL.md` file, zero code changes

## Execution Order Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| Phase 1 | T1-T9 | Backend: storage, services, agent, API |
| Phase 2 | T10-T16 | Frontend: scaffold, pages, components |
| Phase 3 | T17-T20 | Integration: skills, commands, e2e |

**Estimated effort:** ~20 tasks, each 10-30 min of implementation.
PLANEOF; __aone_exit=$?; pwd -P > '/var/folders/hc/15n2_8n91r99sdjxcgdb82k80000gp/T/aone-copilot-cwd-1779854857851-rym5vf2u2a.txt' 2>/dev/null; exit $__aone_exit