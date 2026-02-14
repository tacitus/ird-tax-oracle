"""PDF parser for IRD guide documents.

Extracts structured sections from IRD PDFs (e.g., IR3G, IR330).
Handles Q&A-structured guides, table extraction as markdown, and
font-size-based heading detection with header/footer stripping.
"""

import logging
import re
import statistics
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pymupdf

from src.db.models import ParsedDocument, ParsedSection

logger = logging.getLogger(__name__)

# Minimum thresholds for table detection
_MIN_TABLE_ROWS = 2
_MIN_TABLE_COLS = 2

# Heading font size must be this much larger than median body text
_HEADING_SIZE_RATIO = 1.2

# Minimum Q&A matches to use Q&A sectioning
_MIN_QA_MATCHES = 3

# Patterns for Q&A-style sections in IRD guides
_QA_PATTERNS = [
    re.compile(r"^Question\s+(\d+)\b[.\s]*(.*)$", re.MULTILINE),
    re.compile(r"^Q(\d+)[.:]\s*(.*)$", re.MULTILINE),
]

# Minimum times a text must repeat at same y-position to be considered header/footer
_HEADER_FOOTER_MIN_PAGES = 3


@dataclass
class _TextBlock:
    """A text span extracted from a PDF page."""

    text: str
    font_size: float
    is_bold: bool
    y_pos: float
    page_num: int


@dataclass
class _TableBlock:
    """A table extracted from a PDF page, rendered as markdown."""

    markdown: str
    y_pos: float
    page_num: int


def _extract_title(doc: Any, url: str) -> str:
    """Extract document title from metadata, first large text, or URL fallback."""
    # Try PDF metadata
    title: str = doc.metadata.get("title", "").strip()
    if title:
        return title

    # Try first page — look for largest text
    if len(doc) > 0:
        blocks = doc[0].get_text("dict")["blocks"]
        largest_size = 0.0
        largest_text = ""
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text and span["size"] > largest_size:
                        largest_size = span["size"]
                        largest_text = text

        if largest_text:
            return largest_text

    # URL fallback: extract filename without extension
    path = urlparse(url).path
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    if filename.lower().endswith(".pdf"):
        filename = filename[:-4]
    return filename or "Untitled"


def _extract_tables(page: Any) -> list[_TableBlock]:
    """Extract tables from a page as markdown, returning bounding boxes for exclusion."""
    tables: list[_TableBlock] = []
    found = page.find_tables()
    for table in found.tables:
        if table.row_count < _MIN_TABLE_ROWS or table.col_count < _MIN_TABLE_COLS:
            continue
        md = table.to_markdown()
        if md.strip():
            y_pos = table.bbox[1]  # top y coordinate
            tables.append(_TableBlock(markdown=md, y_pos=y_pos, page_num=page.number))
    return tables


def _rects_overlap(bbox1: tuple[float, ...], bbox2: tuple[float, ...]) -> bool:
    """Check if two bounding boxes overlap."""
    x0_1, y0_1, x1_1, y1_1 = bbox1[:4]
    x0_2, y0_2, x1_2, y1_2 = bbox2[:4]
    return not (x1_1 <= x0_2 or x1_2 <= x0_1 or y1_1 <= y0_2 or y1_2 <= y0_1)


def _extract_text_blocks(
    page: Any,
    table_bboxes: list[tuple[float, ...]],
) -> list[_TextBlock]:
    """Extract text blocks from a page, skipping regions covered by tables."""
    blocks: list[_TextBlock] = []
    page_dict = page.get_text("dict")

    for block in page_dict["blocks"]:
        if "lines" not in block:
            continue
        block_bbox = (block["bbox"][0], block["bbox"][1], block["bbox"][2], block["bbox"][3])

        # Skip text that overlaps with table regions
        if any(_rects_overlap(block_bbox, tb) for tb in table_bboxes):
            continue

        for line in block["lines"]:
            line_texts: list[str] = []
            max_size = 0.0
            any_bold = False
            for span in line["spans"]:
                text = span["text"].strip()
                if text:
                    line_texts.append(span["text"])
                    max_size = max(max_size, span["size"])
                    # flags bit 4 (16) = bold
                    if span["flags"] & 16:
                        any_bold = True

            line_text = "".join(line_texts).strip()
            if line_text:
                blocks.append(
                    _TextBlock(
                        text=line_text,
                        font_size=max_size,
                        is_bold=any_bold,
                        y_pos=line["bbox"][1],
                        page_num=page.number,
                    )
                )

    return blocks


