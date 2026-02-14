"""Tests for the RAG prompt builder."""

from datetime import date

from src.db.models import RetrievalResult
from src.llm.prompts import (
    build_rag_messages,
    format_context_message,
    format_system_prompt,
    get_tax_year_context,
)


def _make_chunk(
    content: str = "Tax rate is 33%",
    title: str = "Income Tax Rates",
    section: str | None = "Individual rates",
    url: str = "https://ird.govt.nz/rates",
    source_type: str | None = "ird_guidance",
    tax_year: str | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        section_title=section,
        source_url=url,
        source_title=title,
        source_type=source_type,
        tax_year=tax_year,
        score=0.5,
    )


# --- Tax year logic ---


def test_tax_year_before_april() -> None:
    """Before April, the tax year started the previous calendar year."""
    ctx = get_tax_year_context(date(2026, 2, 14))
    assert ctx["current_tax_year"] == "2025\u201326"
    assert ctx["tax_year_start"] == "1 April 2025"
    assert ctx["tax_year_end"] == "31 March 2026"


def test_tax_year_after_april() -> None:
    """From April onwards, the tax year starts in the current calendar year."""
    ctx = get_tax_year_context(date(2026, 5, 1))
    assert ctx["current_tax_year"] == "2026\u201327"
    assert ctx["tax_year_start"] == "1 April 2026"
    assert ctx["tax_year_end"] == "31 March 2027"


def test_tax_year_exactly_april_1() -> None:
    """April 1 is the start of a new tax year."""
    ctx = get_tax_year_context(date(2026, 4, 1))
    assert ctx["current_tax_year"] == "2026\u201327"


def test_tax_year_march_31() -> None:
    """March 31 is still the previous tax year."""
    ctx = get_tax_year_context(date(2026, 3, 31))
    assert ctx["current_tax_year"] == "2025\u201326"


# --- System prompt ---


def test_format_system_prompt_contains_tax_year() -> None:
    """System prompt has tax year variables injected."""
    prompt = format_system_prompt(date(2026, 2, 14))
    assert "2025\u201326" in prompt
    assert "1 April 2025" in prompt
    assert "31 March 2026" in prompt


def test_format_system_prompt_contains_key_sections() -> None:
    """System prompt includes all structured sections."""
    prompt = format_system_prompt(date(2026, 2, 14))
    assert "<hard_rules>" in prompt
    assert "<tax_year_rules>" in prompt
    assert "<context_instructions>" in prompt
    assert "<response_style>" in prompt


def test_format_system_prompt_contains_key_instructions() -> None:
    """System prompt contains critical behavioural rules."""
    prompt = format_system_prompt(date(2026, 2, 14))
    assert "NEVER" in prompt
    assert "ALWAYS cite" in prompt
    assert "markdown link" in prompt.lower()
    assert "KiwiSaver" in prompt
    assert "Do NOT end your answer with" in prompt


# --- Context formatting ---


def test_format_context_empty() -> None:
    """Empty chunks produce a no-documents message."""
    result = format_context_message([])
    assert "<context>" in result
    assert "No relevant documents were found" in result
    assert "</context>" in result


def test_format_context_xml_structure() -> None:
    """Context uses XML source tags with metadata."""
    chunk = _make_chunk(
        content="The rate is 33%.",
        source_type="ird_guidance",
        tax_year="2025-26",
    )
    result = format_context_message([chunk])
    assert '<source id="1">' in result
    assert "<title>Income Tax Rates</title>" in result
    assert "<url>https://ird.govt.nz/rates</url>" in result
    assert "<type>ird_guidance</type>" in result
    assert "<section>Individual rates</section>" in result
    assert "<tax_year>2025-26</tax_year>" in result
    assert "The rate is 33%." in result
    assert "</source>" in result
    assert "</context>" in result


def test_format_context_omits_none_fields() -> None:
    """Optional fields are omitted when None."""
    chunk = _make_chunk(section=None, source_type=None, tax_year=None)
    result = format_context_message([chunk])
    assert "<section>" not in result
    assert "<type>" not in result
    assert "<tax_year>" not in result


def test_format_context_multiple_chunks() -> None:
    """Multiple chunks get sequential source IDs."""
    chunks = [
        _make_chunk(content="First"),
        _make_chunk(content="Second", title="Other Page"),
    ]
    result = format_context_message(chunks)
    assert '<source id="1">' in result
    assert '<source id="2">' in result
    assert "First" in result
    assert "Second" in result


def test_format_context_falls_back_to_url_for_title() -> None:
    """When source_title is None, uses source_url as title."""
    chunk = _make_chunk()
    chunk.source_title = None
    result = format_context_message([chunk])
    assert "<title>https://ird.govt.nz/rates</title>" in result


# --- Message builder ---


def test_build_rag_messages_structure() -> None:
    """Messages list has system + context user + question user."""
    messages = build_rag_messages(
        "What is the tax rate?",
        [_make_chunk()],
        today=date(2026, 2, 14),
    )
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "user"


def test_build_rag_messages_system_has_tax_year() -> None:
    """System message includes the injected tax year."""
    messages = build_rag_messages("test", [_make_chunk()], today=date(2026, 2, 14))
    assert "2025\u201326" in messages[0]["content"]


def test_build_rag_messages_context_is_xml() -> None:
    """Context message uses XML format."""
    messages = build_rag_messages("test", [_make_chunk()], today=date(2026, 2, 14))
    context_msg = messages[1]["content"]
    assert "<context>" in context_msg
    assert '<source id="1">' in context_msg


def test_build_rag_messages_question_is_separate() -> None:
    """User question is its own message, not embedded in context."""
    messages = build_rag_messages(
        "What is the tax rate?",
        [_make_chunk()],
        today=date(2026, 2, 14),
    )
    assert messages[2]["content"] == "What is the tax rate?"
    # Question should NOT appear in the context message
    assert "What is the tax rate?" not in messages[1]["content"]


def test_build_rag_messages_empty_context() -> None:
    """Empty chunks still produce three messages."""
    messages = build_rag_messages("q", [], today=date(2026, 2, 14))
    assert len(messages) == 3
    assert "No relevant documents" in messages[1]["content"]
