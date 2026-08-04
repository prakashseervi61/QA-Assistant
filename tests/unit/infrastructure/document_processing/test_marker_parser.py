"""Tests for the Marker PDF parser and PyMuPDF fallback."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.domain.interfaces.document_parser import DocumentParser


class TestMarkerParser:
    """Tests for the MarkerParser implementation."""

    def test_marker_parser_is_document_parser(self):
        """MarkerParser must be a DocumentParser subclass."""
        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
        )

        assert issubclass(MarkerParser, DocumentParser)

    def test_marker_parser_supported_extensions(self):
        """MarkerParser supports .pdf."""
        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
        )

        p = MarkerParser()
        assert ".pdf" in p.get_supported_extensions()

    @patch(
        "src.infrastructure.document_processing.marker_parser"
        "._marker_available",
        True,
    )
    @patch(
        "src.infrastructure.document_processing.marker_parser"
        ".create_model_dict",
        return_value={},
    )
    @patch(
        "src.infrastructure.document_processing.marker_parser"
        ".ConfigParser",
    )
    @patch(
        "src.infrastructure.document_processing.marker_parser"
        ".convert_single_pdf",
    )
    def test_marker_parser_extracts_text(
        self, mock_convert, mock_config, mock_models
    ):
        """MarkerParser returns extracted text from marker."""
        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
        )

        mock_convert.return_value = MagicMock(
            markdown=(
                "# Title\n\nSome content\n\n"
                "| Col1 | Col2 |\n|---|---|\n| a | b |"
            )
        )

        p = MarkerParser()
        result = p._parse_sync(BytesIO(b"fake pdf"))

        assert "# Title" in result
        assert "Some content" in result

    @patch(
        "src.infrastructure.document_processing.marker_parser"
        "._marker_available",
        True,
    )
    @patch(
        "src.infrastructure.document_processing.marker_parser"
        ".create_model_dict",
        return_value={},
    )
    @patch(
        "src.infrastructure.document_processing.marker_parser"
        ".ConfigParser",
    )
    @patch(
        "src.infrastructure.document_processing.marker_parser"
        ".convert_single_pdf",
    )
    def test_marker_parser_handles_tables_as_markdown(
        self, mock_convert, mock_config, mock_models
    ):
        """MarkerParser preserves table structure as markdown."""
        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
        )

        mock_convert.return_value = MagicMock(
            markdown="| Name | Score |\n|---|---|\n| Alice | 95 |"
        )

        p = MarkerParser()
        result = p._parse_sync(BytesIO(b"fake pdf"))

        assert "| Name | Score |" in result
        assert "| Alice | 95 |" in result

    @patch(
        "src.infrastructure.document_processing.marker_parser"
        "._marker_available",
        False,
    )
    def test_marker_parser_raises_when_marker_not_installed(self):
        """MarkerParser raises ImportError when marker-pdf is missing."""
        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
        )

        p = MarkerParser()
        with pytest.raises(ImportError, match="marker-pdf"):
            p._parse_sync(BytesIO(b"fake pdf"))


class TestPDFParserPyMuPDF:
    """Tests for the updated PDFParser using PyMuPDF."""

    @patch(
        "src.infrastructure.document_processing.pdf_parser"
        "._pymupdf_available",
        True,
    )
    @patch(
        "src.infrastructure.document_processing.pdf_parser.pymupdf",
    )
    def test_pymupdf_extracts_text(self, mock_pymupdf):
        """PDFParser uses PyMuPDF when available."""
        from src.infrastructure.document_processing.pdf_parser import (
            PDFParser,
        )

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Extracted text from page"

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        mock_pymupdf.open.return_value = mock_doc

        p = PDFParser()
        result = p._parse_sync(BytesIO(b"fake pdf"))

        assert "Extracted text from page" in result

    @patch(
        "src.infrastructure.document_processing.pdf_parser"
        "._pymupdf_available",
        False,
    )
    @patch(
        "src.infrastructure.document_processing.pdf_parser"
        "._pypdf2_available",
        False,
    )
    def test_no_pdf_library_raises(self):
        """PDFParser raises when no PDF library is available."""
        from src.infrastructure.document_processing.pdf_parser import (
            PDFParser,
        )

        p = PDFParser()
        with pytest.raises(ImportError, match="No PDF parser"):
            p._parse_sync(BytesIO(b"fake pdf"))


class TestParserFactory:
    """Tests for the parser factory selection logic."""

    def test_factory_returns_marker_parser_for_pdf_when_available(self):
        """Factory returns MarkerParser when marker-pdf is installed."""
        from unittest.mock import patch

        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
        )
        from src.infrastructure.document_processing.parser_factory import (
            create_parser,
        )

        with patch(
            "src.infrastructure.document_processing.marker_parser._marker_available",
            True,
        ), patch(
            "src.infrastructure.document_processing.marker_parser.MarkerParser",
            MarkerParser,
        ):
            parser = create_parser(".pdf")
            assert isinstance(parser, MarkerParser)

    def test_factory_falls_back_to_pdfparser_when_marker_unavailable(self):
        """Factory returns PDFParser when marker-pdf is not installed."""
        from src.infrastructure.document_processing.parser_factory import (
            create_parser,
        )
        from src.infrastructure.document_processing.pdf_parser import (
            PDFParser,
        )

        parser = create_parser(".pdf")
        # marker-pdf is not installed in test env, so fallback to PDFParser
        assert isinstance(parser, PDFParser)

    def test_factory_returns_docx_parser(self):
        """Factory returns DOCXParser for .docx."""
        from src.infrastructure.document_processing.docx_parser import (
            DOCXParser,
        )
        from src.infrastructure.document_processing.parser_factory import (
            create_parser,
        )

        parser = create_parser(".docx")
        assert isinstance(parser, DOCXParser)

    def test_factory_returns_txt_parser(self):
        """Factory returns TXTParser for .txt."""
        from src.infrastructure.document_processing.parser_factory import (
            create_parser,
        )
        from src.infrastructure.document_processing.txt_parser import (
            TXTParser,
        )

        parser = create_parser(".txt")
        assert isinstance(parser, TXTParser)

    def test_factory_raises_for_unsupported(self):
        """Factory raises ValueError for unsupported extensions."""
        from src.infrastructure.document_processing.parser_factory import (
            create_parser,
        )

        with pytest.raises(ValueError, match="Unsupported"):
            create_parser(".xyz")
