"""Tax-aware chunker for IRD content.

Converts ParsedDocument sections into ChunkData items ready for embedding.
Handles metadata prefixes, overlap, long-section splitting, and tax year detection.
"""

import logging
import re

from src.db.models import ChunkData, ParsedDocument, ParsedSection

logger = logging.getLogger(__name__)

# Max chunk size in characters before splitting at paragraph boundaries
MAX_CHUNK_CHARS = 6000

# Sentence boundary pattern for overlap extraction
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Tax year patterns
_TAX_YEAR_PATTERNS = [
    re.compile(r"(\d{4})[–-](\d{2,4})"),  # 2025-26 or 2025–2026
    re.compile(r"[Ff]rom\s+1\s+April\s+(\d{4})"),  # From 1 April 2025
    re.compile(r"[Tt]ax\s+year\s+(\d{4})"),  # Tax year 2025
    re.compile(r"(\d{4})/(\d{2,4})\s+tax\s+year", re.IGNORECASE),  # 2025/26 tax year
]


def _detect_tax_year(text: str) -> str | None:
    """Detect tax year from text content.

    Returns the first tax year found, in 'YYYY-YY' format.
    """
    for pattern in _TAX_YEAR_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                year1 = groups[0]
                year2 = groups[1]
                # Normalise to YYYY-YY format
                if len(year1) == 4:
                    if len(year2) == 2:
                        return f"{year1}-{year2}"
                    elif len(year2) == 4:
                        return f"{year1}-{year2[2:]}"
            elif len(groups) == 1:
                year = groups[0]
                if len(year) == 4:
                    next_year = str(int(year) + 1)[2:]
                    return f"{year}-{next_year}"
    return None


def _build_metadata_prefix(page_title: str, section: ParsedSection) -> str:
    """Build [Page Title > Section Heading] prefix for a chunk."""
    if section.parent_heading:
        return f"[{page_title} > {section.parent_heading} > {section.heading}]"
    return f"[{page_title} > {section.heading}]"


def _extract_last_sentences(text: str, n: int = 2) -> str:
    """Extract the last n sentences from text for overlap."""
    sentences = _SENTENCE_BOUNDARY.split(text)
    if len(sentences) <= n:
        return ""
    return " ".join(sentences[-n:])


def _split_at_paragraphs(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text at paragraph boundaries to stay under max_chars.

    Paragraphs are separated by double newlines.
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        if current_len + para_len + 2 > max_chars and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0

        current_parts.append(para)
        current_len += para_len + 2  # +2 for "\n\n"

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def chunk_document(document: ParsedDocument) -> list[ChunkData]:
    """Convert a parsed document into chunks ready for embedding.

    Algorithm:
    1. For each section, build [Page Title > Section Heading] prefix
    2. If section > MAX_CHUNK_CHARS, split at paragraph boundaries
    3. Append 2-sentence overlap from previous chunk
    4. Detect tax year from heading/content
    """
    chunks: list[ChunkData] = []
    prev_overlap = ""

    for section in document.sections:
        if not section.content.strip():
            continue

        prefix = _build_metadata_prefix(document.title, section)
        tax_year = _detect_tax_year(section.heading + " " + section.content)

        section_text = section.content

        # Split oversized sections at paragraph boundaries
        if len(section_text) > MAX_CHUNK_CHARS:
            text_parts = _split_at_paragraphs(section_text)
        else:
            text_parts = [section_text]

        for part in text_parts:
            # Build final chunk content
            content_parts = [prefix, ""]

            if prev_overlap:
                content_parts.append(prev_overlap)
                content_parts.append("")

            content_parts.append(part)
            content = "\n".join(content_parts)

            chunks.append(
                ChunkData(
                    content=content,
                    chunk_index=len(chunks),
                    section_title=section.heading,
                    tax_year=tax_year,
                )
            )

            # Extract overlap for next chunk
            prev_overlap = _extract_last_sentences(part)

    logger.info(
        "Chunked '%s': %d sections -> %d chunks",
        document.title,
        len(document.sections),
        len(chunks),
    )
    return chunks
