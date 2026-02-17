"""Tests for HTTP Basic Auth middleware."""

import base64
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.app import BasicAuthMiddleware

_TEST_USER = b"testuser"
_TEST_PASS = b"testpass123"


def _build_app() -> FastAPI:
    """Build a minimal app with BasicAuthMiddleware for testing."""
    app = FastAPI()
    app.add_middleware(BasicAuthMiddleware)

    @app.get("/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _auth_header(username: str, password: str) -> dict[str, str]:
    """Build a Basic Auth header."""
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


@patch("src.api.app.AUTH_USERNAME", _TEST_USER)
@patch("src.api.app.AUTH_PASSWORD", _TEST_PASS)
def test_valid_credentials_pass() -> None:
    """Correct credentials return 200."""
    app = _build_app()
    client = TestClient(app)
    response = client.get("/test", headers=_auth_header("testuser", "testpass123"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("src.api.app.AUTH_USERNAME", _TEST_USER)
@patch("src.api.app.AUTH_PASSWORD", _TEST_PASS)
def test_missing_auth_header_returns_401() -> None:
    """No Authorization header returns 401 with WWW-Authenticate."""
    app = _build_app()
    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


@patch("src.api.app.AUTH_USERNAME", _TEST_USER)
@patch("src.api.app.AUTH_PASSWORD", _TEST_PASS)
def test_invalid_credentials_returns_401() -> None:
    """Wrong password returns 401."""
    app = _build_app()
    client = TestClient(app)
    response = client.get("/test", headers=_auth_header("testuser", "wrongpassword"))
    assert response.status_code == 401


@patch("src.api.app.AUTH_USERNAME", _TEST_USER)
@patch("src.api.app.AUTH_PASSWORD", _TEST_PASS)
def test_malformed_base64_returns_401() -> None:
    """Garbage in Authorization header returns 401."""
    app = _build_app()
    client = TestClient(app)
    response = client.get("/test", headers={"Authorization": "Basic !!!not-base64!!!"})
    assert response.status_code == 401
