"""API routes for the NZ Tax RAG system."""

import json
import logging
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from src.db.models import AskResponse, ConversationTurn
from src.db.query_log import get_query_stats, update_feedback

logger = logging.getLogger(__name__)

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class AskRequest(BaseModel):
    """Request body for the /ask endpoint."""

    question: str
    history: list[ConversationTurn] = []


class FeedbackRequest(BaseModel):
    """Request body for the /feedback endpoint."""

    query_id: UUID
    feedback: Literal["positive", "negative"]
    note: str | None = None


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Serve the frontend."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Redirect /favicon.ico to the SVG favicon."""
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@router.get("/health")
async def health(request: Request) -> dict:  # type: ignore[type-arg]
    """Health check endpoint with optional query stats."""
    result: dict[str, object] = {"status": "ok"}
    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        stats = await get_query_stats(pool)
        if stats:
            result["query_stats"] = stats
    return result


_MAX_HISTORY_TURNS = 5


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """Answer a tax question using RAG-grounded LLM."""
    orchestrator = request.app.state.orchestrator
    history = body.history[:_MAX_HISTORY_TURNS] or None
    return await orchestrator.ask(body.question, history=history)


@router.post("/ask/stream")
async def ask_stream(body: AskRequest, request: Request) -> StreamingResponse:
    """Stream a tax question answer via Server-Sent Events."""
    orchestrator = request.app.state.orchestrator
    history = body.history[:_MAX_HISTORY_TURNS] or None

    async def event_generator():  # type: ignore[no-untyped-def]
        try:
            async for event in orchestrator.ask_stream(body.question, history=history):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception("Error during streaming")
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback")
async def feedback(body: FeedbackRequest, request: Request) -> JSONResponse:
    """Record user feedback on an answer."""
    pool = request.app.state.pool
    updated = await update_feedback(pool, body.query_id, body.feedback, body.note)
    if not updated:
        return JSONResponse({"error": "Query not found"}, status_code=404)
    return JSONResponse({"status": "ok"})
