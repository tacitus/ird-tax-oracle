"""Add taxtechnical source types and metadata columns."""

from yoyo import step

__depends__ = {"0003_document_chunks"}

steps = [
    # Expand source_type CHECK constraint to include new types
    step(
        """
        ALTER TABLE document_sources
        DROP CONSTRAINT IF EXISTS document_sources_source_type_check
        """,
        """
        ALTER TABLE document_sources
        ADD CONSTRAINT document_sources_source_type_check
        CHECK (source_type IN (
            'ird_guidance', 'legislation', 'tib',
            'guide_pdf', 'interpretation_statement'
        ))
        """,
    ),
    step(
        """
        ALTER TABLE document_sources
        ADD CONSTRAINT document_sources_source_type_check
        CHECK (source_type IN (
            'ird_guidance', 'legislation', 'tib',
            'guide_pdf', 'interpretation_statement',
            'qwba', 'fact_sheet', 'operational_statement'
        ))
        """,
        """
        ALTER TABLE document_sources
        DROP CONSTRAINT IF EXISTS document_sources_source_type_check
        """,
    ),
    # Add metadata columns
    step(
        "ALTER TABLE document_sources ADD COLUMN identifier TEXT",
        "ALTER TABLE document_sources DROP COLUMN IF EXISTS identifier",
    ),
    step(
        "ALTER TABLE document_sources ADD COLUMN issue_date DATE",
        "ALTER TABLE document_sources DROP COLUMN IF EXISTS issue_date",
    ),
    step(
        "ALTER TABLE document_sources ADD COLUMN superseded_by TEXT",
        "ALTER TABLE document_sources DROP COLUMN IF EXISTS superseded_by",
    ),
    # Index on identifier for lookups
    step(
        "CREATE INDEX idx_document_sources_identifier ON document_sources (identifier) WHERE identifier IS NOT NULL",
        "DROP INDEX IF EXISTS idx_document_sources_identifier",
    ),
]
