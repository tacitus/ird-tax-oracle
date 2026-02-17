"""Tests for the query orchestrator ask() flow."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import RetrievalResult
from src.llm.gateway import CompletionResult
from src.orchestrator import Orchestrator


def _make_retrieval_result(
    content: str = "Tax rate is 39%",
    source_url: str = "https://ird.govt.nz/rates",
    source_title: str = "Tax rates",
    section_title: str | None = "Individual rates",
) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        section_title=section_title,
        source_url=source_url,
        source_title=source_title,
        source_type="ird_guidance",
        score=0.5,
    )


def _tool_call(name: str, arguments: dict) -> MagicMock:  # type: ignore[type-arg]
    """Build a fake tool_call object matching LiteLLM's response shape."""
    tc = MagicMock()
    tc.id = "call_123"
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


@pytest.mark.asyncio
async def test_ask_happy_path(mock_retriever: AsyncMock, mock_llm: AsyncMock) -> None:
    """Retrieve -> single LLM call -> post-processed answer with sources."""
    orch = Orchestrator(mock_retriever, mock_llm)
    resp = await orch.ask("What is the top tax rate?")

    assert resp.answer == "The top tax rate is 39%."
    assert resp.model == "gemini/gemini-2.5-flash"
    assert len(resp.sources) == 2
    assert resp.sources[0].url == "https://ird.govt.nz/rates"
    mock_retriever.search.assert_awaited_once_with("What is the top tax rate?")
    mock_llm.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_with_tool_call(mock_retriever: AsyncMock) -> None:
    """LLM requests search_tax_documents -> executes -> second LLM call -> answer."""
    followup_chunk = _make_retrieval_result(
        content="KiwiSaver info",
        source_url="https://ird.govt.nz/kiwisaver",
        source_title="KiwiSaver",
    )

    # First call: LLM returns a tool call
    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}
    first_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("search_tax_documents", {"query": "kiwisaver"})],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    # Second call: LLM returns final answer
    second_result = CompletionResult(
        content="KiwiSaver contributions are tax-free.",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [first_result, second_result]

    # Retriever returns different results for followup search
    mock_retriever.search.side_effect = [
        [_make_retrieval_result()],  # initial search
        [followup_chunk],  # tool-triggered search
    ]

    orch = Orchestrator(mock_retriever, llm)
    resp = await orch.ask("Tell me about KiwiSaver")

    assert resp.answer == "KiwiSaver contributions are tax-free."
    assert llm.complete.await_count == 2
    assert mock_retriever.search.await_count == 2
    # Sources should include both initial and followup chunks
    urls = {s.url for s in resp.sources}
    assert "https://ird.govt.nz/kiwisaver" in urls


@pytest.mark.asyncio
async def test_ask_max_tool_rounds_respected(mock_retriever: AsyncMock) -> None:
    """Tool loop stops after _MAX_TOOL_ROUNDS (3)."""
    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}

    # LLM always returns a tool call — should stop after 3 rounds
    perpetual_tool_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("search_tax_documents", {"query": "loop"})],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    final_result = CompletionResult(
        content="Final answer after max rounds.",
        tool_calls=[_tool_call("search_tax_documents", {"query": "more"})],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    # initial + 3 rounds = 4 calls; 4th still has tool_calls but loop exits
    llm.complete.side_effect = [
        perpetual_tool_result,
        perpetual_tool_result,
        perpetual_tool_result,
        final_result,
    ]

    orch = Orchestrator(mock_retriever, llm)
    resp = await orch.ask("loop question")

    # 1 initial + 3 followups = 4 total LLM calls
    assert llm.complete.await_count == 4
    assert resp.answer == "Final answer after max rounds."


@pytest.mark.asyncio
async def test_ask_deduplicates_sources_by_url(
    mock_retriever: AsyncMock, mock_llm: AsyncMock
) -> None:
    """Multiple chunks from the same URL produce a single source."""
    mock_retriever.search.return_value = [
        _make_retrieval_result(content="Chunk 1", source_url="https://ird.govt.nz/rates"),
        _make_retrieval_result(content="Chunk 2", source_url="https://ird.govt.nz/rates"),
        _make_retrieval_result(content="Chunk 3", source_url="https://ird.govt.nz/paye"),
    ]

    orch = Orchestrator(mock_retriever, mock_llm)
    resp = await orch.ask("rates?")

    urls = [s.url for s in resp.sources]
    assert urls == ["https://ird.govt.nz/rates", "https://ird.govt.nz/paye"]


@pytest.mark.asyncio
async def test_execute_tool_unknown(
    mock_retriever: AsyncMock, mock_llm: AsyncMock
) -> None:
    """Unknown tool name returns error dict without crashing."""
    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}

    first_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("nonexistent_tool", {"foo": "bar"})],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    second_result = CompletionResult(
        content="I couldn't find that tool.",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    mock_llm.complete.side_effect = [first_result, second_result]

    orch = Orchestrator(mock_retriever, mock_llm)
    resp = await orch.ask("use a fake tool")

    assert resp.answer == "I couldn't find that tool."
    assert mock_llm.complete.await_count == 2
