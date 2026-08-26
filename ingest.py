"""
ingest.py
---------
Run this script once (or whenever documents are updated) to build the FAISS vector index.

Usage:
    python ingest.py
"""

import os
import sys
import yaml
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))

from modules.loader import load_documents
from modules.splitter import split_documents
from modules.embedder import build_vectorstore

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.yaml")
ENV_PATH = os.path.join(BASE_DIR, "config", ".env")
DOCUMENTS_PATH = os.path.join(BASE_DIR, "data", "documents")


def main():
    load_dotenv(ENV_PATH)

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    print("=" * 60)
    print("Enterprise Knowledge Assistant - Document Ingestion")
    print("=" * 60)

    print("\n[1/3] Loading documents...")
    docs = load_documents(DOCUMENTS_PATH)
    if not docs:
        print("No documents found in data/documents/. Add .txt or .pdf files and retry.")
        sys.exit(1)

    print("\n[2/3] Splitting into chunks...")
    cfg = config["chunking"]
    chunks = split_documents(docs, chunk_size=cfg["chunk_size"], chunk_overlap=cfg["chunk_overlap"])

    print("\n[3/3] Building FAISS vector store...")
    build_vectorstore(chunks, config)

    print("\nIngestion complete! Run the app with: streamlit run app.py")


if __name__ == "__main__":
    main()
