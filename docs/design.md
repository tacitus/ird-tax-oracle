# NZ Personal Income Tax — RAG System Design

> **Last updated:** 2026-02-17
>
> **Revision history:**
> | Date | Change |
> |------|--------|
> | 2026-02-17 | Updated docs to match actual implementation: project structure, migrations, docker compose, LLM gateway, embedder, auth, frontend, config files, test files |
> | 2026-02-14 | Added yoyo-migrations for schema management; switched vector index from IVFFlat to HNSW; moved docs to `docs/`; fixed stale references (Claude→Gemini fallback chain, Scrapy→httpx, feedback CHECK constraint); reorganised open questions |
> | 2026-02-13 | Pivoted to Gemini (LLM + embeddings); adopted `google-genai` SDK for embeddings (LiteLLM `task_type` bug); single API key stack |
> | 2026-02-13 | Initial design — architecture, RAG pipeline, database schema, project structure |

## 1. Scope

Personal income tax for New Zealand residents, covering:

- Tax brackets and marginal rates (by tax year)
- PAYE (Pay As You Earn) withholding
- ACC earner's levy
- Student loan repayments
- Working for Families tax credits
- Independent earner tax credit (IETC)
- KiwiSaver contributions and employer contributions
- Tax codes (M, ME, SL, etc.)
- PIE (Portfolio Investment Entity) tax rates
- Donation tax credits
- Resident withholding tax (RWT) on interest/dividends
- Individual tax returns (IR3) guidance

Out of scope (for now): GST, business/company tax, trust tax, international tax (beyond basic residency), provisional tax for businesses.

---

## 2. Document Sources

### Tier 1 — Primary (ingest first)
| Source | URL Pattern | Content Type | Priority |
|--------|------------|--------------|----------|
| IRD Income Tax Guidance | `ird.govt.nz/income-tax/income-tax-for-individuals/*` | HTML | **Highest** |
| IRD Tax Rates & Codes | `ird.govt.nz/income-tax/income-tax-for-individuals/tax-codes-and-tax-rates-for-individuals/*` | HTML | **Highest** |
| IRD Forms & Guides (IR3G, IR3, etc.) | `ird.govt.nz/-/media/project/ir/home/documents/forms-and-guides/*` | PDF | **High** |
| Tax Technical — Interpretation Statements | `taxtechnical.ird.govt.nz/interpretation-statements/*` | HTML | **High** |
| Tax Information Bulletins (TIBs) | `taxtechnical.ird.govt.nz/tib/*` | HTML/PDF | **High** |

### Tier 2 — Secondary (ingest after Tier 1 is working)
| Source | URL Pattern | Content Type | Priority |
|--------|------------|--------------|----------|
| Income Tax Act 2007 (selected parts) | `legislation.govt.nz/act/public/2007/0097/latest/*` | HTML | Medium |
| Tax Administration Act 1994 (selected parts) | `legislation.govt.nz/act/public/1994/0166/latest/*` | HTML | Medium |
| Tax Policy — Discussion docs | `taxpolicy.ird.govt.nz/*` | HTML/PDF | Low |

### Key Observation
The Income Tax Act 2007 is enormous (900+ sections across Parts A–Z). For personal income tax we primarily need:
- **Part B** — Core obligations (income tax liability)
- **Part C** — Income (especially subparts CA, CB, CE for employment income)
- **Part D** — Deductions
- **Part L** — Tax credits (subparts LA–LJ)
- **Part M** — Tax codes and PAYE
- **Part R** — General collection rules
- **Schedule 1** — Tax rates

We should NOT try to ingest the entire Act. Selective ingestion of relevant Parts keeps the corpus manageable and reduces noise in retrieval.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      API Layer                          │
│                     (FastAPI)                           │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Router   │→│ Orchestrator │→│  Tool Dispatcher   │  │
│  └──────────┘  └──────┬───────┘  └────────┬──────────┘  │
│                       │                    │             │
│              ┌────────▼────────┐  ┌───────▼──────────┐  │
│              │   LLM Gateway   │  │  RAG Retriever   │  │
│              │   (LiteLLM)     │  │  (Hybrid Search) │  │
│              └────────┬────────┘  └───────┬──────────┘  │
│                       │                    │             │
└───────────────────────┼────────────────────┼────────────┘
                        │                    │
              ┌─────────▼─────────┐  ┌──────▼──────────┐
              │  Any LLM Provider │  │   PostgreSQL     │
              │  (Gemini, Ollama, │  │   + pgvector     │
              │   Claude, GPT…)   │  │                  │
              └───────────────────┘  └─────────────────┘

