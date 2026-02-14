# NZ Tax RAG

Answers personal income tax questions for New Zealand residents using IRD official guidance and legislation. Hybrid retrieval (semantic + keyword search with RRF) over a PostgreSQL/pgvector corpus, with Gemini LLM via LiteLLM.

## Quick Start

```bash
cp .env.example .env
# Edit .env — set DB_PASSWORD, GEMINI_API_KEY, LLM_DEFAULT_MODEL, DATABASE_URL

docker compose up
```

Verify: `curl http://localhost:8008/health`

## Development

All commands run inside containers:

```bash
docker compose run --rm dev pytest                                # Run tests
docker compose run --rm dev pytest tests/test_chunker.py -k "name" # Single test
docker compose run --rm dev ruff check src/                       # Lint
docker compose run --rm dev ruff format src/                      # Format
docker compose run --rm dev mypy src/                             # Type check
docker compose run --rm dev python scripts/migrate.py             # Apply migrations
docker compose run --rm dev python scripts/ingest.py              # Run full ingestion
docker compose run --rm dev python scripts/ingest.py --url "..."  # Ingest single URL
```

## Architecture

**API (FastAPI)** → **Orchestrator** → **LLM Gateway (LiteLLM)** + **RAG Retriever (hybrid search)**

Offline **Ingestion Pipeline**: Crawler → HTML/PDF Parser → Tax-aware Chunker → Embedder → pgvector

- PostgreSQL 17 + pgvector for storage and vector search
- Gemini embeddings (768d) with asymmetric retrieval
- Gemini 2.5 Flash as primary LLM, with fallback chain

See [docs/design.md](docs/design.md) for full architecture, schema, chunking strategy, and retrieval design. Data sources documented in [docs/data-sources.md](docs/data-sources.md).

## Status

Iteration 1 complete — ingestion pipeline operational. 41 IRD sources ingested, 141 chunks with embeddings.
