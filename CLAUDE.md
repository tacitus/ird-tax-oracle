# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NZ Personal Income Tax RAG system — answers personal income tax questions for New Zealand residents using IRD official guidance and legislation. Uses hybrid retrieval (semantic + keyword search with RRF) over a PostgreSQL/pgvector corpus, with Gemini LLM via LiteLLM.

**Status:** Iteration 2 complete — adds LLM tool calling, tax calculators, SSE streaming, query logging with feedback, and evaluation framework on top of the Iteration 1 RAG foundation.

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
docker compose run --rm dev python scripts/eval.py               # Run evaluation suite
docker compose run --rm dev python scripts/seed_tax_rules.py     # Seed tax bracket data
```

## Architecture

Three-layer system: **API (FastAPI)** → **Orchestrator** → **LLM Gateway (LiteLLM)** + **RAG Retriever (hybrid search)**

Offline **Ingestion Pipeline**: Crawler (httpx) → Parser (BS4/pymupdf4llm) → Tax-aware Chunker → Embedder → pgvector

### Key modules in `src/`

- `api/` — FastAPI app factory (`create_app()` in `app.py`), routes (`/`, `/ask`, `/ask/stream`, `/feedback`, `/health` in `routes.py`), Basic Auth middleware, DI via `app.state`
- `llm/` — LiteLLM wrapper with streaming (`gateway.py`), system prompts (`prompts.py`), tool definitions (`tools.py`), LLM response postprocessor (`postprocess.py`)
- `rag/` — Hybrid retriever with source_type/tax_year filtering (semantic + keyword + RRF in `retriever.py`), async embedding service (`embedder.py`)
- `ingestion/` — HTTP crawler (`crawler.py`), parsers (`parsers/html_parser.py`, `parsers/pdf_parser.py`, `parsers/taxtechnical_parser.py`), tax-aware chunker (`chunker.py`), pipeline orchestrator (`pipeline.py`)
- `orchestrator.py` — Query→retrieve→tool loop→LLM→answer flow with SSE streaming (`ask_stream`)
- `calculators/` — Deterministic NZ tax calculators: income tax, PAYE, student loan, ACC levy (`tax_data.py` has bracket data)
- `db/` — asyncpg connection pool (`session.py`), Pydantic models (`models.py`), query logging with feedback (`query_log.py`)

### Database

- PostgreSQL 17 + pgvector (`pgvector/pgvector:pg17` image)
- Schema managed by **yoyo-migrations** in `migrations/`
- Core tables: `document_sources` (with `identifier`, `issue_date`, `superseded_by` metadata), `document_chunks` (with `vector(768)` + `tsvector`)
- Source types: `ird_guidance`, `legislation`, `tib`, `guide_pdf`, `interpretation_statement`, `qwba`, `fact_sheet`, `operational_statement`
- HNSW index on embeddings (not IVFFlat — works on empty tables)
- `query_log` table with feedback columns (`positive`/`negative` + note) and `tool_calls` JSONB
- `tax_years` and `tax_brackets` tables for future dynamic rate lookups

### Embeddings

- Model: `gemini-embedding-001` at 768 dimensions
- Uses `google-genai` SDK directly (NOT LiteLLM) to preserve `task_type` parameter for asymmetric retrieval (`RETRIEVAL_DOCUMENT` vs `RETRIEVAL_QUERY`)
- Async API (`client.aio.models.embed_content`) with batch support (`embed_documents`)
- Same `GEMINI_API_KEY` as LLM

### LLM

- Primary: `gemini/gemini-2.5-flash` via LiteLLM
- Temperature 0.1 for factual tax answers
- Tool definitions in OpenAI format (LiteLLM translates per-provider)
- Multi-round tool calling: calculators (income_tax, paye, student_loan, acc) + document search
- Streaming via LiteLLM's async streaming API

### Auth

- HTTP Basic Auth middleware on all routes (`BasicAuthMiddleware` in `app.py`)
- Credentials from `AUTH_USERNAME` / `AUTH_PASSWORD` env vars
- Timing-safe comparison via `secrets.compare_digest`

### Frontend

- Static HTML/CSS/JS served from `static/` directory
- `GET /` serves `static/index.html`, static assets mounted at `/static`
- SSE streaming with real-time answer rendering (marked + DOMPurify)
- Tool-use indicator pills, thumbs up/down feedback, copy-link sharing

## Code Conventions

- Python 3.12+, strict mypy, ruff with rules E/F/I/UP/B/SIM, 100-char line length
- Async throughout: asyncpg for DB, pytest-asyncio (auto mode) for tests
- Use proper logging (no print statements)
- Use `.env` file for env vars (not inline in docker compose)
- Pydantic models for all data structures
- YAML configs in `config/` — `embeddings.yaml`, `sources.yaml`, `sources_taxtechnical.yaml`; Pydantic Settings in `config/settings.py`

## Environment

Copy `.env.example` to `.env` and set: `DB_PASSWORD`, `GEMINI_API_KEY`, `LLM_DEFAULT_MODEL`, `DATABASE_URL`, `AUTH_USERNAME`, `AUTH_PASSWORD`

## Design Reference

Full architecture, schema DDL, chunking strategy, retrieval design, and phased build plan in `docs/design.md`.
