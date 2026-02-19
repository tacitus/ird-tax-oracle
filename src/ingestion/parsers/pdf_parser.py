"""PDF parser for IRD guide documents.

Extracts structured sections from IRD PDFs (e.g., IR3G, IR330).
Uses pymupdf4llm for markdown extraction, then splits into sections
via Q&A pattern detection or markdown heading detection.
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

import pymupdf
import pymupdf4llm  # type: ignore[import-untyped]

from src.db.models import ParsedDocument, ParsedSection

logger = logging.getLogger(__name__)

# Minimum Q&A matches to use Q&A sectioning
_MIN_QA_MATCHES = 3

# Patterns for Q&A-style sections in IRD guides
_QA_PATTERNS = [
    re.compile(r"^Question\s+(\d+)\b[.\s]*(.*)$", re.MULTILINE),
    re.compile(r"^Q(\d+)[.:]\s*(.*)$", re.MULTILINE),
]


def _strip_markdown_formatting(text: str) -> str:
    """Strip markdown bold/italic markers from text."""
    text = re.sub(r'\*{1,2}(.+?)\*{1,2}', r'\1', text)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text)
    return text.strip()


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


def _pdf_to_markdown(doc: Any) -> str:
    """Convert PDF document to markdown using pymupdf4llm.

    Uses margins to strip header/footer regions automatically.
    """
    md_text: str = pymupdf4llm.to_markdown(
        doc,
        write_images=False,
        show_progress=False,
        margins=(0, 50, 0, 30),  # (left, top, right, bottom) — strip headers, light bottom clip
    )
    return md_text


def _markdown_to_sections(md_text: str) -> list[ParsedSection]:
    """Split markdown text into sections based on heading markers.

    Tracks parent headings by level for hierarchical context.
    Falls back to a single "Content" section if no headings found.
    """
    # Split on markdown headings (# ## ###)
    heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    matches = list(heading_pattern.finditer(md_text))
    if not matches:
        content = md_text.strip()
        if content:
            return [ParsedSection(heading="Content", content=content)]
        return []

    sections: list[ParsedSection] = []

    # Content before first heading
    intro_text = md_text[: matches[0].start()].strip()
    if intro_text:
        sections.append(ParsedSection(heading="Introduction", content=intro_text))

    # Track parent headings by level for hierarchical context
    parent_headings: dict[int, str] = {}

    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading = _strip_markdown_formatting(match.group(2).strip())

        # Update parent tracking
        parent_headings[level] = heading
        # Clear any deeper levels
        for deeper in list(parent_headings.keys()):
            if deeper > level:
                del parent_headings[deeper]

        # Build full heading with parent context for sub-headings
        if level > 1 and 1 in parent_headings:
            heading = f"{parent_headings[1]} > {heading}"

        # Extract content between this heading and the next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        content = md_text[start:end].strip()

        if content:
            sections.append(ParsedSection(heading=heading, content=content))

    return sections


def _detect_qa_sections(md_text: str) -> list[ParsedSection] | None:
    """Try to split markdown text into Q&A sections.

    Returns None if fewer than _MIN_QA_MATCHES are found, signaling
    the caller should fall back to heading-based detection.
    """
    # Find all Q&A pattern matches
    qa_matches: list[tuple[int, int, str]] = []  # (start, end, heading)
    for pattern in _QA_PATTERNS:
        for m in pattern.finditer(md_text):
            num = m.group(1)
            rest = m.group(2).strip()
            heading = f"Question {num}"
            if rest:
                heading = f"Question {num} {rest}"
            qa_matches.append((m.start(), m.end(), heading))

    # Sort by position and deduplicate (patterns may overlap)
    qa_matches.sort(key=lambda x: x[0])
    if len(qa_matches) < _MIN_QA_MATCHES:
        return None

    sections: list[ParsedSection] = []

    # Content before first Q&A as introduction
    intro_text = md_text[: qa_matches[0][0]].strip()
    if intro_text:
        sections.append(ParsedSection(heading="Introduction", content=intro_text))

    # Each Q&A section
    for i, (_start, end, heading) in enumerate(qa_matches):
        next_start = qa_matches[i + 1][0] if i + 1 < len(qa_matches) else len(md_text)
        content = md_text[end:next_start].strip()
        if content:
            sections.append(ParsedSection(heading=heading, content=content))

    return sections


def _clean_page_numbers(text: str) -> str:
    """Remove standalone page numbers (lines that are just a number)."""
    lines = text.split("\n")
    cleaned = [line for line in lines if not re.match(r"^\s*\d{1,3}\s*$", line)]
    return "\n".join(cleaned)


def parse_pdf(pdf_bytes: bytes, url: str) -> ParsedDocument:
    """Parse a PDF document into structured sections.

    Uses pymupdf4llm for markdown extraction, then splits into sections
    using Q&A detection (for IRD guides like IR3G) or markdown heading
    detection as fallback.

    Args:
        pdf_bytes: Raw PDF file content.
        url: Source URL (for metadata).

    Returns:
        ParsedDocument with title and list of sections.
    """
    doc: Any = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]

    title = _extract_title(doc, url)

    # Convert to markdown via pymupdf4llm
    md_text = _pdf_to_markdown(doc)
    doc.close()

    # Strip null bytes — PyMuPDF can extract \x00 from some PDFs,
    # and PostgreSQL rejects them in text fields
    md_text = md_text.replace("\x00", "")

    if not md_text.strip():
        logger.warning("No content extracted from PDF: %s", url)
        return ParsedDocument(title=title, url=url, sections=[])

    # Try Q&A sectioning first, fall back to markdown heading-based
    sections = _detect_qa_sections(md_text)
    if sections is None:
        sections = _markdown_to_sections(md_text)

    # Clean page numbers from section content
    for section in sections:
        section.content = _clean_page_numbers(section.content)

    logger.info("Parsed PDF '%s': %d sections", title, len(sections))
    return ParsedDocument(title=title, url=url, sections=sections)