┌─────────────────────────────────────────────────────────┐
│              Ingestion Pipeline (offline)                │
│                                                         │
│  Crawler → Parser → Chunker → Embedder → pgvector      │
└─────────────────────────────────────────────────────────┘
```

---

## 4. LLM Abstraction Layer

### Why LiteLLM

LiteLLM provides a unified OpenAI-compatible interface across 100+ providers. Critically for us:
- **Tool/function calling** is translated automatically between providers
- **Fallback chains** — if Gemini Flash is unavailable, fall to Gemini Pro, then to local Ollama
- **Cost tracking** built in
- **Streaming** support across providers

### Configuration

The default model is set via `LLM_DEFAULT_MODEL` env var (default: `gemini/gemini-2.5-flash`). No YAML config file — model selection is a single env var read by `config/settings.py`.

### LLM Gateway Interface

```python
# src/llm/gateway.py
class CompletionResult(BaseModel):
    """Result from an LLM completion, carrying both content and tool calls."""
    content: str | None = None
    tool_calls: list[Any] | None = None
    raw_message: Any = None
    model: str = ""

class LLMGateway:
    """Async LLM completion via LiteLLM."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_default_model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResult:
        """Send messages to the LLM and return the response."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        if tools:
            kwargs["tools"] = tools
        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return CompletionResult(
            content=message.content,
            tool_calls=message.tool_calls,
            raw_message=message,
            model=response.model or self.model,
        )
```

### Design Decision: Tool Definitions in OpenAI Format

Since LiteLLM translates OpenAI-format tools to each provider's native format, we define all tools once in OpenAI format. This is the contract — change the model, tools stay the same.

---

## 5. RAG Pipeline — Detailed Design

### 5.1 Document Ingestion

```
                ┌──────────┐
                │ Scheduler│ (or manual trigger)
                └────┬─────┘
                     │
            ┌────────▼────────┐
            │   IRD Crawler   │
            │  (httpx + rate  │
            │     limit)      │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  Content Parser │
            │  HTML: BS4      │
            │  PDF: pymupdf4llm│
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  Tax-Aware      │
            │  Chunker        │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  Embedding      │
            │  Service        │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  PostgreSQL     │
            │  (pgvector)     │
            └─────────────────┘
```

### 5.2 Tax-Aware Chunking Strategy

Standard chunking (fixed token windows) will break tax content badly. Tax documents have:
- Cross-references ("see section CE 1(1)(a)")
- Nested definitions that span paragraphs
- Numbered lists where each item depends on the header
- Examples that only make sense with the preceding rule

**Chunking Rules:**

1. **IRD Guidance Pages (HTML):** Chunk by `<h2>` or `<h3>` section boundaries. Each chunk includes the page title + breadcrumb as metadata prefix, so the chunk is self-contextualising.

2. **Legislation (HTML):** Chunk by section (e.g., "CE 1 Amounts derived in connection with employment"). Never split a section. If a section exceeds ~1500 tokens, split at subsection level but prepend the section header to each sub-chunk.

3. **PDF Guides (IR3G, etc.):** Parse with pymupdf, chunk by "Question" boundaries (IR3 guide is structured as Q&A). Each chunk gets the question number + title.

4. **Tax Information Bulletins:** Chunk by article/determination boundary. Each TIB contains multiple items; each item is a chunk.

**Overlap:** 2-sentence overlap between consecutive chunks from the same document, to preserve cross-references.

**Metadata per chunk:**

```python
@dataclass
class ChunkMetadata:
    source_url: str                 # Where it came from
    source_type: str                # "ird_guidance" | "legislation" | "tib" | "guide"
    document_title: str             # Human-readable title
    section_id: Optional[str]       # e.g., "CE 1" for legislation
    section_title: Optional[str]    # e.g., "Amounts derived in connection with employment"
    tax_year_applicable: Optional[str]  # e.g., "2025-26" if specified
    last_crawled: datetime
    parent_chunk_id: Optional[str]  # For hierarchical navigation
