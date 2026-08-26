import os
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def load_documents(folder_path: str) -> list[Document]:
    """Load all supported documents from a folder, preserving source filename metadata."""
    docs = []
    if not os.path.exists(folder_path):
        print(f"Documents folder not found: {folder_path}")
        return docs

    for filename in sorted(os.listdir(folder_path)):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        filepath = os.path.join(folder_path, filename)
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(filepath)
            else:
                loader = TextLoader(filepath, encoding="utf-8")

            loaded = loader.load()
            for doc in loaded:
                doc.metadata["source_file"] = filename
            docs.extend(loaded)
            print(f"  Loaded: {filename} ({len(loaded)} section(s))")
        except Exception as e:
            print(f"  Warning: Could not load {filename}: {e}")

    print(f"Total documents loaded: {len(docs)}")
    return docs
