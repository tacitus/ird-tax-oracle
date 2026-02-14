"""HTTP crawler for IRD pages with rate limiting and content hashing."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime

import httpx

from src.db.models import CrawlResult

logger = logging.getLogger(__name__)

# Rate limit: 1 request per second
_REQUEST_INTERVAL = 1.0

_DEFAULT_HEADERS = {
    "User-Agent": "NZTaxRAG/0.1 (educational tax research tool)",
    "Accept": "text/html,application/xhtml+xml,application/pdf",
    "Accept-Language": "en-NZ,en;q=0.9",
}


def _detect_content_type(response: httpx.Response, url: str) -> str:
    """Determine whether the response is HTML or PDF."""
    ct = response.headers.get("content-type", "")
    if "application/pdf" in ct:
        return "pdf"
    if url.lower().endswith(".pdf"):
        return "pdf"
    return "html"


class Crawler:
    """Async HTTP crawler with rate limiting."""

    def __init__(self, rate_limit: float = _REQUEST_INTERVAL) -> None:
        self._rate_limit = rate_limit
        self._last_request_time: float = 0.0

    async def _wait_for_rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def crawl(self, url: str) -> CrawlResult:
        """Crawl a single URL and return the result with content hash.

        Args:
            url: The URL to crawl.

        Returns:
            CrawlResult with content and SHA256 hash.

        Raises:
            httpx.HTTPStatusError: If the response status is 4xx/5xx.
        """
        await self._wait_for_rate_limit()

        logger.info("Crawling: %s", url)
        async with httpx.AsyncClient(
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = _detect_content_type(response, url)

        if content_type == "pdf":
            raw_bytes = response.content
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            html = ""
            size = len(raw_bytes)
        else:
            raw_bytes = None
            html = response.text
            content_hash = hashlib.sha256(html.encode()).hexdigest()
            size = len(html)

        logger.info(
            "Crawled %s: %s, %d bytes, hash=%s...",
            url,
            content_type,
            size,
            content_hash[:12],
        )

        return CrawlResult(
            url=url,
            html=html,
            content_hash=content_hash,
            status_code=response.status_code,
            crawled_at=datetime.now(UTC),
            raw_bytes=raw_bytes,
            content_type=content_type,
        )
