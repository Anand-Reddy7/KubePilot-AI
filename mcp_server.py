from mcp.server.mcpserver import MCPServer

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


# 1. Create MCP server
mcp = MCPServer(
    "kubernetes-operations",
    version="1.0.0"
)


# 2. Connect to Kubernetes
config.load_kube_config()

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


# 3. Get Kubernetes pods
@mcp.tool()
def get_pods(namespace: str) -> list:
    """
    Get all pods and their container status
    from a Kubernetes namespace.
    """

    try:
        core_v1.read_namespace(
            name=namespace
        )

        pods = core_v1.list_namespaced_pod(
            namespace=namespace
        )

        result = []

        for pod in pods.items:

            container_statuses = []

            if pod.status.container_statuses:

                for status in pod.status.container_statuses:

                    container_state = "unknown"

                    if status.state.waiting:

                        container_state = (
                            status.state.waiting.reason
                        )

                    elif status.state.running:

                        container_state = "Running"

                    elif status.state.terminated:

                        container_state = (
                            status.state.terminated.reason
                            or "Terminated"
                        )

                    container_statuses.append({
                        "name": status.name,
                        "ready": status.ready,
                        "restart_count":
                            status.restart_count,
                        "state": container_state
                    })

            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "containers": container_statuses
            })

        return result

    except ApiException as e:

        if e.status == 404:

            raise ValueError(
                f"Kubernetes namespace "
                f"'{namespace}' does not exist."
            )

        raise


# 4. Get Kubernetes nodes
@mcp.tool()
def get_nodes() -> list:
    """
    Get all worker nodes from the Kubernetes cluster.
    """

    nodes = core_v1.list_node()

    result = []

    for node in nodes.items:

        result.append({
            "name": node.metadata.name,
            "os": node.status.node_info.os_image,
            "kernel":
                node.status.node_info.kernel_version,
            "container_runtime":
                node.status.node_info.container_runtime_version
        })

    return result


# 5. Get Kubernetes events
@mcp.tool()
def get_events(namespace: str) -> list:
    """
    Get Kubernetes events from a namespace.
    """

    try:
        core_v1.read_namespace(
            name=namespace
        )

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
                f"Kubernetes namespace "
                f"'{namespace}' does not exist."
            )

        raise


# 6. Get Kubernetes pod logs
@mcp.tool()
def get_pod_logs(
    namespace: str,
    pod_name: str
) -> str:
    """
    Get logs from a Kubernetes pod.
    """

    try:
        core_v1.read_namespace(
            name=namespace
        )

        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace
        )

        return logs

    except ApiException as e:

        if e.status == 400:
            return (
                f"Logs are not available for pod '{pod_name}'. "
                "The container may not have started yet. "
                "Check pod status and Kubernetes events."
            )

        if e.status == 404:
            return (
                f"Pod '{pod_name}' was not found "
                f"in namespace '{namespace}'."
            )

        return (
            f"Unable to retrieve logs for pod "
            f"'{pod_name}': {e.reason}"
        )

@mcp.tool()
def update_deployment_image(
    namespace: str,
    deployment_name: str,
    container_name: str,
    image: str
) -> dict:
    """
    Update the container image of a Kubernetes Deployment.
    This is a write operation that modifies the Kubernetes workload.
    """

    patch = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "image": image
                        }
                    ]
                }
            }
        }
    }

    apps_v1.patch_namespaced_deployment(
        name=deployment_name,
        namespace=namespace,
        body=patch
    )

    return {
        "status": "updated",
        "deployment": deployment_name,
        "container": container_name,
        "image": image
    }


# 7. Start MCP server
if __name__ == "__main__":
    mcp.run()