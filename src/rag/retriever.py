"""Hybrid retriever: semantic search + keyword search with RRF fusion."""

import logging

import asyncpg
import numpy as np

from src.db.models import RetrievalResult
from src.rag.embedder import GeminiEmbedder

logger = logging.getLogger(__name__)

# RRF constant — standard value from the original paper
_RRF_K = 60


class HybridRetriever:
    """Two-query hybrid search over document_chunks with RRF fusion."""

    def __init__(self, pool: asyncpg.Pool, embedder: GeminiEmbedder) -> None:
        self._pool = pool
        self._embedder = embedder

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_type: str | None = None,
        tax_year: str | None = None,
    ) -> list[RetrievalResult]:
        """Run hybrid search and return top-k results fused with RRF.

        Args:
            query: User's natural-language question.
            top_k: Number of results to return.
            source_type: Optional filter by document source type.
            tax_year: Optional filter by tax year.

        Returns:
            Ranked list of RetrievalResult.
        """
        fetch_k = top_k * 3  # over-fetch for better fusion

        query_embedding = await self._embedder.embed_query(query)

        async with self._pool.acquire() as conn:
            semantic_rows = await self._semantic_search(
                conn, query_embedding, fetch_k, source_type, tax_year
            )
            keyword_rows = await self._keyword_search(
                conn, query, fetch_k, source_type, tax_year
            )

        return rrf_fuse(semantic_rows, keyword_rows, top_k)

    async def _semantic_search(
        self,
        conn: asyncpg.Connection,
        embedding: list[float],
        limit: int,
        source_type: str | None = None,
        tax_year: str | None = None,
    ) -> list[RetrievalResult]:
        """Cosine-distance search via pgvector HNSW index."""
        # $1=embedding, $2=limit, $3+=optional filters
        conditions = ["s.is_active = TRUE", "s.superseded_by IS NULL"]
        filter_params: list[object] = []
        idx = 3

        if source_type:
            conditions.append(f"s.source_type = ${idx}")
            filter_params.append(source_type)
            idx += 1

        if tax_year:
            conditions.append(f"c.tax_year = ${idx}")
            filter_params.append(tax_year)
            idx += 1

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT c.content, c.section_title, c.tax_year,
                   s.url AS source_url, s.title AS source_title,
                   s.source_type,
                   c.embedding <=> $1 AS distance
            FROM document_chunks c
            JOIN document_sources s ON s.id = c.source_id
            WHERE {where_clause}
            ORDER BY c.embedding <=> $1
            LIMIT $2
        """

        rows = await conn.fetch(
            sql, np.array(embedding, dtype=np.float32), limit, *filter_params
        )
        return [
            RetrievalResult(
                content=r["content"],
                section_title=r["section_title"],
                source_url=r["source_url"],
                source_title=r["source_title"],
                source_type=r["source_type"],
                tax_year=r["tax_year"],
                score=1.0 - float(r["distance"]),
            )
            for r in rows
        ]

    async def _keyword_search(
        self,
        conn: asyncpg.Connection,
        query: str,
        limit: int,
        source_type: str | None = None,
        tax_year: str | None = None,
    ) -> list[RetrievalResult]:
        """Full-text search using tsvector index."""
        # $1=query, $2=limit, $3+=optional filters
        conditions = [
            "c.search_vector @@ plainto_tsquery('english', $1)",
            "s.is_active = TRUE",
            "s.superseded_by IS NULL",
        ]
        filter_params: list[object] = []
        idx = 3

        if source_type:
            conditions.append(f"s.source_type = ${idx}")
            filter_params.append(source_type)
            idx += 1

        if tax_year:
            conditions.append(f"c.tax_year = ${idx}")
            filter_params.append(tax_year)
            idx += 1

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT c.content, c.section_title, c.tax_year,
                   s.url AS source_url, s.title AS source_title,
                   s.source_type,
                   ts_rank_cd(c.search_vector, plainto_tsquery('english', $1)) AS rank
            FROM document_chunks c
            JOIN document_sources s ON s.id = c.source_id
            WHERE {where_clause}
            ORDER BY rank DESC
            LIMIT $2
        """

        rows = await conn.fetch(sql, query, limit, *filter_params)
        return [
            RetrievalResult(
                content=r["content"],
                section_title=r["section_title"],
                source_url=r["source_url"],
                source_title=r["source_title"],
                source_type=r["source_type"],
                tax_year=r["tax_year"],
                score=float(r["rank"]),
            )
            for r in rows
        ]


def rrf_fuse(
    semantic: list[RetrievalResult],
    keyword: list[RetrievalResult],
    top_k: int,
) -> list[RetrievalResult]:
    """Reciprocal Rank Fusion across two ranked lists.

    Each chunk's RRF score = sum(1 / (k + rank)) across lists it appears in.
    Chunks are keyed by (source_url, section_title, content[:100]).
    """
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievalResult] = {}

    for rank_list in [semantic, keyword]:
        for rank, result in enumerate(rank_list):
            key = _chunk_key(result)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
            if key not in chunks:
                chunks[key] = result

    sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]
    return [
        chunks[k].model_copy(update={"score": scores[k]})
        for k in sorted_keys
    ]


def _chunk_key(result: RetrievalResult) -> str:
    """Stable dedup key for a retrieval result."""
    return f"{result.source_url}|{result.section_title}|{result.content[:100]}"
