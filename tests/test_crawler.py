"""Tests for the HTTP crawler."""

import hashlib

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.ingestion.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    """Crawler with rate limiting disabled for fast tests."""
    return Crawler(rate_limit=0.0)


@pytest.mark.asyncio
async def test_crawl_html_page(httpx_mock: HTTPXMock, crawler: Crawler) -> None:
    """HTML response produces CrawlResult with html, content_hash, content_type='html'."""
    html = "<html><body>Tax info</body></html>"
    httpx_mock.add_response(url="https://ird.govt.nz/page", text=html)

    result = await crawler.crawl("https://ird.govt.nz/page")

    assert result.content_type == "html"
    assert result.html == html
    assert result.raw_bytes is None
    assert result.status_code == 200
    assert result.content_hash == hashlib.sha256(html.encode()).hexdigest()


@pytest.mark.asyncio
async def test_crawl_pdf_by_content_type(httpx_mock: HTTPXMock, crawler: Crawler) -> None:
    """PDF content-type populates raw_bytes and sets content_type='pdf'."""
    pdf_bytes = b"%PDF-1.4 fake pdf content"
    httpx_mock.add_response(
        url="https://ird.govt.nz/doc",
        content=pdf_bytes,
        headers={"content-type": "application/pdf"},
    )

    result = await crawler.crawl("https://ird.govt.nz/doc")

    assert result.content_type == "pdf"
    assert result.raw_bytes == pdf_bytes
    assert result.html == ""
    assert result.content_hash == hashlib.sha256(pdf_bytes).hexdigest()


@pytest.mark.asyncio
async def test_crawl_pdf_by_url_extension(httpx_mock: HTTPXMock, crawler: Crawler) -> None:
    """.pdf URL extension is detected as PDF even with generic content-type."""
    pdf_bytes = b"%PDF-1.4 another fake"
    httpx_mock.add_response(
        url="https://ird.govt.nz/guide.pdf",
        content=pdf_bytes,
        headers={"content-type": "application/octet-stream"},
    )

    result = await crawler.crawl("https://ird.govt.nz/guide.pdf")

    assert result.content_type == "pdf"
    assert result.raw_bytes == pdf_bytes


@pytest.mark.asyncio
async def test_crawl_http_error_raises(httpx_mock: HTTPXMock, crawler: Crawler) -> None:
    """404 response raises httpx.HTTPStatusError."""
    httpx_mock.add_response(url="https://ird.govt.nz/missing", status_code=404)

    with pytest.raises(httpx.HTTPStatusError):
        await crawler.crawl("https://ird.govt.nz/missing")


@pytest.mark.asyncio
async def test_content_hash_deterministic(httpx_mock: HTTPXMock, crawler: Crawler) -> None:
    """Same content produces the same SHA256 hash across crawls."""
    html = "<html><body>Stable content</body></html>"
    httpx_mock.add_response(url="https://ird.govt.nz/stable", text=html)

    r1 = await crawler.crawl("https://ird.govt.nz/stable")

    httpx_mock.add_response(url="https://ird.govt.nz/stable", text=html)
    r2 = await crawler.crawl("https://ird.govt.nz/stable")

    assert r1.content_hash == r2.content_hash
