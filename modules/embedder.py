import os
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

load_dotenv()

INDEX_NAME = "index"
# modules/ is one level below the project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_index_path(config: dict) -> str:
    """Resolve faiss_path relative to the project root, never the process CWD."""
    path = config["vectordb"]["faiss_path"]
    return path if os.path.isabs(path) else os.path.join(_PROJECT_ROOT, path)


def get_embedding_model(config: dict):
    provider = config["embedding"]["provider"].lower()
    if provider == "openai":
        return OpenAIEmbeddings(
            model=config["embedding"]["openai_model"],
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif provider in ("gemini", "google"):
        return GoogleGenerativeAIEmbeddings(
            model=config["embedding"]["gemini_model"],
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")


def build_vectorstore(chunks: list[Document], config: dict) -> FAISS:
    embeddings = get_embedding_model(config)
    index_path = _resolve_index_path(config)
    os.makedirs(index_path, exist_ok=True)
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(index_path, index_name=INDEX_NAME)
    print(f"FAISS index saved to: {index_path}")
    return vectorstore


def load_vectorstore(config: dict) -> FAISS:
    embeddings = get_embedding_model(config)
    index_path = _resolve_index_path(config)
    vectorstore = FAISS.load_local(
        index_path,
        embeddings,
        index_name=INDEX_NAME,
        allow_dangerous_deserialization=True,
    )
    print(f"FAISS index loaded from: {index_path}")
    return vectorstore


def vectorstore_exists(config: dict) -> bool:
    index_path = _resolve_index_path(config)
    return (
        os.path.isfile(os.path.join(index_path, f"{INDEX_NAME}.faiss"))
        and os.path.isfile(os.path.join(index_path, f"{INDEX_NAME}.pkl"))
    )
