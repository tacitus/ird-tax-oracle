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

from src.db.models import AskResponse
from src.db.query_log import update_feedback

logger = logging.getLogger(__name__)

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class AskRequest(BaseModel):
    """Request body for the /ask endpoint."""

    question: str


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
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """Answer a tax question using RAG-grounded LLM."""
    orchestrator = request.app.state.orchestrator
    return await orchestrator.ask(body.question)


@router.post("/ask/stream")
async def ask_stream(body: AskRequest, request: Request) -> StreamingResponse:
    """Stream a tax question answer via Server-Sent Events."""
    orchestrator = request.app.state.orchestrator

    async def event_generator():  # type: ignore[no-untyped-def]
        try:
            async for event in orchestrator.ask_stream(body.question):
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
