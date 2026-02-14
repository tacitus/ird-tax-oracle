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
    assert response.json() == {"status": "ok"}


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
    mock_orchestrator.ask.assert_called_once_with("What is the top tax rate?")


def test_ask_missing_question(client: TestClient) -> None:
    """POST /ask without question returns 422."""
    response = client.post("/ask", json={})
    assert response.status_code == 422
