from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage
from langchain.mcp import MCPAdapter

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from tools.rag_tools import search_book


# 1. Define Agent State
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# 2. Create LangGraph Agent
async def create_graph(mcp_client, checkpointer):

    # Discover Kubernetes tools dynamically from MCP
    adapter = MCPAdapter(mcp_client)

    mcp_tools = await adapter.list_tools()

    print("\nDiscovered MCP tools:")

    for tool in mcp_tools:
        print(f"- {tool.name}")

    # Kubernetes MCP tools + Qdrant RAG tool
    tools = mcp_tools + [search_book]

    print("\nAvailable Agent tools:")

    for tool in tools:
        print(f"- {tool.name}")

    tool_node = ToolNode(tools)


    # 3. Create LLM
    model = ChatOpenAI(
        model="gpt-5.4"
    )

    model_with_tools = model.bind_tools(tools)


    # 4. LLM Node
    async def llm_node(state: AgentState):

        response = await model_with_tools.ainvoke(
            state["messages"]
        )

        return {
            "messages": [response]
        }


    # 5. Route after LLM
    def route_after_llm(state: AgentState):

        last_message = state["messages"][-1]

        tool_calls = getattr(
            last_message,
            "tool_calls",
            None
        )

        # No tool call -> finish
        if not tool_calls:
            return "end"

        # Check whether write operation requires approval
        for tool_call in tool_calls:

            if tool_call["name"] == "update_deployment_image":
                return "approval"

        # Read-only tools and RAG execute directly
        return "tools"


    # 6. Human Approval Node
    def approval_node(state: AgentState):

        last_message = state["messages"][-1]

        tool_calls = getattr(
            last_message,
            "tool_calls",
            []
        )

        for tool_call in tool_calls:

            if tool_call["name"] == "update_deployment_image":

                decision = interrupt(
                    {
                        "type": "approval_required",
                        "tool": tool_call["name"],
                        "arguments": tool_call["args"]
                    }
                )

                # Approved -> keep original tool call
                # ToolNode executes it next
                if decision == "approve":
                    return {}

                # Rejected -> satisfy tool_call_id
                # without executing Kubernetes change
                return {
                    "messages": [
                        ToolMessage(
                            content=(
                                "The user rejected this "
                                "Kubernetes change."
                            ),
                            tool_call_id=tool_call["id"]
                        )
                    ]
                }

        return {}


    # 7. Route after Human Approval
    def route_after_approval(state: AgentState):

        last_message = state["messages"][-1]

        tool_calls = getattr(
            last_message,
            "tool_calls",
            None
        )

        # Approval kept original AI tool call
        if tool_calls:
            return "tools"

        # Rejection added ToolMessage
        return "llm"


    # 8. Build LangGraph
    builder = StateGraph(AgentState)

    builder.add_node(
        "llm",
        llm_node
    )

    builder.add_node(
        "tools",
        tool_node
    )

    builder.add_node(
        "approval",
        approval_node
    )


    # 9. Define Graph Flow
    builder.add_edge(
        START,
        "llm"
    )

    builder.add_conditional_edges(
        "llm",
        route_after_llm,
        {
            "tools": "tools",
            "approval": "approval",
            "end": END
        }
    )

    builder.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "tools": "tools",
            "llm": "llm"
        }
    )

    builder.add_edge(
        "tools",
        "llm"
    )


    # 10. Compile with PostgreSQL Checkpointer
    graph = builder.compile(
        checkpointer=checkpointer
    )

    return graph