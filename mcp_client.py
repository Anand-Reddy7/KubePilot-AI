import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


# 1. Locate MCP server
BASE_DIR = Path(__file__).resolve().parent

MCP_SERVER = BASE_DIR / "mcp_server.py"


# 2. Configure stdio MCP server
server = StdioServerParameters(
    command=sys.executable,
    args=[
        str(MCP_SERVER)
    ]
)


# 3. Connect and test MCP
async def main():

    async with Client(server) as client:

        # List tools
        tools = await client.list_tools()

        print("Available MCP tools:")

        for tool in tools.tools:

            print(
                f"- {tool.name}"
            )

        # Call Kubernetes MCP tool
        result = await client.call_tool(
            "get_pods",
            {
                "namespace": "ai-agent-lab"
            }
        )

        print("\nContent:")
        print(result.content)

        print("\nStructured Content:")
        print(result.structured_content)

        print("\nTool error:")
        print(result.is_error)


if __name__ == "__main__":
    asyncio.run(main())