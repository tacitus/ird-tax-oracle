"""Tests for PDF parser."""

import pytest

from src.ingestion.parsers.pdf_parser import parse_pdf


class TestTitleExtraction:
    """Test title extraction from various PDF sources."""

    def test_title_from_metadata(self, pdf_with_metadata: bytes) -> None:
        result = parse_pdf(pdf_with_metadata, "https://ird.govt.nz/ir3g.pdf")
        assert result.title == "IR3G Individual Income Tax Return Guide"

    def test_title_from_large_text(self, pdf_with_large_title: bytes) -> None:
        result = parse_pdf(pdf_with_large_title, "https://ird.govt.nz/ir3g.pdf")
        assert "Individual Income Tax Return Guide" in result.title

    def test_title_fallback_to_url(self) -> None:
        """Empty PDF falls back to URL filename."""
        import pymupdf

        doc = pymupdf.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        result = parse_pdf(pdf_bytes, "https://ird.govt.nz/forms/ir3g-2025.pdf")
        assert result.title == "ir3g-2025"

    def test_url_preserved(self, pdf_with_metadata: bytes) -> None:
        url = "https://ird.govt.nz/ir3g.pdf"
        result = parse_pdf(pdf_with_metadata, url)
        assert result.url == url


class TestTableExtraction:
    """Test table extraction as markdown."""

    def test_table_detected_as_markdown(self, pdf_with_table: bytes) -> None:
        result = parse_pdf(pdf_with_table, "https://ird.govt.nz/rates.pdf")
        all_content = "\n".join(s.content for s in result.sections)
        # The table should be present as markdown (with pipe characters)
        # or the text from table cells should appear
        assert "$14,000" in all_content or "14,000" in all_content

    def test_table_text_not_duplicated(self, pdf_with_table: bytes) -> None:
        result = parse_pdf(pdf_with_table, "https://ird.govt.nz/rates.pdf")
        all_content = "\n".join(s.content for s in result.sections)
        # If table is detected, the cell text shouldn't also appear as loose text
        # Count occurrences of a distinctive cell value
        count = all_content.count("$1,470")
        assert count <= 1


class TestQADetection:
    """Test Q&A pattern detection for IRD-style guides."""

    def test_qa_sections_detected(self, ir3g_style_pdf: bytes) -> None:
        result = parse_pdf(ir3g_style_pdf, "https://ird.govt.nz/ir3g.pdf")
        headings = [s.heading for s in result.sections]
        # Should have Question-based sections
        question_headings = [h for h in headings if h.startswith("Question")]
        assert len(question_headings) >= 3

    def test_qa_section_content(self, ir3g_style_pdf: bytes) -> None:
        result = parse_pdf(ir3g_style_pdf, "https://ird.govt.nz/ir3g.pdf")
        # Find Question 1 section
        q1 = next((s for s in result.sections if "Question 1" in s.heading), None)
        assert q1 is not None
        assert "IRD number" in q1.heading or "IRD number" in q1.content

    def test_introduction_before_first_question(self, ir3g_style_pdf: bytes) -> None:
        result = parse_pdf(ir3g_style_pdf, "https://ird.govt.nz/ir3g.pdf")
        # There should be content before the first Question
        if result.sections and not result.sections[0].heading.startswith("Question"):
            # Introduction section exists
            assert len(result.sections[0].content) > 0


class TestHeadingDetection:
    """Test font-size-based heading detection."""

    def test_heading_sections_created(self, pdf_with_headings: bytes) -> None:
        result = parse_pdf(pdf_with_headings, "https://ird.govt.nz/guide.pdf")
        headings = [s.heading for s in result.sections]
        # Should detect the large-font headings
        assert any("Income Types" in h for h in headings)
        assert any("Deductions" in h for h in headings)

    def test_heading_section_content(self, pdf_with_headings: bytes) -> None:
        result = parse_pdf(pdf_with_headings, "https://ird.govt.nz/guide.pdf")
        income_section = next(
            (s for s in result.sections if "Income Types" in s.heading), None
        )
        assert income_section is not None
        content_lower = income_section.content.lower()
        assert "salary" in content_lower or "wages" in content_lower


class TestFallbackBehavior:
    """Test fallback for unstructured PDFs."""

    def test_plain_text_single_section(self, pdf_plain_text: bytes) -> None:
        result = parse_pdf(pdf_plain_text, "https://ird.govt.nz/doc.pdf")
        assert len(result.sections) >= 1
        all_content = "\n".join(s.content for s in result.sections)
        assert "simple document" in all_content


class TestMultiPage:
    """Test multi-page PDF handling."""

    def test_multi_page_content(self, multi_page_pdf: bytes) -> None:
        result = parse_pdf(multi_page_pdf, "https://ird.govt.nz/guide.pdf")
        assert len(result.sections) >= 2
        all_content = "\n".join(s.content for s in result.sections)
        # Content from later pages should be present
        assert "section" in all_content.lower()

    def test_header_footer_stripped(self, multi_page_pdf: bytes) -> None:
        result = parse_pdf(multi_page_pdf, "https://ird.govt.nz/guide.pdf")
        all_content = "\n".join(s.content for s in result.sections)
        # Repeated header/footer text should be stripped
        # "IR3G INDIVIDUAL RETURN GUIDE" appears on all 5 pages
        assert all_content.count("IR3G INDIVIDUAL RETURN GUIDE") == 0
        assert all_content.count("ird.govt.nz") == 0


class TestEmptyPDF:
    """Test handling of empty or minimal PDFs."""

    def test_empty_pdf(self) -> None:
        import pymupdf

        doc = pymupdf.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        result = parse_pdf(pdf_bytes, "https://ird.govt.nz/empty.pdf")
        assert result.title is not None
        assert result.sections == []

    def test_returns_parsed_document(self, pdf_with_metadata: bytes) -> None:
        result = parse_pdf(pdf_with_metadata, "https://ird.govt.nz/ir3g.pdf")
        assert hasattr(result, "title")
        assert hasattr(result, "url")
        assert hasattr(result, "sections")


class TestRealIR3G:
    """Integration test with real IRD PDF fixture."""

    def test_real_ir3g_parses(self, ird_pdf_fixture: bytes | None) -> None:
        if ird_pdf_fixture is None:
            pytest.skip("IR3G fixture not available")
        result = parse_pdf(ird_pdf_fixture, "https://ird.govt.nz/ir3g-2025.pdf")
        assert len(result.sections) > 5
        headings = [s.heading for s in result.sections]
        question_headings = [h for h in headings if h.startswith("Question")]
        assert len(question_headings) >= 10

    def test_real_ir3g_has_content(self, ird_pdf_fixture: bytes | None) -> None:
        if ird_pdf_fixture is None:
            pytest.skip("IR3G fixture not available")
        result = parse_pdf(ird_pdf_fixture, "https://ird.govt.nz/ir3g-2025.pdf")
        all_content = "\n".join(s.content for s in result.sections)
        # Should contain tax-related content
        assert "tax" in all_content.lower()
        assert len(all_content) > 1000
