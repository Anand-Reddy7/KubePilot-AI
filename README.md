# KubePilot-AI

A local Kubernetes troubleshooting assistant with a browser chat interface. It uses FastAPI, LangGraph, OpenAI, and an MCP server to inspect Kubernetes pods, nodes, events, and logs. Runbook search uses Qdrant; PostgreSQL stores chat metadata and LangGraph checkpoints. The agent can request approval to update a deployment's container image.

The Python application and MCP server run as separate processes on your host, connected through Streamable HTTP. Docker Compose runs PostgreSQL and Qdrant. The MCP server accesses Kubernetes through its local kubeconfig.

## Prerequisites

- Python 3.12. The documented working setup uses Python 3.12 on Apple Silicon macOS.
- Docker Desktop or another running Docker engine, such as Colima, and Docker Compose.
- `kubectl`, a valid kubeconfig, and access to your intended Kubernetes cluster.
- An OpenAI API key with access to the configured `gpt-5.4` chat model and `text-embedding-3-small` embedding model. Chat and ingestion make paid API requests.
- Available local ports: `5432` (PostgreSQL), `6333` and `6334` (Qdrant), `8000` (application), and `8001` (MCP server).

This is a local development application, without application authentication. Keep the web server bound to `127.0.0.1`. The supplied Compose configuration publishes database ports on all host interfaces and uses development database credentials; use a trusted development machine/network. Do not expose this configuration as a public service.

## 1. Clone and create a Python environment

Clone this repository using its GitHub clone URL, then change into its root directory:

```bash
cd KubePilot-AI
```

On **Apple Silicon macOS**, explicitly use ARM64 to avoid mixing Intel and ARM Python packages:

```bash
arch -arm64 python3 -m venv .venv-arm64
source .venv-arm64/bin/activate
arch -arm64 python -m pip install --upgrade pip
arch -arm64 python -m pip install --only-binary=cryptography -r requirements.txt
```

On **other platforms**, create a native environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

These shell examples use bash/zsh. Windows activation is `.venv\Scripts\Activate.ps1` in PowerShell. Other operating systems have not been verified with these exact dependency pins; Intel macOS may require a compatible OpenSSL source-build setup for `cryptography`.

`requirements.txt` includes the application dependencies, including FastMCP, Qdrant integration, and PostgreSQL checkpoint support. The supplemental dependency versions were taken from the working ARM64 environment.

Verify the environment:

```bash
python -m pip check
python -c "from cryptography.exceptions import InvalidTag; from fastmcp import Client; from langchain.mcp import MCPAdapter; from mcp.server.mcpserver import MCPServer; from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; print('Imports OK')"
```

For Apple Silicon, prefix subsequent `python` commands with `arch -arm64` if your terminal runs under Rosetta. Always use the same architecture for installation and execution.

## 2. Export application settings

Export these settings in the **application terminal**, before launching Uvicorn. Exports apply to the current shell and its child processes; they are not shared with other terminals or an already-running app.

