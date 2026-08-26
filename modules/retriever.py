import re
import numpy as np
from rank_bm25 import BM25Okapi
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


class HybridRetriever:
    """
    Combines FAISS semantic search and BM25 keyword search.
    Results from both are normalized and merged with configurable weights.
    """

    def __init__(self, vectorstore: FAISS, chunks: list[Document], config: dict):
        self.vectorstore = vectorstore
        self.chunks = chunks

        bm25_cfg = config.get("bm25", {})
        corpus = [_tokenize(doc.page_content) for doc in chunks]
        self.bm25 = BM25Okapi(corpus, k1=bm25_cfg.get("k1", 1.5), b=bm25_cfg.get("b", 0.75))

        retrieval = config.get("retrieval", {})
        self.top_k_semantic = retrieval.get("top_k_semantic", 10)
        self.top_k_bm25 = retrieval.get("top_k_bm25", 10)
        self.top_k_hybrid = retrieval.get("top_k_hybrid", 10)

        hybrid_cfg = config.get("hybrid", {})
        self.semantic_weight = hybrid_cfg.get("semantic_weight", 0.6)
        self.bm25_weight = hybrid_cfg.get("bm25_weight", 0.4)

        # Absolute (non-normalized) thresholds used to detect out-of-scope queries.
        # Min-max normalization always stretches the best match to 1.0, even when
        # nothing is truly relevant, so we also check raw scores before trusting a result.
        self.max_semantic_distance = retrieval.get("max_semantic_distance", 1.0)
        self.min_bm25_score = retrieval.get("min_bm25_score", 0.5)

    def _normalize(self, scores: np.ndarray) -> np.ndarray:
        min_s, max_s = scores.min(), scores.max()
        if max_s == min_s:
            # All scores equal: return zeros if all zero, else equal relevance
            return np.zeros_like(scores) if max_s == 0 else np.ones_like(scores)
        return (scores - min_s) / (max_s - min_s)

    def retrieve(self, query: str) -> tuple[list[tuple[Document, float]], bool]:
        # --- Stage 1: Semantic (FAISS) retrieval ---
        # similarity_search_with_score returns (doc, L2_distance); lower = more relevant
        semantic_raw = self.vectorstore.similarity_search_with_score(query, k=self.top_k_semantic)
        semantic_docs = [doc for doc, _ in semantic_raw]
        raw_distances = np.array([s for _, s in semantic_raw]) if semantic_raw else np.array([])
        # Negate distances so higher value = more relevant before normalizing
        semantic_scores = self._normalize(-raw_distances) if len(raw_distances) else raw_distances

        # --- Stage 2: BM25 keyword retrieval ---
        bm25_scores_all = self.bm25.get_scores(_tokenize(query))
        top_bm25_idx = np.argsort(bm25_scores_all)[::-1][: self.top_k_bm25]
        bm25_docs = [self.chunks[i] for i in top_bm25_idx]
        raw_bm25_top = [bm25_scores_all[i] for i in top_bm25_idx]
        bm25_scores = self._normalize(np.array(raw_bm25_top))

        # --- Stage 3: Merge by document content (deduplication) ---
        score_map: dict[str, tuple[Document, float]] = {}

        for doc, score in zip(semantic_docs, semantic_scores):
            key = doc.page_content
            score_map[key] = (doc, self.semantic_weight * float(score))

        for doc, score in zip(bm25_docs, bm25_scores):
            key = doc.page_content
            if key in score_map:
                existing_doc, existing_score = score_map[key]
                score_map[key] = (existing_doc, existing_score + self.bm25_weight * float(score))
            else:
                score_map[key] = (doc, self.bm25_weight * float(score))

        ranked = sorted(score_map.values(), key=lambda x: x[1], reverse=True)

        # --- Relevance guard: is the best raw match actually close enough to trust? ---
        best_distance = float(raw_distances.min()) if len(raw_distances) else float("inf")
        best_bm25 = float(max(raw_bm25_top)) if raw_bm25_top else 0.0
        is_relevant = (best_distance <= self.max_semantic_distance) or (best_bm25 >= self.min_bm25_score)

        return ranked[: self.top_k_hybrid], is_relevant
