from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Same embedding model that rag.py uses
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)

# 1. Load your source document
loader = TextLoader("kubernetes_runbook.txt")
documents = loader.load()

# 2. Split into chunks
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

chunks = splitter.split_documents(documents)

print(f"Created {len(chunks)} chunks")

# 3. Create Qdrant collection and insert embeddings
vectorstore = QdrantVectorStore.from_documents(
    documents=chunks,
    embedding=embeddings,
    url="http://localhost:6333",
    collection_name="kubernetes_runbooks",
)

print("Qdrant ingestion completed")