```

### 5.3 Embedding Model

**Recommendation: `gemini-embedding-001` (Google AI Studio)**

Rationale:
- #1 on MTEB multilingual leaderboard — state-of-the-art quality
- Default 3072 dimensions, supports Matryoshka truncation to 1536 or 768
- Uses the same `GEMINI_API_KEY` — single API key for the entire stack
- Free tier available for development; paid tier is cost-effective
- 2048 token input limit (sufficient for our chunk sizes)
- Supports `task_type` parameter: `RETRIEVAL_DOCUMENT` for indexing chunks, 
  `RETRIEVAL_QUERY` for embedding search queries — this asymmetric embedding 
  improves retrieval quality
- 100+ languages including Māori (relevant for NZ legislation)

**We'll use 768 dimensions.** Our corpus is ~5K chunks — 768 is more than 
sufficient and keeps pgvector indexes lean. Can bump to 1536 or 3072 later 
if retrieval quality needs improvement.

**Important: Use `google-genai` SDK directly, NOT LiteLLM for embeddings.**
There is a known LiteLLM issue where the `task_type` parameter is ignored 
when routing Gemini embedding calls through the proxy. Since `task_type` is 
important for RAG quality (asymmetric document/query embeddings), we use 
Google's SDK directly for the embedding service. LiteLLM is still used for 
all LLM completion/tool-calling.

```yaml
# config/embeddings.yaml
embeddings:
  provider: "gemini"                  # "gemini" | "ollama" (for fully local)
  model: "gemini-embedding-001"
  dimensions: 768                     # MRL truncation: 768, 1536, or 3072
  task_type_document: "RETRIEVAL_DOCUMENT"
  task_type_query: "RETRIEVAL_QUERY"
  # API key: uses GEMINI_API_KEY from environment (same as LLM)
  
  # For fully local alternative (no API dependency):
  # provider: "ollama"
  # model: "nomic-embed-text"
  # dimensions: 768
  # base_url: "http://ollama:11434"
```

```python
# src/rag/embedder.py — Gemini embedding using google-genai SDK (async)
from google import genai
from google.genai import types

class GeminiEmbedder:
    def __init__(self, model: str | None = None, dimensions: int | None = None) -> None:
        config = load_yaml_config("embeddings.yaml")["embeddings"]
        self.model = model or config["model"]
        self.dimensions = dimensions or config["dimensions"]
        self.client = genai.Client()  # reads GEMINI_API_KEY from env

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks for storage."""
        result = await self.client.aio.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.dimensions,
            ),
        )
        return [e.values for e in result.embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query — uses RETRIEVAL_QUERY task type for asymmetric retrieval."""
        result = await self.client.aio.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.dimensions,
            ),
        )
        return result.embeddings[0].values
```

### 5.4 Hybrid Retrieval

Pure vector search misses exact identifiers. "Section CE 1" or "IR3" are semantically opaque but critically important for tax. We combine:

1. **Semantic search** — pgvector cosine similarity on embeddings
2. **Keyword search** — PostgreSQL `tsvector` full-text search
3. **Reciprocal Rank Fusion (RRF)** to merge both result sets

```python
# Pseudocode for hybrid retrieval
async def retrieve(query: str, top_k: int = 10) -> list[Chunk]:
    # 1. Embed the query (uses RETRIEVAL_QUERY task_type — asymmetric)
    query_embedding = await embedder.embed_query(query)
    
    # 2. Semantic search (pgvector)
    semantic_results = await db.execute("""
        SELECT id, content, metadata,
               1 - (embedding <=> $1::vector) AS similarity
        FROM document_chunks
        ORDER BY embedding <=> $1::vector
        LIMIT $2
    """, query_embedding, top_k * 2)
    
    # 3. Keyword search (tsvector)
    keyword_results = await db.execute("""
        SELECT id, content, metadata,
               ts_rank(search_vector, plainto_tsquery('english', $1)) AS rank
        FROM document_chunks
        WHERE search_vector @@ plainto_tsquery('english', $1)
        ORDER BY rank DESC
        LIMIT $2
    """, query, top_k * 2)
    
    # 4. Reciprocal Rank Fusion
    return reciprocal_rank_fusion(semantic_results, keyword_results, k=top_k)
