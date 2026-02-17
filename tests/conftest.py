"""Shared test fixtures."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest

from src.db.models import RetrievalResult
from src.llm.gateway import CompletionResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- Mock factories for orchestrator / retriever / LLM tests ---


def _make_retrieval_result(
    content: str = "Tax rate is 39%",
    source_url: str = "https://ird.govt.nz/rates",
    source_title: str = "Tax rates",
    section_title: str | None = "Individual rates",
    source_type: str = "ird_guidance",
    score: float = 0.5,
) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        section_title=section_title,
        source_url=source_url,
        source_title=source_title,
        source_type=source_type,
        score=score,
    )


@pytest.fixture
def mock_retriever() -> AsyncMock:
    """Async mock of HybridRetriever returning canned results."""
    retriever = AsyncMock()
    retriever.search.return_value = [
        _make_retrieval_result(),
        _make_retrieval_result(
            content="PAYE is deducted by your employer.",
            source_url="https://ird.govt.nz/paye",
            source_title="PAYE",
            section_title="How PAYE works",
        ),
    ]
    return retriever


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Async mock of LLMGateway returning a simple text completion."""
    llm = AsyncMock()
    llm.complete.return_value = CompletionResult(
        content="The top tax rate is 39%.",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )
    return llm


@pytest.fixture
def mock_embedder() -> AsyncMock:
    """Async mock of GeminiEmbedder returning a fixed 768-dim vector."""
    embedder = AsyncMock()
    embedder.embed_query.return_value = [0.1] * 768
    return embedder


@pytest.fixture
def mock_db_pool() -> MagicMock:
    """Mock of asyncpg.Pool with context-managed acquire().

    asyncpg.Pool.acquire() returns an async context manager (not a coroutine),
    so we use MagicMock for the pool and configure __aenter__/__aexit__ manually.
    """
    conn = AsyncMock()
    conn.fetch.return_value = []

    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire.return_value = acm
    return pool


@pytest.fixture
def ird_guidance_html() -> str:
    """Load the IRD guidance page HTML fixture."""
    return (FIXTURES_DIR / "ird_guidance_page.html").read_text()


@pytest.fixture
def taxtechnical_full_content_html() -> str:
    """Load the taxtechnical full content page HTML fixture."""
    return (FIXTURES_DIR / "taxtechnical_full_content.html").read_text()


@pytest.fixture
def taxtechnical_pdf_stub_html() -> str:
    """Load the taxtechnical PDF stub page HTML fixture."""
    return (FIXTURES_DIR / "taxtechnical_pdf_stub.html").read_text()


# --- PDF fixtures ---


