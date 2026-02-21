"""Post-processing for LLM answer text.

Defence-in-depth: fixes common LLM output issues even when the prompt
instructs otherwise (LLMs aren't deterministic).
"""

import re

from src.db.models import SourceReference

# Matches a trailing Sources/References block (with optional bold/heading markers)
_TRAILING_SOURCES_RE = re.compile(
    r"\n{1,3}"  # leading blank lines
    r"(?:\*{0,2}#{0,3}\s*)"  # optional bold ** or heading ###
    r"(?:Sources?|References?)"  # section title
    r"(?:\s*:?\s*\*{0,2})"  # optional colon and closing bold
    r"\n"  # newline after title
    r"(?:[-*\d].*\n?)*"  # bullet/numbered list lines
    r"\Z",  # must be at end of string
    re.IGNORECASE,
)

# Matches a bare https:// URL that isn't already inside a markdown link
_BARE_URL_RE = re.compile(
    r"(?<!\]\()(?<!\()"  # not preceded by ]( or (
    r"(https?://[^\s)\]>,]+)",  # capture the URL
)


def strip_trailing_sources(answer: str) -> str:
    """Remove any trailing Sources/References block the LLM generated.

    The frontend renders its own structured sources section from the
    retrieval results, so a duplicate LLM-generated list is unwanted.
    """
    return _TRAILING_SOURCES_RE.sub("", answer).rstrip()


def linkify_bare_urls(answer: str, sources: list[SourceReference]) -> str:
    """Convert bare URLs in the answer to markdown links.

    Uses source titles from retrieval results as link text when available.
    URLs already inside ``[text](url)`` markdown are left unchanged.
    """
    # Build a lookup from URL to title
    url_titles: dict[str, str] = {}
    for src in sources:
        if src.title:
            url_titles[src.url] = src.title

    def _replace_url(match: re.Match[str]) -> str:
        url = match.group(1).rstrip(".")
        title = url_titles.get(url, url)
        return f"[{title}]({url})"

    return _BARE_URL_RE.sub(_replace_url, answer)


# Matches markdown links: [text](url)
_MARKDOWN_LINK_RE = re.compile(r"\[.+?\]\(https?://[^\s)]+\)")


def ensure_citations(answer: str, sources: list[SourceReference]) -> str:
    """Append a source link if the answer contains no markdown links at all.

    This is a safety net: the LLM is prompted to cite inline, but sometimes
    it doesn't. When that happens, append the primary source as a footer.
    """
    if not sources or _MARKDOWN_LINK_RE.search(answer):
        return answer

    primary = sources[0]
    title = primary.title or primary.url
    return f"{answer}\n\nFor more details, see [{title}]({primary.url})."