```

### 5.5 Optional Reranker

A cross-encoder reranker (e.g., `BAAI/bge-reranker-v2-m3` or Cohere Rerank) applied to the top-k fusion results can significantly improve precision. This is a phase 2 addition — get the basic hybrid search working first.

---

## 6. Database Schema

**Managed by [yoyo-migrations](https://ollycope.com/software/yoyo/latest/)** — lightweight, Python-native migration tool. Each migration is a Python file in `migrations/` with explicit `step()` up/down pairs and `__depends__` for ordering. Migrations run automatically on container startup via `scripts/migrate.py`.

Current migrations: `0001_extensions`, `0002_document_sources`, `0003_document_chunks`, `0004_taxtechnical_fields`. The `tax_years`, `tax_brackets`, and `query_log` tables shown below are planned for Phase 2.

> **Why not raw SQL in `docker-entrypoint-initdb.d`?** That only runs on a fresh database. Yoyo tracks applied migrations in `_yoyo_migration` and applies only what's new, so schema changes are safe on existing data.

> **Why HNSW, not IVFFlat?** IVFFlat requires training data (the `lists` parameter sizes clusters from existing rows). On an empty table it either fails or produces near-random results. HNSW works immediately with zero rows and has better recall at our corpus size (~5K chunks). The tradeoff is slightly higher memory, which is irrelevant at this scale.

```sql
-- Migrations (actual: 0001_extensions, 0002_document_sources,
-- 0003_document_chunks, 0004_taxtechnical_fields)
-- tax_years, tax_brackets, query_log tables are planned for Phase 2.
--
-- Migration 0001: Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for fuzzy text matching

-- ============================================================
-- DOCUMENT SOURCES — track what we've crawled
-- ============================================================
CREATE TABLE document_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT UNIQUE NOT NULL,
    source_type     TEXT NOT NULL CHECK (source_type IN (
                        'ird_guidance', 'legislation', 'tib',
                        'guide_pdf', 'interpretation_statement',
                        'qwba', 'fact_sheet', 'operational_statement'
                    )),
    identifier      TEXT,                  -- e.g. "IS 24/07" (added in 0004)
    issue_date      DATE,                  -- publication date (added in 0004)
    superseded_by   TEXT,                  -- identifier of replacement (added in 0004)
    title           TEXT,
    last_crawled_at TIMESTAMPTZ,
    content_hash    TEXT,              -- SHA256 of raw content, for change detection
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DOCUMENT CHUNKS — the core RAG table
-- ============================================================
CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,           -- position within document
    content         TEXT NOT NULL,
    
    -- Metadata (denormalised for retrieval speed)
    section_id      TEXT,                       -- e.g., "CE 1" for legislation
    section_title   TEXT,
    tax_year        TEXT,                       -- e.g., "2025-26" if specified
    parent_chunk_id UUID REFERENCES document_chunks(id),
    
    -- Search vectors
    embedding       vector(768),                -- pgvector (Gemini MRL @ 768 dims)
    search_vector   tsvector GENERATED ALWAYS AS (
                        to_tsvector('english', content)
                    ) STORED,
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(source_id, chunk_index)
);

-- Indexes for search performance
CREATE INDEX idx_chunks_embedding ON document_chunks 
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_chunks_search ON document_chunks 
    USING gin (search_vector);
CREATE INDEX idx_chunks_source ON document_chunks(source_id);
CREATE INDEX idx_chunks_section ON document_chunks(section_id) 
    WHERE section_id IS NOT NULL;
CREATE INDEX idx_chunks_tax_year ON document_chunks(tax_year) 
    WHERE tax_year IS NOT NULL;

-- ============================================================
-- TAX RULES — structured data for calculations (phase 2)
-- ============================================================
CREATE TABLE tax_years (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tax_year        TEXT UNIQUE NOT NULL,        -- e.g., "2025-26"
    start_date      DATE NOT NULL,               -- e.g., 2025-04-01
    end_date        DATE NOT NULL,               -- e.g., 2026-03-31
    is_current      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tax_brackets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tax_year_id     UUID NOT NULL REFERENCES tax_years(id),
    lower_bound     NUMERIC NOT NULL,
    upper_bound     NUMERIC,                     -- NULL = no upper bound
    rate            NUMERIC(5,4) NOT NULL,       -- e.g., 0.1050 for 10.5%
    bracket_order   INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tax_year_id, bracket_order)
);

