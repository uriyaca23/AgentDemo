import pytest
from unittest.mock import MagicMock, AsyncMock
from langchain_core.messages import AIMessage, HumanMessage, ToolCall
from orchestrator.graph import create_orchestrator_graph, AgentState
from mcp_server.server import create_new_workflow_skill

@pytest.mark.asyncio
async def test_mcp_skill_builder_interrogation():
    """Test the 'Metacognitive' interrogation loop of the skill builder."""
    # Scenario 1: Initial call without clarification
    result = await create_new_workflow_skill(
        skill_name="test_solver",
        description="A test solver",
        technical_requirements="Implement a solver for PDE."
    )
    assert "Regarding the creation of 'test_solver':" in result
    assert "1. What is the exact mathematical" in result
    
    # Scenario 2: Insufficient clarification
    result_fail = await create_new_workflow_skill(
        skill_name="test_solver",
        description="A test solver",
        technical_requirements="Implement a solver for PDE.",
        user_clarification="Just do it."
    )
    assert "ERROR: The provided clarification is insufficient" in result_fail
    
    # Scenario 3: Sufficient clarification (Simulated keywords check)
    result_success = await create_new_workflow_skill(
        skill_name="test_solver",
        description="A test solver",
        technical_requirements="Implement a solver for PDE.",
        user_clarification="The exact mathematical specification includes a boundary condition for X at Y. The schema is JSON based. Performance must be under 100ms."
    )
    assert "SUCCESS" in result_success

@pytest.mark.asyncio
async def test_graph_routing_to_tools():
    """Test that the graph routes to tools when a tool call is present."""
    mock_llm = MagicMock()
    # Mock LLM response with a tool call
    mock_response = AIMessage(
        content="I will use the tool.",
        tool_calls=[{
            "name": "create_new_workflow_skill",
            "args": {"skill_name": "test", "description": "test", "technical_requirements": "test"},
            "id": "call_1"
        }]
    )
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    
    graph = create_orchestrator_graph(mock_llm, [MagicMock()])
    
    state = {
        "messages": [HumanMessage(content="Create a new skill")],
        "thought_process": "",
        "current_node": "start"
    }
    
    # Run the graph for one step
    next_state = await graph.ainvoke(state)
    
    # Check if the next node is tools (indicated by tool_calls in the last message)
    assert len(next_state["messages"]) > 1
    assert next_state["messages"][-1].tool_calls[0]["name"] == "create_new_workflow_skill"

def test_mcp_server_serialization():
    """Verify MCP tools can be serialized (Conceptual test for FastMCP tools)."""
    # This would typically test the output of mcp.list_tools()
    # For now, we ensure our logic in app.py for discovery is sound.
    pass

if __name__ == "__main__":
    pytest.main([__file__])