def _make_pdf(
    pages: list[list[tuple[str, float, bool]]],
    footer: str | None = None,
) -> bytes:
    """Build a synthetic PDF from a list of pages.

    Each page is a list of (text, font_size, bold) tuples.
    Text is placed sequentially down the page.
    If footer is provided, it's placed at the bottom of every page.
    """
    doc = pymupdf.open()
    for page_items in pages:
        page = doc.new_page(width=595, height=842)  # A4
        y = 72  # start 1 inch from top
        for text, size, _bold in page_items:
            fontname = "helv"
            page.insert_text(
                (72, y),
                text,
                fontsize=size,
                fontname=fontname,
            )
            y += size * 1.5
        if footer:
            page.insert_text((72, 820), footer, fontsize=8, fontname="helv")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def pdf_with_metadata() -> bytes:
    """PDF with a title in metadata."""
    doc = pymupdf.open()
    doc.new_page()
    doc.set_metadata({"title": "IR3G Individual Income Tax Return Guide"})
    page = doc[0]
    page.insert_text((72, 100), "Some body text here.", fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def pdf_with_large_title() -> bytes:
    """PDF with no metadata title but large text on first page."""
    return _make_pdf([
        [
            ("Individual Income Tax Return Guide", 24.0, True),
            ("This guide helps you fill in your return.", 10.0, False),
        ],
    ])


@pytest.fixture
def pdf_with_table() -> bytes:
    """PDF containing a table with tax brackets."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text((72, 72), "Tax rates for individuals", fontsize=16)
    page.insert_text((72, 100), "The following rates apply:", fontsize=10)

    # Build a table using drawn cell borders + text
    y_start = 130
    col_widths = [150, 150, 100]
    row_height = 20
    headers = ["Income band", "Rate", "Tax"]
    rows = [
        ["$0 - $14,000", "10.5%", "$1,470"],
        ["$14,001 - $48,000", "17.5%", "$5,950"],
        ["$48,001 - $70,000", "30%", "$6,600"],
        ["$70,001 - $180,000", "33%", "$36,300"],
        ["$180,001+", "39%", "-"],
    ]

    x_start = 72
    all_rows = [headers] + rows
    for row_idx, row in enumerate(all_rows):
        y = y_start + row_idx * row_height
        x = x_start
        for col_idx, cell in enumerate(row):
            # Draw cell border
            rect = pymupdf.Rect(x, y, x + col_widths[col_idx], y + row_height)
            page.draw_rect(rect)
            page.insert_text((x + 4, y + 14), cell, fontsize=9)
            x += col_widths[col_idx]

    notes_y = y_start + len(all_rows) * row_height + 30
    page.insert_text((72, notes_y), "Notes about tax rates.", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def ir3g_style_pdf() -> bytes:
    """PDF with Q&A-structured content mimicking IR3G format."""
    pages: list[list[tuple[str, float, bool]]] = [
        [
            ("IR3G Individual Return Guide", 24.0, True),
            ("2025", 28.0, True),
            ("This guide helps you complete your IR3.", 10.0, False),
        ],
        [
            ("Using this guide", 18.0, True),
            ("Before you start, make sure you have all statements.", 10.0, False),
            ("Question 1 IRD number", 10.0, True),
            ("Enter your IRD number in the boxes provided.", 10.0, False),
            ("You can find this on any correspondence from us.", 10.0, False),
            ("Question 2 Your name", 10.0, True),
            ("Print your full name as shown on your records.", 10.0, False),
        ],
        [
            ("Question 3 Bank account number", 10.0, True),
            ("Enter your NZ bank account number for refunds.", 10.0, False),
            ("The fastest way to get any refund is direct credit.", 10.0, False),
            ("Question 4 Income from employment", 10.0, True),
            ("Include all salary and wages earned during the year.", 10.0, False),
            ("Copy the total from your SOI to Box 12B.", 10.0, False),
            ("Question 5 Interest income", 10.0, True),
            ("Include gross interest from all NZ sources.", 10.0, False),
        ],
    ]
    return _make_pdf(pages)


@pytest.fixture
def pdf_with_headings() -> bytes:
    """PDF with font-size-based headings (no Q&A pattern)."""
    pages: list[list[tuple[str, float, bool]]] = [
        [
            ("Tax Guide Overview", 22.0, True),
            ("This document covers tax obligations.", 10.0, False),
            ("Income Types", 16.0, True),
            ("Salary and wages are the most common income type.", 10.0, False),
            ("Employment income is taxed at source through PAYE.", 10.0, False),
            ("Deductions", 16.0, True),
            ("You may be able to claim deductions for work expenses.", 10.0, False),
        ],
    ]
    return _make_pdf(pages)


@pytest.fixture
def pdf_plain_text() -> bytes:
    """PDF with no headings and no Q&A structure."""
    return _make_pdf([
        [
            ("This is a simple document about tax.", 10.0, False),
            ("It has no headings or structure.", 10.0, False),
            ("All content is in plain body text.", 10.0, False),
        ],
    ])


@pytest.fixture
def multi_page_pdf() -> bytes:
    """PDF with content spanning multiple pages and repeated header/footer."""
    pages: list[list[tuple[str, float, bool]]] = []
    for i in range(5):
        page_items: list[tuple[str, float, bool]] = [
            ("IR3G INDIVIDUAL RETURN GUIDE", 8.0, False),  # header
        ]
        if i == 0:
            page_items.append(("Tax Guide", 22.0, True))
            page_items.append(("Introduction to the guide.", 10.0, False))
        else:
            page_items.append((f"Section {i}", 16.0, True))
            page_items.append((f"Content for section {i} goes here.", 10.0, False))
            page_items.append(("More detail about this section.", 10.0, False))
        pages.append(page_items)
    return _make_pdf(pages, footer="ird.govt.nz")


@pytest.fixture
def ird_pdf_fixture() -> bytes | None:
    """Load the real IR3G PDF fixture if available."""
    path = FIXTURES_DIR / "ir3g.pdf"
    if path.exists():
        return path.read_bytes()
    return None
