"""Pydantic models for database rows and pipeline data structures."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

# --- Database row models ---


class DocumentSource(BaseModel):
    """A crawled document source (maps to document_sources table)."""

    id: UUID
    url: str
    source_type: str
    title: str | None = None
    last_crawled_at: datetime | None = None
    content_hash: str | None = None
    identifier: str | None = None
    issue_date: date | None = None
    superseded_by: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class DocumentChunk(BaseModel):
    """A chunk of content with embedding (maps to document_chunks table)."""

    id: UUID
    source_id: UUID
    chunk_index: int
    content: str
    section_id: str | None = None
    section_title: str | None = None
    tax_year: str | None = None
    parent_chunk_id: UUID | None = None
    embedding: list[float] | None = None
    created_at: datetime


# --- Pipeline data structures ---


class CrawlResult(BaseModel):
    """Result of crawling a single URL."""

    url: str
    html: str
    content_hash: str
    status_code: int
    crawled_at: datetime = Field(default_factory=datetime.now)
    raw_bytes: bytes | None = None
    content_type: str = "html"


class ParsedSection(BaseModel):
    """A section extracted from an HTML page by the parser."""

    heading: str
    content: str
    heading_level: int = 2  # h2 or h3
    parent_heading: str | None = None  # h2 heading if this is an h3 section


class ParsedDocument(BaseModel):
    """Full result of parsing an HTML page."""

    title: str
    url: str
    sections: list[ParsedSection]
    pdf_url: str | None = None


class ChunkData(BaseModel):
    """A chunk ready for embedding and storage."""

    content: str
    chunk_index: int
    section_title: str | None = None
    tax_year: str | None = None


# --- Query response models ---


class RetrievalResult(BaseModel):
    """A single result from hybrid retrieval."""

    content: str
    section_title: str | None = None
    source_url: str
    source_title: str | None = None
    source_type: str | None = None
    tax_year: str | None = None
    score: float


class SourceReference(BaseModel):
    """A cited source in an answer."""

    url: str
    title: str | None = None
    section_title: str | None = None


class ToolUsed(BaseModel):
    """A tool that was invoked during answer generation."""

    name: str
    label: str


class AskResponse(BaseModel):
    """Response from the /ask endpoint."""

    answer: str
    sources: list[SourceReference]
    model: str
    tools_used: list[ToolUsed] = []
    query_id: UUID | None = None
