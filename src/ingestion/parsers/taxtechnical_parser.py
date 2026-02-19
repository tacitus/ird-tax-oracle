"""HTML parser for taxtechnical.ird.govt.nz pages.

Handles two page types:
1. Full inline content (revenue alerts, operational statements): h2-sectioned
   articles with paragraphs, lists, metadata.
2. PDF stub pages (interpretation statements, case summaries): metadata + brief
   description + PDF download link.
"""

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag  # type: ignore[attr-defined]

from src.db.models import ParsedDocument, ParsedSection
from src.ingestion.parsers.html_parser import _get_text_content

logger = logging.getLogger(__name__)

# Content wrapper selectors in priority order
_CONTENT_SELECTORS = [
    "#main-content-tt",
    ".article-container",
    "article",
    "main",
]

# Elements to strip before parsing
_STRIP_SELECTORS = [
    "nav",
    "footer",
    "header",
    ".breadcrumb",
    ".breadcrumbs",
    ".sidebar",
    "script",
    "style",
    "noscript",
]

# Stub detection: if body text is below this word count and a PDF link exists,
# treat the page as a stub.
_STUB_WORD_THRESHOLD = 300


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title from h1 or <title> tag.

    No bilingual handling — taxtechnical pages use simple English titles.
    """
    h1 = soup.find("h1")
    if h1 and isinstance(h1, Tag):
        return h1.get_text(strip=True)

    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        for sep in [" - ", " | ", " – "]:
            if sep in title_text:
                title_text = title_text.split(sep)[0].strip()
        return title_text

    return "Untitled"


def _find_content_root(soup: BeautifulSoup) -> Tag:
    """Find the main content container."""
    for selector in _CONTENT_SELECTORS:
        element = soup.select_one(selector)
        if element:
            logger.debug("Found content root: %s", selector)
            return element

    logger.warning("No content wrapper found, falling back to <body>")
    body = soup.find("body")
    if body and isinstance(body, Tag):
        return body
    return soup


def _strip_unwanted(root: Tag) -> None:
    """Remove navigation, footer, and other non-content elements."""
    for selector in _STRIP_SELECTORS:
        for element in root.select(selector):
            element.decompose()


def _extract_metadata(root: Tag) -> ParsedSection | None:
    """Extract reference number and issue date from the page content.

    Looks for patterns like "Reference: IS 24/10" and "Issued: 01 December 2024"
    in the text near the top of the article.
    """
    text = root.get_text(separator="\n")
    lines: list[str] = []

    ref_match = re.search(r"Reference:\s*(.+)", text)
    if ref_match:
        lines.append(f"Reference: {ref_match.group(1).strip()}")

    date_match = re.search(r"Issued:\s*(.+)", text)
    if date_match:
        lines.append(f"Issued: {date_match.group(1).strip()}")

    if not lines:
        return None

    return ParsedSection(
        heading="Metadata",
        content="\n".join(lines),
        heading_level=2,
    )


def _find_pdf_url(root: Tag, page_url: str) -> str | None:
    """Find a PDF download link in the content."""
    for link in root.find_all("a", href=True):
        href = link["href"]
        if isinstance(href, list):
            href = href[0]
        if href.lower().endswith(".pdf"):
            return urljoin(page_url, href)
    return None


def _count_body_words(root: Tag) -> int:
    """Count words in body text, excluding headings and metadata."""
    word_count = 0
    for element in root.find_all(["p", "li"]):
        # Skip paragraphs that are metadata
        text = element.get_text(strip=True)
        if text.startswith(("Reference:", "Issued:")):
            continue
        word_count += len(text.split())
    return word_count


def _walk_sections(root: Tag) -> list[ParsedSection]:
    """Walk DOM tree, splitting on h2/h3 boundaries.

    Same flat find_all approach as html_parser but without bilingual heading
    handling or NOINDEX noise filtering.
    """
    sections: list[ParsedSection] = []
    all_headings = root.find_all(["h2", "h3"])

    if not all_headings:
        text = _get_text_content(root)
        if text:
            sections.append(
                ParsedSection(heading="Content", content=text, heading_level=2)
            )
        return sections

    # Collect content before the first heading as "Introduction"
    intro_parts: list[str] = []
    for element in root.descendants:
        if element == all_headings[0]:
            break
        if isinstance(element, NavigableString):
            parent_tags = {p.name for p in element.parents if isinstance(p, Tag)}
            if not parent_tags & {"h1", "h2", "h3", "h4", "h5", "h6"}:
                text = element.strip()
                if text and not text.startswith(("Reference:", "Issued:")):
                    intro_parts.append(text)

    intro_text = "\n\n".join(intro_parts).strip()
    if intro_text:
        sections.append(
            ParsedSection(heading="Introduction", content=intro_text, heading_level=2)
        )

    # Process each heading and its following content
    current_h2: str | None = None

    for i, heading in enumerate(all_headings):
        heading_level = int(heading.name[1])
        heading_text = heading.get_text(strip=True)

        if heading_level == 2:
            current_h2 = heading_text

        # Collect content between this heading and the next
        next_heading = all_headings[i + 1] if i + 1 < len(all_headings) else None
        content_parts: list[str] = []
        collecting = False

        for element in root.descendants:
            if element is heading:
                collecting = True
                continue
            if next_heading and element is next_heading:
                break
            if not collecting:
                continue

            if isinstance(element, NavigableString):
                parent_tags = {p.name for p in element.parents if isinstance(p, Tag)}
                if parent_tags & {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    continue
                text = element.strip()
                if text:
                    content_parts.append(text)

        content = " ".join(content_parts).strip()
        if content:
            sections.append(
                ParsedSection(
                    heading=heading_text,
                    content=content,
                    heading_level=heading_level,
                    parent_heading=current_h2 if heading_level == 3 else None,
                )
            )

    return sections


def parse_taxtechnical(html: str, url: str) -> ParsedDocument:
    """Parse a taxtechnical.ird.govt.nz HTML page into structured sections.

    Args:
        html: Raw HTML content.
        url: Source URL (for resolving relative PDF links).

    Returns:
        ParsedDocument with title, sections, and optional pdf_url.
    """
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    content_root = _find_content_root(soup)
    _strip_unwanted(content_root)

    metadata = _extract_metadata(content_root)
    pdf_url = _find_pdf_url(content_root, url)
    word_count = _count_body_words(content_root)

    is_stub = word_count < _STUB_WORD_THRESHOLD and pdf_url is not None

    sections: list[ParsedSection] = []

    if metadata:
        sections.append(metadata)

    if is_stub:
        # For stubs, collect non-metadata body text as a description section
        desc_parts: list[str] = []
        for p in content_root.find_all("p"):
            text = p.get_text(strip=True)
            if text and not text.startswith(("Reference:", "Issued:")):
                # Skip paragraphs that are just PDF links
                if p.find("a", href=lambda h: h and h.endswith(".pdf")):
                    continue
                desc_parts.append(text)
        if desc_parts:
            sections.append(
                ParsedSection(
                    heading="Description",
                    content="\n\n".join(desc_parts),
                    heading_level=2,
                )
            )
    else:
        # Full content: walk sections normally
        content_sections = _walk_sections(content_root)
        sections.extend(content_sections)

    if not sections:
        full_text = _get_text_content(content_root)
        if full_text:
            sections = [
                ParsedSection(heading="Content", content=full_text, heading_level=2)
            ]

    logger.info(
        "Parsed taxtechnical '%s': %d sections, stub=%s, pdf=%s",
        title,
        len(sections),
        is_stub,
        pdf_url is not None,
    )

    return ParsedDocument(
        title=title,
        url=url,
        sections=sections,
        pdf_url=pdf_url,
    )
