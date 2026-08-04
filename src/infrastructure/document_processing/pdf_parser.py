"""PDF parser with PyMuPDF primary and PyPDF2 fallback."""

import logging
from typing import BinaryIO

from src.domain.interfaces.document_parser import DocumentParser

logger = logging.getLogger(__name__)

# Check availability at import time
try:
    import pymupdf  # type: ignore[import-untyped]

    _pymupdf_available = True
except ImportError:
    _pymupdf_available = False

try:
    from PyPDF2 import PdfReader  # type: ignore[import-untyped]

    _pypdf2_available = True
except ImportError:
    _pypdf2_available = False


class PDFParser(DocumentParser):
    """PDF parser using PyMuPDF (primary) with PyPDF2 fallback."""

    def _parse_sync(self, file: BinaryIO) -> str:
        if _pymupdf_available:
            return self._parse_pymupdf(file)
        elif _pypdf2_available:
            return self._parse_pypdf2(file)
        else:
            raise ImportError(
                "No PDF parser available. "
                "Install pymupdf or PyPDF2: "
                "pip install pymupdf PyPDF2"
            )

    def _parse_pymupdf(self, file: BinaryIO) -> str:
        content = file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        text_parts: list[str] = []
        try:
            for page in doc:
                text = page.get_text()
                if text:
                    text_parts.append(text)
        finally:
            doc.close()
        return "\n\n".join(text_parts)

    def _parse_pypdf2(self, file: BinaryIO) -> str:
        reader = PdfReader(file)
        text_parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n\n".join(text_parts)

    async def parse(self, file: BinaryIO) -> str:
        import asyncio

        return await asyncio.to_thread(self._parse_sync, file)

    def get_supported_extensions(self) -> list[str]:
        return [".pdf"]
