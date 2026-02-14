"""Create document_sources table."""

from yoyo import step

__depends__ = {"0001_extensions"}

steps = [
    step(
        """
        CREATE TABLE document_sources (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            url             TEXT UNIQUE NOT NULL,
            source_type     TEXT NOT NULL CHECK (source_type IN (
                                'ird_guidance', 'legislation', 'tib',
                                'guide_pdf', 'interpretation_statement'
                            )),
            title           TEXT,
            last_crawled_at TIMESTAMPTZ,
            content_hash    TEXT,
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "DROP TABLE IF EXISTS document_sources",
    ),
]
