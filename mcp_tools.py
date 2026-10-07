import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient


BASE_DIR = Path(__file__).resolve().parent
MCP_SERVER = BASE_DIR / "mcp_server.py"


client = MultiServerMCPClient(
    {
        "kubernetes": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(MCP_SERVER)]
        }
    }
)


async def load_mcp_tools():
    return await client.get_tools()


async def test():
    print("Python:", sys.executable)
    print("MCP server:", MCP_SERVER)

    tools = await load_mcp_tools()

    print("\nMCP tools available:")

    for tool in tools:
        print(f"- {tool.name}")


if __name__ == "__main__":
    asyncio.run(test())