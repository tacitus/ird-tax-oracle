# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NZ Personal Income Tax RAG system — answers personal income tax questions for New Zealand residents using IRD official guidance and legislation. Uses hybrid retrieval (semantic + keyword search with RRF) over a PostgreSQL/pgvector corpus, with Gemini LLM via LiteLLM.

**Status:** Iteration 1 complete — ingestion pipeline operational (crawler, HTML parser, tax-aware chunker, Gemini embedder, pgvector storage). 41 IRD sources ingested, 141 chunks with embeddings.

## Commands

```bash
# Docker (primary development method)
docker compose up                            # Start db, migrate, api
docker compose --profile local-llm up        # Include local Ollama
docker compose logs -f api                   # Tail API logs

# Development (docker-first — all commands via containers)
docker compose run --rm dev pytest                                # Run all tests
docker compose run --rm dev pytest tests/test_chunker.py -k "test_name"  # Single test
docker compose run --rm dev ruff check src/                       # Lint
docker compose run --rm dev ruff format src/                      # Format
docker compose run --rm dev mypy src/                             # Type check (strict mode)
docker compose run --rm dev python scripts/migrate.py             # Apply migrations
docker compose run --rm dev python scripts/ingest.py              # Run full ingestion
docker compose run --rm dev python scripts/ingest.py --url "..."  # Ingest single URL
```

## Architecture

Three-layer system: **API (FastAPI)** → **Orchestrator** → **LLM Gateway (LiteLLM)** + **RAG Retriever (hybrid search)**

Offline **Ingestion Pipeline**: Crawler (httpx) → Parser (BS4/PyMuPDF) → Tax-aware Chunker → Embedder → pgvector

### Key modules in `src/`

- `api/` — FastAPI app factory (`create_app()`), routes (`/ask`, `/health`, `/admin/*`), dependency injection
- `llm/` — LiteLLM wrapper (`gateway.py`), system prompts, tool definitions in OpenAI format
- `rag/` — Hybrid retriever (semantic + keyword + RRF), embedding service, optional reranker
- `ingestion/` — HTTP crawler, HTML/PDF parsers, tax-aware chunker, pipeline orchestrator
- `orchestrator/` — Query→retrieve→LLM→answer flow
- `db/` — asyncpg connection pool, Pydantic models
- `calculators/` — Deterministic tax calculations (Phase 2, tool-callable by LLM)

### Database

- PostgreSQL 17 + pgvector (`pgvector/pgvector:pg17` image)
- Schema managed by **yoyo-migrations** in `migrations/`
- Core tables: `document_sources`, `document_chunks` (with `vector(768)` + `tsvector`), `tax_brackets`, `query_log`
- HNSW index on embeddings (not IVFFlat — works on empty tables)

### Embeddings

- Model: `gemini-embedding-001` at 768 dimensions
- Uses `google-genai` SDK directly (NOT LiteLLM) to preserve `task_type` parameter for asymmetric retrieval (`RETRIEVAL_DOCUMENT` vs `RETRIEVAL_QUERY`)
- Same `GEMINI_API_KEY` as LLM

### LLM

- Primary: `gemini/gemini-2.5-flash` via LiteLLM
- Fallback chain: Gemini 2.5 Pro → Ollama llama3.1
- Temperature 0.1 for factual tax answers
- Tool definitions in OpenAI format (LiteLLM translates per-provider)

## Code Conventions

- Python 3.12+, strict mypy, ruff with rules E/F/I/UP/B/SIM, 100-char line length
- Async throughout: asyncpg for DB, pytest-asyncio (auto mode) for tests
- Use proper logging (no print statements)
- Use `.env` file for env vars (not inline in docker compose)
- Pydantic models for all data structures
- YAML configs in `config/` for LLM, embeddings, and ingestion sources
- FastAPI dependency injection via `dependencies.py`

## Environment

Copy `.env.example` to `.env` and set: `DB_PASSWORD`, `GEMINI_API_KEY`, `LLM_DEFAULT_MODEL`, `DATABASE_URL`

## Design Reference

Full architecture, schema DDL, chunking strategy, retrieval design, and phased build plan in `docs/design.md`.
