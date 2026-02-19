"""FastAPI application factory."""

import base64
import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.routes import router
from src.db.session import close_pool, get_pool
from src.llm.gateway import LLMGateway
from src.orchestrator import Orchestrator
from src.rag.embedder import GeminiEmbedder
from src.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: init DB pool, build orchestrator. Shutdown: close pool."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting up...")

    pool = await get_pool()
    embedder = GeminiEmbedder()
    retriever = HybridRetriever(pool, embedder)
    llm = LLMGateway()
    app.state.orchestrator = Orchestrator(retriever, llm, pool=pool)

    yield

    logger.info("Shutting down...")
    await close_pool()


STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

UNAUTHORIZED = Response(
    content="Unauthorized",
    status_code=401,
    headers={"WWW-Authenticate": "Basic"},
)


AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "").encode()
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "").encode()


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Enforce HTTP Basic Auth on all requests."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                username, password = decoded.split(":", 1)
            except Exception:
                return UNAUTHORIZED
            if secrets.compare_digest(username.encode(), AUTH_USERNAME) and secrets.compare_digest(
                password.encode(), AUTH_PASSWORD
            ):
                return await call_next(request)
        return UNAUTHORIZED


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="NZ Tax RAG", lifespan=lifespan)
    app.add_middleware(BasicAuthMiddleware)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
