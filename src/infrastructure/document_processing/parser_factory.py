"""Factory for creating document parsers by file extension."""

from src.domain.interfaces.document_parser import DocumentParser

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def create_parser(file_extension: str) -> DocumentParser:
    """Create the appropriate parser for a given file extension.

    For .pdf, prefers MarkerParser (best quality), falls back to
    PDFParser if marker-pdf is not importable.
    """
    ext = file_extension.lower()

    if ext == ".pdf":
        from src.infrastructure.document_processing.marker_parser import (
            MarkerParser,
            _marker_available,
        )

        if _marker_available:
            return MarkerParser()

        from src.infrastructure.document_processing.pdf_parser import (
            PDFParser,
        )

        return PDFParser()

    elif ext == ".docx":
        from src.infrastructure.document_processing.docx_parser import (
            DOCXParser,
        )

        return DOCXParser()

    elif ext == ".txt":
        from src.infrastructure.document_processing.txt_parser import (
            TXTParser,
        )

        return TXTParser()

    else:
        raise ValueError(
            f"Unsupported file type: {ext}. "
            f"Supported types: {sorted(_SUPPORTED_EXTENSIONS)}"
        )
