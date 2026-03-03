import os
import json
import logging
from typing import Annotated, TypedDict, List, Dict, Any, Union, Optional
from typing_extensions import Required

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

# State Definition
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    thought_process: str
    current_node: str
    next_step: Optional[str]

# System Prompt Optimization for Qwen/Think-Step-By-Step
SYSTEM_PROMPT = """You are a Principal AI Orchestrator. 
Your primary goal is to solve complex researcher requests using available tools.

CRITICAL INSTRUCTIONS:
1. THINK BEFORE YOU ACT: For every user request, you must first output a detailed 'Thought' block. 
2. EXPLAIN YOUR REASONING: Explain why you are choosing a specific tool or why you need more information.
3. INTERROGATION RULE: If you are using the 'create_new_workflow_skill' tool, you MUST challenge the user. Do not implement a tool until the researcher has provided rigorous technical specifications. Ask about boundary conditions, schemas, and performance constraints.
4. FORMATTING: Return your final answer clearly. If you are in the middle of a thought process, maintain the 'Thought' trace in your internal state.

Current Node: {current_node}
"""

def create_orchestrator_graph(llm: ChatOpenAI, tools: List[Any]):
    """Creates the LangGraph state machine."""
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)
    
    # ─── Nodes ──────────────────────────────────────────────────
    
    async def call_model(state: AgentState, config: RunnableConfig):
        """Node: LLM Reasoning."""
        logger.info("Entering LLM reasoning node")
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT.format(current_node="llm_reasoning")),
            MessagesPlaceholder(variable_name="messages"),
        ])
        chain = prompt | llm_with_tools
        
        # We use astream_events in the app layer, but here we just return the result
        response = await chain.ainvoke(state, config)
        
        # Extract "thought" if any (assuming model might put it in content or we prompt for it)
        # For Qwen, it might use a specific tag or just plain text before tool calls.
        thought = ""
        if isinstance(response.content, str) and "Thought:" in response.content:
            thought = response.content.split("Thought:")[1].split("\n")[0].strip()
            
        return {
            "messages": [response],
            "thought_process": thought,
            "current_node": "llm_reasoning"
        }

    # Prebuilt tool node
    tool_node = ToolNode(tools)

    # ─── Graph Construction ─────────────────────────────────────
    
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    
    workflow.set_entry_point("agent")
    
    # Define conditional edges
    def should_continue(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges(
        "agent",
        should_continue,
    )
    
    workflow.add_edge("tools", "agent")
    
    return workflow.compile(checkpointer=MemorySaver())

if __name__ == "__main__":
    # Example initialization (for testing/structure)
    llm = ChatOpenAI(model="qwen3.5-35b", api_key="placeholder", base_url="http://emulator:8000/api/v1")
    # In practice, tools are fetched dynamically from MCP
    # graph = create_orchestrator_graph(llm, [])
    pass
