from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from psycopg_pool import AsyncConnectionPool

from agent import create_graph


# 1. PostgreSQL Configuration
DB_URI = (
    "postgresql://agentuser:agentpassword"
    "@localhost:5432/agentdb"
)


# 2. FastAPI Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):

    # Application database pool
    async with AsyncConnectionPool(
        conninfo=DB_URI,
        open=False
    ) as db_pool:

        await db_pool.open()

        app.state.db_pool = db_pool

        # Create our application-owned chats table
        async with db_pool.connection() as conn:

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    thread_id VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )

            await conn.commit()

        print("Application database connected")

        # LangGraph PostgreSQL checkpointer
        async with AsyncPostgresSaver.from_conn_string(
            DB_URI
        ) as checkpointer:

            await checkpointer.setup()

            print("PostgreSQL checkpointer connected")

            # MCP connection
            transport = StdioTransport(
                command="python",
                args=["mcp_server.py"]
            )

            async with Client(transport) as mcp_client:

                print("MCP client connected")

                app.state.graph = await create_graph(
                    mcp_client,
                    checkpointer
                )

                print("LangGraph agent ready")

                yield


# 3. Create FastAPI Application
app = FastAPI(
    title="Kubernetes Agent",
    lifespan=lifespan
)


# 4. Request Models
class ChatRequest(BaseModel):
    message: str
    thread_id: str


class ApprovalRequest(BaseModel):
    thread_id: str
    decision: str


# 5. Response Builder
def build_response(result):

    if "__interrupt__" in result:

        interrupts = result["__interrupt__"]

        return {
            "status": "approval_required",
            "approval": interrupts[0].value
        }

    messages = result.get("messages", [])

    if not messages:
        return {
            "status": "completed",
            "answer": ""
        }

    return {
        "status": "completed",
        "answer": messages[-1].content
    }


# 6. Create / Update Chat Metadata
async def save_chat(thread_id: str, message: str):

    title = message.strip()

    if len(title) > 60:
        title = title[:60] + "..."

    async with app.state.db_pool.connection() as conn:

        await conn.execute(
            """
            INSERT INTO chats (
                thread_id,
                title
            )
            VALUES (%s, %s)

            ON CONFLICT (thread_id)
            DO UPDATE SET
                updated_at = NOW()
            """,
            (
                thread_id,
                title
            )
        )

        await conn.commit()


# 7. Chat Endpoint
@app.post("/chat")
async def chat(payload: ChatRequest):

    await save_chat(
        payload.thread_id,
        payload.message
    )

    config = {
        "configurable": {
            "thread_id": payload.thread_id
        }
    }

    result = await app.state.graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=payload.message
                )
            ]
        },
        config=config
    )

    return build_response(result)


# 8. List Existing Chats
@app.get("/threads")
async def list_threads():

    async with app.state.db_pool.connection() as conn:

        cursor = await conn.execute(
            """
            SELECT
                thread_id,
                title,
                created_at,
                updated_at
            FROM chats
            ORDER BY updated_at DESC
            """
        )

        rows = await cursor.fetchall()

    return [
        {
            "thread_id": row[0],
            "title": row[1],
            "created_at": row[2],
            "updated_at": row[3]
        }
        for row in rows
    ]


# 9. Load Existing Chat History
@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    state = await app.state.graph.aget_state(
        config
    )

    if not state or not state.values:
        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    messages = state.values.get(
        "messages",
        []
    )

    history = []

    for message in messages:

        message_type = getattr(
            message,
            "type",
            ""
        )

        # User messages
        if message_type == "human":

            history.append(
                {
                    "role": "user",
                    "content": message.content
                }
            )

        # Assistant messages
        elif message_type == "ai":

            # Don't display empty AI messages
            # that only contain tool calls
            if message.content:

                history.append(
                    {
                        "role": "assistant",
                        "content": message.content
                    }
                )

        # ToolMessages intentionally aren't displayed
        # in normal chat UI

    return {
        "thread_id": thread_id,
        "messages": history
    }


# 10. Human Approval Endpoint
@app.post("/approval")
async def approval(payload: ApprovalRequest):

    if payload.decision not in {
        "approve",
        "reject"
    }:
        raise HTTPException(
            status_code=400,
            detail="decision must be approve or reject"
        )

    config = {
        "configurable": {
            "thread_id": payload.thread_id
        }
    }

    result = await app.state.graph.ainvoke(
        Command(
            resume=payload.decision
        ),
        config=config
    )

    return build_response(result)


# 11. Health Endpoint
@app.get("/health")
async def health():

    return {
        "status": "ok"
    }


# 12. Static UI
# Keep this LAST
app.mount(
    "/",
    StaticFiles(
        directory="static",
        html=True
    ),
    name="static"
)