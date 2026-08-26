# ⚡ Zapit AI Assistant

A production-oriented RAG (Retrieval-Augmented Generation) chatbot that answers questions about the **Zapit** enterprise file transfer application — installation, configuration, commands, error codes, troubleshooting, security, and more.

Built with LangChain, FAISS, BM25, Cross-Encoder Reranking, Conversational Memory, and a Streamlit UI. Answers are strictly grounded in the Zapit documentation — if something isn't in the docs, the assistant says so instead of guessing.

---

## Architecture

```
Zapit Documentation (TXT / MD / PDF)
        ↓
  Document Loader  (modules/loader.py)
        ↓
  Text Chunking    (modules/splitter.py)
        ↓
  Embeddings + FAISS Index  (modules/embedder.py)

                    ┌── Vector Search (FAISS)
User Query ────────┤
                    └── Keyword Search (BM25)
                              ↓
                       Hybrid Results
                              ↓
                    Cross-Encoder Reranking  (modules/reranker.py)
                              ↓
                Relevance Guard (blocks out-of-scope questions)
                              ↓
               LLM + Conversation Memory  (modules/rag_chain.py)
                              ↓
             Grounded Answer + Source Citations
                              ↓
                       Streamlit UI  (app.py)
```

---

## Features

| Feature | Implementation |
|---|---|
| Document Ingestion | PDF + TXT/MD via LangChain loaders |
| Chunking | `RecursiveCharacterTextSplitter` |
| Embeddings | OpenAI `text-embedding-3-small` or Google Gemini |
| Vector Store | FAISS (local, no cloud needed) |
| Hybrid Search | FAISS semantic + BM25 keyword (weighted fusion) |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Relevance Guard | Raw-score threshold check — skips the LLM entirely for out-of-scope questions |
| Conversation Memory | Sliding window of last N turns via `MessagesPlaceholder` |
| Source Citations | Source filenames attached to every answer |
| Hallucination Mitigation | System prompt + relevance guard restrict answers to Zapit docs only |
| UI | Streamlit chat with welcome banner, history, sources panel, clear button |

---

## Project Structure

```
Zapit-AI-Assistant/
├── app.py                  # Streamlit application entry point
├── ingest.py                # One-time (or repeatable) document ingestion script
├── requirements.txt
├── config/
│   ├── config.yaml          # All configuration (LLM, embeddings, retrieval tuning)
│   └── .env                 # API keys (create this — see Setup below)
├── data/
│   └── documents/           # Zapit documentation lives here (.txt, .md, .pdf)
├── modules/
│   ├── loader.py            # Document loading (PDF, TXT, MD)
│   ├── splitter.py           # Text chunking
│   ├── embedder.py           # Embeddings + FAISS build/load
│   ├── retriever.py          # Hybrid retriever (FAISS + BM25) + relevance guard
│   ├── reranker.py           # Cross-encoder reranker
│   ├── memory.py             # Chat history formatting
│   └── rag_chain.py          # Prompt + LLM chain
├── .streamlit/
│   └── config.toml          # Streamlit server settings
└── vectorstores/             # Auto-created; stores the FAISS index files
```

---

## Prerequisites

Before you start, make sure the new system has:

- **Python 3.10 or later** installed (check with `python --version`)
- **pip** available (comes with Python)
- An **OpenAI API key** (or a **Google Gemini API key** if you prefer Gemini)
- Internet access (for downloading packages and calling the LLM/embedding API)

---

## Setup Instructions (Fresh System)

Follow these steps in order after copying/cloning the `Zapit-AI-Assistant` folder onto the new machine.

### Step 1 — Open a terminal in the project folder

```powershell
cd path\to\Zapit-AI-Assistant
```

### Step 2 — Create a virtual environment

```powershell
python -m venv .venv
```

### Step 3 — Activate the virtual environment

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

You should now see `(.venv)` at the start of your terminal prompt.

### Step 4 — Install dependencies

```powershell
pip install -r requirements.txt
```

This installs LangChain, FAISS, Streamlit, sentence-transformers (for reranking), and all other required packages. This step can take a few minutes the first time.

### Step 5 — Add your API key

