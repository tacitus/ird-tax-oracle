"""Tests for the RAG prompt builder."""

from src.db.models import RetrievalResult
from src.llm.prompts import build_rag_messages


def _make_chunk(
    content: str = "Tax rate is 33%",
    title: str = "Income Tax Rates",
    section: str | None = "Individual rates",
    url: str = "https://ird.govt.nz/rates",
) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        section_title=section,
        source_url=url,
        source_title=title,
        score=0.5,
    )


def test_build_rag_messages_structure() -> None:
    """Messages list has system + user, both with correct roles."""
    messages = build_rag_messages("What is the tax rate?", [_make_chunk()])
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_build_rag_messages_system_prompt_content() -> None:
    """System prompt contains key instructions."""
    messages = build_rag_messages("test", [_make_chunk()])
    system = messages[0]["content"]
    assert "NZ" in system
    assert "ONLY" in system
    assert "I don't have enough information" in system


def test_build_rag_messages_includes_context() -> None:
    """User message contains the chunk content and source label."""
    chunk = _make_chunk(content="Resident withholding tax applies.")
    messages = build_rag_messages("What is RWT?", [chunk])
    user_msg = messages[1]["content"]
    assert "Resident withholding tax applies." in user_msg
    assert "Income Tax Rates > Individual rates" in user_msg
    assert "[1]" in user_msg
    assert "What is RWT?" in user_msg


def test_build_rag_messages_multiple_chunks() -> None:
    """Multiple chunks are numbered sequentially."""
    chunks = [
        _make_chunk(content="First chunk"),
        _make_chunk(content="Second chunk", title="Other Page", section=None),
    ]
    messages = build_rag_messages("question", chunks)
    user_msg = messages[1]["content"]
    assert "[1]" in user_msg
    assert "[2]" in user_msg
    assert "First chunk" in user_msg
    assert "Second chunk" in user_msg


def test_build_rag_messages_no_section_title() -> None:
    """Source label works without section title."""
    chunk = _make_chunk(section=None)
    messages = build_rag_messages("q", [chunk])
    user_msg = messages[1]["content"]
    # Should show title without " > None"
    assert "Income Tax Rates" in user_msg
    assert "> None" not in user_msg
