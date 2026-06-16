from langchain.agents import AgentState


class TrainAgentState(AgentState):
    """Extended agent state with workspace context."""
    workspace_id: str
    ppt_style: str  # Pre-selected PPT visual style (e.g. "swiss-modern", "bold-signal")
    current_ppt_task_id: str  # PPT task ID for narration generation (empty when not narrating)
