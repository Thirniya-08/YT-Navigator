"""ReAct Agent to process messages with tool calls."""

import copy
import os
import traceback
from typing import Literal

import structlog
from asgiref.sync import sync_to_async
from django.conf import settings
from langchain_core.messages import (
    AIMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import CompiledStateGraph

from app.schemas import (
    AgentOutput,
    AgentState,
)
from app.services.agent.prompts import SYSTEM_PROMPT_TEMPLATE
from app.services.vector_database.tools import (
    SQLTools,
    VectorDatabaseTools,
)
from app.utils.rate_limiter import create_retry_decorator

logger = structlog.get_logger(__name__)

# Maximum number of tool call rounds before forcing a final answer
MAX_TOOL_ITERATIONS = 2  # Reduced from 3 to prevent long processing

tools = [
    VectorDatabaseTools.tool(),
    SQLTools.tool(),
]

@create_retry_decorator(max_retries=5, base_delay=1.0, max_delay=60.0)
def create_model():
    """Create ChatGroq model with rate limiting."""
    return ChatGroq(
        model_name=settings.POWERFUL_LLM,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.0,
        max_tokens=2000,  # Further reduced to stay well under 6000 TPM limit
    ).bind_tools(tools)

model = create_model()

tools_by_name = {tool.name: tool for tool in tools}


# Define our tool node
async def tool_node(state: AgentState) -> AgentState:
    """Process tool calls from the last message.

    Args:
        state: The current agent state containing messages and tool calls.

    Returns:
        Dict with updated messages containing tool responses.
    """
    outputs = []
    for tool_call in state.messages[-1].tool_calls:
        try:
            tool = tools_by_name[tool_call["name"]]
            # Check if the tool has a coroutine (async) or only a sync func
            if tool.coroutine is not None:
                tool_result = await tool.ainvoke(tool_call["args"])
            else:
                # Run sync tools in a thread to avoid blocking the event loop
                tool_result = await sync_to_async(tool.invoke, thread_sensitive=False)(tool_call["args"])
            # Ensure result is a string
            if not isinstance(tool_result, str):
                tool_result = str(tool_result)
        except Exception as e:
            logger.error("Tool execution error", tool_name=tool_call["name"], error=str(e), traceback=traceback.format_exc())
            tool_result = f"Tool error: {str(e)}"
        outputs.append(
            ToolMessage(
                content=tool_result,
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )
    return {"messages": outputs}


async def call_model(
    state: AgentState,
    config: RunnableConfig,
) -> AgentState:
    """Call the model with the system prompt and tool calls.

    Args:
        state: The current agent state containing messages and tool calls.
        config: The configuration for the runnable.

    Returns:
        Dict with updated messages containing the model's response.
    """
    output_parser = PydanticOutputParser(pydantic_object=AgentOutput)

    # Safely get channel description
    channel_str = "No channel (single video mode)"
    if state.channel is not None:
        try:
            channel_str = await state.channel.pretty_str()
        except Exception as e:
            logger.warning("Error getting channel pretty_str", error=str(e))
            channel_str = str(state.channel)

    system_prompt = SystemMessage(
        SYSTEM_PROMPT_TEMPLATE.format(
            channel=channel_str,
            user=state.user,
            format_instructions=output_parser.get_format_instructions(),
        )
    )

    trimmed_messages = trim_messages(
        copy.deepcopy(state.messages),
        strategy="last",
        token_counter=model,
        max_tokens=5000,  # Further reduced to speed up processing
        start_on="human",
        include_system=False,
        allow_partial=False,
    )

    response = await model.ainvoke([system_prompt] + trimmed_messages, config)

    # Ensure response content is valid AgentOutput JSON
    try:
        AgentOutput.model_validate_json(response.content)
    except Exception:
        logger.warning("LLM response is not valid AgentOutput JSON, wrapping it")
        # Try to extract JSON from the response (LLM may have added extra text around it)
        import json
        import re
        content = response.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if "placeholder" in parsed:
                    wrapped = AgentOutput(**parsed)
                    response.content = wrapped.model_dump_json()
                    return {"messages": [response]}
            except Exception:
                pass
        # Fallback: wrap plain text as AgentOutput
        wrapped = AgentOutput(placeholder=str(content), videos=[])
        response.content = wrapped.model_dump_json()

    return {"messages": [response]}


def _count_tool_iterations(state: AgentState) -> int:
    """Count the number of tool call rounds in the current conversation."""
    count = 0
    for msg in state.messages:
        if isinstance(msg, ToolMessage):
            count += 1
    # Each tool call round can have multiple ToolMessages, approximate by counting ToolMessage groups
    return count


def should_continue(state: AgentState) -> Literal["end", "continue"]:
    """Determine if the agent should continue or end based on the last message.

    Args:
        state: The current agent state containing messages.

    Returns:
        Literal["end", "continue"]: "end" if there are no tool calls, "continue" otherwise.
    """
    messages = state.messages
    last_message = messages[-1]
    # If there is no function call, then we finish
    if not last_message.tool_calls:
        return "end"
    # Check if we've exceeded the max tool iterations
    tool_count = _count_tool_iterations(state)
    if tool_count >= MAX_TOOL_ITERATIONS * 2:  # Each round has ~2 tool messages
        return "end"
    return "continue"


def build_workflow() -> CompiledStateGraph:
    """Build the workflow for the agent.

    Returns:
        CompiledStateGraph: The compiled workflow for the agent.
    """
    workflow = StateGraph(AgentState)

    # Define the two nodes we will cycle between
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")

    # We now add a conditional edge
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            # If `tools`, then we call the tool node.
            "continue": "tools",
            # Otherwise we finish.
            "end": END,
        },
    )

    workflow.add_edge("tools", "agent")

    return workflow.compile()


react_agent = build_workflow()
