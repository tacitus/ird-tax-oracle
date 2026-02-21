"""Gemini embedding service using the google-genai SDK.

Uses async API for non-blocking embedding generation. Supports asymmetric
retrieval with different task types for documents vs queries.
"""

import logging

from google import genai
from google.genai import types

from config import load_yaml_config

logger = logging.getLogger(__name__)

# Module-level LRU cache for query embeddings (sync wrapper stores results)
_EMBED_CACHE_SIZE = 256


class GeminiEmbedder:
    """Embed text using Gemini's embedding model via the google-genai SDK."""

    def __init__(
        self,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        config = load_yaml_config("embeddings.yaml")["embeddings"]
        self.model = model or config["model"]
        self.dimensions = dimensions or config["dimensions"]
        self._task_type_document = config.get("task_type_document", "RETRIEVAL_DOCUMENT")
        self._task_type_query = config.get("task_type_query", "RETRIEVAL_QUERY")
        self.client = genai.Client()  # reads GEMINI_API_KEY from env
        self._query_cache: dict[str, list[float]] = {}
        self._cache_max = _EMBED_CACHE_SIZE

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks for storage.

        Args:
            texts: List of text chunks to embed.

        Returns:
            List of embedding vectors (one per text).
        """
        if not texts:
            return []

        logger.info("Embedding %d document chunks...", len(texts))
        result = await self.client.aio.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=self._task_type_document,
                output_dimensionality=self.dimensions,
            ),
        )
        return [e.values for e in result.embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query — uses RETRIEVAL_QUERY task type for asymmetric retrieval.

        Results are cached in-memory to avoid re-embedding identical queries.

        Args:
            text: Query text to embed.

        Returns:
            Embedding vector.
        """
        if text in self._query_cache:
            logger.debug("Embedding cache hit for query: %s", text[:40])
            return self._query_cache[text]

        result = await self.client.aio.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=self._task_type_query,
                output_dimensionality=self.dimensions,
            ),
        )
        embedding = result.embeddings[0].values

        # Evict oldest entries if cache is full
        if len(self._query_cache) >= self._cache_max:
            oldest_key = next(iter(self._query_cache))
            del self._query_cache[oldest_key]
        self._query_cache[text] = embedding

        return embedding
