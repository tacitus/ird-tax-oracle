"""Tests for the tax-aware chunker."""

from src.db.models import ParsedDocument, ParsedSection
from src.ingestion.chunker import MAX_CHUNK_CHARS, chunk_document


def _make_document(
    title: str = "Test Page",
    sections: list[ParsedSection] | None = None,
) -> ParsedDocument:
    """Helper to create a ParsedDocument for testing."""
    if sections is None:
        sections = [
            ParsedSection(heading="Section A", content="First section content."),
            ParsedSection(heading="Section B", content="Second section content."),
        ]
    return ParsedDocument(title=title, url="https://example.com/test", sections=sections)


class TestChunkDocument:
    """Tests for chunk_document function."""

    def test_metadata_prefix(self) -> None:
        """Chunks include [Page > Section] metadata prefix."""
        doc = _make_document(title="Tax Rates")
        chunks = chunk_document(doc)
        assert chunks[0].content.startswith("[Tax Rates > Section A]")

    def test_h3_prefix_includes_parent(self) -> None:
        """h3 sections include parent h2 in prefix."""
        doc = _make_document(
            title="Tax Rates",
            sections=[
                ParsedSection(
                    heading="Old rates",
                    content="These are old rates.",
                    heading_level=3,
                    parent_heading="Previous rates",
                ),
            ],
        )
        chunks = chunk_document(doc)
        assert "[Tax Rates > Previous rates > Old rates]" in chunks[0].content

    def test_overlap_between_chunks(self) -> None:
        """Second chunk includes overlap from first chunk."""
        doc = _make_document(
            sections=[
                ParsedSection(
                    heading="Section A",
                    content=(
                        "The standard rate is 33%. "
                        "This applies to most income. "
                        "Some exceptions exist for specific categories. "
                        "Check the IRD website for details."
                    ),
                ),
                ParsedSection(
                    heading="Section B",
                    content="For special cases, different rules apply.",
                ),
            ],
        )
        chunks = chunk_document(doc)
        assert len(chunks) == 2
        # Second chunk should contain overlap text from end of first chunk
        assert "Check the IRD website for details." in chunks[1].content

    def test_long_section_splitting(self) -> None:
        """Sections exceeding MAX_CHUNK_CHARS are split at paragraph boundaries."""
        long_content = "\n\n".join(
            [f"Paragraph {i}. " + "x" * 500 for i in range(20)]
        )
        doc = _make_document(
            sections=[ParsedSection(heading="Long section", content=long_content)],
        )
        chunks = chunk_document(doc)
        assert len(chunks) > 1
        for chunk in chunks:
            # Each chunk content (including prefix) should be reasonable
            assert len(chunk.content) < MAX_CHUNK_CHARS + 1000  # allow for prefix/overlap

    def test_tax_year_detection_hyphen(self) -> None:
        """Detects tax year in YYYY-YY format."""
        doc = _make_document(
            sections=[
                ParsedSection(
                    heading="Rates for 2025-26",
                    content="These rates apply for the 2025-26 tax year.",
                ),
            ],
        )
        chunks = chunk_document(doc)
        assert chunks[0].tax_year == "2025-26"

    def test_tax_year_detection_from_april(self) -> None:
        """Detects tax year from 'From 1 April YYYY' pattern."""
        doc = _make_document(
            sections=[
                ParsedSection(
                    heading="New rates",
                    content="From 1 April 2025, the new rates will apply.",
                ),
            ],
        )
        chunks = chunk_document(doc)
        assert chunks[0].tax_year == "2025-26"

    def test_no_tax_year(self) -> None:
        """Returns None when no tax year is detected."""
        doc = _make_document(
            sections=[
                ParsedSection(heading="General info", content="Tax is collected by IRD."),
            ],
        )
        chunks = chunk_document(doc)
        assert chunks[0].tax_year is None

    def test_empty_section_skipped(self) -> None:
        """Empty sections produce no chunks."""
        doc = _make_document(
            sections=[
                ParsedSection(heading="Empty", content=""),
                ParsedSection(heading="Has content", content="Real content here."),
            ],
        )
        chunks = chunk_document(doc)
        assert len(chunks) == 1
        assert chunks[0].section_title == "Has content"

    def test_chunk_indexes_sequential(self) -> None:
        """Chunk indexes are 0-based and sequential."""
        doc = _make_document(
            sections=[
                ParsedSection(heading=f"Section {i}", content=f"Content for section {i}.")
                for i in range(5)
            ],
        )
        chunks = chunk_document(doc)
        assert [c.chunk_index for c in chunks] == list(range(5))

    def test_section_title_preserved(self) -> None:
        """Section title is preserved in chunk metadata."""
        doc = _make_document(
            sections=[
                ParsedSection(heading="IETC", content="The credit is $520."),
            ],
        )
        chunks = chunk_document(doc)
        assert chunks[0].section_title == "IETC"
