"""Shared test fixtures."""

from pathlib import Path

import pymupdf
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
