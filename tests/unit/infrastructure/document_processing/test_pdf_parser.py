"""PDF parser (PyMuPDF primary, PyPDF2 fallback) and parser factory tests."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.domain.interfaces.document_parser import DocumentParser


class TestPDFParserPyMuPDF:
    """Tests for the PDFParser using PyMuPDF."""

    @patch(
        "src.infrastructure.document_processing.pdf_parser._pymupdf_available",
        True,
    )
    @patch(
        "src.infrastructure.document_processing.pdf_parser.pymupdf",
        create=True,
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
        "src.infrastructure.document_processing.pdf_parser._pymupdf_available",
        False,
    )
    @patch(
        "src.infrastructure.document_processing.pdf_parser._pypdf2_available",
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

    def test_factory_returns_pdf_parser_for_pdf(self):
        """Factory returns PDFParser for .pdf."""
        from src.infrastructure.document_processing.parser_factory import (
            create_parser,
        )
        from src.infrastructure.document_processing.pdf_parser import (
            PDFParser,
        )

        parser = create_parser(".pdf")
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


def test_pdf_parser_is_document_parser():
    """PDFParser implements the DocumentParser interface."""
    from src.infrastructure.document_processing.pdf_parser import (
        PDFParser,
    )

    assert issubclass(PDFParser, DocumentParser)
