"""Tests for the LLM gateway wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.gateway import CompletionResult, LLMGateway


def _mock_response(content: str | None = "Hello", tool_calls: list | None = None) -> MagicMock:  # type: ignore[type-arg]
    """Build a mock LiteLLM response object."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.model = "gemini/gemini-2.5-flash"
    return response


@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_complete_returns_text(mock_acompletion: AsyncMock) -> None:
    """Mocked litellm.acompletion returns CompletionResult with content."""
    mock_acompletion.return_value = _mock_response(content="The answer is 42.")

    gw = LLMGateway(model="test-model")
    result = await gw.complete([{"role": "user", "content": "question"}])

    assert isinstance(result, CompletionResult)
    assert result.content == "The answer is 42."
    assert result.tool_calls is None
    assert result.model == "gemini/gemini-2.5-flash"


@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_complete_returns_tool_calls(mock_acompletion: AsyncMock) -> None:
    """Response with tool_calls is parsed correctly."""
    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_abc"
    fake_tool_call.function.name = "search_tax_documents"
    fake_tool_call.function.arguments = '{"query": "PAYE"}'

    mock_acompletion.return_value = _mock_response(content=None, tool_calls=[fake_tool_call])

    gw = LLMGateway(model="test-model")
    result = await gw.complete([{"role": "user", "content": "PAYE info"}])

    assert result.content is None
    assert result.tool_calls is not None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].function.name == "search_tax_documents"


@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_complete_passes_tools_kwarg(mock_acompletion: AsyncMock) -> None:
    """tools parameter is forwarded to litellm."""
    mock_acompletion.return_value = _mock_response()
    tools = [{"type": "function", "function": {"name": "test_tool"}}]

    gw = LLMGateway(model="test-model")
    await gw.complete([{"role": "user", "content": "hi"}], tools=tools)

    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["tools"] == tools
    assert call_kwargs["model"] == "test-model"
