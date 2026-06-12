import logging
import os

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
import uuid

from langchain.agents.middleware import dynamic_prompt, wrap_model_call, ModelRequest
from langchain_core.messages import AIMessage

from src.agent.prompt_manager import SYSTEM_PROMPT
from src.agent.skill_manager import SkillManager
from src.agent.state import TrainAgentState
from src.storage.database import Database
from src.storage.file_store import FileStore
from src.storage.vector_store import VectorStore
from src.tools.clarify_form import clarify_form
from src.tools.load_skill import create_load_skill_tool
from src.tools.rag_search import create_rag_search_tool
from src.tools.save_output import create_save_output_tool

logger = logging.getLogger(__name__)


def create_graph(
    db: Database,
    vector_store: VectorStore,
    file_store: FileStore,
    skill_manager: SkillManager,
):
    # --- Model ---
    model = ChatOpenAI(
        model=os.getenv("LLM_MODEL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        streaming=True,
        extra_body={"enable_thinking": True},
    )

    # --- Tools ---
    rag_tool = create_rag_search_tool(vector_store)
    load_skill_tool = create_load_skill_tool(skill_manager)
    save_output_tool = create_save_output_tool(db, file_store)
    tools = [clarify_form, rag_tool, load_skill_tool, save_output_tool]

    # --- Middleware ---
    @dynamic_prompt
    async def inject_doc_context(request: ModelRequest) -> str:
        workspace_id = request.state.get("workspace_id", "default")
        doc_summaries = []
        if db:
            if db.connection is None:
                await db.initialize()
            docs = await db.list_documents(workspace_id)
            doc_summaries = [
                f"[{d['filename']}](id:{d['id'][:8]}): {d['summary']}"
                for d in docs
                if d.get("summary")
            ]

        prompt = SYSTEM_PROMPT
        if doc_summaries:
            summaries_text = "\n".join(f"- {s}" for s in doc_summaries)
            prompt += f"\n\n## 当前知识库文档摘要\n{summaries_text}"

        logger.info(
            "[Agent] workspace=%s, %d doc summaries injected",
            workspace_id,
            len(doc_summaries),
        )
        return prompt

    return create_agent(
        model=model,
        tools=tools,
        state_schema=TrainAgentState,
        middleware=[inject_doc_context, patch_tool_call_ids],
    )


def _make_default_graph():
    """Create a default graph instance for langgraph serve."""
    from dotenv import load_dotenv

    load_dotenv()

    data_dir = os.getenv("DATA_DIR", "./data")
    _db = Database(f"{data_dir}/train_agent.db")
    _vector_store = VectorStore(f"{data_dir}/chroma")
    _file_store = FileStore(f"{data_dir}/files")
    _skill_manager = SkillManager(os.path.join(os.path.dirname(__file__), "../../skills"))
    return create_graph(
        db=_db,
        vector_store=_vector_store,
        file_store=_file_store,
        skill_manager=_skill_manager,
    )


graph = _make_default_graph()
