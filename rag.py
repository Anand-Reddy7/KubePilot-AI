from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore


embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)

vectorstore = QdrantVectorStore.from_existing_collection(
    embedding=embeddings,
    collection_name="kubernetes_runbooks",
    url="http://localhost:6333"
)

retriever = vectorstore.as_retriever(
    search_kwargs={
        "k": 3
    }
)