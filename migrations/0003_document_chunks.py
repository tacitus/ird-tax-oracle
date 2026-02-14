"""Create document_chunks table with vector and full-text search indexes."""

from yoyo import step

__depends__ = {"0002_document_sources"}

steps = [
    step(
        """
        CREATE TABLE document_chunks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id       UUID NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
            chunk_index     INTEGER NOT NULL,
            content         TEXT NOT NULL,

            -- Metadata (denormalised for retrieval speed)
            section_id      TEXT,
            section_title   TEXT,
            tax_year        TEXT,
            parent_chunk_id UUID REFERENCES document_chunks(id),

            -- Search vectors
            embedding       vector(768),
            search_vector   tsvector GENERATED ALWAYS AS (
                                to_tsvector('english', content)
                            ) STORED,

            created_at      TIMESTAMPTZ DEFAULT NOW(),

            UNIQUE(source_id, chunk_index)
        )
        """,
        "DROP TABLE IF EXISTS document_chunks",
    ),
    step(
        """
        CREATE INDEX idx_chunks_embedding ON document_chunks
            USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
        """,
        "DROP INDEX IF EXISTS idx_chunks_embedding",
    ),
    step(
        """
        CREATE INDEX idx_chunks_search ON document_chunks
            USING gin (search_vector)
        """,
        "DROP INDEX IF EXISTS idx_chunks_search",
    ),
    step(
        """
        CREATE INDEX idx_chunks_source ON document_chunks(source_id)
        """,
        "DROP INDEX IF EXISTS idx_chunks_source",
    ),
    step(
        """
        CREATE INDEX idx_chunks_section ON document_chunks(section_id)
            WHERE section_id IS NOT NULL
        """,
        "DROP INDEX IF EXISTS idx_chunks_section",
    ),
    step(
        """
        CREATE INDEX idx_chunks_tax_year ON document_chunks(tax_year)
            WHERE tax_year IS NOT NULL
        """,
        "DROP INDEX IF EXISTS idx_chunks_tax_year",
    ),
]