| Variable | When needed | Local value or purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | Required for the app and ingestion | Your OpenAI API key |
| `MCP_SERVER_URL` | Recommended explicit setting | `http://127.0.0.1:8001/mcp` (also the code's default) |
| `LANGSMITH_TRACING` | Optional tracing | `true` to enable; `false` to disable |
| `LANGSMITH_API_KEY` | Required when tracing is enabled | Your LangSmith workspace's API key |
| `LANGSMITH_ENDPOINT` | Required for APAC tracing | `https://apac.api.smith.langchain.com` |
| `LANGSMITH_PROJECT` | Optional tracing project name | `kubepilot-local` |
| `LANGSMITH_HIDE_INPUTS` | Optional trace content control | `false` to display inputs; `true` to hide them |
| `LANGSMITH_HIDE_OUTPUTS` | Optional trace content control | `false` to display outputs; `true` to hide them |
| `LANGSMITH_WORKSPACE_ID` | If required by your LangSmith key | Workspace ID, especially for organization-scoped keys |

### OpenAI key and MCP connection

In the terminal that will run ingestion and the application, run these commands **one at a time** in bash/zsh:

```bash
echo "Paste your OpenAI API key at the next prompt, then press Enter:"
read -r -s OPENAI_API_KEY
export OPENAI_API_KEY
echo
```

After running the `read` command, paste the key and press Enter. Input is hidden. Do not replace the variable name with your key. The variable must be named `OPENAI_API_KEY`, not `api_key`.

Verify presence without printing the secret:

```bash
python -c 'import os; print("Key is set" if os.getenv("OPENAI_API_KEY", "").strip() else "Key is missing")'
```

Set the MCP endpoint:

```bash
export MCP_SERVER_URL="http://127.0.0.1:8001/mcp"
```

The application does **not** automatically load `.env`. Repeat these exports in each new terminal session, or use your own secure environment configuration. Never commit API keys or kubeconfig credentials. Database URLs and model names are currently hardcoded; exporting alternative database/model variables will not change them.

### Optional: LangSmith tracing in APAC

Create your key in the [APAC LangSmith UI](https://apac.smith.langchain.com/). In the application terminal, enter it using these commands **one at a time**, pasting the key after running `read`:

```bash
echo "Paste your LangSmith API key after running the next command:"
read -r -s LANGSMITH_API_KEY
export LANGSMITH_API_KEY
echo
```

Then export the tracing settings:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_ENDPOINT="https://apac.api.smith.langchain.com"
export LANGSMITH_PROJECT="kubepilot-local"
export LANGSMITH_HIDE_INPUTS=false
export LANGSMITH_HIDE_OUTPUTS=false
```

These content settings let you inspect prompts, model responses, tool results, and retrieved runbooks. They can send cluster details and pod logs to LangSmith. Set both `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS` to `true` to hide input/output payloads; metadata and errors may still contain information. See [LangSmith's masking guidance](https://docs.langchain.com/langsmith/mask-inputs-outputs).

If your key requires a workspace ID, also export `LANGSMITH_WORKSPACE_ID` with the ID from your workspace settings. For accounts in another region, use that region's API endpoint rather than the APAC URL. See [LangSmith configuration](https://reference.langchain.com/python/langsmith).

Verify settings without printing either API key:

```bash
arch -arm64 python - <<'PY'
import os

for name in (
    "MCP_SERVER_URL", "LANGSMITH_TRACING", "LANGSMITH_ENDPOINT",
    "LANGSMITH_PROJECT", "LANGSMITH_HIDE_INPUTS", "LANGSMITH_HIDE_OUTPUTS",
):
    print(f"{name}: {os.getenv(name, 'NOT SET')}")
for name in ("OPENAI_API_KEY", "LANGSMITH_API_KEY"):
    print(f"{name} set: {bool(os.getenv(name, '').strip())}")
PY
```

Omit `arch -arm64` on other platforms. If you do not want tracing, run `export LANGSMITH_TRACING=false`; no LangSmith key is needed in that case.

## 3. Start PostgreSQL and Qdrant

Start your Docker engine first. From the repository root:

```bash
docker compose -f k8s/docker-compose.yml up -d
docker compose -f k8s/docker-compose.yml ps
docker compose -f k8s/docker-compose.yml exec postgres pg_isready -U agentuser -d agentdb
curl -fsS http://localhost:6333/collections
```

If `docker compose` is unavailable but the standalone command is installed, replace it with `docker-compose` in every command above and below. The verified macOS setup uses `docker-compose`.

The application expects these values, already configured in Compose:

| Service | Local configuration |
| --- | --- |
| PostgreSQL | Host `localhost`, port `5432`, database `agentdb`, user `agentuser`, password `agentpassword` |
| Qdrant | `http://localhost:6333`, collection `kubernetes_runbooks` |

PostgreSQL tables are created automatically when the application starts. Docker named volumes preserve database contents. Keep the same Compose project name/location when restarting to reuse them. Do not run `down -v` unless you intend to delete stored chats and runbooks.

Use `k8s/docker-compose.yml` for this setup. `k8s/postgress.yml` is a duplicate Compose configuration; `k8s/qdrant.yml` is a separate Kubernetes manifest and is not needed here.

## 4. Verify Kubernetes access

```bash
kubectl config current-context
kubectl cluster-info
kubectl get nodes
```

Confirm that the selected context is the cluster you intend the agent to access. The MCP server loads your kubeconfig on startup. Your cluster credentials need permission to read namespaces, nodes, pods, pod logs, and events. The additional listing tools need `list` permission on namespaces, deployments, services, secrets, and configmaps; namespaced tools also check namespace existence with `get` on namespaces. Updating deployment images also requires permission to patch deployments.

Available additional read-only tools:

| Tool | Input | Returned information |
| --- | --- | --- |
| `get_namespaces` | None | Namespace names and phases |
| `get_deployments` | `namespace` | Names, replica counts, and container images |
| `get_services` | `namespace` | Names, types, addresses, selectors, and ports |
| `list_secrets` | `namespace` | Names, types, and data key counts; no secret values or annotations |
| `list_config_maps` | `namespace` | Names and text/binary key names; no configuration values or annotations |

The agent discovers MCP tools automatically at application startup. After changing the MCP server, restart its process and then restart the application. Secret listing fetches Secret objects from Kubernetes but returns only the fields above to the agent and its traces.

You can ask about any namespace you can access. The sample `ai-agent-lab` manifests are optional troubleshooting fixtures, including intentionally broken workloads. They are not prerequisites for starting the app; do not apply the entire `k8s/` directory as a Kubernetes manifest bundle.

## 5. Initialize the runbook collection once

Check for an existing collection:

```bash
curl -fsS http://localhost:6333/collections/kubernetes_runbooks
```

If it exists and already contains your runbook data, skip ingestion. A new Docker volume will not contain this collection. The app connects to it during import, so initialize it **before launching Uvicorn**.

**Current repository limitation:** `ingest.py` expects `kubernetes_runbook.txt`, which is not included. The maintained runbooks are in `knowledge/*.md`. Use this one-time command from the repository root to load those files without changing application source:

```bash
python - <<'PY'
from pathlib import Path
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

paths = sorted(Path("knowledge").glob("*.md"))
if not paths:
    raise SystemExit("No runbooks found; run this from the repository root.")

documents = []
for path in paths:
    documents.extend(TextLoader(str(path), encoding="utf-8").load())

chunks = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=200
).split_documents(documents)

QdrantVectorStore.from_documents(
    documents=chunks,
    embedding=OpenAIEmbeddings(model="text-embedding-3-small"),
    url="http://localhost:6333",
    collection_name="kubernetes_runbooks",
)
print(f"Ingested {len(chunks)} chunks from {len(paths)} runbooks.")
PY
```

On Apple Silicon under Rosetta, use `arch -arm64 python - <<'PY'` as the first line. Ingestion calls the OpenAI embeddings API. Repeating this command can add duplicate documents; it is intended for initial setup of an empty database.

## 6. Start the MCP server — terminal 1

From the repository root in a separate terminal:

```bash
source .venv-arm64/bin/activate
arch -arm64 python mcp_server.py
```

On other platforms, activate `.venv` and run `python mcp_server.py`.

The server listens at `http://127.0.0.1:8001/mcp`. Keep this terminal running. It needs Kubernetes access, but does not need your OpenAI key, LangSmith key, PostgreSQL, or Qdrant. It loads the default kubeconfig; for a different file, export `KUBECONFIG` with that file's path **in the MCP terminal before starting it**.

The `/mcp` endpoint is a protocol endpoint, not a browser UI. Keep it local: the MCP server includes a deployment-image write tool, and approval is enforced by the agent rather than the MCP server itself.

## 7. Start the application — terminal 2

Use the application terminal where you exported the settings in step 2. Keep your environment active and run from the repository root, after the MCP server is listening:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

For the verified Apple Silicon setup:

```bash
arch -arm64 python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete`, then open:

- Application: <http://127.0.0.1:8000/>
- API documentation: <http://127.0.0.1:8000/docs>
- Basic health endpoint: <http://127.0.0.1:8000/health>

The app connects to `MCP_SERVER_URL`; it does not launch or stop the MCP server. There is no separate frontend build. Stopping the application leaves MCP running. After restarting MCP, restart the application to establish a fresh connection.

For tracing, send a **new chat message**, then open `kubepilot-local` in the [APAC LangSmith UI](https://apac.smith.langchain.com/). Starting the server or opening the homepage alone does not run the agent. Expand child runs to inspect model calls and tools. Changes to trace visibility settings apply to new requests after an application restart; previously hidden content is not restored.

Try a read-only request such as “List the nodes in my Kubernetes cluster,” then ask a runbook question such as “How do I troubleshoot ImagePullBackOff?” A successful `/health` response alone does not verify Kubernetes access or all tool calls.

## Restarting after initial setup

1. Start Docker and your Kubernetes cluster, if it is local.
2. Run `docker compose -f k8s/docker-compose.yml up -d` (or `docker-compose`) from the repository root.
3. In terminal 1, activate your environment and start `mcp_server.py` as shown in step 6.
4. In terminal 2, change into the repository root and activate your environment.
5. Export `OPENAI_API_KEY` and `MCP_SERVER_URL` in terminal 2. If tracing is wanted, also export the LangSmith key, APAC endpoint, project, tracing flag, and visibility settings from step 2.
6. Start Uvicorn in terminal 2 using the command in step 7.

You do not need to reinstall dependencies or ingest runbooks on every restart. Stop the application with Ctrl+C in terminal 2; stop MCP separately with Ctrl+C in terminal 1. To stop the database containers while retaining data:

```bash
docker compose -f k8s/docker-compose.yml stop
```

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `Missing credentials` | Set and export `OPENAI_API_KEY` in the same terminal as Uvicorn. A `.env` file alone is not loaded. |
| `cryptography` architecture error or `_EVP_DigestSqueeze` | On Apple Silicon, use a clean ARM64 environment and the binary-wheel installation command above. Do not reuse an Intel environment. |
| FastMCP reports missing client support | Inspect the first exception in the traceback; a failed `cryptography` import can cause this wrapper error. |
| Qdrant collection not found | Complete the one-time ingestion step before starting the app. |
| PostgreSQL connection refused | Confirm Docker is running, port `5432` is available, and `pg_isready` succeeds. |
| MCP server startup failure | Verify its activated Python environment, kubeconfig, and that port `8001` is available. |
| Application cannot connect to MCP | Start `mcp_server.py` first and verify `MCP_SERVER_URL=http://127.0.0.1:8001/mcp` in the application terminal. |
| No LangSmith traces | Check `LANGSMITH_TRACING=true`, key presence, APAC endpoint, and workspace. Restart the app, send a new chat message, then open the APAC UI and correct project. Check terminal logs for upload errors. |
| Trace metadata visible but inputs/outputs empty | Set `LANGSMITH_HIDE_INPUTS=false` and `LANGSMITH_HIDE_OUTPUTS=false`, restart the app, and send a new message if you want payloads recorded. |
| Kubernetes permission error | Verify the selected context and its permissions for the requested resource. |
| `LangChainBetaWarning` | Informational warning about `langchain.mcp`; it does not prevent startup. |
| `/favicon.ico` returns 404 | No browser tab icon is included; the app still works. |

## Current limitations

- Approval handling assumes a single deployment-image update in a model response. Multiple tool calls in the same response are not correctly handled by the approval flow. Use a development cluster and avoid requests for batches of changes.
- Pending approval controls are not restored when reloading a chat. Avoid refreshing or switching chats while a request or approval is pending.
- Database URLs and model names are currently hardcoded in the Python files.
- There is no authentication or per-user chat isolation; this setup is intended for local development.

## Repository layout

```text
main.py             FastAPI endpoints, database lifecycle, static UI hosting
agent.py            LangGraph agent and approval flow
mcp_server.py       Kubernetes MCP tools
rag.py              Qdrant retriever
ingest.py           Original single-file ingestion script (see setup caveat)
tools/rag_tools.py  Runbook search tool
knowledge/          Markdown troubleshooting runbooks
static/index.html   Browser chat interface
k8s/                Compose configuration and optional Kubernetes examples
requirements.txt    Application dependency pins
```

`.gitignore` excludes virtual environments, Python caches, local `.env` secrets, credential directories, and local data exports. It does not remove files already tracked by Git or erase secrets from Git history. Review staged changes before publishing; revoke any credentials previously exposed in logs or commits.
