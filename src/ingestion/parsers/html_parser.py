"""HTML parser for IRD guidance pages.

Extracts structured sections from ird.govt.nz and taxtechnical.ird.govt.nz pages.
Handles bilingual titles, strips navigation/footer, splits on h2/h3 boundaries.
"""

import logging

from bs4 import BeautifulSoup, NavigableString, Tag

from src.db.models import ParsedDocument, ParsedSection

logger = logging.getLogger(__name__)

# Content wrapper selectors in priority order
_CONTENT_SELECTORS = [
    "#main-content-wrapper",
    "#main-content",
    "main",
    "article",
    '[role="main"]',
]

# Elements to strip before parsing
_STRIP_SELECTORS = [
    "nav",
    "footer",
    "header",
    ".breadcrumb",
    ".breadcrumbs",
    ".side-nav",
    ".sidebar",
    ".navigation",
    ".page-nav",
    ".skip-link",
    ".sr-only",
    "script",
    "style",
    "noscript",
    ".feedback",
    ".last-updated",
    "#feedback",
    ".related-content",
    ".row-splitter",
]

# Noise strings to filter from extracted text (IRD template artifacts)
_NOISE_PATTERNS = {
    "END NOINDEX",
    "START NOINDEX",
    "Start LeftHandNavigation",
    "End LeftHandNavigation",
    "Start RightHandSide",
    "End RightHandSide",
    "Start MainContent",
    "End MainContent",
    "Start KeyDateSummary",
    "End KeyDateSummary",
}


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title, handling IRD's bilingual h1 pattern.

    IRD pages use two patterns for bilingual titles:
    1. "English title / Te reo title" (slash-separated)
    2. <h1><span aria-hidden="true" lang="mi">Te reo</span> English title</h1>
    """
    h1 = soup.find("h1")
    if h1 and isinstance(h1, Tag):
        # Remove aria-hidden spans (Māori text) before extracting
        for span in h1.find_all("span", attrs={"aria-hidden": "true"}):
            span.decompose()

        title_text = h1.get_text(strip=True)

        # Also handle slash-separated bilingual titles
        if " / " in title_text:
            title_text = title_text.split(" / ")[0].strip()
        return title_text

    # Fallback to <title> tag
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        # Remove common suffixes like " - Inland Revenue" or " | ird.govt.nz"
        for sep in [" - ", " | ", " – "]:
            if sep in title_text:
                title_text = title_text.split(sep)[0].strip()
        return title_text

    return "Untitled"


def _find_content_root(soup: BeautifulSoup) -> Tag:
    """Find the main content container using priority selectors."""
    for selector in _CONTENT_SELECTORS:
        element = soup.select_one(selector)
        if element:
            logger.debug("Found content root: %s", selector)
            return element

    logger.warning("No content wrapper found, falling back to <body>")
    body = soup.find("body")
    if body and isinstance(body, Tag):
        return body
    return soup  # type: ignore[return-value]


def _strip_unwanted(root: Tag) -> None:
    """Remove navigation, footer, and other non-content elements in place."""
    for selector in _STRIP_SELECTORS:
        for element in root.select(selector):
            element.decompose()


def _get_text_content(element: Tag) -> str:
    """Extract clean text from an element, preserving paragraph breaks."""
    # Replace <br> with newlines
    for br in element.find_all("br"):
        br.replace_with("\n")

    # Get text with separator for block elements
    text = element.get_text(separator="\n", strip=False)

    # Clean up whitespace: collapse multiple spaces on each line, collapse multiple newlines
    lines = []
    for line in text.split("\n"):
        cleaned = line.strip()
        if cleaned:
            lines.append(cleaned)

    return "\n\n".join(lines)


def _extract_heading_text(heading: Tag) -> str:
    """Extract heading text, handling bilingual headings.

    Removes aria-hidden spans (Māori text) and handles slash-separated titles.
    """
    # Remove aria-hidden spans before extracting text
    for span in heading.find_all("span", attrs={"aria-hidden": "true"}):
        span.decompose()

    text = heading.get_text(strip=True)
    if " / " in text:
        text = text.split(" / ")[0].strip()
    return text


def _collect_content_between(
    start_element: Tag | None, stop_tags: set[str], root: Tag
) -> str:
    """Collect text content from siblings after start_element until a stop tag.

    This is a helper for the flat heading-based approach — it collects
    all text between two headings by walking the element tree.
    """
    parts: list[str] = []

    def _walk(element: Tag) -> bool:
        """Walk element tree, collecting text. Returns False to stop."""
        for child in element.children:
            if isinstance(child, NavigableString):
                text = child.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            if child.name and child.name.lower() in stop_tags:
                return False  # Hit next heading
            # Check if this element contains a heading — if so, walk into it
            if child.find(stop_tags):
                if not _walk(child):
                    return False
            else:
                text = _get_text_content(child)
                if text:
                    parts.append(text)
        return True

    return "\n\n".join(parts)


def _walk_sections(root: Tag) -> list[ParsedSection]:
    """Walk DOM tree, splitting on h2/h3 boundaries regardless of nesting depth.

    Uses find_all to locate all h2/h3 headings in the tree, then collects
    content between consecutive headings.
    """
    sections: list[ParsedSection] = []

    # Find all h2 and h3 headings anywhere in the tree
    all_headings = root.find_all(["h2", "h3"])

    if not all_headings:
        # No headings — collect all content as a single section
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
            # Only include if not inside a heading
            parent_tags = {p.name for p in element.parents if isinstance(p, Tag)}
            if not parent_tags & {"h1", "h2", "h3", "h4", "h5", "h6"}:
                text = element.strip()
                if text and text not in _NOISE_PATTERNS:
                    intro_parts.append(text)

    intro_text = "\n\n".join(intro_parts).strip()
    if intro_text:
        sections.append(
            ParsedSection(heading="Introduction", content=intro_text, heading_level=2)
        )

    # Process each heading and its following content
    current_h2: str | None = None

    for i, heading in enumerate(all_headings):
        heading_level = int(heading.name[1])  # h2 -> 2, h3 -> 3
        heading_text = _extract_heading_text(heading)

        if heading_level == 2:
            current_h2 = heading_text

        # Collect content between this heading and the next one
        content_parts: list[str] = []
        # Walk siblings and descendants after this heading until the next heading
        next_heading = all_headings[i + 1] if i + 1 < len(all_headings) else None

        # Walk all elements between this heading and the next
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
                # Skip text inside headings
                parent_tags = {p.name for p in element.parents if isinstance(p, Tag)}
                if parent_tags & {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    continue
                text = element.strip()
                if text and text not in _NOISE_PATTERNS:
                    content_parts.append(text)

        # Build clean content from collected text
        content = " ".join(content_parts)
        # Re-add paragraph boundaries at sentence breaks for readability
        content = content.strip()

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


def parse_html(html: str, url: str) -> ParsedDocument:
    """Parse an IRD HTML page into structured sections.

    Args:
        html: Raw HTML content.
        url: Source URL (for metadata).

    Returns:
        ParsedDocument with title and list of sections.
    """
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    content_root = _find_content_root(soup)
    _strip_unwanted(content_root)

    sections = _walk_sections(content_root)

    if not sections:
        # If no sections found, treat entire content as one section
        full_text = _get_text_content(content_root)
        if full_text:
            sections = [
                ParsedSection(
                    heading="Content",
                    content=full_text,
                    heading_level=2,
                )
            ]

    logger.info("Parsed '%s': %d sections", title, len(sections))
    return ParsedDocument(title=title, url=url, sections=sections)
