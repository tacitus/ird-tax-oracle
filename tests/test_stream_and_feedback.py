"""Tests for /ask/stream SSE endpoint, /feedback endpoint, and LLMGateway.stream()."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from src.api.routes import STATIC_DIR, router
from src.llm.gateway import LLMGateway

# --- Fixtures ---


@pytest.fixture
def app() -> FastAPI:
    """Create a test app with the router and static mount but no lifespan (no DB)."""
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# --- /ask/stream tests ---


def test_ask_stream_returns_sse_events(app: FastAPI, client: TestClient) -> None:
    """POST /ask/stream returns a series of SSE events."""
    mock_orchestrator = AsyncMock()

    async def fake_stream(question: str, history=None):  # type: ignore[no-untyped-def]
        yield {"type": "status", "message": "Searching tax documents..."}
        yield {"type": "chunk", "delta": "The "}
        yield {"type": "chunk", "delta": "answer."}
        yield {"type": "sources", "sources": []}
        yield {"type": "done", "model": "test-model", "query_id": None}

    mock_orchestrator.ask_stream = fake_stream
    app.state.orchestrator = mock_orchestrator

    response = client.post(
        "/ask/stream",
        json={"question": "What is the top tax rate?"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    # Parse SSE events
    events = []
    for line in response.text.strip().split("\n\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    assert len(events) == 5
    assert events[0]["type"] == "status"
    assert events[1]["type"] == "chunk"
    assert events[1]["delta"] == "The "
    assert events[2]["type"] == "chunk"
    assert events[2]["delta"] == "answer."
    assert events[3]["type"] == "sources"
    assert events[4]["type"] == "done"


def test_ask_stream_handles_error(app: FastAPI, client: TestClient) -> None:
    """POST /ask/stream handles errors gracefully."""
    mock_orchestrator = AsyncMock()

    async def failing_stream(question: str):  # type: ignore[no-untyped-def]
        yield {"type": "status", "message": "Searching..."}
        raise RuntimeError("LLM failed")

    mock_orchestrator.ask_stream = failing_stream
    app.state.orchestrator = mock_orchestrator

    response = client.post(
        "/ask/stream",
        json={"question": "Will this fail?"},
    )

    assert response.status_code == 200
    events = []
    for line in response.text.strip().split("\n\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    # Should have the status event plus an error event
    assert any(e["type"] == "error" for e in events)


def test_ask_stream_missing_question(client: TestClient) -> None:
    """POST /ask/stream without question returns 422."""
    response = client.post("/ask/stream", json={})
    assert response.status_code == 422


# --- /feedback tests ---


def test_feedback_positive(app: FastAPI, client: TestClient) -> None:
    """POST /feedback with positive feedback returns ok."""
    query_id = uuid4()
    mock_pool = MagicMock()

    async def mock_update_feedback(pool, qid, fb, note=None):  # type: ignore[no-untyped-def]
        return True

    app.state.pool = mock_pool

    with patch("src.api.routes.update_feedback", side_effect=mock_update_feedback):
        response = client.post(
            "/feedback",
            json={
                "query_id": str(query_id),
                "feedback": "positive",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_feedback_negative_with_note(app: FastAPI, client: TestClient) -> None:
    """POST /feedback with negative feedback and note returns ok."""
    query_id = uuid4()
    mock_pool = MagicMock()
    app.state.pool = mock_pool

    async def mock_update_feedback(pool, qid, fb, note=None):  # type: ignore[no-untyped-def]
        assert fb == "negative"
        assert note == "Answer was wrong"
        return True

    with patch("src.api.routes.update_feedback", side_effect=mock_update_feedback):
        response = client.post(
            "/feedback",
            json={
                "query_id": str(query_id),
                "feedback": "negative",
                "note": "Answer was wrong",
            },
        )

    assert response.status_code == 200


def test_feedback_query_not_found(app: FastAPI, client: TestClient) -> None:
    """POST /feedback returns 404 when query not found."""
    mock_pool = MagicMock()
    app.state.pool = mock_pool

    async def mock_update_feedback(pool, qid, fb, note=None):  # type: ignore[no-untyped-def]
        return False

    with patch("src.api.routes.update_feedback", side_effect=mock_update_feedback):
        response = client.post(
            "/feedback",
            json={
                "query_id": str(uuid4()),
                "feedback": "positive",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"error": "Query not found"}


def test_feedback_invalid_feedback_value(client: TestClient) -> None:
    """POST /feedback with invalid feedback value returns 422."""
    response = client.post(
        "/feedback",
        json={
            "query_id": str(uuid4()),
            "feedback": "maybe",
        },
    )
    assert response.status_code == 422


def test_feedback_missing_query_id(client: TestClient) -> None:
    """POST /feedback without query_id returns 422."""
    response = client.post(
        "/feedback",
        json={"feedback": "positive"},
    )
    assert response.status_code == 422


# --- LLMGateway.stream() tests ---


class _FakeStreamChunk:
    """Simulates a LiteLLM streaming chunk."""

    def __init__(self, content: str | None) -> None:
        self.choices = [MagicMock()]
        self.choices[0].delta = MagicMock()
        self.choices[0].delta.content = content


class _FakeAsyncIterator:
    """Async iterator over stream chunks."""

    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks
        self._index = 0

    def __aiter__(self) -> "_FakeAsyncIterator":
        return self

    async def __anext__(self) -> _FakeStreamChunk:
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_stream_yields_deltas(mock_acompletion: AsyncMock) -> None:
    """LLMGateway.stream() yields content deltas."""
    chunks = [
        _FakeStreamChunk("Hello"),
        _FakeStreamChunk(" world"),
        _FakeStreamChunk("!"),
    ]
    mock_acompletion.return_value = _FakeAsyncIterator(chunks)

    gw = LLMGateway(model="test-model")
    deltas = []
    async for delta in gw.stream([{"role": "user", "content": "hi"}]):
        deltas.append(delta)

    assert deltas == ["Hello", " world", "!"]


@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_stream_skips_none_content(mock_acompletion: AsyncMock) -> None:
    """LLMGateway.stream() skips chunks with None content."""
    chunks = [
        _FakeStreamChunk(None),  # e.g. role chunk
        _FakeStreamChunk("Hello"),
        _FakeStreamChunk(None),
        _FakeStreamChunk(" there"),
    ]
    mock_acompletion.return_value = _FakeAsyncIterator(chunks)

    gw = LLMGateway(model="test-model")
    deltas = []
    async for delta in gw.stream([{"role": "user", "content": "hi"}]):
        deltas.append(delta)

    assert deltas == ["Hello", " there"]


@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_stream_passes_correct_params(mock_acompletion: AsyncMock) -> None:
    """LLMGateway.stream() passes stream=True and temperature."""
    mock_acompletion.return_value = _FakeAsyncIterator([])

    gw = LLMGateway(model="test-model")
    async for _ in gw.stream([{"role": "user", "content": "hi"}]):
        pass

    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["stream"] is True
    assert call_kwargs["temperature"] == 0.1
    assert call_kwargs["model"] == "test-model"
