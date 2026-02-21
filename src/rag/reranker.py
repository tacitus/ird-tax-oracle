"""Cross-encoder reranker using sentence-transformers.

Re-scores retrieval results using a cross-encoder model that jointly
encodes (query, passage) pairs, producing more accurate relevance
scores than bi-encoder similarity alone.
"""

import logging

from sentence_transformers import CrossEncoder

from src.db.models import RetrievalResult

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"


class CrossEncoderReranker:
    """Reranks retrieval results using a cross-encoder model."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        logger.info("Loading cross-encoder model: %s", model_name)
        self._model = CrossEncoder(model_name)
        logger.info("Cross-encoder model loaded")

    def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Re-score and reorder results using the cross-encoder.

        Args:
            query: The user's search query.
            results: Candidate results from the retriever.
            top_k: Number of results to return after reranking.

        Returns:
            Top-k results reordered by cross-encoder score.
        """
        if not results:
            return []

        pairs = [(query, r.content) for r in results]
        scores = self._model.predict(pairs)

        scored = sorted(
            zip(scores, results, strict=True),
            key=lambda x: x[0],
            reverse=True,
        )

        return [
            result.model_copy(update={"score": float(score)})
            for score, result in scored[:top_k]
        ]
