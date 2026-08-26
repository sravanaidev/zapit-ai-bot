"""
app.py
------
Streamlit UI for the Enterprise Knowledge Assistant.

Run with:
    streamlit run app.py
"""

import os
import sys
import yaml
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))

from modules.loader import load_documents
from modules.splitter import split_documents
from modules.embedder import build_vectorstore, load_vectorstore, vectorstore_exists
from modules.retriever import HybridRetriever
from modules.reranker import CrossEncoderReranker
from modules.memory import format_chat_history
from modules.rag_chain import answer_question, format_context_and_sources

WELCOME_HTML = """
<div style="background: linear-gradient(135deg, #0f2744 0%, #1a4a80 100%);
            padding: 28px 32px; border-radius: 14px; margin-bottom: 24px;">
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 12px;">
        <span style="font-size: 2.4rem;">⚡</span>
        <h1 style="color: #ffffff; margin: 0; font-size: 1.9rem; font-weight: 700;">Welcome to Zapit AI Assistant</h1>
    </div>
    <p style="color: #a8c8f0; font-size: 1.05rem; margin: 0; line-height: 1.6;">
        I am here to help with your queries regarding the <strong style="color:#e8f4ff;">Zapit application</strong>.<br>
        Ask me anything about installation, configuration, commands, troubleshooting, error codes, and more.
    </p>
    <div style="margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px;">
        <span style="background:#1e5799; color:#cce4ff; padding:4px 12px; border-radius:20px; font-size:0.82rem;">🔧 Installation</span>
        <span style="background:#1e5799; color:#cce4ff; padding:4px 12px; border-radius:20px; font-size:0.82rem;">📋 Commands</span>
        <span style="background:#1e5799; color:#cce4ff; padding:4px 12px; border-radius:20px; font-size:0.82rem;">🔒 Security & Encryption</span>
        <span style="background:#1e5799; color:#cce4ff; padding:4px 12px; border-radius:20px; font-size:0.82rem;">🚀 Transfer Modes</span>
        <span style="background:#1e5799; color:#cce4ff; padding:4px 12px; border-radius:20px; font-size:0.82rem;">🛠️ Troubleshooting</span>
        <span style="background:#1e5799; color:#cce4ff; padding:4px 12px; border-radius:20px; font-size:0.82rem;">❗ Error Codes</span>
    </div>
</div>
"""

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.yaml")
ENV_PATH = os.path.join(BASE_DIR, "config", ".env")
DOCUMENTS_PATH = os.path.join(BASE_DIR, "data", "documents")

load_dotenv(ENV_PATH)


@st.cache_resource(show_spinner=False)
def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@st.cache_resource(show_spinner=False)
def _initialize_pipeline():
    """Load documents, build vector store, and initialize retrievers. Cached across sessions."""
    config = _load_config()

    docs = load_documents(DOCUMENTS_PATH)
    if not docs:
        raise RuntimeError(
            "No documents found in data/documents/. "
            "Add .txt or .pdf files, then restart the app."
        )

    cfg = config["chunking"]
    chunks = split_documents(docs, chunk_size=cfg["chunk_size"], chunk_overlap=cfg["chunk_overlap"])

    # Load or build FAISS index
    if vectorstore_exists(config):
        vectorstore = load_vectorstore(config)
    else:
        vectorstore = build_vectorstore(chunks, config)

    retriever = HybridRetriever(vectorstore, chunks, config)

    reranker = None
    if config.get("reranking", {}).get("enabled", True):
        reranker = CrossEncoderReranker(config)

    return retriever, reranker, config


def _render_sidebar(config: dict) -> None:
    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.chat_history = []
            st.rerun()

        st.divider()
        st.header("📂 Zapit Docs Loaded")
        if os.path.exists(DOCUMENTS_PATH):
            files = [
                f for f in sorted(os.listdir(DOCUMENTS_PATH))
                if not f.startswith(".") and os.path.splitext(f)[1] in {".txt", ".pdf", ".md"}
            ]
            if files:
                for fname in files:
                    st.markdown(f"📄 {fname}")
            else:
                st.info("No documents found.")

        st.divider()
        reranking_on = config.get("reranking", {}).get("enabled", True)
        st.caption(f"🔍 Hybrid Search: ON")
        st.caption(f"🎯 Reranking: {'ON' if reranking_on else 'OFF'}")
        st.caption(f"🧠 Memory Window: {config.get('memory', {}).get('window_size', 5)} turns")
        st.divider()
        st.caption("Powered by LangChain · FAISS · BM25 · Streamlit")
        st.caption("Zapit v4.4 Documentation")


def main() -> None:
    config = _load_config()
    ui_cfg = config.get("ui", {})

    st.set_page_config(
        page_title=ui_cfg.get("title", "Zapit AI Assistant"),
        page_icon="⚡",
        layout="wide",
    )

    st.title("⚡ Zapit AI Assistant")
    st.caption(ui_cfg.get("description", "Your intelligent guide to the Zapit file transfer application"))

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Load pipeline
    with st.spinner("Initializing knowledge base..."):
        try:
            retriever, reranker, rag_config = _initialize_pipeline()
        except Exception as exc:
            st.error(f"❌ Initialization failed: {exc}")
            st.stop()

    _render_sidebar(rag_config)

    # Show welcome banner only when chat is empty
    if not st.session_state.messages:
        st.markdown(WELCOME_HTML, unsafe_allow_html=True)

    # Replay prior messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("📚 Sources used"):
                    for src in msg["sources"]:
                        st.markdown(f"📄 `{src}`")

    # Chat input
    question = st.chat_input("Ask about Zapit installation, commands, errors, transfer modes...")
    if not question:
        return

    # Display the user's message
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Searching Zapit documentation..."):
            try:
                # Step 1 — Hybrid retrieval (vector + BM25)
                hybrid_results, is_relevant = retriever.retrieve(question)

                if not hybrid_results or not is_relevant:
                    answer = (
                        "I couldn't find relevant information in the Zapit documentation for your query. "
                        "Please refer to the official Zapit guide or contact your system administrator."
                    )
                    sources: list[str] = []
                else:
                    # Step 2 — Reranking
                    if reranker:
                        docs_only = [doc for doc, _ in hybrid_results]
                        ranked = reranker.rerank(question, docs_only)
                    else:
                        ranked = hybrid_results

                    # Step 3 — Conversation memory
                    window = rag_config.get("memory", {}).get("window_size", 5)
                    chat_history_msgs = format_chat_history(
                        st.session_state.chat_history, window_size=window
                    )

                    # Step 4 — LLM answer with grounded context
                    answer = answer_question(
                        question=question,
                        ranked_docs=ranked,
                        chat_history=chat_history_msgs,
                        config=rag_config,
                    )
                    _, sources = format_context_and_sources(ranked)

                st.markdown(answer)
                if sources:
                    with st.expander("📚 Sources used"):
                        for src in sources:
                            st.markdown(f"📄 `{src}`")

                # Persist turn
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )
                st.session_state.chat_history.append({"human": question, "ai": answer})

            except Exception as exc:
                error_msg = f"⚠️ Something went wrong: {exc}"
                st.error(error_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_msg, "sources": []}
                )


if __name__ == "__main__":
    main()
