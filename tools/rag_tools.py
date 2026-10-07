from langchain_core.tools import tool

from rag import retriever


@tool
def search_book(query: str) -> str:
    """
    Search the internal Kubernetes troubleshooting runbook before providing
    troubleshooting guidance, remediation steps, configuration fixes, or
    example Kubernetes YAML.

    Use this tool when the user asks how to troubleshoot or fix a Kubernetes
    problem, requests remediation steps, asks what configuration should be
    changed, or asks for example YAML related to a Kubernetes issue.

    Prefer the procedures and examples retrieved from this runbook instead of
    answering only from generic model knowledge.
    """

    documents = retriever.invoke(
        query
    )

    if not documents:

        return (
            "No relevant runbook "
            "information found."
        )

    results = []

    for document in documents:

        source = document.metadata.get(
            "source",
            "unknown"
        )

        results.append(
            f"Source: {source}\n\n"
            f"{document.page_content}"
        )

    return "\n\n---\n\n".join(
        results
    )