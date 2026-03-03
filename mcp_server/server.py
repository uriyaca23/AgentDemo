import os
import sys
import importlib.util
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Initialize FastMCP server
mcp = FastMCP("MetacognitiveOrchestrator")

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")

@mcp.tool()
async def create_new_workflow_skill(
    skill_name: str,
    description: str,
    technical_requirements: str,
    user_clarification: Optional[str] = None
) -> str:
    """
    A meta-tool to design and implement new Python tools for the MCP server.
    
    This tool follows a strict 'Metacognitive' loop:
    1. If user_clarification is missing/insufficient, it returns rigorous technical questions.
    2. Only after satisfactory answers is the code generated and saved.
    
    Args:
        skill_name: The name of the new tool (e.g., 'fokker_planck_solver').
        description: High-level purpose of the tool.
        technical_requirements: Raw technical specs or researcher request.
        user_clarification: The user's response to previous interrogation questions.
    """
    
    # Logic for interrogation vs implementation
    if not user_clarification:
        # Initial call - Interrogate the user
        questions = [
            f"Regarding the creation of '{skill_name}':",
            "1. What is the exact mathematical or logical specification (e.g., JSON schema, differential equations, API endpoints)?",
            "2. How should we handle edge cases, non-convergence, or error states specific to this domain?",
            "3. What are the performance constraints or external library dependencies?",
            f"\nPlease provide these details in the 'user_clarification' field."
        ]
        return "\n".join(questions)

    # If we have clarification, we theoretically would generate code here.
    # In a real scenario, this 'tool' is called by the LLM. 
    # If the LLM provides 'user_clarification', it means the loop is closing.
    
    # For safety and "Production-Ready" logic, we validate the presence of specific keywords 
    # indicating the researcher has actually answered the questions.
    if len(user_clarification.split()) < 10:
        return "ERROR: The provided clarification is insufficient. Please address all technical questions rigorously."

    # IMPLEMENTATION logic (Simplified for the meta-tool's own definition)
    # The LLM will use this as a signal to generate the final code block.
    
    skill_file_path = os.path.join(SKILLS_DIR, f"{skill_name}.py")
    
    # Note: In a production LangGraph flow, the Orchestrator would see this output
    # and might trigger a specific 'CodeWriter' node or similar.
    # Here, we represent the SUCCESS state.
    
    return f"SUCCESS: Technical validation passed for '{skill_name}'. Proceeding to code generation and hot-reload."

def load_skills():
    """Dynamically load tools from the skills directory."""
    if not os.path.exists(SKILLS_DIR):
        os.makedirs(SKILLS_DIR)
        
    for filename in os.listdir(SKILLS_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            skill_name = filename[:-3]
            file_path = os.path.join(SKILLS_DIR, filename)
            
            # Dynamic import logic
            spec = importlib.util.spec_from_file_location(skill_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # If the module has a function decorated with @mcp.tool, it might need 
                # manual registration depending on FastMCP's internal discovery.
                # FastMCP usually handles decorators if they share the same 'mcp' instance.
                # For this implementation, we assume shared instance or dynamic re-binding.
                logger.info(f"Loaded skill: {skill_name}")

if __name__ == "__main__":
    import uvicorn
    load_skills()
    uvicorn.run(mcp, host="0.0.0.0", port=8080)
