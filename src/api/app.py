"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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
    app.state.orchestrator = Orchestrator(retriever, llm)

    yield

    logger.info("Shutting down...")
    await close_pool()


STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="NZ Tax RAG", lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