Create a file named `.env` inside the `config/` folder (if it doesn't already exist):

```powershell
notepad config\.env
```

Add the following line (replace with your real key):

```env
OPENAI_API_KEY=sk-your-real-key-here
```

> If you prefer Google Gemini instead of OpenAI, add `GOOGLE_API_KEY=...` instead, and update `config/config.yaml` (see Step 6).

**Never commit or share this `.env` file** — it contains a secret key.

### Step 6 — (Optional) Choose your LLM/embedding provider

Open `config/config.yaml` and confirm the provider matches the key you added:

```yaml
llm:
  provider: "openai"      # or "gemini"

embedding:
  provider: "openai"      # or "gemini"
```

The defaults are already set to `openai` and will work as-is if you added an `OPENAI_API_KEY`.

### Step 7 — Add or update Zapit documentation (optional)

The `data/documents/` folder already ships with:
- `zapit_complete_guide.md`
- `zapit_commands_reference.txt`
- `zapit_install_removal_guide.txt`

To add more documentation (e.g. a new release guide), simply drop additional `.txt`, `.md`, or `.pdf` files into `data/documents/`.

### Step 8 — Build the knowledge base (ingest documents)

Run this once to process the documents and build the FAISS vector index:

```powershell
python ingest.py
```

Expected output ends with:
```
Ingestion complete! Run the app with: streamlit run app.py
```

> ⚠️ Re-run this command any time you add, remove, or edit files in `data/documents/`. The app will not pick up document changes automatically.

### Step 9 — Launch the application

```powershell
streamlit run app.py
```

Streamlit will print a local URL, typically:

```
Local URL: http://localhost:8501
```

Open that URL in your browser. You should see the **"Welcome to Zapit AI Assistant"** banner and a chat box.

### Step 10 — Ask a question

Try one of these to confirm everything works end-to-end:

- "How do I install Zapit on a fresh server?"
- "What does error ZAPIT-2007 mean?"
- "How do I resume a failed transfer?"
- "What congestion control modes does Zapit support?"

Each answer should include an expandable **📚 Sources used** section listing the Zapit document(s) it was grounded in.

---

## Running It Again Later

Every time you come back to use the app on the same machine:

```powershell
cd path\to\Zapit-AI-Assistant
.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
streamlit run app.py
```

You do **not** need to re-run `ingest.py` unless the documents changed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `streamlit : command not recognized` | The venv isn't activated, or you're not using the full path. Run `.venv\Scripts\Activate.ps1` first, or call `.venv\Scripts\streamlit.exe run app.py` directly. |
| `ModuleNotFoundError: No module named 'langchain...'` | Dependencies aren't installed in the active environment. Re-run `pip install -r requirements.txt` with the venv activated. |
| `ModuleNotFoundError: No module named 'langchain.prompts'` | You have a newer LangChain version — this project already imports from `langchain_core.prompts`, so pull the latest code. |
| App says it can't find any documents | Make sure files exist in `data/documents/` and re-run `python ingest.py`. |
| Answers seem to cite unrelated documents | Delete the `vectorstores/` folder and re-run `python ingest.py` to rebuild a clean index. |
| `OPENAI_API_KEY not found` error | Confirm `config/.env` exists and contains a valid `OPENAI_API_KEY=...` line with no quotes. |
| Port 8501 already in use | Run `streamlit run app.py --server.port 8502` to use a different port. |
| Lots of `torchvision` warnings in the console | Harmless — caused by Streamlit's file watcher scanning the `transformers` package. Already suppressed via `.streamlit/config.toml` (`fileWatcherType = "none"`). |

---

## Configuration Reference (`config/config.yaml`)

| Key | Description |
|---|---|
| `llm.provider` | `openai` or `gemini` |
| `embedding.provider` | `openai` or `gemini` |
| `chunking.chunk_size` | Characters per chunk (default 600) |
| `chunking.chunk_overlap` | Overlap between chunks (default 100) |
| `retrieval.top_k_semantic` | Documents fetched by FAISS |
| `retrieval.top_k_bm25` | Documents fetched by BM25 |
| `retrieval.max_semantic_distance` | Max FAISS L2 distance considered "relevant" |
| `retrieval.min_bm25_score` | Min BM25 score considered "relevant" |
| `hybrid.semantic_weight` | Weight for semantic results (0–1) |
| `hybrid.bm25_weight` | Weight for BM25 results (0–1) |
| `reranking.enabled` | Enable/disable cross-encoder reranking |
| `reranking.final_k` | Final documents passed to the LLM |
| `memory.window_size` | Number of past conversation turns to include |

---

## Security Notes

- `config/.env` contains your API key — do not commit it to version control or share it publicly.
- The relevance guard and system prompt restrict answers to the ingested Zapit documentation, reducing hallucination risk, but responses should still be verified for anything safety-critical (e.g. production commands).
