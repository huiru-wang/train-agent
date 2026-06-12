import logging
import os

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from src.agent.skill_manager import SkillManager
from src.agent.state import TrainAgentState
from src.middlewares import (
    create_inject_doc_context,
    log_after_agent,
    log_after_model,
    log_before_agent,
    log_before_model,
)
from langchain.agents.middleware import SummarizationMiddleware
from src.storage.database import Database
from src.storage.file_store import FileStore
from src.storage.vector_store import VectorStore
from src.tools.clarify_form import clarify_form
from src.tools.load_skill import create_load_skill_tool
from src.tools.rag_search import create_rag_search_tool
from src.tools.run_skill_script import create_run_skill_script_tool
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
        model=os.getenv("MAIN_MODEL"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_API_BASE"),
        streaming=True,
        extra_body={"enable_thinking": True},
    )

    # --- Tools ---
    rag_tool = create_rag_search_tool(vector_store)
    load_skill_tool = create_load_skill_tool(skill_manager)
    save_output_tool = create_save_output_tool(db, file_store)
    run_skill_script_tool = create_run_skill_script_tool(skill_manager)
    tools = [
        clarify_form,
        rag_tool,
        load_skill_tool,
        save_output_tool,
        run_skill_script_tool,
    ]

    # --- Middleware ---
    inject_doc_context = create_inject_doc_context(db)

    return create_agent(
        model=model,
        tools=tools,
        state_schema=TrainAgentState,
        middleware=[
            log_before_agent,
            log_before_model,
            inject_doc_context,
            log_after_model,
            log_after_agent,
            SummarizationMiddleware(
                model=os.getenv("MAIN_MODEL"),
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_API_BASE"),
                trigger=("tokens", 12000),
                keep=("messages", 20),
            ),
        ],
    )


def _make_default_graph():
    """Create a default graph instance for langgraph serve."""
    from dotenv import load_dotenv

    load_dotenv()

    data_dir = os.getenv("DATA_DIR", "./data")
    _db = Database(f"{data_dir}/train_agent.db")
    _vector_store = VectorStore(f"{data_dir}/chroma")
    _file_store = FileStore(f"{data_dir}/files")
    _skill_manager = SkillManager(
        os.path.join(os.path.dirname(__file__), "../../skills")
    )
    return create_graph(
        db=_db,
        vector_store=_vector_store,
        file_store=_file_store,
        skill_manager=_skill_manager,
    )


graph = _make_default_graph()
