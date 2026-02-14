"""Tests for taxtechnical.ird.govt.nz HTML parser."""

from src.ingestion.parsers.taxtechnical_parser import parse_taxtechnical

BASE_URL = "https://www.taxtechnical.ird.govt.nz/revenue-alerts/ra-0701"


class TestFullContentPage:
    """Tests for full inline content pages (revenue alerts, operational statements)."""

    def test_title_extraction(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        assert result.title == "Revenue Alert - RA 07/01"

    def test_metadata_section(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        metadata = result.sections[0]
        assert metadata.heading == "Metadata"
        assert "Reference: RA 07/01" in metadata.content
        assert "Issued: 15 March 2007" in metadata.content

    def test_h2_sections(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        # Skip metadata section — get content section headings
        content_headings = [
            s.heading for s in result.sections if s.heading != "Metadata"
        ]
        assert "Background" in content_headings
        assert "Application" in content_headings
        assert "Summary" in content_headings
        # "Detailed Analysis" h2 has no direct text (only h3 children),
        # so it won't appear as its own section — the h3s carry the content
        assert "Travel Allowances" in content_headings
        assert "Meal Allowances" in content_headings

    def test_h3_parent_heading(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        travel = next(s for s in result.sections if s.heading == "Travel Allowances")
        assert travel.heading_level == 3
        assert travel.parent_heading == "Detailed Analysis"

    def test_no_pdf_url(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        assert result.pdf_url is None

    def test_content_has_text(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        bg = next(s for s in result.sections if s.heading == "Background")
        assert "employee allowances" in bg.content

    def test_strips_nav_and_footer(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        all_text = " ".join(s.content for s in result.sections)
        assert "Copyright" not in all_text
        assert "breadcrumb" not in all_text.lower()

    def test_list_items_in_content(self, taxtechnical_full_content_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_full_content_html, BASE_URL)
        app = next(s for s in result.sections if s.heading == "Application")
        assert "Travel allowances" in app.content


class TestPdfStubPage:
    """Tests for PDF stub pages (interpretation statements, etc.)."""

    def test_title_extraction(self, taxtechnical_pdf_stub_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_pdf_stub_html, BASE_URL)
        assert result.title == "IS 24/10 - Income tax - Share investments"

    def test_pdf_url_detected(self, taxtechnical_pdf_stub_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_pdf_stub_html, BASE_URL)
        assert result.pdf_url is not None
        assert result.pdf_url.endswith(".pdf")
        assert "is-24-10.pdf" in result.pdf_url

    def test_pdf_url_resolved(self, taxtechnical_pdf_stub_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_pdf_stub_html, BASE_URL)
        assert result.pdf_url is not None
        assert result.pdf_url.startswith("https://")

    def test_metadata_section(self, taxtechnical_pdf_stub_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_pdf_stub_html, BASE_URL)
        metadata = result.sections[0]
        assert metadata.heading == "Metadata"
        assert "Reference: IS 24/10" in metadata.content
        assert "Issued: 01 December 2024" in metadata.content

    def test_description_section(self, taxtechnical_pdf_stub_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_pdf_stub_html, BASE_URL)
        desc = next(
            (s for s in result.sections if s.heading == "Description"), None
        )
        assert desc is not None
        assert "share investments" in desc.content.lower()

    def test_minimal_sections(self, taxtechnical_pdf_stub_html: str) -> None:
        result = parse_taxtechnical(taxtechnical_pdf_stub_html, BASE_URL)
        # Stub pages should have metadata + description, not full h2 sections
        assert len(result.sections) <= 3


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_page(self) -> None:
        result = parse_taxtechnical("<html><body></body></html>", BASE_URL)
        assert result.title == "Untitled"
        assert result.sections == []

    def test_no_content_wrapper_fallback(self) -> None:
        html = """
        <html><body>
            <h1>Some Title</h1>
            <h2>Section One</h2>
            <p>Some content here.</p>
        </body></html>
        """
        result = parse_taxtechnical(html, BASE_URL)
        assert result.title == "Some Title"
        assert len(result.sections) >= 1

    def test_no_metadata(self) -> None:
        html = """
        <html><body>
            <div id="main-content-tt">
                <h1>Plain Page</h1>
                <h2>Only Section</h2>
                <p>Content without any reference or date metadata.</p>
            </div>
        </body></html>
        """
        result = parse_taxtechnical(html, BASE_URL)
        assert not any(s.heading == "Metadata" for s in result.sections)

    def test_no_headings(self) -> None:
        html = """
        <html><body>
            <div id="main-content-tt">
                <h1>Title Only</h1>
                <p>Just a paragraph with no section headings at all.</p>
                <p>Another paragraph of content.</p>
            </div>
        </body></html>
        """
        result = parse_taxtechnical(html, BASE_URL)
        assert result.title == "Title Only"
        assert len(result.sections) >= 1

    def test_title_fallback_to_title_tag(self) -> None:
        html = """
        <html>
        <head><title>Fallback Title - Tax Technical</title></head>
        <body>
            <div id="main-content-tt">
                <p>No h1 here.</p>
            </div>
        </body></html>
        """
        result = parse_taxtechnical(html, BASE_URL)
        assert result.title == "Fallback Title"

    def test_relative_pdf_url_resolved(self) -> None:
        html = """
        <html><body>
            <div id="main-content-tt">
                <h1>Test</h1>
                <p><a href="/media/doc.pdf">Download PDF</a></p>
            </div>
        </body></html>
        """
        result = parse_taxtechnical(html, BASE_URL)
        assert result.pdf_url is not None
        assert result.pdf_url.startswith("https://")
        assert "/media/doc.pdf" in result.pdf_url
