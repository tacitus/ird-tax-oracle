"""Tests for the query orchestrator ask() flow."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import ConversationTurn, RetrievalResult
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


# Default mock LLM answer includes a markdown link so ensure_citations() is a no-op
_DEFAULT_ANSWER = (
    "The top tax rate is 39%"
    " ([Tax rates](https://ird.govt.nz/rates))."
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

    assert resp.answer == _DEFAULT_ANSWER
    assert resp.model == "gemini/gemini-2.5-flash"
    assert resp.tools_used == []
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
        content=(
            "KiwiSaver contributions are tax-free"
            " ([KiwiSaver](https://ird.govt.nz/kiwisaver))."
        ),
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

    assert resp.answer == (
        "KiwiSaver contributions are tax-free"
        " ([KiwiSaver](https://ird.govt.nz/kiwisaver))."
    )
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
        content=(
            "Final answer after max rounds"
            " ([Tax rates](https://ird.govt.nz/rates))."
        ),
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
    assert resp.answer == (
        "Final answer after max rounds"
        " ([Tax rates](https://ird.govt.nz/rates))."
    )


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
async def test_tool_filters_forwarded_to_retriever(mock_retriever: AsyncMock) -> None:
    """Tool args with source_type_filter and tax_year_filter are passed to retriever."""
    followup_chunk = _make_retrieval_result(
        content="Legislation result",
        source_url="https://ird.govt.nz/legislation",
        source_title="Income Tax Act",
    )

    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}
    first_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("search_tax_documents", {
            "query": "tax rates",
            "source_type_filter": "legislation",
            "tax_year_filter": "2024-25",
        })],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    second_result = CompletionResult(
        content="The legislation says...",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [first_result, second_result]

    mock_retriever.search.side_effect = [
        [_make_retrieval_result()],  # initial search
        [followup_chunk],  # filtered tool search
    ]

    orch = Orchestrator(mock_retriever, llm)
    await orch.ask("What does the law say about 2024-25 rates?")

    # Second search call should include filters
    second_call = mock_retriever.search.call_args_list[1]
    assert second_call.kwargs.get("source_type") == "legislation"
    assert second_call.kwargs.get("tax_year") == "2024-25"


@pytest.mark.asyncio
async def test_tool_without_filters_passes_none(mock_retriever: AsyncMock) -> None:
    """Tool args without optional filters pass None to retriever."""
    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}
    first_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("search_tax_documents", {"query": "kiwisaver"})],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    second_result = CompletionResult(
        content="KiwiSaver info.",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [first_result, second_result]

    orch = Orchestrator(mock_retriever, llm)
    await orch.ask("Tell me about KiwiSaver")

    second_call = mock_retriever.search.call_args_list[1]
    assert second_call.kwargs.get("source_type") is None
    assert second_call.kwargs.get("tax_year") is None


@pytest.mark.asyncio
async def test_calculator_tool_dispatch(mock_retriever: AsyncMock) -> None:
    """LLM requests calculate_income_tax -> executes calculator -> feeds result back."""
    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}

    first_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("calculate_income_tax", {
            "annual_income": 65000,
            "tax_year": "2025-26",
        })],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    second_result = CompletionResult(
        content=(
            "On $65,000 you'd pay $11,720.50 in income tax"
            " ([Tax rates](https://ird.govt.nz/rates))."
        ),
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [first_result, second_result]

    orch = Orchestrator(mock_retriever, llm)
    resp = await orch.ask("How much tax on $65,000?")

    assert resp.answer == (
        "On $65,000 you'd pay $11,720.50 in income tax"
        " ([Tax rates](https://ird.govt.nz/rates))."
    )
    assert llm.complete.await_count == 2
    assert len(resp.tools_used) == 1
    assert resp.tools_used[0].name == "calculate_income_tax"
    assert resp.tools_used[0].label == "Income tax calculator"

    # Verify the tool result sent back to LLM contains correct calculation
    second_call_messages = llm.complete.call_args_list[1][0][0]
    tool_response_msg = [m for m in second_call_messages if m.get("role") == "tool"][0]
    tool_data = json.loads(tool_response_msg["content"])
    assert tool_data["total_tax"] == 11720.5
    assert tool_data["effective_rate"] == 18.03


@pytest.mark.asyncio
async def test_paye_tool_dispatch(mock_retriever: AsyncMock) -> None:
    """LLM requests calculate_paye -> executes calculator -> answer."""
    tool_msg = MagicMock()
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}

    first_result = CompletionResult(
        content=None,
        tool_calls=[_tool_call("calculate_paye", {
            "annual_income": 65000,
            "pay_period": "monthly",
            "has_student_loan": True,
        })],
        raw_message=tool_msg,
        model="gemini/gemini-2.5-flash",
    )
    second_result = CompletionResult(
        content="Your monthly take-home would be...",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [first_result, second_result]

    orch = Orchestrator(mock_retriever, llm)
    await orch.ask("What's my take-home on $65k monthly with student loan?")

    assert llm.complete.await_count == 2
    second_call_messages = llm.complete.call_args_list[1][0][0]
    tool_response_msg = [m for m in second_call_messages if m.get("role") == "tool"][0]
    tool_data = json.loads(tool_response_msg["content"])
    assert "annual" in tool_data
    assert tool_data["annual"]["student_loan"] > 0


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
        content=(
            "I couldn't find that tool"
            " ([Tax rates](https://ird.govt.nz/rates))."
        ),
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    mock_llm.complete.side_effect = [first_result, second_result]

    orch = Orchestrator(mock_retriever, mock_llm)
    resp = await orch.ask("use a fake tool")

    assert resp.answer == (
        "I couldn't find that tool"
        " ([Tax rates](https://ird.govt.nz/rates))."
    )
    assert mock_llm.complete.await_count == 2


# --- Conversation history tests ---


@pytest.mark.asyncio
async def test_ask_with_history_rewrites_query(
    mock_retriever: AsyncMock,
) -> None:
    """With history, rewrite_query is called and retriever uses the rewritten query."""
    # LLM: first call is the rewrite, second is the main completion
    rewrite_result = CompletionResult(
        content="What are the NZ income tax brackets for 2024-25?",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )
    answer_result = CompletionResult(
        content=(
            "The 2024-25 brackets are..."
            " ([Tax rates](https://ird.govt.nz/rates))."
        ),
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [rewrite_result, answer_result]

    history = [
        ConversationTurn(
            question="What are the tax brackets?",
            answer="The current brackets are...",
        ),
    ]

    orch = Orchestrator(mock_retriever, llm)
    resp = await orch.ask("What about for 2024-25?", history=history)

    # Retriever should receive the rewritten query
    mock_retriever.search.assert_awaited_once_with(
        "What are the NZ income tax brackets for 2024-25?"
    )
    # LLM called twice: rewrite + main completion
    assert llm.complete.await_count == 2
    assert "2024-25" in resp.answer


@pytest.mark.asyncio
async def test_ask_without_history_skips_rewrite(
    mock_retriever: AsyncMock, mock_llm: AsyncMock
) -> None:
    """Without history, no rewrite call is made."""
    orch = Orchestrator(mock_retriever, mock_llm)
    await orch.ask("What are the tax brackets?")

    # Only one LLM call (no rewrite)
    mock_llm.complete.assert_awaited_once()
    mock_retriever.search.assert_awaited_once_with("What are the tax brackets?")


@pytest.mark.asyncio
async def test_ask_history_passed_to_messages(
    mock_retriever: AsyncMock,
) -> None:
    """History is passed through to build_rag_messages for the main LLM call."""
    rewrite_result = CompletionResult(
        content="Standalone question",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )
    answer_result = CompletionResult(
        content="Answer text ([Tax rates](https://ird.govt.nz/rates)).",
        tool_calls=None,
        raw_message=MagicMock(),
        model="gemini/gemini-2.5-flash",
    )

    llm = AsyncMock()
    llm.complete.side_effect = [rewrite_result, answer_result]

    history = [
        ConversationTurn(question="Prior Q", answer="Prior A"),
    ]

    orch = Orchestrator(mock_retriever, llm)
    await orch.ask("Follow-up?", history=history)

    # The main completion (second call) should include history in messages
    main_call_messages = llm.complete.call_args_list[1][0][0]
    # Find the history messages: after system + context, before the final question
    user_messages = [m for m in main_call_messages if m.get("role") == "user"]
    assistant_messages = [m for m in main_call_messages if m.get("role") == "assistant"]
    assert any(m["content"] == "Prior Q" for m in user_messages)
    assert any(m["content"] == "Prior A" for m in assistant_messages)
