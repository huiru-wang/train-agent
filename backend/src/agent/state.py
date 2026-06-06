from langchain.agents import AgentState


class TrainAgentState(AgentState):
    """Extended agent state with workspace context."""
    workspace_id: str