-- ============================================================
-- QUERY LOG — for evaluation and improvement
-- ============================================================
CREATE TABLE query_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    model_used      TEXT NOT NULL,
    chunks_used     UUID[] DEFAULT '{}',         -- references to document_chunks
    tool_calls      JSONB DEFAULT '[]',
    latency_ms      INTEGER,
    feedback        TEXT CHECK (feedback IN ('positive', 'negative')),
    feedback_note   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. Project Structure

```
nz-tax-rag/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                  # uv
├── yoyo.ini                        # yoyo-migrations config (sources dir only, no creds)
├── .env.example                    # Template for environment variables
│
├── static/                         # Frontend (served by FastAPI)
│   ├── index.html
│   ├── favicon.svg
│   ├── css/
│   └── js/
│
├── docs/                           # Design documentation
│   ├── design.md                   # System design document (this file)
│   ├── architecture.mermaid        # Architecture diagram (Mermaid)
│   ├── prompt_design.md            # LLM prompt engineering notes
│   ├── data-sources.md             # Source documentation
│   └── taxtechnical.ird.nz.md     # Tax Technical site analysis
│
├── migrations/                     # yoyo-migrations (Python step files)
│   ├── 0001_extensions.py
│   ├── 0002_document_sources.py
│   ├── 0003_document_chunks.py
│   └── 0004_taxtechnical_fields.py # Source type expansion + metadata columns
│
├── config/
│   ├── embeddings.yaml             # Embedding model config
│   ├── sources.yaml                # IRD guidance sources to crawl
│   ├── sources_taxtechnical.yaml   # Tax Technical sources to crawl
│   └── settings.py                 # Pydantic Settings (env vars)
│
├── src/
│   ├── __init__.py
│   │
│   ├── api/                        # FastAPI application
│   │   ├── __init__.py
│   │   ├── app.py                  # App factory, lifespan, BasicAuth middleware
│   │   └── routes.py               # Routes: /, /ask, /health, /favicon.ico
│   │
│   ├── llm/                        # LLM abstraction
│   │   ├── __init__.py
│   │   ├── gateway.py              # LiteLLM wrapper (CompletionResult)
│   │   ├── prompts.py              # System prompts
│   │   ├── tools.py                # Tool definitions (OpenAI format)
│   │   └── postprocess.py          # LLM response postprocessor
│   │
│   ├── rag/                        # RAG pipeline
│   │   ├── __init__.py
│   │   ├── retriever.py            # Hybrid search (semantic + keyword + RRF)
│   │   └── embedder.py             # Async Gemini embedding (batch support)
│   │
│   ├── ingestion/                  # Document ingestion pipeline
│   │   ├── __init__.py
│   │   ├── crawler.py              # HTTP crawler (httpx + rate limiting)
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   ├── html_parser.py      # BeautifulSoup — IRD guidance pages
│   │   │   ├── pdf_parser.py       # pymupdf4llm — PDF guides
│   │   │   └── taxtechnical_parser.py  # Tax Technical site parser
│   │   ├── chunker.py              # Tax-aware chunking
│   │   └── pipeline.py             # Orchestrates crawl → parse → chunk → embed → store
│   │
│   ├── orchestrator.py             # Query→retrieve→LLM→answer flow (flat module)
│   │
│   └── db/                         # Database layer
│       ├── __init__.py
│       ├── session.py              # asyncpg connection pool
│       └── models.py               # Pydantic models for DB rows
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/                   # Test fixture data
│   ├── test_api.py
│   ├── test_chunker.py
│   ├── test_parser.py
│   ├── test_pdf_parser.py
│   ├── test_postprocess.py
│   ├── test_prompts.py
│   ├── test_retriever.py
│   ├── test_taxtechnical_parser.py
│   └── eval/                       # Evaluation suite (planned)
│
└── scripts/
    ├── migrate.py                  # CLI: apply/rollback/list migrations
    └── ingest.py                   # CLI: run ingestion pipeline
```

**Planned (Phase 2):**
- `src/calculators/` — Deterministic tax calculations (income_tax, paye, acc, student_loan), tool-callable by LLM
- `src/rag/reranker.py` — Optional cross-encoder reranker
- `scripts/seed_tax_rules.py` — Populate tax brackets
- `scripts/eval.py` — Run evaluation suite

