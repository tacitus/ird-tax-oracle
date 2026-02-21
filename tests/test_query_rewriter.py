"""Tests for the query rewriter module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import ConversationTurn
from src.llm.gateway import CompletionResult
from src.llm.query_rewriter import rewrite_query


def _make_turn(question: str, answer: str) -> ConversationTurn:
    return ConversationTurn(question=question, answer=answer)


@pytest.mark.asyncio
async def test_rewrite_returns_unchanged_without_history() -> None:
    """No history means no LLM call — question returned as-is."""
    llm = AsyncMock()
    result = await rewrite_query(llm, "What are the tax brackets?", [])
    assert result == "What are the tax brackets?"
    llm.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_calls_llm_with_history() -> None:
    """With history, the LLM is called and the rewritten query is returned."""
    llm = AsyncMock()
    llm.complete.return_value = CompletionResult(
        content="What are the NZ income tax brackets for 2024-25?",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    history = [
        _make_turn(
            "What are the tax brackets?",
            "The current brackets are...",
        ),
    ]
    result = await rewrite_query(llm, "What about for 2024-25?", history)

    assert result == "What are the NZ income tax brackets for 2024-25?"
    llm.complete.assert_awaited_once()

    # Verify the messages sent to LLM include history
    messages = llm.complete.call_args[0][0]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "What are the tax brackets?"}
    assert messages[2] == {"role": "assistant", "content": "The current brackets are..."}
    assert messages[3] == {"role": "user", "content": "What about for 2024-25?"}


@pytest.mark.asyncio
async def test_rewrite_limits_history_to_3_turns() -> None:
    """Only the last 3 turns of history are sent for rewriting."""
    llm = AsyncMock()
    llm.complete.return_value = CompletionResult(
        content="Rewritten query",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    history = [
        _make_turn(f"Q{i}", f"A{i}") for i in range(5)
    ]
    await rewrite_query(llm, "Follow-up?", history)

    messages = llm.complete.call_args[0][0]
    # system + 3 turns (6 msgs) + current question = 10 messages
    assert len(messages) == 8
    # First history message should be Q2 (skipping Q0, Q1)
    assert messages[1]["content"] == "Q2"


@pytest.mark.asyncio
async def test_rewrite_falls_back_on_empty_llm_content() -> None:
    """If LLM returns None content, the original question is returned."""
    llm = AsyncMock()
    llm.complete.return_value = CompletionResult(
        content=None,
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    history = [_make_turn("Q1", "A1")]
    result = await rewrite_query(llm, "Original question", history)
    assert result == "Original question"
