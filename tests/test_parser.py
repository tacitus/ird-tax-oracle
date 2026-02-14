"""Tests for the HTML parser."""

from src.ingestion.parsers.html_parser import parse_html


class TestParseHtml:
    """Tests for parse_html function."""

    def test_extracts_bilingual_title(self, ird_guidance_html: str) -> None:
        """Parser extracts English part of bilingual h1 title."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        assert doc.title == "Tax rates for individuals"

    def test_strips_navigation(self, ird_guidance_html: str) -> None:
        """Parser removes nav, breadcrumb, skip-link, and footer elements."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        all_content = " ".join(s.content for s in doc.sections)
        assert "Skip to main content" not in all_content
        assert "Contact us" not in all_content

    def test_splits_on_h2_boundaries(self, ird_guidance_html: str) -> None:
        """Parser creates sections at h2 boundaries."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        headings = [s.heading for s in doc.sections if s.heading_level == 2]
        assert "Income tax rates from 1 April 2025" in headings
        assert "Independent earner tax credit (IETC)" in headings
        # "Previous tax rates" h2 has no direct content — only h3 subsections
        # so it correctly doesn't appear as a standalone section
        all_headings = [s.heading for s in doc.sections]
        assert "Rates for 2024-25 tax year" in all_headings

    def test_splits_on_h3_boundaries(self, ird_guidance_html: str) -> None:
        """Parser creates sub-sections at h3 boundaries."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        h3_sections = [s for s in doc.sections if s.heading_level == 3]
        assert len(h3_sections) >= 2
        assert any("2024-25" in s.heading for s in h3_sections)

    def test_h3_has_parent_heading(self, ird_guidance_html: str) -> None:
        """h3 sections record their parent h2 heading."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        h3_sections = [s for s in doc.sections if s.heading_level == 3]
        for section in h3_sections:
            assert section.parent_heading == "Previous tax rates"

    def test_preserves_url(self, ird_guidance_html: str) -> None:
        """Parser preserves the source URL."""
        url = "https://example.com/tax-rates"
        doc = parse_html(ird_guidance_html, url)
        assert doc.url == url

    def test_clean_text_output(self, ird_guidance_html: str) -> None:
        """Parser produces clean text without excessive whitespace."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        for section in doc.sections:
            assert "  " not in section.content  # no double spaces
            assert section.content == section.content.strip()

    def test_handles_heading_in_div(self, ird_guidance_html: str) -> None:
        """Parser handles h2 headings wrapped in div elements."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        headings = [s.heading for s in doc.sections]
        assert "How to check your tax rate" in headings

    def test_introduction_content(self, ird_guidance_html: str) -> None:
        """Content before first h2 goes into Introduction section."""
        doc = parse_html(ird_guidance_html, "https://example.com/tax-rates")
        intro = [s for s in doc.sections if s.heading == "Introduction"]
        assert len(intro) == 1
        assert "progressive tax rates" in intro[0].content

    def test_empty_html(self) -> None:
        """Parser handles minimal HTML without crashing."""
        doc = parse_html("<html><body></body></html>", "https://example.com")
        assert doc.title == "Untitled"
        assert len(doc.sections) == 0

    def test_no_content_wrapper(self) -> None:
        """Parser falls back to body when no content wrapper exists."""
        html = """
        <html>
        <head><title>Simple page - IRD</title></head>
        <body>
            <h2>Section one</h2>
            <p>Some content here.</p>
        </body>
        </html>
        """
        doc = parse_html(html, "https://example.com")
        assert doc.title == "Simple page"
        assert len(doc.sections) >= 1

    def test_title_fallback_to_title_tag(self) -> None:
        """Parser uses <title> when no h1 exists."""
        html = """
        <html>
        <head><title>RWT rates - Inland Revenue</title></head>
        <body><div id="main-content-wrapper">
            <h2>Current rates</h2>
            <p>The default RWT rate is 33%.</p>
        </div></body>
        </html>
        """
        doc = parse_html(html, "https://example.com")
        assert doc.title == "RWT rates"