---

## 8. Docker Composition

```yaml
# docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: nz_tax
      POSTGRES_USER: taxapp
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5434:5432"              # Host port 5434 (5432 often taken by OrbStack)
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taxapp -d nz_tax"]
      interval: 5s
      retries: 5

  migrate:
    build: .
    command: python scripts/migrate.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql://taxapp:${DB_PASSWORD}@db:5432/nz_tax
    depends_on:
      db:
        condition: service_healthy

  api:
    build: .
    command: uvicorn src.api.app:create_app --host 0.0.0.0 --port 8000 --factory
    ports:
      - "8008:8000"              # Host port 8008
    env_file: .env               # All env vars (GEMINI_API_KEY, AUTH_*, etc.)
    environment:
      DATABASE_URL: postgresql+asyncpg://taxapp:${DB_PASSWORD}@db:5432/nz_tax
    depends_on:
      migrate:
        condition: service_completed_successfully
    volumes:
      - ./config:/app/config
      - ./static:/app/static     # Frontend assets

  dev:                           # Dev/test runner
    build: .
    command: bash
    env_file: .env
    environment:
      DATABASE_URL: postgresql://taxapp:${DB_PASSWORD}@db:5432/nz_tax
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app

  # Optional: local LLM via Ollama
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    profiles:
      - local-llm   # only starts with: docker compose --profile local-llm up

volumes:
  pgdata:
  ollama_data:
```

---

## 9. Build Sequence

### Phase 1: RAG Foundation (START HERE)
1. **Database** — Stand up Postgres + pgvector, run migrations
2. **Ingestion pipeline** — Crawler + parser + chunker + embedder for Tier 1 IRD guidance pages
3. **Retriever** — Hybrid search (semantic + keyword)
4. **Orchestrator** — Basic query → retrieve → LLM → answer flow
5. **API** — `/ask` endpoint
6. **Evaluation** — 20+ test scenarios with known answers

### Phase 2: Calculations + Depth
7. **Tax calculators** — Pure Python, deterministic, tool-callable
8. **Ingest Tier 2** — Legislation, TIBs, interpretation statements
9. **Reranker** — Cross-encoder for improved precision
10. **Tax year awareness** — Route queries to correct year's data

### Phase 3: Production Hardening
11. **Caching** — Cache frequent queries + embeddings
12. **Monitoring** — Latency, cost, error rates
13. **Citation quality** — Ensure every answer links to source
14. **Feedback loop** — Use query_log feedback to identify gaps

---

## 10. Key Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| IRD changes page structure | Ingestion breaks | Content hash change detection + alerts; modular parsers |
| LLM hallucination on tax figures | Wrong tax advice | Calculators are deterministic (not LLM); RAG grounds answers in source text |
| Embedding model changes | All vectors invalidated | Re-embed pipeline; version tracking in metadata |
| pgvector performance at scale | Slow retrieval | At NZ tax corpus size (~5K chunks), this is a non-risk. Already using HNSW index |
| Cross-references in legislation | Chunks lose context | Parent chunk linking; section header prepending; overlap |
| Tax year ambiguity in queries | Wrong year's rules applied | Default to current tax year; LLM trained to ask when ambiguous |

---

## 11. Open Questions

### Resolved
1. **Rate limiting on IRD crawling** — Yes. 1 req/sec max, respect robots.txt.
2. **Embedding model** — Gemini `gemini-embedding-001` at 768 dims. Same API key as LLM. Re-embedding ~5K chunks takes minutes if switching to local — acceptable risk.
3. **Schema migrations** — yoyo-migrations. Python-native, lightweight, explicit up/down steps.
4. **Vector index type** — HNSW (not IVFFlat). Works on empty tables, better recall at our scale.
5. **Authentication** — HTTP Basic Auth middleware on all routes. Credentials via `AUTH_USERNAME` / `AUTH_PASSWORD` env vars. Timing-safe comparison with `secrets.compare_digest`.

### Still Open
6. **How often to re-crawl?** — IRD guidance changes infrequently. Monthly seems sufficient, with a manual trigger for budget announcements.
7. **Evaluation ground truth** — Who validates the test scenarios? Ideally someone with NZ tax knowledge reviews them.
