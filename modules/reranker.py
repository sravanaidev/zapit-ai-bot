from sentence_transformers import CrossEncoder
from langchain_core.documents import Document


class CrossEncoderReranker:
    """
    Re-ranks candidate documents using a cross-encoder model.
    Scores each (query, document) pair for relevance and returns top-k.
    """

    def __init__(self, config: dict):
        rerank_cfg = config.get("reranking", {})
        model_name = rerank_cfg.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.model = CrossEncoder(model_name)
        self.max_chars = int(rerank_cfg.get("max_chunk_chars", 1200))
        self.final_k = int(rerank_cfg.get("final_k", 4))

    def rerank(
        self,
        query: str,
        docs: list[Document],
        top_k: int | None = None,
    ) -> list[tuple[Document, float]]:
        if not docs:
            return []
        if top_k is None:
            top_k = self.final_k

        pairs = [(query, doc.page_content[: self.max_chars]) for doc in docs]
        scores = self.model.predict(pairs, convert_to_numpy=True, show_progress_bar=False)
        ranked = sorted(zip(docs, scores.tolist()), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
