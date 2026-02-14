"""API routes for the NZ Tax RAG system."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.db.models import AskResponse

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class AskRequest(BaseModel):
    """Request body for the /ask endpoint."""

    question: str


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Serve the frontend."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """Answer a tax question using RAG-grounded LLM."""
    orchestrator = request.app.state.orchestrator
    return await orchestrator.ask(body.question)