def _merge_page_content(
    text_blocks: list[_TextBlock],
    table_blocks: list[_TableBlock],
) -> list[_TextBlock | _TableBlock]:
    """Interleave text and table blocks by y-position."""
    items: list[tuple[float, int, _TextBlock | _TableBlock]] = []
    for tb in text_blocks:
        items.append((tb.y_pos, 0, tb))
    for tab in table_blocks:
        items.append((tab.y_pos, 1, tab))
    items.sort(key=lambda x: x[0])
    return [item[2] for item in items]


def _strip_headers_footers(
    all_blocks: list[_TextBlock],
    page_count: int,
    page_height: float = 842.0,
) -> set[str]:
    """Detect repeated text in page margins across pages (headers/footers).

    Only considers text in the top or bottom 15% of the page to avoid
    stripping repeated body content.
    """
    if page_count < _HEADER_FOOTER_MIN_PAGES:
        return set()

    margin = page_height * 0.15

    # Track (normalized_text, rounded_y) -> set of page numbers
    position_pages: dict[tuple[str, int], set[int]] = {}
    for block in all_blocks:
        # Only consider text in header/footer margins
        if block.y_pos > margin and block.y_pos < (page_height - margin):
            continue
        key = (block.text.strip().lower(), round(block.y_pos))
        position_pages.setdefault(key, set()).add(block.page_num)

    noise_texts: set[str] = set()
    for (text, _y), pages in position_pages.items():
        if len(pages) >= _HEADER_FOOTER_MIN_PAGES:
            noise_texts.add(text)

    return noise_texts


def _compute_median_font_size(text_blocks: list[_TextBlock]) -> float:
    """Compute the median font size across all text blocks."""
    if not text_blocks:
        return 12.0
    sizes = [b.font_size for b in text_blocks]
    return statistics.median(sizes)


def _detect_qa_sections(
    content_blocks: list[_TextBlock | _TableBlock],
) -> list[ParsedSection] | None:
    """Try to split content into Q&A sections based on "Question N:" patterns.

    Returns None if fewer than _MIN_QA_MATCHES are found, signaling
    the caller should fall back to heading-based detection.
    """
    # Build full text to find Q&A boundaries
    text_items: list[tuple[int, str]] = []  # (block_index, text)
    for i, block in enumerate(content_blocks):
        if isinstance(block, _TextBlock):
            text_items.append((i, block.text))

    # Find all Q&A pattern matches with their block indices
    qa_starts: list[tuple[int, str]] = []  # (block_index, heading_text)
    for idx, text in text_items:
        for pattern in _QA_PATTERNS:
            m = pattern.match(text)
            if m:
                num = m.group(1)
                rest = m.group(2).strip()
                heading = f"Question {num}"
                if rest:
                    heading = f"Question {num} {rest}"
                qa_starts.append((idx, heading))
                break

    if len(qa_starts) < _MIN_QA_MATCHES:
        return None

    sections: list[ParsedSection] = []

    # Content before first Q&A as introduction
    if qa_starts[0][0] > 0:
        intro_parts = _collect_text(content_blocks[: qa_starts[0][0]])
        if intro_parts.strip():
            sections.append(
                ParsedSection(heading="Introduction", content=intro_parts.strip())
            )

    # Each Q&A section
    for i, (start_idx, heading) in enumerate(qa_starts):
        end_idx = qa_starts[i + 1][0] if i + 1 < len(qa_starts) else len(content_blocks)
        # Skip the heading block itself (start from start_idx + 1),
        # but include the heading block if it has more text after the Q number
        section_blocks = content_blocks[start_idx + 1 : end_idx]
        content = _collect_text(section_blocks).strip()
        if content:
            sections.append(ParsedSection(heading=heading, content=content))

    return sections


