"""Ingestion pipeline: crawl → parse → chunk → embed → store.

Orchestrates the full flow from URL to stored chunks in PostgreSQL.
Supports upsert semantics with content hash change detection.
"""

import asyncio
import logging
from datetime import UTC, date, datetime

import asyncpg

from src.db.models import ChunkData, CrawlResult, ParsedDocument
from src.db.session import get_pool
from src.ingestion.chunker import chunk_document
from src.ingestion.crawler import Crawler
from src.ingestion.parsers.html_parser import parse_html
from src.ingestion.parsers.pdf_parser import parse_pdf
from src.ingestion.parsers.taxtechnical_parser import parse_taxtechnical
from src.rag.embedder import GeminiEmbedder

logger = logging.getLogger(__name__)

# Batch size for embedding API calls
_EMBED_BATCH_SIZE = 20


class IngestionPipeline:
    """Full ingestion pipeline from URL to stored chunks."""

    def __init__(self, embedder: GeminiEmbedder, crawler: Crawler | None = None) -> None:
        self.embedder = embedder
        self.crawler = crawler or Crawler()

    async def _get_existing_hash(
        self, pool: asyncpg.Pool, url: str
    ) -> str | None:
        """Get the content hash for an existing source URL."""
        row = await pool.fetchrow(
            "SELECT content_hash FROM document_sources WHERE url = $1",
            url,
        )
        return row["content_hash"] if row else None

    async def _embed_chunks(self, chunks: list[ChunkData]) -> list[list[float]]:
        """Embed all chunks in batches with rate-limit retry."""
        all_embeddings: list[list[float]] = []
        texts = [c.content for c in chunks]

        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i : i + _EMBED_BATCH_SIZE]
            # Retry with exponential backoff on rate limit errors
            for attempt in range(4):
                try:
                    embeddings = await self.embedder.embed_documents(batch)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 3:
                        wait = 5 * (attempt + 1)  # 5, 10, 15 seconds
                        logger.warning("Rate limited, retrying in %ds...", wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
            all_embeddings.extend(embeddings)
            logger.info(
                "Embedded batch %d-%d of %d",
                i,
                min(i + _EMBED_BATCH_SIZE, len(texts)),
                len(texts),
            )
            # Delay between batches to avoid Gemini API rate limits
            # Longer delay for large documents (>100 chunks)
            if i + _EMBED_BATCH_SIZE < len(texts):
                delay = 4.0 if len(texts) > 100 else 1.0
                await asyncio.sleep(delay)

        return all_embeddings

    async def _store_chunks(
        self,
        conn: asyncpg.Connection,
        source_id: str,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
    ) -> int:
        """Store chunks in database within an existing transaction.

        Deletes old chunks for this source, then inserts new ones.
        Returns number of chunks inserted.
        """
        # Delete existing chunks for this source
        await conn.execute(
            "DELETE FROM document_chunks WHERE source_id = $1::uuid",
            source_id,
        )

        # Insert new chunks
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            await conn.execute(
                """
                INSERT INTO document_chunks
                    (source_id, chunk_index, content, section_title, tax_year, embedding)
                VALUES ($1::uuid, $2, $3, $4, $5, $6)
                """,
                source_id,
                chunk.chunk_index,
                chunk.content,
                chunk.section_title,
                chunk.tax_year,
                embedding,
            )

        return len(chunks)

    async def _upsert_source(
        self,
        conn: asyncpg.Connection,
        url: str,
        source_type: str,
        title: str,
        content_hash: str,
        identifier: str | None = None,
        issue_date: date | None = None,
    ) -> str:
        """Insert or update a document source. Returns the source ID."""
        row = await conn.fetchrow(
            """
            INSERT INTO document_sources
                (url, source_type, title, content_hash, last_crawled_at, identifier, issue_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                content_hash = EXCLUDED.content_hash,
                last_crawled_at = EXCLUDED.last_crawled_at,
                identifier = COALESCE(EXCLUDED.identifier, document_sources.identifier),
                issue_date = COALESCE(EXCLUDED.issue_date, document_sources.issue_date),
                updated_at = NOW()
            RETURNING id
            """,
            url,
            source_type,
            title,
            content_hash,
            datetime.now(UTC),
            identifier,
            issue_date,
        )
        return str(row["id"])

    async def process_url(
        self,
        url: str,
        source_type: str = "ird_guidance",
        title: str | None = None,
        force: bool = False,
        dry_run: bool = False,
        identifier: str | None = None,
        issue_date: date | None = None,
    ) -> dict[str, int | str | bool]:
        """Process a single URL through the full pipeline.

        Args:
            url: URL to crawl and ingest.
            source_type: Type classification for the source.
            title: Optional override title (otherwise extracted from HTML).
            force: Re-process even if content hash is unchanged.
            dry_run: Crawl, parse, chunk but don't embed or store.
            identifier: Publication reference (e.g. "QB 25/01", "IS 24/10").
            issue_date: Publication date.

        Returns:
            Dict with processing stats.
        """
        pool = await get_pool()

        # Crawl
        crawl_result: CrawlResult = await self.crawler.crawl(url)

        # Check for changes
        if not force:
            existing_hash = await self._get_existing_hash(pool, url)
            if existing_hash == crawl_result.content_hash:
                logger.info("Skipping %s (content unchanged)", url)
                return {"url": url, "skipped": True, "reason": "content unchanged"}

        # Parse
        if crawl_result.content_type == "pdf":
            if crawl_result.raw_bytes is None:
                logger.error("PDF crawl result missing raw_bytes: %s", url)
                return {"url": url, "skipped": True, "reason": "missing PDF bytes"}
            parsed: ParsedDocument = parse_pdf(crawl_result.raw_bytes, url)
        elif "taxtechnical.ird.govt.nz" in url:
            parsed = parse_taxtechnical(crawl_result.html, url)
        else:
            parsed = parse_html(crawl_result.html, url)
        page_title = title or parsed.title

        # Follow PDF link if the parser detected one (e.g. taxtechnical stub pages)
        if parsed.pdf_url:
            logger.info("Following PDF link: %s", parsed.pdf_url)
            pdf_crawl = await self.crawler.crawl(parsed.pdf_url)
            if pdf_crawl.content_type == "pdf" and pdf_crawl.raw_bytes:
                pdf_parsed = parse_pdf(pdf_crawl.raw_bytes, url)
                parsed = ParsedDocument(
                    title=parsed.title,
                    url=url,
                    sections=parsed.sections + pdf_parsed.sections,
                )

        # Chunk
        chunks: list[ChunkData] = chunk_document(parsed)

        if not chunks:
            logger.warning("No chunks produced for %s", url)
            return {"url": url, "skipped": True, "reason": "no chunks produced"}

        if dry_run:
            logger.info(
                "DRY RUN: %s -> %d sections, %d chunks",
                url,
                len(parsed.sections),
                len(chunks),
            )
            return {
                "url": url,
                "dry_run": True,
                "sections": len(parsed.sections),
                "chunks": len(chunks),
                "title": page_title,
            }

        # Embed
        embeddings = await self._embed_chunks(chunks)

        # Store atomically
        async with pool.acquire() as conn, conn.transaction():
                source_id = await self._upsert_source(
                    conn, url, source_type, page_title, crawl_result.content_hash,
                    identifier=identifier, issue_date=issue_date,
                )
                stored = await self._store_chunks(conn, source_id, chunks, embeddings)

        logger.info(
            "Processed %s: %d sections, %d chunks stored",
            url,
            len(parsed.sections),
            stored,
        )

        return {
            "url": url,
            "title": page_title,
            "sections": len(parsed.sections),
            "chunks": stored,
            "content_hash": crawl_result.content_hash,
        }
