"""Tests for LLM answer post-processing."""

from src.db.models import SourceReference
from src.llm.postprocess import linkify_bare_urls, strip_trailing_sources


# --- strip_trailing_sources ---


def test_strip_trailing_sources_plain() -> None:
    """Removes a plain 'Sources:' bullet list at the end."""
    answer = (
        "The tax rate is 33%.\n\n"
        "Sources:\n"
        "- IRD: Tax rates for individuals\n"
        "- Income Tax Act 2007, s YA 1\n"
    )
    result = strip_trailing_sources(answer)
    assert result == "The tax rate is 33%."


def test_strip_trailing_sources_bold() -> None:
    """Removes a bold '**Sources:**' variant."""
    answer = (
        "The tax rate is 33%.\n\n"
        "**Sources:**\n"
        "- IRD: Tax rates\n"
    )
    result = strip_trailing_sources(answer)
    assert result == "The tax rate is 33%."


def test_strip_trailing_sources_heading() -> None:
    """Removes a '### Sources' heading variant."""
    answer = (
        "The tax rate is 33%.\n\n"
        "### Sources\n"
        "- IRD: Tax rates\n"
    )
    result = strip_trailing_sources(answer)
    assert result == "The tax rate is 33%."


def test_strip_trailing_references() -> None:
    """Removes a 'References:' variant."""
    answer = (
        "The tax rate is 33%.\n\n"
        "References:\n"
        "- Some reference\n"
    )
    result = strip_trailing_sources(answer)
    assert result == "The tax rate is 33%."


def test_strip_trailing_sources_numbered() -> None:
    """Removes numbered list variants."""
    answer = (
        "The tax rate is 33%.\n\n"
        "Sources:\n"
        "1. IRD: Tax rates\n"
        "2. Income Tax Act\n"
    )
    result = strip_trailing_sources(answer)
    assert result == "The tax rate is 33%."


def test_strip_trailing_sources_preserves_body() -> None:
    """Leaves non-trailing content unchanged."""
    answer = "The Sources: of information are varied.\n\nHere is the answer."
    result = strip_trailing_sources(answer)
    assert result == answer


def test_strip_no_sources_block() -> None:
    """Returns answer unchanged when there's no trailing sources block."""
    answer = "The tax rate is 33%."
    result = strip_trailing_sources(answer)
    assert result == answer


# --- linkify_bare_urls ---


def _make_sources() -> list[SourceReference]:
    return [
        SourceReference(
            url="https://www.ird.govt.nz/income-tax/rates",
            title="Tax rates for individuals",
            section_title=None,
        ),
        SourceReference(
            url="https://www.ird.govt.nz/kiwisaver",
            title="KiwiSaver",
            section_title="Contributions",
        ),
    ]


def test_linkify_bare_url_with_known_source() -> None:
    """Bare URL matching a source gets its title as link text."""
    answer = "See https://www.ird.govt.nz/income-tax/rates for details."
    result = linkify_bare_urls(answer, _make_sources())
    assert result == (
        "See [Tax rates for individuals]"
        "(https://www.ird.govt.nz/income-tax/rates) for details."
    )


def test_linkify_bare_url_unknown_source() -> None:
    """Bare URL not in sources uses the URL itself as link text."""
    answer = "Check https://www.ird.govt.nz/other-page for more."
    result = linkify_bare_urls(answer, _make_sources())
    assert result == (
        "Check [https://www.ird.govt.nz/other-page]"
        "(https://www.ird.govt.nz/other-page) for more."
    )


def test_linkify_preserves_existing_markdown_links() -> None:
    """URLs already in [text](url) format are not double-wrapped."""
    answer = (
        "See [Tax rates](https://www.ird.govt.nz/income-tax/rates) "
        "for details."
    )
    result = linkify_bare_urls(answer, _make_sources())
    assert result == answer


def test_linkify_no_urls() -> None:
    """Answer with no URLs is returned unchanged."""
    answer = "The tax rate is 33% for income over $70,000."
    result = linkify_bare_urls(answer, _make_sources())
    assert result == answer


def test_linkify_empty_sources() -> None:
    """Works with empty sources list — bare URLs become self-referencing links."""
    answer = "See https://www.ird.govt.nz/income-tax/rates for details."
    result = linkify_bare_urls(answer, [])
    assert result == (
        "See [https://www.ird.govt.nz/income-tax/rates]"
        "(https://www.ird.govt.nz/income-tax/rates) for details."
    )
