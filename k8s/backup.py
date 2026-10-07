## Main.py
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage

from tools.kubernetes_tools import (
    get_nodes,
    get_pods,
    get_pod_logs,
    get_events
)


# 1. Create the LLM
model = ChatOpenAI(
    model="gpt-5.4"
)


# 2. Define Kubernetes tools available to the LLM
tools = [
    get_nodes,
    get_pods,
    get_pod_logs,
    get_events
]


# 3. Tell the LLM which tools it can use
model_with_tools = model.bind_tools(tools)


# 4. Map tool name returned by LLM to actual Python tool
tool_map = {}

for tool in tools:
    tool_map[tool.name] = tool


# 5. Start conversation with the user's request
messages = [
    HumanMessage(
        content="Investigate why the application is failing in the ai-agent-lab namespace."
    )
]


# 6. Limit agent iterations to avoid an endless LLM → Tool loop
iterations = 0
max_iterations = 10


# 7. Agent loop: LLM decides → tool executes → result goes back to LLM
while iterations < max_iterations:

    iterations += 1
    print(f"\n======= Agent iteration {iterations} =======")


    # Ask LLM what to do next
    ai_message = model_with_tools.invoke(messages)

    # Save LLM response in conversation history
    messages.append(ai_message)

    print("\nLLM Response:")
    print(ai_message.content)

    print("\nTool Calls:")
    print(ai_message.tool_calls)


    # 8. No tool call means the LLM has finished investigation
    if not ai_message.tool_calls:

        print("\nFinal Answer:")
        print(ai_message.content)

        break


    # 9. Execute all tools requested by the LLM
    for tool_call in ai_message.tool_calls:

        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # Find the actual tool using the tool name
        selected_tool = tool_map[tool_name]

        print(f"\nSelected Tool: {tool_name}")
        print(f"Tool Arguments: {tool_args}")


        try:

            # Execute Kubernetes tool
            tool_result = selected_tool.invoke(
                tool_args
            )

            print("\nKubernetes Result:")
            print(tool_result)


            # 10. Send Kubernetes result back to LLM
            messages.append(
                ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call["id"]
                )
            )


        except ValueError as e:

            print("\nTool Error:")
            print(str(e))

            # Send tool error back to LLM instead of crashing agent
            messages.append(
                ToolMessage(
                    content=f"Tool execution failed: {str(e)}",
                    tool_call_id=tool_call["id"]
                )
            )


# 11. Agent did not finish within allowed iterations
else:

    print(
        f"\nAgent stopped after reaching "
        f"{max_iterations} iterations."
    )

## Tools.py
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from langchain_core.tools import tool


# 1. Load kubeconfig and create Kubernetes Core V1 API client
config.load_kube_config()
core_v1 = client.CoreV1Api()


# 2. Tool: Get worker nodes from the cluster
@tool
def get_nodes() -> list:
    """Get all worker nodes from the Kubernetes cluster."""

    nodes = core_v1.list_node()

    result = []

    for node in nodes.items:
        result.append({
            "name": node.metadata.name,
            "os": node.status.node_info.os_image,
            "kernel": node.status.node_info.kernel_version,
            "container_runtime": node.status.node_info.container_runtime_version
        })

    return result


# 3. Tool: Get pods from a namespace
@tool
def get_pods(namespace: str) -> list:
    """Get all the pods running in Kubernetes namespace."""

    try:
        # Verify namespace exists
        core_v1.read_namespace(name=namespace)

        pods = core_v1.list_namespaced_pod(
            namespace=namespace
        )

        result = []

        for pod in pods.items:
            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "node": pod.spec.node_name
            })

        return result

    except ApiException as e:

        if e.status == 404:
            raise ValueError(
                f"Kubernetes namespace '{namespace}' does not exist."
            )

        raise


# 4. Tool: Get logs from a specific pod
@tool
def get_pod_logs(namespace: str, pod_name: str) -> str:
    """Get logs from Kubernetes pod in a namespace."""

    try:
        # Verify namespace exists
        core_v1.read_namespace(name=namespace)

        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace
        )

        return logs

    except ApiException as e:

        if e.status == 404:
            raise ValueError(
                f"Pod '{pod_name}' or namespace '{namespace}' not found."
            )

        raise


# 5. Tool: Get Kubernetes events from a namespace
@tool
def get_events(namespace: str) -> list:
    """Get Kubernetes events from a namespace."""

    try:
        # Verify namespace exists
        core_v1.read_namespace(name=namespace)

        events = core_v1.list_namespaced_event(
            namespace=namespace
        )

        result = []

        for event in events.items:
            result.append({
                "type": event.type,
                "reason": event.reason,
                "object": event.involved_object.name,
                "kind": event.involved_object.kind,
                "message": event.message
            })

        return result

    except ApiException as e:

        if e.status == 404:
            raise ValueError(
                f"Kubernetes namespace '{namespace}' does not exist."
            )

        raise