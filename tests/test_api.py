"""Tests for the API endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from src.api.routes import STATIC_DIR, router
from src.db.models import AskResponse, SourceReference


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


def test_index_serves_frontend(client: TestClient) -> None:
    """GET / returns the index.html page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "NZ Tax Assistant" in response.text


def test_health(client: TestClient) -> None:
    """GET /health returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_ask_returns_answer(app: FastAPI, client: TestClient) -> None:
    """POST /ask calls orchestrator and returns structured response."""
    mock_response = AskResponse(
        answer="The top tax rate is 39%.",
        sources=[
            SourceReference(
                url="https://ird.govt.nz/rates",
                title="Tax rates",
                section_title="Individual rates",
            )
        ],
        model="gemini/gemini-2.5-flash",
    )
    mock_orchestrator = AsyncMock()
    mock_orchestrator.ask.return_value = mock_response
    app.state.orchestrator = mock_orchestrator

    response = client.post("/ask", json={"question": "What is the top tax rate?"})

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "The top tax rate is 39%."
    assert len(data["sources"]) == 1
    assert data["sources"][0]["url"] == "https://ird.govt.nz/rates"
    assert data["model"] == "gemini/gemini-2.5-flash"
    mock_orchestrator.ask.assert_called_once_with(
        "What is the top tax rate?", history=None
    )


def test_ask_missing_question(client: TestClient) -> None:
    """POST /ask without question returns 422."""
    response = client.post("/ask", json={})
    assert response.status_code == 422


def test_ask_with_history(app: FastAPI, client: TestClient) -> None:
    """POST /ask with history passes it through to orchestrator."""
    mock_response = AskResponse(
        answer="In 2024-25 the brackets were...",
        sources=[
            SourceReference(
                url="https://ird.govt.nz/rates",
                title="Tax rates",
            )
        ],
        model="gemini/gemini-2.5-flash",
    )
    mock_orchestrator = AsyncMock()
    mock_orchestrator.ask.return_value = mock_response
    app.state.orchestrator = mock_orchestrator

    history = [
        {"question": "What are the tax brackets?", "answer": "The current brackets are..."},
    ]
    response = client.post("/ask", json={
        "question": "What about for 2024-25?",
        "history": history,
    })

    assert response.status_code == 200
    # Verify history was passed to orchestrator
    call_kwargs = mock_orchestrator.ask.call_args
    assert call_kwargs[1]["history"] is not None
    assert len(call_kwargs[1]["history"]) == 1
    assert call_kwargs[1]["history"][0].question == "What are the tax brackets?"


def test_ask_history_capped_at_5(app: FastAPI, client: TestClient) -> None:
    """History is capped at 5 turns server-side."""
    mock_response = AskResponse(
        answer="Answer.",
        sources=[],
        model="gemini/gemini-2.5-flash",
    )
    mock_orchestrator = AsyncMock()
    mock_orchestrator.ask.return_value = mock_response
    app.state.orchestrator = mock_orchestrator

    history = [
        {"question": f"Q{i}", "answer": f"A{i}"} for i in range(8)
    ]
    response = client.post("/ask", json={
        "question": "Follow-up?",
        "history": history,
    })

    assert response.status_code == 200
    call_kwargs = mock_orchestrator.ask.call_args
    assert len(call_kwargs[1]["history"]) == 5


def test_ask_without_history_passes_none(app: FastAPI, client: TestClient) -> None:
    """POST /ask without history passes None to orchestrator."""
    mock_response = AskResponse(
        answer="Answer.",
        sources=[],
        model="gemini/gemini-2.5-flash",
    )
    mock_orchestrator = AsyncMock()
    mock_orchestrator.ask.return_value = mock_response
    app.state.orchestrator = mock_orchestrator

    response = client.post("/ask", json={"question": "Tax question?"})

    assert response.status_code == 200
    call_kwargs = mock_orchestrator.ask.call_args
    assert call_kwargs[1]["history"] is None