def _detect_heading_sections(
    content_blocks: list[_TextBlock | _TableBlock],
    median_size: float,
) -> list[ParsedSection]:
    """Split content into sections based on font-size-detected headings."""
    heading_threshold = median_size * _HEADING_SIZE_RATIO

    # Find heading blocks: text significantly larger than body text, or bold + larger
    heading_indices: list[tuple[int, str]] = []
    for i, block in enumerate(content_blocks):
        if isinstance(block, _TextBlock) and block.font_size >= heading_threshold:
            heading_indices.append((i, block.text.strip()))

    if not heading_indices:
        # No headings found — return all as single section
        content = _collect_text(content_blocks).strip()
        if content:
            return [ParsedSection(heading="Content", content=content)]
        return []

    sections: list[ParsedSection] = []

    # Content before first heading
    if heading_indices[0][0] > 0:
        intro = _collect_text(content_blocks[: heading_indices[0][0]]).strip()
        if intro:
            sections.append(ParsedSection(heading="Introduction", content=intro))

    # Each heading section
    for i, (start_idx, heading) in enumerate(heading_indices):
        end_idx = (
            heading_indices[i + 1][0] if i + 1 < len(heading_indices) else len(content_blocks)
        )
        content = _collect_text(content_blocks[start_idx + 1 : end_idx]).strip()
        if content:
            sections.append(ParsedSection(heading=heading, content=content))

    return sections


def _collect_text(blocks: list[_TextBlock | _TableBlock]) -> str:
    """Collect text from a sequence of blocks into a single string."""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, _TableBlock):
            parts.append(block.markdown)
        else:
            parts.append(block.text)
    # Strip null bytes — PyMuPDF can extract \x00 from some PDFs,
    # and PostgreSQL rejects them in text fields
    return "\n\n".join(parts).replace("\x00", "")


def _clean_page_numbers(text: str) -> str:
    """Remove standalone page numbers (lines that are just a number)."""
    lines = text.split("\n")
    cleaned = [line for line in lines if not re.match(r"^\s*\d{1,3}\s*$", line)]
    return "\n".join(cleaned)


def parse_pdf(pdf_bytes: bytes, url: str) -> ParsedDocument:
    """Parse a PDF document into structured sections.

    Extracts text with font metadata, detects tables, strips headers/footers,
    then splits into sections using Q&A detection (for IRD guides like IR3G)
    or font-size-based heading detection as fallback.

    Args:
        pdf_bytes: Raw PDF file content.
        url: Source URL (for metadata).

    Returns:
        ParsedDocument with title and list of sections.
    """
    doc: Any = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]

    title = _extract_title(doc, url)

    # Extract all content from all pages
    all_text_blocks: list[_TextBlock] = []
    all_content: list[_TextBlock | _TableBlock] = []

    page_count: int = len(doc)
    for i in range(page_count):
        page = doc[i]
        # Extract tables first to get their bounding boxes
        table_blocks = _extract_tables(page)
        table_bboxes: list[tuple[float, ...]] = [
            t.bbox for t in page.find_tables().tables
        ]

        # Extract text blocks, skipping table regions
        text_blocks = _extract_text_blocks(page, table_bboxes)
        all_text_blocks.extend(text_blocks)

        # Merge text and tables by y-position
        page_content = _merge_page_content(text_blocks, table_blocks)
        all_content.extend(page_content)

    # Strip headers and footers
    page_height: float = doc[0].rect.height if page_count > 0 else 842.0
    noise_texts = _strip_headers_footers(all_text_blocks, page_count, page_height)
    if noise_texts:
        all_content = [
            block
            for block in all_content
            if not (
                isinstance(block, _TextBlock)
                and block.text.strip().lower() in noise_texts
            )
        ]

    doc.close()

    if not all_content:
        logger.warning("No content extracted from PDF: %s", url)
        return ParsedDocument(title=title, url=url, sections=[])

    # Compute median font size for heading detection
    remaining_text_blocks = [b for b in all_content if isinstance(b, _TextBlock)]
    median_size = _compute_median_font_size(remaining_text_blocks)

    # Try Q&A sectioning first, fall back to heading-based
    sections = _detect_qa_sections(all_content)
    if sections is None:
        sections = _detect_heading_sections(all_content, median_size)

    # Clean page numbers from section content
    for section in sections:
        section.content = _clean_page_numbers(section.content)

    logger.info("Parsed PDF '%s': %d sections", title, len(sections))
    return ParsedDocument(title=title, url=url, sections=sections)
